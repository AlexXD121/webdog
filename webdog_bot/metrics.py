import time
import shutil
import logging
from typing import Dict, Any, List, Deque
from collections import deque
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("MetricsTracker")

class MetricsTracker:
    """
    Central Nervous System for Bot Health.
    Singleton pattern to ensure global aggregation.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MetricsTracker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._start_time = time.time()
        
        # Request Metrics (Bucketed by hour timestamp)
        # Structure: {timestamp: {"success": int, "fail": int, "count": int}}
        self._buckets: Dict[int, Dict[str, int]] = {} 
        
        # Latency (Global average for simplicity of trend)
        self._total_latency = 0.0
        self._request_count = 0
        
        # DB Metrics (Rolling window of last 1000 ops)
        self._db_write_latencies: Deque[float] = deque(maxlen=1000)
        
        # Worker Stats
        self._active_workers = 0
        self._total_workers = 0

    def record_request(self, latency: float, success: bool):
        """
        Record a web request outcome.
        """
        # Update Global Latency
        self._total_latency += latency
        self._request_count += 1
        
        # Update 24h Window Buckets
        now = time.time()
        hour_ts = int(now // 3600) * 3600
        
        if hour_ts not in self._buckets:
            self._buckets[hour_ts] = {"success": 0, "fail": 0, "count": 0}
            
        # Prune old buckets (> 24h)
        cutoff = now - (24 * 3600)
        # Using list(keys) to allow modification during iteration if needed, 
        # though we just iterate to find ones to delete.
        to_remove = [ts for ts in self._buckets if ts < cutoff]
        for ts in to_remove:
            del self._buckets[ts]
            
        # Record stats
        bucket = self._buckets[hour_ts]
        bucket["count"] += 1
        if success:
            bucket["success"] += 1
        else:
            bucket["fail"] += 1

    def record_db_operation(self, latency: float):
        """
        Record database write latency.
        """
        self._db_write_latencies.append(latency)

    def update_worker_stats(self, active: int, total: int):
        """
        Update current worker saturation.
        """
        self._active_workers = active
        self._total_workers = total

    def get_system_status(self) -> Dict[str, Any]:
        """
        Generate comprehensive health report.
        """
        now = time.time()
        
        # Calculate Success Rate (24h)
        total_reqs = 0
        total_success = 0
        for b in self._buckets.values():
            total_reqs += b["count"]
            total_success += b["success"]
            
        success_rate = (total_success / total_reqs * 100) if total_reqs > 0 else 100.0
        
        # Avg Latency
        avg_latency = (self._total_latency / self._request_count) if self._request_count > 0 else 0.0
        
        # DB Latency
        avg_db_latency = (sum(self._db_write_latencies) / len(self._db_write_latencies)) if self._db_write_latencies else 0.0
        
        # Disk Space
        try:
            total, used, free = shutil.disk_usage(".")
            free_mb = free // (1024 * 1024)
        except Exception:
            free_mb = 0
        
        # Alerts
        alerts = []
        if success_rate < 80.0 and total_reqs > 10:
             alerts.append("CRITICAL: Success rate below 80%")
        if free_mb < 500: # 500MB
             alerts.append("CRITICAL: Low Disk Space")
             
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": int(now - self._start_time),
            "performance": {
                "avg_request_latency_sec": round(avg_latency, 3),
                "avg_db_write_latency_sec": round(avg_db_latency, 3),
                "success_rate_24h_percent": round(success_rate, 2),
                "total_requests_24h": total_reqs
            },
            "workers": {
                "active": self._active_workers,
                "total": self._total_workers,
                "saturation_percent": round((self._active_workers / self._total_workers * 100) if self._total_workers > 0 else 0, 1)
            },
            "system": {
                "disk_free_mb": free_mb
            },
            "alerts": alerts
        }

# Global Accessor
def get_metrics_tracker() -> MetricsTracker:
    return MetricsTracker()
