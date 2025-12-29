import unittest
import sys
import os
import time
from pathlib import Path
from datetime import datetime, timedelta

# Adjust path
sys.path.append(str(Path(__file__).parent.parent / "webdog_bot"))

from history_manager import HistoryManager, EXPORT_DIR

class TestCleanup(unittest.TestCase):
    def setUp(self):
        EXPORT_DIR.mkdir(exist_ok=True)
        # Create dummy files
        self.old_file = EXPORT_DIR / "old_export.csv"
        self.new_file = EXPORT_DIR / "new_export.csv"
        
        # Write old file (make it look old via os.utime)
        self.old_file.write_text("old")
        old_time = time.time() - 3600 * 2 # 2 hours ago
        os.utime(self.old_file, (old_time, old_time))
        
        # Write new file
        self.new_file.write_text("new")
        
    def tearDown(self):
        if self.old_file.exists(): self.old_file.unlink()
        if self.new_file.exists(): self.new_file.unlink()

    def test_cleanup_exports(self):
        HistoryManager.cleanup_exports(max_age_minutes=60)
        
        self.assertFalse(self.old_file.exists(), "Old file should be deleted")
        self.assertTrue(self.new_file.exists(), "New file should be kept")

if __name__ == '__main__':
    unittest.main()
