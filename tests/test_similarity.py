import unittest
import logging
import sys
from pathlib import Path

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from similarity import SimilarityEngine
from models import ChangeType

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SimilarityTest")

class TestSimilarityEngine(unittest.TestCase):
    
    def setUp(self):
        self.engine = SimilarityEngine()
        
    def test_case_1_ui_tweak(self):
        logger.info("Test Case 1: UI Tweak (High Similarity)")
        
        # Longer text to ensure statistical significance for Jaccard
        text1 = (
            "The quick brown fox jumps over the lazy dog. "
            "This pangram contains every letter of the English alphabet. "
            "It is widely used for display of fonts and testing typewriters."
        )
        text2 = (
            "The quick brown fox leaps over the lazy dog. "
            "This pangram contains every letter of the English alphabet. "
            "It is widely used for display of fonts and testing typewriters."
        )
        
        # HTML structure is identical
        html1 = "<div><p>Content</p></div>"
        html2 = "<div><p>Content</p></div>"
        
        metrics = self.engine.compare_content(text1, text2, html1, html2)
        change_type = self.engine.classify_change(metrics.final_score)
        
        logger.info(f"UI Tweak Metrics: {metrics}")
        
        # Expect very high score (> 0.95 for UI Tweak)
        self.assertGreater(metrics.final_score, 0.95)
        self.assertEqual(change_type, ChangeType.UI_TWEAK)
        logger.info("SUCCESS: UI Tweak correctly classified.")

    def test_case_2_major_overhaul(self):
        logger.info("Test Case 2: Major Overhaul (Low Similarity)")
        
        text1 = "Python is a programming language suitable for data science."
        text2 = "To bake a cake, verify you have flour and sugar."
        
        html1 = "<article><h1>Python</h1><p>Code here.</p></article>"
        html2 = "<section><h2>Recipe</h2><ul><li>Flour</li></ul></section>"
        
        metrics = self.engine.compare_content(text1, text2, html1, html2)
        change_type = self.engine.classify_change(metrics.final_score)
        
        logger.info(f"Major Overhaul Metrics: {metrics}")
        
        # Expect low score
        self.assertLess(metrics.final_score, 0.50)
        self.assertEqual(change_type, ChangeType.MAJOR_OVERHAUL)
        logger.info("SUCCESS: Major Overhaul correctly classified.")

    def test_case_3_threshold_logic(self):
        logger.info("Test Case 3: Threshold Logic")
        
        # Scenario: Score is 0.90 (High similarity, small change)
        # User Threshold: 0.85 
        # Logic: If Similarity (0.90) < Threshold (0.85) -> FALSE (Do not alert)
        # Logic: If Similarity (0.80) < Threshold (0.85) -> TRUE (Alert)
        
        # We simulate a partial change
        text1 = "Hello world this is a test page."
        text2 = "Hello world this is a test site." 
        # Jaccard: 6 common / 8 total unique (page, site overlap?)
        # "Hello world this is a test page" -> 7 words
        # "Hello world this is a test site" -> 7 words
        # Common: Hello, world, this, is, a, test (6). Union: 8 (page, site diff). 6/8 = 0.75
        # Levenshtein: high
        # Semantic: 1.0
        
        html1 = "<p>Msg</p>"
        html2 = "<p>Msg</p>"
        
        metrics = self.engine.compare_content(text1, text2, html1, html2)
        logger.info(f"Threshold Test Metrics: {metrics.final_score}")
        
        # Let's say score comes out around 0.88-0.92
        
        # 1. User is very sensitive (Threshold 0.95) -> Wants to know about ANY change
        # Score 0.90 < 0.95 -> True (Alert)
        self.assertTrue(self.engine.should_alert(metrics.final_score, 0.95))
        
        # 2. User is chill (Threshold 0.85) -> Only wants big changes
        # Score 0.90 < 0.85 -> False (No Alert)
        # Wait: 0.90 is NOT less than 0.85. Correct.
        self.assertFalse(self.engine.should_alert(metrics.final_score, 0.85))
        
        logger.info("SUCCESS: Threshold logic verified.")

if __name__ == '__main__':
    unittest.main()
