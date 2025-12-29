import asyncio
import time
import urllib.parse
import logging
import httpx
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass

from headers import get_random_headers

# Constants
CACHE_TTL = 30  # seconds
HARD_TIMEOUT = 15.0 # seconds

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
    - Caches results for short duration (30s).
    - Applies stealth headers.
    """
    
    def __init__(self):
        # normalize_url -> Future[FetchResult]
        self._active_requests: Dict[str, asyncio.Future] = {}
        
        # normalized_url -> (FetchResult, timestamp)
        self._cache: Dict[str, Tuple[FetchResult, float]] = {}
        
        # Shared client (optional, but good for connection pooling)
        # We will instantiate a new client per request or share?
        # Sharing a client is better for keep-alive, but tricky with rotating headers per request?
        # Actually, httpx.AsyncClient can take headers per request.
        # But we want to rotate mostly per sit/session.
        # For simplicity and robustness against tracking, creating a fresh client or using 
        # a shared one with minimal cookie persistence is key.
        # "Stealth" usually implies not carrying over cookies between different sites, 
        # but MAYBE within same site? 
        # Requirement: "One fetch shared".
        # Let's use a single shared client but clear cookies? Or just new client per fetch for maximum isolation?
        # Tests show "FetchResult".
        # Let's use a shared client for performance but override headers.
        self._client = httpx.AsyncClient(verify=False, follow_redirects=True, timeout=HARD_TIMEOUT)

    async def close(self):
        await self._client.aclose()

    def normalize_url(self, url: str) -> str:
        """
        Strips tracking parameters to ensure clean de-duplication keys.
        """
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        
        # Filter out tracking params
        tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid'}
        clean_query = {k: v for k, v in query.items() if k not in tracking_params}
        
        # Sort for consistency
        sorted_query = urllib.parse.urlencode(clean_query, doseq=True)
        
        # Reconstruct
        clean_url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            sorted_query,
            parsed.fragment
        ))
        
        # Normalize trailing slash? Usually standardizing on 'no slash' or 'slash' depends, 
        # but let's just stick to what `files` usually do. 
        # Let's lower-case the scheme and netloc at least.
        return clean_url.lower() # basic normalization

    async def fetch(self, url: str) -> FetchResult:
        """
        Fetch a URL with de-duplication and caching.
        """
        normalized_url = self.normalize_url(url)
        now = time.time()
        
        # 1. Check Cache
        if normalized_url in self._cache:
            result, ts = self._cache[normalized_url]
            if now - ts < CACHE_TTL:
                logger.debug(f"[Cache Hit] {normalized_url}")
                return result
            else:
                del self._cache[normalized_url] # Expired
        
        # 2. Check Active Requests
        if normalized_url in self._active_requests:
            logger.debug(f"[Collapsing Request] Waiting for active fetch: {normalized_url}")
            return await self._active_requests[normalized_url]
            
        # 3. New Request
        future = asyncio.get_running_loop().create_future()
        self._active_requests[normalized_url] = future
        
        # Launch the actual worker task
        # We assume ownership of fulfilling the future
        try:
            # Wrap in wait_for for Hard Timeout
            # Note: httpx has its own timeout, but asyncio.wait_for is the "Hard" guarantee 
            # that cancels the task even if libs act up.
            result = await asyncio.wait_for(
                self._execute_http_request(url, normalized_url), 
                timeout=HARD_TIMEOUT
            )
            
            # Update Cache
            self._cache[normalized_url] = (result, time.time())
            
            # Fulfill Future
            if not future.done():
                future.set_result(result)
            
            return result
            
        except asyncio.TimeoutError:
            err_msg = f"Hard Timeout ({HARD_TIMEOUT}s) exceeded for {url}"
            logger.error(err_msg)
            result = FetchResult(url, None, 0, error=err_msg, timestamp=time.time())
            
            if not future.done():
                future.set_result(result) 
            return result
            
        except Exception as e:
            err_msg = f"Fetch failed: {e}"
            logger.error(err_msg)
            result = FetchResult(url, None, 0, error=err_msg, timestamp=time.time())
            if not future.done():
                future.set_result(result)
            return result
            
        finally:
            # Cleanup active request map
            if normalized_url in self._active_requests:
                del self._active_requests[normalized_url]

    async def _execute_http_request(self, original_url: str, normalized_key: str) -> FetchResult:
        """
        Performs the physical network call with stealth headers.
        """
        headers = get_random_headers()
        try:
            # We use the original URL for the actual fetch, but key by normalized
            logger.info(f"[Network Call] Fetching {original_url}...")
            resp = await self._client.get(original_url, headers=headers)
            
            # For this task, we return text. 
            # In real professional bot, we might handle encoding carefully.
            return FetchResult(
                url=original_url,
                content=resp.text,
                status_code=resp.status_code,
                timestamp=time.time()
            )
        except httpx.RequestError as e:
            return FetchResult(original_url, None, 0, error=str(e), timestamp=time.time())
