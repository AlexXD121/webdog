import unittest
import logging
import json
import os
import shutil
import asyncio
from pathlib import Path
import sys

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from logger import setup_logging, set_correlation_id, get_correlation_id

class TestStructuredLogging(unittest.TestCase):
    
    TEST_LOG_FILE = "tests/test_logs/webdog.log"
    
    def setUp(self):
        # Setup clean log dir
        log_dir = os.path.dirname(self.TEST_LOG_FILE)
        if os.path.exists(log_dir):
            shutil.rmtree(log_dir)
        setup_logging(self.TEST_LOG_FILE, level=logging.INFO)
        
    def tearDown(self):
        # Close handlers to release file lock
        logging.shutdown()
        
    def read_last_log_line(self) -> dict:
        with open(self.TEST_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return json.loads(lines[-1])

    def test_basic_json_structure(self):
        logger = logging.getLogger("TestModule")
        logger.info("Hello World")
        
        data = self.read_last_log_line()
        self.assertEqual(data["level"], "INFO")
        self.assertEqual(data["component"], "TestModule")
        self.assertEqual(data["message"], "Hello World")
        self.assertIn("timestamp", data)
        self.assertNotIn("correlation_id", data) # Default None

    def test_correlation_id_propagation(self):
        async def async_worker(cid, msg):
            set_correlation_id(cid)
            logging.getLogger("AsyncWorker").info(msg)
            
        # Run async task
        loop = asyncio.new_event_loop()
        loop.run_until_complete(async_worker("user-123", "Processing request"))
        loop.close()
        
        data = self.read_last_log_line()
        self.assertEqual(data["correlation_id"], "user-123")
        self.assertEqual(data["message"], "Processing request")

    def test_error_stack_trace(self):
        try:
            1 / 0
        except ZeroDivisionError:
            logging.getLogger("ErrorTest").exception("Math failed")
            
        data = self.read_last_log_line()
        self.assertEqual(data["level"], "ERROR")
        self.assertEqual(data["message"], "Math failed")
        self.assertIn("stack_trace", data)
        self.assertIn("ZeroDivisionError", data["stack_trace"])

if __name__ == '__main__':
    unittest.main()
