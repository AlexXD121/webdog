import unittest
import logging
import sys
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from models import Monitor, HistoryEntry
from history_manager import HistoryManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HistoryTest")

class TestHistory(unittest.TestCase):
    
    def setUp(self):
        # Clean exports
        if os.path.exists("exports"):
            shutil.rmtree("exports")
        os.makedirs("exports")
        
    def test_archiving(self):
        logger.info("Test 1: Archiving")
        m = Monitor(url="http://test.com")
        
        # Add old entry (40 days ago)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        m.history_log.append(HistoryEntry(old_ts, "OLD", 0.0, "Old stuff"))
        
        # Add new entry (1 day ago)
        new_ts = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        m.history_log.append(HistoryEntry(new_ts, "NEW", 1.0, "New stuff"))
        
        self.assertEqual(len(m.history_log), 2)
        
        # Archive
        HistoryManager.archive_and_prune(m, days_to_keep=30)
        
        # Check Active
        self.assertEqual(len(m.history_log), 1)
        self.assertEqual(m.history_log[0].change_type, "NEW")
        
        # Check Archive
        self.assertEqual(len(m.history_archive), 1)
        # Verify decompression?
        import zlib, base64, json
        data = json.loads(zlib.decompress(base64.b64decode(m.history_archive[0])).decode('utf-8'))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['change_type'], "OLD")
        
    def test_csv_export(self):
        logger.info("Test 2: CSV Export")
        m = Monitor(url="http://export.com")
        m.history_log.append(HistoryEntry("2023-01-01T12:00:00+00:00", "TEST", 0.5, "Diff"))
        
        path = HistoryManager.export_to_csv(m)
        self.assertTrue(os.path.exists(path))
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("Timestamp (UTC)", content)
            self.assertIn("0.50", content)

    def tearDown(self):
       if os.path.exists("exports"):
           shutil.rmtree("exports")

if __name__ == '__main__':
    unittest.main()
