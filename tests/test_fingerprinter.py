import unittest
import logging
from bs4 import BeautifulSoup

# Adjust path / Import
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from fingerprinter import VersionedContentFingerprinter, BlockPageDetected

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FingerprinterTest")

class TestFingerprinter(unittest.TestCase):
    
    def setUp(self):
        self.fp = VersionedContentFingerprinter()
        
    def test_block_page_detection(self):
        logger.info("Testing Block Page Detection...")
        
        cloudflare_html = """
        <html>
        <head><title>Just a moment...</title></head>
        <body>
            <h1>Checking your browser before accessing example.com</h1>
            <p>Please wait while we verify you are human.</p>
            <div>Ray ID: 1234567890</div>
        </body>
        </html>
        """
        
        self.assertTrue(self.fp.is_block_page(cloudflare_html))
        
        with self.assertRaises(BlockPageDetected):
            self.fp.generate_fingerprint(cloudflare_html)
            
        logger.info("SUCCESS: Cloudflare page correctly flagged.")

    def test_noise_filtering(self):
        logger.info("Testing Noise Filtering...")
        
        # Two HTMLs differing ONLY by timestamp and session ID
        html_a = """
        <html><body>
            <article>
                <h1>Breaking News</h1>
                <p>The market is up.</p>
                <div class="meta">Last Updated: 2024-01-01 10:00:00</div>
                <small>Session ID: abc_123</small>
            </article>
        </body></html>
        """
        
        html_b = """
        <html><body>
            <article>
                <h1>Breaking News</h1>
                <p>The market is up.</p>
                <div class="meta">Last Updated: 2024-01-02 11:30:00</div>
                <small>Session ID: xyz_999</small>
            </article>
        </body></html>
        """
        
        res_a = self.fp.generate_fingerprint(html_a)
        res_b = self.fp.generate_fingerprint(html_b)
        
        self.assertEqual(res_a.version, "v2.0")
        self.assertEqual(res_a.hash, res_b.hash)
        logger.info("SUCCESS: Timestamps and Session IDs ignored.")

    def test_semantic_prioritization(self):
        logger.info("Testing Semantic Prioritization...")
        
        # Change in NAV should be IGNORED (based on our logic to skip nav)
        html_base = "<html><body><nav>Menu 1</nav><main>Real Content</main></body></html>"
        html_nav_change = "<html><body><nav>Menu 2</nav><main>Real Content</main></body></html>"
        html_main_change = "<html><body><nav>Menu 1</nav><main>New Content</main></body></html>"
        
        fp_base = self.fp.generate_fingerprint(html_base)
        fp_nav = self.fp.generate_fingerprint(html_nav_change)
        fp_main = self.fp.generate_fingerprint(html_main_change)
        
        # Base vs Nav Change -> Should be EQUAL (since nav is noise)
        self.assertEqual(fp_base.hash, fp_nav.hash)
        
        # Base vs Main Change -> Should be DIFFERENT
        self.assertNotEqual(fp_base.hash, fp_main.hash)
        
        logger.info("SUCCESS: Navigation changes ignored, Content changes detected.")

if __name__ == '__main__':
    unittest.main()
