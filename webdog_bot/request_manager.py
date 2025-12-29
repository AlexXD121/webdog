import asyncio
import time
import urllib.parse
import logging
import httpx
import random
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from urllib.robotparser import RobotFileParser

from headers import get_random_headers
from circuit_breaker import CircuitBreaker

# Constants
CACHE_TTL = 30  # seconds
HARD_TIMEOUT = 15.0 # seconds
MIN_JITTER = 1.0 # seconds
MAX_JITTER = 5.0 # seconds

logger = logging.getLogger("GlobalRequestManager")

@dataclass
class FetchResult:
    url: str
    content: Optional[str]
    status_code: int
    error: Optional[str] = None
    timestamp: float = 0.0

class FetchTimeoutError(Exception):
    """Raised when a fetch operation exceeds the hard timeout."""
    pass

class GlobalRequestManager:
    """
    Central gateway for all HTTP requests.
    - De-duplicates simultaneous requests to the same URL.
    - Enforces hard timeouts.
    - Caches results.
    - Applies stealth headers (Synchronized).
    - Protects via Circuit Breaker.
    - Respects Robots.txt.
    - Applies Jitter.
    """
    
    def __init__(self):
        # normalize_url -> Future[FetchResult]
        self._active_requests: Dict[str, asyncio.Future] = {}
        
        # normalized_url -> (FetchResult, timestamp)
        self._cache: Dict[str, Tuple[FetchResult, float]] = {}
        
        # normalized_url -> CircuitBreaker
        self._circuits: Dict[str, CircuitBreaker] = {}
        
        # normalized_domain -> RobotFileParser
        self._robots_cache: Dict[str, RobotFileParser] = {}
        
        self._client = httpx.AsyncClient(verify=False, follow_redirects=True, timeout=HARD_TIMEOUT)

    async def close(self):
        await self._client.aclose()
        
    def _get_circuit(self, key: str) -> CircuitBreaker:
        if key not in self._circuits:
            self._circuits[key] = CircuitBreaker(failure_threshold=3, recovery_timeout=3600)
        return self._circuits[key]

    def normalize_url(self, url: str) -> str:
        """
        Strips tracking parameters to ensure clean de-duplication keys.
        """
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        
        tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid'}
        clean_query = {k: v for k, v in query.items() if k not in tracking_params}
        sorted_query = urllib.parse.urlencode(clean_query, doseq=True)
        
        clean_url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            sorted_query,
            parsed.fragment
        ))
        
        return clean_url.lower()

    async def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        """
        Checks Robots.txt rules.
        """
        parsed = urllib.parse.urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{base_url}/robots.txt"
        
        if base_url not in self._robots_cache:
            parser = RobotFileParser()
            try:
                # We fetch robots.txt with a short timeout
                resp = await self._client.get(robots_url, timeout=5.0)
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                else:
                    parser.allow_all = True
            except Exception:
                # If robots.txt fails, usually assume allow or allow_all
                parser.allow_all = True
                
            self._robots_cache[base_url] = parser
            
        return self._robots_cache[base_url].can_fetch(user_agent, url)

from metrics import get_metrics_tracker

# ... (Imports remain, we add metrics import above or let Python handle it if I put it in Imports block. I'll add the import line.)

    async def fetch(self, url: str) -> FetchResult:
        """
        Fetch a URL with de-duplication, caching, circuit protection, robots compliance, and jitter.
        """
        normalized_url = self.normalize_url(url)
        now = time.time()
        
        # 0. Jitter
        delay = random.uniform(MIN_JITTER, MAX_JITTER)
        logger.debug(f"Applying jitter {delay:.2f}s for {url}")
        await asyncio.sleep(delay)
        
        # 1. Circuit Breaker Check
        cb = self._get_circuit(normalized_url)
        if not cb.is_allowable():
            err_msg = f"Circuit Open: Getting failures from {normalized_url}. Cooldown active."
            logger.warning(err_msg)
            # Record fast-fail as failure? Or ignore? Usually ignore for latency stats, 
            # but maybe count for success rate? Let's count as fail for now to reflect unavailability.
            get_metrics_tracker().record_request(0, False)
            return FetchResult(url, None, 0, error=err_msg, timestamp=now)
        
        # 2. Check Cache
        if normalized_url in self._cache:
            result, ts = self._cache[normalized_url]
            if now - ts < CACHE_TTL:
                logger.debug(f"[Cache Hit] {normalized_url}")
                # Cache hit is "instant" success
                get_metrics_tracker().record_request(0, True)
                return result
            else:
                del self._cache[normalized_url] # Expired
        
        # 3. Check Active Requests
        if normalized_url in self._active_requests:
            logger.debug(f"[Collapsing Request] Waiting for active fetch: {normalized_url}")
            # Collapsed request waits for real one. Timer starts now for *this* caller?
            # Or share result?
            # Let's not double count collapsed requests for network metrics, 
            # but for "Service Level" metrics we might. 
            # For simplicity, we only measure *actual* fetches initiated by this manager.
            return await self._active_requests[normalized_url]
            
        # 4. New Request
        future = asyncio.get_running_loop().create_future()
        self._active_requests[normalized_url] = future
        
        # Start Timer for Network Call
        start_time = time.time()
        success = False
        
        try:
            # 5. Robots.txt Compliance
            if not await self.can_fetch(url, "*"):
                 raise Exception("Blocked by Robots.txt directive")

            # Hard Timeout Wrapper
            result = await asyncio.wait_for(
                self._execute_http_request(url, normalized_url, cb), 
                timeout=HARD_TIMEOUT
            )
            
            self._cache[normalized_url] = (result, time.time())
            
            if not future.done():
                future.set_result(result)
            
            # Check result for HTTP success (2xx/3xx presumably from execute)
            # execute handles 429/500 as errors, but returns FetchResult with status.
            # Let's assume if result.error is None it is success.
            success = result.error is None
            
            return result
            
        except asyncio.TimeoutError:
            err_msg = f"Hard Timeout ({HARD_TIMEOUT}s) exceeded for {url}"
            logger.error(err_msg)
            cb.record_failure()
            result = FetchResult(url, None, 0, error=err_msg, timestamp=time.time())
            if not future.done(): future.set_result(result) 
            success = False
            return result
            
        except Exception as e:
            err_msg = f"Fetch failed: {e}"
            logger.error(err_msg)
            cb.record_failure()
            result = FetchResult(url, None, 0, error=err_msg, timestamp=time.time())
            if not future.done(): future.set_result(result)
            success = False
            return result
            
        finally:
            # Stop Timer & Record
            duration = time.time() - start_time
            get_metrics_tracker().record_request(duration, success)
            
            if normalized_url in self._active_requests:
                del self._active_requests[normalized_url]

    async def _execute_http_request(self, original_url: str, normalized_key: str, cb: CircuitBreaker) -> FetchResult:
        """
        Performs network call and updates Circuit Breaker state.
        """
        headers = get_random_headers()
        try:
            logger.info(f"[Network Call] Fetching {original_url}...")
            resp = await self._client.get(original_url, headers=headers)
            
            # Circuit Logic
            if resp.status_code >= 500 or resp.status_code == 429:
                cb.record_failure()
            else:
                cb.record_success()

            return FetchResult(
                url=original_url,
                content=resp.text,
                status_code=resp.status_code,
                timestamp=time.time()
            )
        except httpx.RequestError as e:
            cb.record_failure()
            return FetchResult(original_url, None, 0, error=str(e), timestamp=time.time())
