import unittest
import logging
import time
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from request_manager import GlobalRequestManager
from headers import get_random_headers

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StealthTest")

class TestStealth(unittest.IsolatedAsyncioTestCase):
    
    def test_header_synchronization(self):
        logger.info("Test 1: Header Synchronization")
        for _ in range(5):
            headers = get_random_headers()
            ua = headers["User-Agent"]
            ch = headers.get("Sec-Ch-Ua", "")
            platform = headers.get("Sec-Ch-Ua-Platform", "")
            
            logger.info(f"UA: {ua[:50]}... | Platform: {platform}")
            
            if "Windows" in ua:
                self.assertIn("Windows", platform)
            elif "Macintosh" in ua:
                self.assertIn("macOS", platform)
                
            if "Chrome" in ua and "Edg" not in ua:
                self.assertIn("Google Chrome", ch)
            elif "Edg" in ua:
                self.assertIn("Microsoft Edge", ch)
                
        logger.info("SUCCESS: Headers are synchronized.")

    async def test_jitter(self):
        logger.info("Test 2: Jitter (Random Delay)")
        mgr = GlobalRequestManager()
        
        # Mock network to be instant
        mgr._execute_http_request = AsyncMock(return_value="OK")
        mgr.can_fetch = AsyncMock(return_value=True) # Robot allow
        
        start = time.time()
        # We assume fetch calls sleep.
        # Since we can't easily patch asyncio.sleep inside a running compiled func without strict patching,
        # we will rely on pure execution time or patch asyncio.sleep.
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
             await mgr.fetch("http://example.com")
             
             # Verify sleep was called with value between 1.0 and 5.0
             args, _ = mock_sleep.call_args
             delay = args[0]
             logger.info(f"Jitter Delay Detected: {delay:.2f}s")
             
             self.assertGreaterEqual(delay, 1.0)
             self.assertLessEqual(delay, 5.0)

        logger.info("SUCCESS: Jitter verified.")

    async def test_robots_txt_blocking(self):
        logger.info("Test 3: Robots.txt Compliance")
        mgr = GlobalRequestManager()
        
        # Mock can_fetch to return False
        mgr.can_fetch = AsyncMock(return_value=False)
        
        # Fetch should fail
        result = await mgr.fetch("http://forbidden.com/private")
        
        logger.info(f"Result Error: {result.error}")
        self.assertIn("Blocked by Robots.txt", result.error or "")
        logger.info("SUCCESS: Robots.txt blocking verified.")

if __name__ == '__main__':
    unittest.main()
