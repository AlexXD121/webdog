import time
import logging
from enum import Enum, auto

logger = logging.getLogger("CircuitBreaker")

class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()

class CircuitBreaker:
    """
    Implements a Circuit Breaker pattern to allow "Failing Fast".
    Prevents cascading failures and protects the request pipeline.
    """
    
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 3600):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        
        # Config
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

    def is_allowable(self) -> bool:
        """
        Check if a request is allowed to proceed.
        """
        if self.state == CircuitState.CLOSED:
            return True
            
        if self.state == CircuitState.OPEN:
            now = time.time()
            if (now - self.last_failure_time) > self.recovery_timeout:
                # Transition to Half-Open to probe
                logger.info("Circuit recovery timeout passed. shifting to HALF_OPEN (Probing).")
                self.state = CircuitState.HALF_OPEN
                return True
            return False
            
        if self.state == CircuitState.HALF_OPEN:
            # We allow ONE request to fly.
            # Ideally we should track if a request is already flying, 
            # but for this simple implementation, if we are in HALF_OPEN, 
            # we allow the caller to try. If multiple callers race, 
            # the first failure will trip it back to OPEN anyway.
            # To be strict, we could have a "probing" flag, but is_allowable is usually checked just before fetch.
            return True
            
        return False

    def record_success(self):
        """
        Call this when a request succeeds.
        """
        if self.state != CircuitState.CLOSED:
            logger.info("Circuit probe successful. Closing circuit (Healthy).")
            self.state = CircuitState.CLOSED
            self.failure_count = 0

    def record_failure(self):
        """
        Call this when a request fails.
        """
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            # Probe failed, back to OPEN immediately
            logger.warning("Circuit probe failed. Re-opening circuit.")
            self.state = CircuitState.OPEN
            return

        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                logger.warning(f"Failure threshold ({self.failure_threshold}) reached. Opening circuit.")
                self.state = CircuitState.OPEN
