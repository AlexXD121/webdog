import logging
import json
import datetime
import sys
import os
from logging.handlers import RotatingFileHandler
from contextvars import ContextVar
from typing import Optional, Any, Dict

# Context Var for Correlation ID (e.g. Chat ID)
_correlation_id_ctx = ContextVar("correlation_id", default=None)

def set_correlation_id(cid: Optional[str]):
    """Sets the correlation ID for the current context."""
    _correlation_id_ctx.set(cid)

def get_correlation_id() -> Optional[str]:
    """Gets the current correlation ID."""
    return _correlation_id_ctx.get()

class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings for every log record.
    Includes correlation_id automatically.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        # 1. Base Data
        log_data: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }
        
        # 2. Correlation ID
        cid = get_correlation_id()
        if cid:
            log_data["correlation_id"] = cid
            
        # 3. Exception Info
        if record.exc_info:
            # Format exception
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            log_data["stack_trace"] = record.exc_text
            
        # 4. Extra Fields (if passed via extra={...})
        if hasattr(record, "custom_metrics"):
             log_data["metrics"] = record.custom_metrics # type: ignore

        return json.dumps(log_data)

def setup_logging(log_file: str, level: int = logging.INFO):
    """
    Configures the root logger with rotating JSON handler.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    # Create Directory if needed
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    # Handler: Rotating File (5MB, 5 backups)
    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024, # 5MB
        backupCount=5,
        encoding="utf-8"
    )
    
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)
    
    # Optional: Also log to console (stderr) for dev visibility?
    # For now, let's keep it strictly to file as "Black Box", 
    # OR add a console handler that is human readable? 
    # Requirement says "Black Box Recorder". Usually implies file.
    # We will stick to file for the professional requirement.
    
    # Log startup
    logging.getLogger("System").info("Logging system initialized.")
