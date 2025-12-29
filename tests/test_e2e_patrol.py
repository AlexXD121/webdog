import unittest
import logging
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from main import WebDogBot
from models import Monitor, UserData, WeightedFingerprint
from history_manager import HistoryManager

logging.basicConfig(level=logging.ERROR, stream=sys.stdout) # Show us errors!
logger = logging.getLogger("TestE2E")

class TestE2EPatrol(unittest.IsolatedAsyncioTestCase):
    
    async def test_end_to_end_patrol(self):
        """
        Validates:
        1. Adding a monitor.
        2. Patrol Job execution.
        3. Change Detection (Mocked content change).
        4. Alert Generation (Payload verification).
        5. History Logging.
        """
        logger.info("Starting E2E Patrol Test...")
        bot = WebDogBot()
        
        # Mocks
        bot.request_manager.fetch = AsyncMock()
        bot.db_manager.atomic_write = AsyncMock()
        
        # Mock Context & Bot
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        
        # 1. Setup Data: Existing monitor with old fingerprint
        chat_id = "e2e_test_user"
        initial_fp = bot.fingerprinter.generate_fingerprint("<html>Old Content</html>")
        monitor = Monitor(url="https://changed-site.com", fingerprint=initial_fp)
        
        # Inject into DB load
        mock_data = {chat_id: UserData(monitors=[monitor])}
        bot.db_manager.load_all_monitors = AsyncMock(return_value=mock_data)
        
        # 2. Mock Network Response (CHANGED content)
        # We need to ensure fingerprint differs.
        # Real fingerprinter will hash this. "New Content" != "old_hash_123"
        bot.request_manager.fetch.return_value = MagicMock(content="<html>New Content</html>", error=None)
        
        # 2a. Mock Governor Throttler to bypass queue
        from governor import get_governor
        gov = get_governor()
        # We replace send_message with a simple pass-through awaiter
        async def fast_send(coro):
            await coro
        gov.telegram_throttler.send_message = fast_send
        
        # 2b. Mock Similarity to FORCE ALERT
        bot.similarity_engine.calculate_similarity = MagicMock()
        mock_sim_result = MagicMock()
        mock_sim_result.final_score = 0.0 # Force alert
        bot.similarity_engine.calculate_similarity.return_value = mock_sim_result
        
        # 3. Trigger Patrol
        await bot.patrol_job(context)
        
        # 4. Verify Alert
        # Should have detected change -> called send_message
        context.bot.send_message.assert_called_once()
        
        # Verify Payload
        call_args = context.bot.send_message.call_args
        msg_text = call_args.kwargs['text']
        self.assertIn("https://changed-site.com", msg_text)
        self.assertIn("Change Detected", msg_text)
        
        # 5. Verify History
        # We need to check if history log was appended to the monitor object in memory
        self.assertGreater(len(monitor.history_log), 0)
        latest = monitor.history_log[-1]
        self.assertEqual(latest.change_type, "CHANGE")
        self.assertIn("Alerted", latest.summary)
        
        # 6. Verify DB Write
        bot.db_manager.atomic_write.assert_called_once()
        
        logger.info("E2E Patrol Test Passed.")

if __name__ == '__main__':
    unittest.main()
