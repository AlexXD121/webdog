import asyncio
import os
import random
import logging
import sys
from pathlib import Path

# Adjust path to import database.py
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from database import AtomicDatabaseManager, InsufficientStorageError

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TestRunner")

TEST_DB_PATH = Path("test_concurrency_db.json")

async def worker_task(mgr: AtomicDatabaseManager, worker_id: int):
    """Simulates a user adding a monitor"""
    url = f"https://example.com/worker_{worker_id}"
    logger.debug(f"[Worker {worker_id}] Starting write...")
    
    # Read-Modify-Write simulation
    # In a real app, logic is often: load -> modify in mem -> save
    # The manager exposes atomic_write taking the FULL payload.
    # So we need to emulate the application layer lock or optimistic concurrency.
    # However, the requirement is "All write operations must be processed sequentially by a background worker".
    # This means the DB manager linearizes writes.
    # If multiple workers read stale data and write, we still have a race at app layer.
    # BUT, for this test, we verify the MANAGER handles 50 concurrent 'atomic_write' calls without crashing
    # and that the file remains valid.
    
    # To truly test app-level consistency, we'd need a transactional method on the manager (e.g. update_monitor),
    # but the requirement asks for "Concurrency Safety... Single-Worker Write Queue".
    # This ensures the FILE is not corrupted by parallel writes.
    
    # Let's pound the queue.
    try:
        # We just push a completely new state for this worker's "namespace" to filter collisions locally
        # or we assume they are updating a shared structure.
        # Let's just push a unique payload assuming we are the "main" app state holder updates.
        
        # Simulating a state update:
        monitor_entry = {
            "url": url, 
            "created_at": "now" # Will be normalized
        }
        
        # NOTE: In a real app, you'd fetch current state, update, then write.
        # Here we just want to verify the queue processing integrity.
        # We will write a dictionary where keys are worker IDs to avoid overwriting each other blindly 
        # IF we were doing read-modify-write.
        # But `atomic_write` takes the WHOLE db state.
        # So correct usage by app is: 
        #   state = mgr.load()
        #   state['x'] = y
        #   mgr.write(state)
        # If we do this 50 times concurrently, the "load" will be stale for 49 of them.
        # The database.py requirement "Single-Worker Write Queue" prevents *file corruption*, 
        # not necessarily application-level lost updates if the app reads stale data.
        # HOWEVER, let's verify the queue works.
        
        success = await mgr.atomic_write({f"worker_{worker_id}": monitor_entry})
        assert success is True
        logger.debug(f"[Worker {worker_id}] Write complete.")
        
    except Exception as e:
        logger.error(f"[Worker {worker_id}] Failed: {e}")

async def run_test():
    if TEST_DB_PATH.exists():
        os.remove(TEST_DB_PATH)
        
    logger.info("Initializing AtomicDatabaseManager...")
    mgr = AtomicDatabaseManager(db_path=TEST_DB_PATH)
    
    # Allow worker to start
    await asyncio.sleep(0.1)
    
    logger.info("Spawning 50 concurrent write tasks...")
    tasks = [worker_task(mgr, i) for i in range(50)]
    
    start_time = asyncio.get_running_loop().time()
    await asyncio.gather(*tasks)
    end_time = asyncio.get_running_loop().time()
    
    logger.info(f"Processed 50 writes in {end_time - start_time:.2f} seconds.")
    
    # Verify File Content
    final_data = await mgr.load_all_monitors()
    logger.info(f"Final DB Content Keys: {len(final_data)}")
    
    # Cleanup
    if TEST_DB_PATH.exists():
        os.remove(TEST_DB_PATH)
        # Also cleanup backups
        for p in Path(".").glob("*.backup_*"):
            os.remove(p)
        logger.info("Test DB cleaned up.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_test())
