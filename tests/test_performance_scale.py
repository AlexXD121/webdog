import unittest
import logging
import sys
import asyncio
import time
import tracemalloc
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from main import WebDogBot
from models import Monitor, UserData, WeightedFingerprint

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("TestPerf")

class TestPerformanceScale(unittest.IsolatedAsyncioTestCase):
    
    async def test_scale_1000_monitors(self):
        """
        Simulates one patrol cycle for 1,000 monitors.
        Pass criteria:
        - Execution < 60s (Mocked Network)
        - Memory overhead < 50MB delta (Strict)
        """
        logger.info("Initializing 1k Scale Test...")
        bot = WebDogBot()
        
        # Mocks
        bot.request_manager.fetch = AsyncMock()
        bot.request_manager.fetch.return_value = MagicMock(content="<html>Simple Content</html>", error=None)
        bot.db_manager.atomic_write = AsyncMock() # Don't write 1k items to disk in test
        
        # Bypass Governor (Rate Limiting would slow this down to 200s @ 5RPS)
        # We want to test PROCESSOR speed/memory, not Rate Limiter.
        from governor import get_governor
        gov = get_governor()
        async def fast_acquire(): pass
        gov.acquire_web_token = fast_acquire
        
        # 1. Seed Data
        monitors = []
        for i in range(1000):
            m = Monitor(url=f"http://site-{i}.com", fingerprint=None)
            monitors.append(m)
            
        mock_data = {"perf_user": UserData(monitors=monitors)}
        bot.db_manager.load_all_monitors = AsyncMock(return_value=mock_data)
        
        context = MagicMock()
        
        # 2. Measure Baseline
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()
        start_time = time.time()
        
        # 3. Run Patrol
        logger.info("Starting Patrol Loop...")
        await bot.patrol_job(context)
        
        end_time = time.time()
        snapshot2 = tracemalloc.take_snapshot()
        
        # 4. Stats
        duration = end_time - start_time
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        
        total_delta = sum(stat.size_diff for stat in top_stats) / (1024 * 1024) # MB
        
        logger.info(f"Duration: {duration:.2f}s")
        logger.info(f"Memory Delta: {total_delta:.2f} MB")
        
        # 5. Assertions
        # 1000 items processed. Fingerprinter runs 1000 times (BS4 overhead).
        # Should be reasonably fast if net is 0. BS4 might take 0.01s per page -> 10s.
        self.assertLess(duration, 30.0, "Patrol took too long for 1k items (CPU bound)")
        
        # Memory should be cleaned up mostly, delta represents leaked or retained state.
        # We retained 1000 fingerprints? No, we created them but didn't save to DB (mock write).
        # Actually logic is: monitor.fingerprint = new_fp.
        # So we hold 1000 new FP objects in memory (in `mock_data` struct).
        # 1000 strings + objs is small. 1-2MB.
        # BS4 is heavy but should be GC'd.
        self.assertLess(total_delta, 50.0, "Memory usage spiked too high")
        
        tracemalloc.stop()

if __name__ == '__main__':
    unittest.main()
