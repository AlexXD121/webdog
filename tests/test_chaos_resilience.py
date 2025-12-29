import unittest
import logging
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from main import WebDogBot
from models import Monitor, UserData

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("TestChaos")

class TestChaosResilience(unittest.IsolatedAsyncioTestCase):
    
    async def test_network_blackout(self):
        """
        Simulate 100% Network Failure.
        Bot should not crash, just log errors.
        """
        logger.info("Chaos 1: Network Blackout...")
        bot = WebDogBot()
        
        # Mock Fetch raising Exception
        bot.request_manager.fetch = AsyncMock(side_effect=Exception("Connection Reset"))
        
        # Add Monitor
        monitor = Monitor(url="http://fail.com")
        mock_data = {"user": UserData(monitors=[monitor])}
        bot.db_manager.load_all_monitors = AsyncMock(return_value=mock_data)
        context = MagicMock()
        
        # Run Patrol
        try:
            await bot.patrol_job(context)
            logger.info("Patrol survived blackout.")
        except Exception as e:
            self.fail(f"Bot crashed on network failure: {e}")
            
        # Verify failure count incremented
        self.assertGreater(monitor.metadata.failure_count, 0)
        
    async def test_db_corruption_recovery(self):
        """
        Simulate DB Write Failure (Disk Full / Permission).
        Bot should catch it.
        """
        logger.info("Chaos 2: DB Write Failure...")
        bot = WebDogBot()
        
        # Mock Data load success
        monitor = Monitor(url="http://ok.com", fingerprint=None) # Needs update
        mock_data = {"user": UserData(monitors=[monitor])}
        bot.db_manager.load_all_monitors = AsyncMock(return_value=mock_data)
        
        # Mock Fetch Success -> Updates needed
        bot.request_manager.fetch = AsyncMock()
        bot.request_manager.fetch.return_value = MagicMock(content="<html>ok</html>", error=None)
        
        # Mock DB Write FAILURE
        bot.db_manager.atomic_write = AsyncMock(side_effect=IOError("Disk Full"))
        
        context = MagicMock()
        
        try:
            await bot.patrol_job(context)
            logger.info("Patrol survived DB crash.")
        except Exception as e:
            self.fail(f"Bot crashed on DB failure: {e}")

if __name__ == '__main__':
    unittest.main()
