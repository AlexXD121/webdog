import csv
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Union
from pathlib import Path

from models import Monitor, HistoryEntry

logger = logging.getLogger("HistoryManager")

# Constants
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

class HistoryManager:
    """
    Manages history retention (pruning) and data export.
    """
    
    @staticmethod
    def add_history_entry(monitor: Monitor, change_type: str, score: float, summary: str):
        """
        Adds a new entry and automatically prunes old ones to keep the log healthy.
        """
        entry = HistoryEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            change_type=change_type,
            similarity_score=score,
            summary=summary
        )
        monitor.history_log.append(entry)
        
        # Simple immediate prune check (prevent infinite growth)
        # Detailed 30-day prune can run batch job, but keeping list size sane is good here too.
        # Let's prune by date here to ensure compliance immediately?
        # Or simple length cap for safety? 
        # Requirement: "Automatically purge or archive entries older than 30 days"
        # We'll run the date logic here.
        HistoryManager.archive_and_prune(monitor)

    @staticmethod
    def archive_and_prune(monitor: Monitor, days_to_keep: int = 30):
        """
        Moves entries older than N days to compressed archive.
        """
        if not monitor.history_log:
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        
        active_log = []
        to_archive = []
        
        for entry in monitor.history_log:
            try:
                ts = datetime.fromisoformat(entry.timestamp)
                if ts >= cutoff:
                    active_log.append(entry)
                else:
                    to_archive.append(entry)
            except ValueError:
                continue 
        
        if to_archive:
            try:
                # Serialize list of dicts
                data_str = json.dumps([e.to_dict() for e in to_archive])
                # Compress
                import zlib
                import base64
                compressed = zlib.compress(data_str.encode('utf-8'))
                b64_so = base64.b64encode(compressed).decode('ascii')
                
                monitor.history_archive.append(b64_so)
                logger.info(f"Archived {len(to_archive)} entries for {monitor.url}")
            except Exception as e:
                logger.error(f"Archival failed: {e}")
                # If fail, we keep them in active log or drop?
                # Better to keep them in active_log to avoid data loss, or just drop if crucial.
                # We'll just append them back to active_log in memory so we don't lose them, but we might exceed list size.
                # For safety, let's just log error and proceed with keeping them.
                active_log = monitor.history_log # Revert
                
        monitor.history_log = active_log

    @staticmethod
    def export_to_csv(monitor: Monitor) -> str:
        """
        Generates a CSV file and returns the path.
        """
        filename = f"{monitor.url.replace('://', '_').replace('/', '_')}_history.csv"
        filepath = EXPORT_DIR / filename
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Timestamp (UTC)', 'Change Type', 'Similarity Score', 'Summary'])
                
                for entry in monitor.history_log:
                    writer.writerow([
                        entry.timestamp,
                        entry.change_type,
                        f"{entry.similarity_score:.2f}",
                        entry.summary
                    ])
            return str(filepath)
        except Exception as e:
            logger.error(f"CSV Export failed: {e}")
            return ""

    @staticmethod
    def export_to_json(monitor: Monitor) -> str:
        """
        Generates a JSON file and returns the path.
        """
        filename = f"{monitor.url.replace('://', '_').replace('/', '_')}_history.json"
        filepath = EXPORT_DIR / filename
        
        data = {
            "url": monitor.url,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "history": [entry.to_dict() for entry in monitor.history_log]
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return str(filepath)
        except Exception as e:
            logger.error(f"JSON Export failed: {e}")
            return ""
