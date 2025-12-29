import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# Adjust path to include src
sys.path.append(str(Path(__file__).parent.parent / "webdog_bot"))

from main import WebDogBot
from database import AtomicDatabaseManager
from metrics import get_metrics_tracker
from request_manager import GlobalRequestManager
from fingerprinter import VersionedContentFingerprinter
from similarity import SimilarityEngine
from change_detector import ChangeDetector
from history_manager import HistoryManager
from models import Monitor, ChangeType, HistoryEntry

# Setup Logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SmokeTest")

async def run_smoke_test():
    logger.info("💨 Starting Pre-Deployment Smoke Test...")
    
    # 1. Component Init
    logger.info("[1/6] Initializing Components...")
    bot = WebDogBot()
    
    # Verify DB
    if not bot.db_manager.db_path.exists():
        logger.info("creating new db.json for test...")
    
    # Verify Metrics
    status = get_metrics_tracker().get_system_status()
    if 'uptime_seconds' in status:
        logger.info("✅ Metrics Tracker Active")
    else:
        logger.error("❌ Metrics Tracker Failed")
        return

    # 2. Stealth Fetch
    logger.info("[2/6] Testing Fetch (Google.com)...")
    fetch_result = await bot.request_manager.fetch("https://www.google.com")
    if fetch_result.error:
        logger.error(f"❌ Fetch Failed: {fetch_result.error}")
        return
    logger.info(f"✅ Fetch Success: {fetch_result.status_code}")
    
    # 3. Fingerprinting
    logger.info("[3/6] Testing Fingerprinter...")
    fp = bot.fingerprinter.generate_fingerprint(fetch_result.content)
    if fp.version == "v2.0" and fp.hash:
        logger.info(f"✅ Fingerprint Generated: {fp.hash[:8]}... (v{fp.version})")
    else:
        logger.error("❌ Fingerprint verification failed")
        return

    # 4. Similarity Analysis
    logger.info("[4/6] Testing Similarity Engine...")
    # Create a fake 'old' fingerprint by modifying hash
    import copy
    old_fp = copy.deepcopy(fp)
    old_fp.hash = "different_hash"
    # Modifying weights to simulate change
    old_fp.content_weights['dummy'] = 999.0 
    
    score = bot.similarity_engine.calculate_similarity(old_fp, fp)
    logger.info(f"✅ Similarity Score: {score.final_score:.2f}")

    # 5. Forensic Generation (Diff)
    logger.info("[5/6] Testing Forensic Diff Generation...")
    old_content = "<html><body><h1>Hello World</h1></body></html>"
    new_content = "<html><body><h1>Hello Universe</h1></body></html>"
    
    cd = ChangeDetector()
    diff = cd.generate_safe_diff(old_content, new_content)
    if len(diff) < 3000:
        logger.info("✅ Diff generated and within limits.")
    else:
        logger.error("❌ Diff too large!")
        return

    # 6. History Archival
    logger.info("[6/6] Testing History Archival...")
    monitor = Monitor(url="https://test.com", fingerprint=fp)
    
    monitor.history_log.append(HistoryEntry(
        timestamp="2020-01-01T00:00:00+00:00", # OLD entry
        change_type="TEST",
        similarity_score=0.0,
        summary="Old Entry"
    ))
    
    HistoryManager.archive_and_prune(monitor, days_to_keep=30)
    
    if len(monitor.history_archive) > 0:
        logger.info("✅ Archival Successful (Entry moved to archive)")
    else:
        # Note: If run multiple times very fast, it might not archive if list empty?
        # But we just appended one.
        logger.error("❌ Archival Failed (No entry archived)")
        return

    # Cleanup
    await bot.shutdown()
    logger.info("\n🟢 SMOKE TEST PASSED: Bot is Structurally Production Ready.")

if __name__ == "__main__":
    # Removed deprecated WindowsSelectorEventLoopPolicy for Python 3.10+ compat
    # Default policy on Windows in py3.8+ is Proactor which is usually fine, 
    # unless using specific libraries needing Selector.
    # For this smoke test, standard run should suffice.
    asyncio.run(run_smoke_test())
