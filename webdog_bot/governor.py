import asyncio
import time
import logging
from typing import Optional

logger = logging.getLogger("RateGovernor")

class RateLimiter:
    """
    Token Bucket Rate Limiter.
    Ensures actions do not exceed `rate` per second.
    """
    def __init__(self, rate: float, capacity: int = 1):
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()
        
    async def acquire(self):
        """
        Waits until a token is available.
        """
        async with self.lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now
                
                # Refill
                new_tokens = elapsed * self.rate
                self.tokens = min(self.capacity, self.tokens + new_tokens)
                
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                else:
                    # Wait for enough tokens
                    needed = 1.0 - self.tokens
                    wait_time = needed / self.rate
                    await asyncio.sleep(wait_time)

class TelegramThrottler:
    """
    Strict 30 msg/s regulator (Global).
    Uses a queue worker to drain messages safely.
    """
    def __init__(self, rate_limit: float = 30.0):
        self.queue = asyncio.Queue()
        self.limiter = RateLimiter(rate=rate_limit, capacity=int(rate_limit))
        self.worker_task: Optional[asyncio.Task] = None
        
    async def start(self):
        if not self.worker_task:
            self.worker_task = asyncio.create_task(self._worker())
            logger.info("Telegram Throttler started.")
            
    async def stop(self):
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None
            
    async def send_message(self, bot_send_coroutine):
        """
        Enqueues a message send coroutine.
        Usage: await throttler.send_message(context.bot.send_message(...))
        Wait, we can't await the coro here if we want to queue it.
        We should pass a partial or a lambda? 
        Or enqueue an item (func, args, kwargs, future).
        
        Better: Enqueue the coroutine object itself? 
        If we await `bot.send_message(...)` it happens immediately.
        So caller must pass the coroutine object *un-awaited*? 
        Or simpler: Just queue the data and let worker call.
        But `bot.send_message` requires `bot` instance.
        
        Let's pass a `func` that returns an awaitable.
        """
        # Actually, python-telegram-bot handles some rate limiting, but we want strict control.
        # But for simplicity in this architecture, we might just throttle the *calls*.
        
        # Simpler approach: `acquire` before sending in the caller?
        # That blocks the caller (Patrol Loop).
        # Patrol Loop shouldn't block on alerts.
        # So queuing is better.
        
        # We need a future to return result if needed (e.g. sent message id)
        # But usually we fire and forget alerts.
        
        await self.queue.put(bot_send_coroutine)
        
    async def _worker(self):
        while True:
            coro = await self.queue.get()
            try:
                await self.limiter.acquire()
                # Run the coroutine
                await coro
            except Exception as e:
                logger.error(f"Failed to send throttled message: {e}")
            finally:
                self.queue.task_done()

class GlobalGovernor:
    """
    Singleton for system-wide limits.
    """
    _instance = None
    
    def __init__(self):
        # 5 RPS for scraping (Safe/Ethical default)
        self.web_limiter = RateLimiter(rate=5.0, capacity=5)
        self.telegram_throttler = TelegramThrottler(rate_limit=25.0) # Safety margin below 30
        
    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance
        
    async def acquire_web_token(self):
         await self.web_limiter.acquire()
         
    # Adaptive Logic Helper
    @property
    def is_congested(self) -> bool:
         # If fetching queue (in RequestManager) or Throttler queue is huge.
         # We don't have direct access to RequestManager queue here easily unless passed.
         # But we can check Telegram queue.
         return self.telegram_throttler.queue.qsize() > 50

# Global instance access
def get_governor():
    return GlobalGovernor.get_instance()
