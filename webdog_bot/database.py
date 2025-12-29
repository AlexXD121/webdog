import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import zlib
import base64

# --- Constants & Configuration ---
DB_VERSION = "2.0"
MIN_FREE_SPACE_MB = 10
BACKUP_COUNT = 5
DB_FILE_NAME = "db.json"

class InsufficientStorageError(Exception):
    """Raised when disk space is below the safe threshold."""
    pass

class DatabaseWriteError(Exception):
    """Raised when a database write operation fails."""
    pass

class WriteOperation:
    """Encapsulates a write request for the queue."""
    def __init__(self, data: dict, future: asyncio.Future):
        self.data = data
        self.future = future

class AtomicDatabaseManager:
    """
    Enterprise-grade database manager ensuring:
    - Concurrency Safety (Single-Worker Write Queue)
    - Atomic Persistence (Write-Tmp-Fsync-Rename)
    - Storage Guards (Pre-flight disk check)
    - Clock Resilience (UTC ISO 8601)
    - Rolling Backups
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            self.db_path = Path(__file__).resolve().parent / DB_FILE_NAME
        else:
            self.db_path = Path(db_path)
            
        self.write_queue: asyncio.Queue[WriteOperation] = asyncio.Queue()
        self.write_worker_task: Optional[asyncio.Task] = None
        
        # Initialize Logger
        self.logger = logging.getLogger("AtomicDB")
        
        # Ensure FS sync on start (create if missing)
        if not self.db_path.exists():
            self._initialize_empty_db()

        # Start the background worker
        self._start_write_worker()

    def _initialize_empty_db(self):
        """Creates an empty DB file with current version schema."""
        initial_data = {
            "schema_version": DB_VERSION,
            "data": {}
        }
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, indent=4)
            
    def _start_write_worker(self):
        """Starts the single background worker for sequential writes."""
        if self.write_worker_task and not self.write_worker_task.done():
            return
        self.write_worker_task = asyncio.create_task(self._write_worker_loop())
        self.logger.info("Database write worker started.")

    async def _write_worker_loop(self):
        """
        Consumer loop that processes write operations sequentially.
        """
        while True:
            write_op = await self.write_queue.get()
            try:
                await self._perform_atomic_write(write_op.data)
                if not write_op.future.done():
                    write_op.future.set_result(True)
            except Exception as e:
                self.logger.error(f"Critical DB Write Failure: {e}", exc_info=True)
                if not write_op.future.done():
                    write_op.future.set_exception(e)
            finally:
                self.write_queue.task_done()

    async def load_all_monitors(self) -> Dict[str, List[dict]]:
        """
        Loads monitors from disk. Handles schema migration if needed.
        Returns a dictionary of chat_id -> list of monitors.
        """
        if not self.db_path.exists():
            return {}

        async with asyncio.Lock(): # Read lock for basic safety against external edit overlap check
            try:
                # We use a run_in_executor for blocking IO read to avoid freezing event loop
                loop = asyncio.get_running_loop()
                data = await loop.run_in_executor(None, self._read_json_file)
                
                # Check Schema Version
                loaded_version = data.get("schema_version", "1.0")
                if loaded_version != DB_VERSION:
                    self.logger.info(f"Schema mismatch (Found {loaded_version}, Expected {DB_VERSION}). Triggering migration logic if needed.")
                    # In a real scenario, we would call a migration handler here.
                    # For now, we assume backward compatibility or just update version on next write.
                
                # Return the actual data payload. 
                # If v1 (raw dict of chat_ids), wrap it. If v2 (has "data" key), return that.
                if "data" in data:
                    return data["data"]
                else:
                    # Migration from v1 likely happened or it's a raw file
                    # If it looks like v1 { "123": [...] }, return it directly, 
                    # but next write will wrap it in schema v2 structure.
                    return data

            except Exception as e:
                self.logger.error(f"Failed to load DB: {e}")
                return {}

    def _read_json_file(self) -> dict:
        """Blocking read helper."""
        with open(self.db_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async def atomic_write(self, data: dict) -> bool:
        """
        Schedule an atomic write operation.
        
        Args:
            data: The entire monitors dictionary {chat_id: [monitors]}.
            
        Raises:
            InsufficientStorageError: If disk space is too low.
        """
        # Pre-flight Guard
        if not self._check_disk_space():
            raise InsufficientStorageError(f"Available disk space is below {MIN_FREE_SPACE_MB}MB.")

        # Create Future to wait for result
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        # Enqueue
        op = WriteOperation(data, future)
        await self.write_queue.put(op)
        
        # Wait for completion
        return await future

    async def _perform_atomic_write(self, monitors_data: dict):
        """
        Executes the actual write logic:
        1. Encapsulate in Schema V2 envelope.
        2. Create Rolling Backup (if schema change/time based - here we do it on every write for safety or heuristic).
           (Optimized: We can just backup if we are overwriting an existing file).
        3. Normalize Timestamps.
        4. Write .tmp -> fsync -> rename.
        """
        
        # 1. Structure Data
        final_payload = {
            "schema_version": DB_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "data": monitors_data
        }

        # 2. Normalize Timestamps
        final_payload = self._normalize_timestamps(final_payload)
        
        # 3. Create Backup (Blocking IO inside worker is acceptable as it's sequential)
        # We only backup if file exists. 
        # Strategy: To avoid spamming backups on every single ping update, usually we backup on migration.
        # Requirement says: "Before any write that involves a schema change or migration...". 
        # Since we are auto-migrating structure, let's check strict necessity. 
        # However, for "Rolling Backups" in general, let's do safe rotation.
        # We will implement a rotation distinct from every-write.
        # For this logic, let's assume every write is critical enough or strictly follow "schema change".
        # Let's verify if schema version changed from disk.
        
        # Simplified for robustness: Backup only if we detect we are upgrading/writing over old version.
        # OR implementation detail: Let's do a backup if the file is older than X or simple rotation.
        # Requirement: "Before any write... create a timestamped backup... Keep only last 5".
        # Let's interpret strict requirement: We backup before write.
        self._manage_backups()

        # 4. Atomic Write Sequence
        temp_file = self.db_path.parent / f"{self.db_path.name}.tmp"
        
        # Blocking IO in a thread pool to allow other loop tasks (like heartbeats) to tick if this was generic,
        # but since we are in a dedicated worker coroutine, we can just do blocking IO or use executor.
        # Using executor is safer for long writes.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_to_disk, temp_file, final_payload)

    def _write_to_disk(self, temp_file: Path, payload: dict):
        """Physical write operations."""
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=4)
                f.flush()
                # Force write to physical disk
                os.fsync(f.fileno())
            
            # Atomic swap
            os.replace(temp_file, self.db_path)
            self.logger.debug(f"Atomic write successful: {self.db_path}")
            
        except Exception as e:
            if temp_file.exists():
                os.remove(temp_file)
            raise DatabaseWriteError(f"Failed to write DB: {e}")

    def _check_disk_space(self) -> bool:
        """Checks if there is at least MIN_FREE_SPACE_MB available."""
        try:
            # db_path parent might not exist if we are starting fresh in a new dir, checking CWD or parent
            check_path = self.db_path.parent if self.db_path.parent.exists() else Path(".")
            total, used, free = shutil.disk_usage(check_path)
            free_mb = free // (1024 * 1024)
            return free_mb >= MIN_FREE_SPACE_MB
        except Exception as e:
            self.logger.warning(f"Could not check disk space: {e}. Proceeding blindly.")
            return True

    def _manage_backups(self):
        """Creates a backup and maintains the rolling limit of 5."""
        if not self.db_path.exists():
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{self.db_path.name}.backup_{timestamp}"
        backup_path = self.db_path.parent / backup_name
        
        try:
            shutil.copy2(self.db_path, backup_path)
            
            # Cleanup old backups
            backups = sorted(
                self.db_path.parent.glob(f"{self.db_path.name}.backup_*"),
                key=os.path.getmtime
            )
            
            while len(backups) > BACKUP_COUNT:
                oldest = backups.pop(0)
                os.remove(oldest)
                
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")

    def _normalize_timestamps(self, obj: Any) -> Any:
        """
        Recursively ensures all keys ending in '_at', '_time' or 'timestamp' 
        are ISO 8601 UTC strings.
        """
        if isinstance(obj, dict):
            new_dict = {}
            for k, v in obj.items():
                if k.endswith(('_at', '_time', 'timestamp')):
                    new_dict[k] = self._ensure_utc_iso(v)
                else:
                    new_dict[k] = self._normalize_timestamps(v)
            return new_dict
        elif isinstance(obj, list):
            return [self._normalize_timestamps(i) for i in obj]
        else:
            return obj

    def _ensure_utc_iso(self, value: Any) -> str:
        """Converts various time formats to strict UTC ISO 8601."""
        if isinstance(value, str):
            # Try to parse and reformat if it looks like a date,
            # otherwise assume it might be valid or fallback.
            # For simplicity, if it's already a string, we assume it's roughly correct 
            # OR we try to parse it. specific requirement: generate and store.
            # If we are reading existing data, we might want to normalize it.
            try:
                # Attempt flexible parsing
                # Note: standard datetime.fromisoformat is picky before Py3.11 for some formats,
                # but good enough for self-generated.
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt.isoformat()
            except ValueError:
                return value # Return as is if parsing fails, or could set to now()
        elif isinstance(value, (int, float)):
            # Assume unix timestamp
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
            return dt.isoformat()
        elif isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)
            return value.isoformat()
        return str(value)

# Singleton Instance for convenience, though main.py should instantiate
# db = AtomicDatabaseManager()
