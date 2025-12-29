import unittest
import logging
import sys
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from main import WebDogBot
from governor import get_governor

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("TestLoad")

class TestLoadAPI(unittest.IsolatedAsyncioTestCase):
    
    async def test_web_rate_limiting(self):
        """
        Spam 20 requests. Limit is 5 RPS.
        Should take at least 3-4 seconds.
        """
        logger.info("Load 1: Web Request Flooding (5 RPS)...")
        bot = WebDogBot()
        
        # Mock Fetch to be instant
        bot.request_manager._client.get = AsyncMock()
        bot.request_manager._client.get.return_value = MagicMock(status_code=200, text="ok")
        
        start = time.time()
        
        tasks = []
        for i in range(20):
            tasks.append(bot.request_manager.fetch(f"http://site-{i}.com"))
            
        await asyncio.gather(*tasks)
        
        duration = time.time() - start
        logger.info(f"Processed 20 reqs in {duration:.2f}s")
        
        # 5 RPS -> 20 reqs needs 4 seconds (modulo burst).
        # Token bucket size 5. refill 5/s.
        # T=0: 5 tokens used (Instantly).
        # T=1: 5 tokens refill. Used.
        # T=2: 5 tokens refill. Used.
        # T=3: 5 tokens. Used.
        # Total ~3s.
        
        self.assertGreater(duration, 2.5, "Rate Limiter failed to throttle web requests")
        
    async def test_telegram_throttling(self):
        """
        Spam 100 messages. Limit 30/s.
        Should take > 3s.
        """
        logger.info("Load 2: Telegram Message Flooding (30 msg/s)...")
        gov = get_governor()
        await gov.telegram_throttler.start()
        
        # Mock the coroutine execution
        mock_send = AsyncMock()
        
        start = time.time()
        
        # Queue 100 messages
        for i in range(100):
            # we pass the coroutine object
            coro = mock_send()
            await gov.telegram_throttler.send_message(coro) # This is instant
            
        # Wait for drain
        await gov.telegram_throttler.queue.join()
        
        duration = time.time() - start
        logger.info(f"Processed 100 msgs in {duration:.2f}s")
        
        self.assertGreater(duration, 2.0, "Telegram Throttler failed to throttle messages")
        
        await gov.telegram_throttler.stop()

if __name__ == '__main__':
    unittest.main()
