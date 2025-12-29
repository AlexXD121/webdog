import unittest
import logging
import time
import sys
from pathlib import Path

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from metrics import MetricsTracker, get_metrics_tracker

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MetricsTest")

class TestMetrics(unittest.TestCase):
    
    def setUp(self):
        # Reset singleton logic manually for test isolation if needed, 
        # but since it's a new test class instance, we can just instantiate a fresh one 
        # OR rely on `_instance` reset.
        # Python singletons persist across tests in same process.
        MetricsTracker._instance = None 
        self.tracker = get_metrics_tracker()
        
    def test_request_calculations(self):
        logger.info("Test 1: Request Calculations")
        
        # Simulate 50 Success, 50 Fail
        # Latency 0.1s each
        for _ in range(50):
            self.tracker.record_request(0.1, True)
            
        for _ in range(50):
            self.tracker.record_request(0.1, False)
            
        status = self.tracker.get_system_status()
        perf = status["performance"]
        
        logger.info(f"Performance Stats: {perf}")
        
        self.assertEqual(perf["total_requests_24h"], 100)
        self.assertAlmostEqual(perf["success_rate_24h_percent"], 50.0)
        self.assertAlmostEqual(perf["avg_request_latency_sec"], 0.1)
        
    def test_alerts(self):
        logger.info("Test 2: Alerts Logic")
        
        # Simulate poor performance
        for _ in range(20):
             self.tracker.record_request(0.1, False) # 100% fail
             
        status = self.tracker.get_system_status()
        alerts = status["alerts"]
        
        logger.info(f"Alerts: {alerts}")
        self.assertTrue(any("Success rate below 80%" in a for a in alerts))

    def test_worker_stats(self):
        logger.info("Test 3: Worker Stats")
        self.tracker.update_worker_stats(5, 10)
        
        status = self.tracker.get_system_status()
        workers = status["workers"]
        
        self.assertEqual(workers["active"], 5)
        self.assertEqual(workers["saturation_percent"], 50.0)

if __name__ == '__main__':
    unittest.main()
