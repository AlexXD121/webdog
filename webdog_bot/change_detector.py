import difflib
import logging
from typing import List
from models import Monitor, ForensicSnapshot, ChangeType

logger = logging.getLogger("ChangeDetector")

class ChangeDetector:
    """
    Handles forensic snapshot creation and safe diff generation.
    """
    
    # Telegram limit is ~4096. We stay safe with 3000 for diffs 
    # to allow for headers/footers in the message.
    MAX_DIFF_LENGTH = 3000
    SNAPSHOT_LIMIT = 3
    
    def generate_safe_diff(self, old_text: str, new_text: str) -> str:
        """
        Generates a unified diff, safely truncated for Telegram.
        """
        if not old_text or not new_text:
             return "No history available for diff."

        # Split into lines
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()
        
        # Generate Diff
        diff_gen = difflib.unified_diff(
            old_lines, 
            new_lines, 
            fromfile="Previous", 
            tofile="Current", 
            lineterm=""
        )
        
        # Build String
        diff_text = "\n".join(diff_gen)
        
        if not diff_text:
            return "No differences found."
            
        # Check Length
        if len(diff_text) <= self.MAX_DIFF_LENGTH:
            return f"```diff\n{diff_text}\n```"
            
        # Truncate Logic
        # Calculate stats for summary
        added = 0
        removed = 0
        for line in diff_text.splitlines():
            if line.startswith('+') and not line.startswith('+++'):
                added += 1
            elif line.startswith('-') and not line.startswith('---'):
                removed += 1
                
        # Create truncated version
        truncated = diff_text[:self.MAX_DIFF_LENGTH]
        # Try to cut at newline
        last_newline = truncated.rfind('\n')
        if last_newline > 0:
            truncated = truncated[:last_newline]
            
        summary = (
            f"\n... (Diff Truncated)\n"
            f"📊 Stats: +{added} lines, -{removed} lines.\n"
            f"Check WebDog Dashboard for full forensic details."
        )
        
        return f"```diff\n{truncated}\n```\n{summary}"

    def create_snapshot(self, monitor: Monitor, content: str, change_type: ChangeType) -> None:
        """
        Creates a compressed snapshot and manages the rotation limit (Keep last 3).
        Modifies the monitor object in-place.
        """
        # Create new
        snapshot = ForensicSnapshot.create(content, change_type)
        
        # Append
        monitor.forensic_snapshots.append(snapshot)
        
        # Rotate
        while len(monitor.forensic_snapshots) > self.SNAPSHOT_LIMIT:
             # Remove oldest
             monitor.forensic_snapshots.pop(0)
