import unittest
import logging
import sys
import time
from pathlib import Path
from unittest.mock import patch

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from circuit_breaker import CircuitBreaker, CircuitState

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CircuitBreakerTest")

class TestCircuitBreaker(unittest.TestCase):
    
    def test_failure_threshold(self):
        logger.info("Test 1: Failure Threshold")
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)
        
        # 1. Closed initially
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.is_allowable())
        
        # 2. Add Failures
        cb.record_failure() # 1
        self.assertEqual(cb.state, CircuitState.CLOSED)
        cb.record_failure() # 2
        self.assertEqual(cb.state, CircuitState.CLOSED)
        cb.record_failure() # 3 -> Trip
        
        self.assertEqual(cb.state, CircuitState.OPEN)
        logger.info("Circuit Tripped to OPEN.")
        
        # 3. Fast Fail
        self.assertFalse(cb.is_allowable())
        logger.info("SUCCESS: Circuit rejects requests when OPEN.")

    def test_recovery_flow(self):
        logger.info("Test 2: Recovery Flow")
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=1) # Short timeout
        
        # Trip it
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        
        # Wait for timeout (Mocking time would be better, but sleep 1.1 is easy here)
        time.sleep(1.1)
        
        # Should be allowable now (Transition to HALF_OPEN)
        self.assertTrue(cb.is_allowable())
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        logger.info("Circuit shifted to HALF_OPEN.")
        
        # Scenario A: Probe Success
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        logger.info("SUCCESS: Circuit recovered to CLOSED.")
        
        # Reset and try Scenario B: Probe Failure
        cb.record_failure() # Trip again
        self.assertEqual(cb.state, CircuitState.OPEN)
        time.sleep(1.1)
        self.assertTrue(cb.is_allowable()) # Half open
        
        cb.record_failure() # Probe Fails
        self.assertEqual(cb.state, CircuitState.OPEN)
        logger.info("SUCCESS: Circuit re-opened on probe failure.")

if __name__ == '__main__':
    unittest.main()
