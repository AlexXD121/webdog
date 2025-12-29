import unittest
import logging
import sys
from pathlib import Path

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from change_detector import ChangeDetector
from models import Monitor, ChangeType

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ChangeDetectorTest")

class TestChangeDetector(unittest.TestCase):
    
    def setUp(self):
        self.detector = ChangeDetector()
        
    def test_case_a_small_diff(self):
        logger.info("Test Case A: Small Diff")
        old = "foo\nbar\nbaz"
        new = "foo\nbar\nqux"
        
        diff = self.detector.generate_safe_diff(old, new)
        logger.info(f"Small Diff:\n{diff}")
        
        self.assertIn("-baz", diff)
        self.assertIn("+qux", diff)
        self.assertLess(len(diff), 3100)
        
    def test_case_b_massive_diff(self):
        logger.info("Test Case B: Massive Diff")
        
        # Generate huge content
        old = "line\n" * 1000
        new = "line\n" * 500 + "modified\n" * 500
        
        diff = self.detector.generate_safe_diff(old, new)
        
        # Verify Safety
        logger.info(f"Diff Length: {len(diff)}")
        self.assertLess(len(diff), 4000) # strict telegram limit
        self.assertIn("Diff Truncated", diff)
        self.assertIn("Stats:", diff)
        
        logger.info("SUCCESS: Massive diff truncated safely.")

    def test_case_c_snapshot_rotation(self):
        logger.info("Test Case C: Snapshot Rotation")
        
        # Mock Monitor with empty snapshots
        monitor = Monitor(url="http://test.com")
        self.assertEqual(len(monitor.forensic_snapshots), 0)
        
        # Add 5 snapshots
        for i in range(5):
            content = f"content version {i}"
            self.detector.create_snapshot(monitor, content, ChangeType.CONTENT_UPDATE)
            
        # Verify Count
        self.assertEqual(len(monitor.forensic_snapshots), 3)
        
        # Verify we have the LATEST 3 (indices 2, 3, 4)
        # Decompress last one
        last_content = monitor.forensic_snapshots[-1].decompress()
        self.assertEqual(last_content, "content version 4")
        
        first_kept_content = monitor.forensic_snapshots[0].decompress()
        self.assertEqual(first_kept_content, "content version 2")
        
        logger.info("SUCCESS: Snapshot rotation verified (Kept last 3).")

if __name__ == '__main__':
    unittest.main()
