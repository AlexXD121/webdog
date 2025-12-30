import unittest
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

import interface
from models import Monitor
# We can't easily mock valid Telegram bot objects without complex mocking frameworks, 
# but we can test the Interface Generation logic functions directly.

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("InterfaceTest")

class TestInterface(unittest.TestCase):
    
    def test_pagination_logic(self):
        logger.info("Test 1: Pagination")
        
        # Create 15 dummy monitors
        monitors = [Monitor(url=f"site_{i}.com") for i in range(15)]
        
        # Page 0 (0-5)
        kb_p0 = interface.get_monitor_list_keyboard(monitors, page=0)
        # Should have Next, No Prev
        # Structure is list of lists of InlineKeyboardButton
        rows = kb_p0.inline_keyboard
        # Last row is menu, 2nd last is nav
        nav_row = rows[-2]
        
        labels = [b.text for b in nav_row]
        logger.info(f"Page 0 Nav: {labels}")
        self.assertIn("Next", str(labels))
        self.assertNotIn("Prev", str(labels))
        
        # Check Item Count (5 items + nav + menu? No, 5 item rows)
        # Actual structure: 5 rows of items, 1 row nav, 1 row menu = 7 rows total
        self.assertEqual(len(rows), 7) 

        # Page 2 (10-15) -> Final page
        kb_p2 = interface.get_monitor_list_keyboard(monitors, page=2)
        rows_2 = kb_p2.inline_keyboard
        nav_row_2 = rows_2[-2]
        labels_2 = [b.text for b in nav_row_2]
        
        logger.info(f"Page 2 Nav: {labels_2}")
        self.assertIn("Prev", str(labels_2))
        self.assertNotIn("Next", str(labels_2))

    def test_snooze_keyboard(self):
        logger.info("Test 2: Snooze Keyboard")
        kb = interface.get_alert_keyboard("google.com")
        rows = kb.inline_keyboard
        
        # Check buttons exist
        b_1h = rows[0][0]
        self.assertIn("Snooze 1h", b_1h.text)
        self.assertEqual(b_1h.callback_data, "SNOOZE_60_google.com")

if __name__ == '__main__':
    unittest.main()
