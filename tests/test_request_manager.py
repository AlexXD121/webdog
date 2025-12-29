import asyncio
import logging
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Adjust path 
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from request_manager import GlobalRequestManager, FetchTimeoutError

# Configure Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RequestManagerTest")

async def mock_slow_response(*args, **kwargs):
    """Simulates a slow server"""
    await asyncio.sleep(20) # Longer than 15s timeout
    return MagicMock(text="Too late", status_code=200)

async def mock_fast_response(*args, **kwargs):
    """Simulates a fast server"""
    await asyncio.sleep(0.5)
    return MagicMock(text="Fast content", status_code=200)

async def test_deduplication():
    logger.info("--- Testing Deduplication ---")
    mgr = GlobalRequestManager()
    
    # Mock the internal client.get to count calls
    mgr._client.get = AsyncMock(side_effect=mock_fast_response)
    
    url = "https://example.com/api"
    
    # Spawn 10 concurrent requests
    logger.info("Spawning 10 concurrent requests...")
    tasks = [mgr.fetch(url) for _ in range(10)]
    results = await asyncio.gather(*tasks)
    
    # Verify results
    assert len(results) == 10
    for r in results:
        assert r.content == "Fast content"
        assert r.error is None
    
    # Verify ONLY 1 network call was made
    call_count = mgr._client.get.call_count
    logger.info(f"Total Network Calls: {call_count}")
    assert call_count == 1
    logger.info("SUCCESS: Deduplication verified.")
    
    await mgr.close()

async def test_hard_timeout():
    logger.info("--- Testing Hard Timeout ---")
    mgr = GlobalRequestManager()
    
    # Mock client to hang
    mgr._client.get = AsyncMock(side_effect=mock_slow_response)
    
    url = "https://example.com/slow"
    
    start = time.time()
    result = await mgr.fetch(url)
    end = time.time()
    
    duration = end - start
    logger.info(f"Fetch took {duration:.2f}s")
    
    # Verify it returned (didn't hang forever) and has error
    assert duration < 16.0 # Should be close to 15s
    assert result.error is not None
    assert "Hard Timeout" in result.error
    
    logger.info("SUCCESS: Hard Timeout verified.")
    await mgr.close()

async def test_normalization():
    logger.info("--- Testing Normalization ---")
    mgr = GlobalRequestManager()
    
    url1 = "https://example.com?utm_source=twitter"
    url2 = "https://example.com?fbclid=12345"
    
    n1 = mgr.normalize_url(url1)
    n2 = mgr.normalize_url(url2)
    
    logger.info(f"Normalized 1: {n1}")
    logger.info(f"Normalized 2: {n2}")
    
    assert n1 == n2
    assert "utm_source" not in n1
    logger.info("SUCCESS: URL Normalization verified.")
    await mgr.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    async def main():
        await test_deduplication()
        await test_hard_timeout()
        await test_normalization()
        
    asyncio.run(main())
