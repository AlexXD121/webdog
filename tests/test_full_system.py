import unittest
import logging
import sys
import asyncio
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from main import WebDogBot
from models import Monitor

logging.basicConfig(level=logging.INFO)

class TestFullSystem(unittest.IsolatedAsyncioTestCase):
    
    async def test_lifecycle_and_patrol(self):
        """
        Simulates a full run cycle.
        """
        bot = WebDogBot()
        
        # Mock Dependencies to avoid real net/telegram calls
        bot.request_manager.fetch = AsyncMock() 
        bot.request_manager.fetch.return_value = MagicMock(content="<html>Test</html>", error=None)
        
        bot.application = MagicMock()
        bot.application.job_queue = MagicMock()
        
        # 1. Start Up
        await bot.startup()
        self.assertTrue(bot.db_manager.db_path.exists())
        
        # 2. Add Monitor manually to DB
        chat_id = "12345"
        await bot.delete_monitor_logic(chat_id, "http://example.com") # clean
        
        # Use Watch Command Logic (Simulation)
        # We manually inject because calling cmd_watch requires Update/Context objects
        # Let's just create monitor in DB
        # Actually, let's test atomic write via delete first (which we did)
        
        # 3. Inject Data
        from models import UserData, WeightedFingerprint
        monitor = Monitor(url="http://example.com", fingerprint=None)
        all_data = await bot.db_manager.load_all_monitors()
        all_data[chat_id] = UserData(monitors=[monitor])
        await bot.db_manager.atomic_write(all_data)
        
        # 4. Run Patrol Cycle
        # We mock context
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        
        await bot.patrol_job(context)
        
        # 5. Verify Patrol Actions
        # Fetch should be called
        bot.request_manager.fetch.assert_called_with("http://example.com")
        
        # Data should have fingerprint now
        all_data_after = await bot.db_manager.load_all_monitors()
        m_after = all_data_after[chat_id].monitors[0]
        self.assertIsNotNone(m_after.fingerprint)
        self.assertGreater(m_after.metadata.check_count, 0)
        
        # 6. Shutdown
        await bot.shutdown()
        
        # 7. Check Governor Stop
        # verified implicit by no error
        
if __name__ == '__main__':
    unittest.main()
