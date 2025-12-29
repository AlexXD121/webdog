import asyncio
import os
import json
import logging
import sys
import zlib
import base64
from pathlib import Path

# Adjust path to import database.py and models.py
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from database import AtomicDatabaseManager
from models import ForensicSnapshot, ChangeType, UserData

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DataModelTest")

TEST_DB_PATH = Path("test_models_db.json")

async def test_forensic_compression():
    logger.info("--- Testing Forensic Compression ---")
    
    html_content = "<html><body><h1>Hello World</h1><p>This is a test.</p></body></html>" * 10
    
    # Compress
    snapshot = ForensicSnapshot.create(html_content, ChangeType.CONTENT_UPDATE)
    logger.info(f"Original Size: {len(html_content)} bytes")
    logger.info(f"Compressed (Base64) Size: {len(snapshot.compressed_content)} bytes")
    
    # Save to JSON simulation
    json_str = json.dumps(snapshot.__dict__)
    loaded_dict = json.loads(json_str)
    
    # Reconstruct
    loaded_snapshot = ForensicSnapshot(**loaded_dict)
    
    # Decompress
    decompressed_html = loaded_snapshot.decompress()
    
    assert decompressed_html == html_content
    logger.info("SUCCESS: Decompressed content matches original.")

async def test_migration():
    logger.info("--- Testing Migration V1 -> V2 ---")
    
    if TEST_DB_PATH.exists():
        os.remove(TEST_DB_PATH)
        
    # Seed Legacy V1 Data (Dict format)
    legacy_data = {
        "12345": {"url": "https://example.com", "hash": "abc123hash"},
        "67890": [{"url": "https://google.com", "hash": "xyz789hash"}] # Mixed Format
    }
    
    # Write "Raw" V1 file (mimicking old database.py behavior)
    with open(TEST_DB_PATH, 'w') as f:
        json.dump(legacy_data, f) # No schema wrapper, just raw data
        
    logger.info("Seeded Legacy V1 DB.")
    
    # Initialize Manager (Should trigger migration on load)
    mgr = AtomicDatabaseManager(db_path=TEST_DB_PATH)
    
    # Give generic background worker time to start? Not needed for load_all_monitors
    
    # Load Data
    data = await mgr.load_all_monitors()
    
    # Verify Structure
    assert "12345" in data
    assert isinstance(data["12345"], UserData)
    assert len(data["12345"].monitors) == 1
    assert data["12345"].monitors[0].url == "https://example.com"
    assert data["12345"].monitors[0].fingerprint.hash == "abc123hash"
    assert data["12345"].monitors[0].fingerprint.version == "legacy"
    
    assert "67890" in data
    assert len(data["67890"].monitors) == 1
    assert data["67890"].monitors[0].url == "https://google.com"
    
    logger.info(f"Migrated User 12345: {data['12345']}")
    
    # Write back to check persistency
    success = await mgr.atomic_write(data)
    assert success
    
    # Check underlying file
    with open(TEST_DB_PATH, 'r') as f:
        saved_file = json.load(f)
        
    assert saved_file["schema_version"] == "2.0"
    assert "12345" in saved_file["data"]
    assert "monitors" in saved_file["data"]["12345"]
    
    logger.info("SUCCESS: Migration and Save verified.")
    
    # Cleanup
    if TEST_DB_PATH.exists():
        os.remove(TEST_DB_PATH)
    for p in Path('.').glob("*.backup_*"): # cleanup backups made during write
        os.remove(p)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    async def main():
        await test_forensic_compression()
        await test_migration()
        
    asyncio.run(main())
