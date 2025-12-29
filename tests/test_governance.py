import unittest
import logging
import sys
import time
import asyncio
from pathlib import Path

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from governor import RateLimiter, TelegramThrottler, GlobalGovernor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GovernanceTest")

class TestGovernance(unittest.IsolatedAsyncioTestCase):
    
    async def test_rate_limiter(self):
        logger.info("Test 1: Rate Limiter (5 RPS)")
        # 5 RPS means 1 token every 0.2s. Capacity 5.
        rl = RateLimiter(rate=5.0, capacity=5)
        
        start = time.time()
        
        # Acquire 10 tokens.
        # First 5 are instant (burst).
        # Next 5 take 0.2s each -> 1.0s total wait roughly.
        # Wait, 6th token needs 0.2s wait.
        # 10 tokens total. 5 instant. 5 waits.
        # Total time ~ 1.0s?
        
        for _ in range(10):
            await rl.acquire()
            
        duration = time.time() - start
        logger.info(f"Acquired 10 tokens in {duration:.4f}s")
        
        # With capacity 5, first 5 are free. then we wait for 5 more.
        # To get 5 more at 5/sec -> 1 second.
        # So duration should be close to 1.0s. 
        self.assertGreater(duration, 0.8) # Allow some jitter/perf variance
        self.assertLess(duration, 1.5)

    async def test_telegram_throttler(self):
        logger.info("Test 2: Telegram Throttle")
        throttler = TelegramThrottler(rate_limit=50.0) # Faster for test
        await throttler.start()
        
        counter = 0
        async def dummy_send():
            nonlocal counter
            counter += 1
            
        # Queue 20 messages
        for _ in range(20):
            await throttler.send_message(dummy_send())
            
        # Wait for drain
        # 20 msgs at 50/sec -> 0.4s
        await asyncio.sleep(0.6) 
        
        self.assertEqual(counter, 20)
        await throttler.stop()

if __name__ == '__main__':
    unittest.main()
