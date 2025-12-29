import difflib
import logging
from typing import Set, List, Dict
from bs4 import BeautifulSoup
from models import SimilarityMetrics, ChangeType, WeightedFingerprint

logger = logging.getLogger("SimilarityEngine")

class SimilarityEngine:
    """
    Multi-algorithm content comparison engine.
    - Jaccard: Word-level set overlap.
    - Levenshtein: Character-level edit distance.
    - Semantic: HTML structure tag counting comparison.
    """
    
    # Weights defined in design
    WEIGHT_JACCARD = 0.4
    WEIGHT_LEVENSHTEIN = 0.4
    WEIGHT_SEMANTIC = 0.2
    
    # Thresholds for classification
    THRESHOLD_UI_TWEAK = 0.95
    THRESHOLD_CONTENT_UPDATE = 0.70

    def compute_jaccard(self, text1: str, text2: str) -> float:
        """
        Calculates Jaccard similarity index (intersection over union) of words.
        """
        set1 = set(text1.lower().split())
        set2 = set(text2.lower().split())
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        if union == 0:
            return 1.0 # Both empty -> identical
            
        return intersection / union

    def compute_levenshtein(self, text1: str, text2: str) -> float:
        """
        Calculates Levenshtein ratio (similarity) between 0.0 and 1.0.
        Uses difflib.SequenceMatcher for efficient calculation.
        """
        return difflib.SequenceMatcher(None, text1, text2).ratio()

    def compute_semantic_structure(self, html1: str, html2: str) -> float:
        """
        Compares the 'shape' of the document by counting tag frequencies.
        Returns a similarity score based on how close the tag counts are.
        """
        def get_structure_map(html: str) -> Dict[str, int]:
            soup = BeautifulSoup(html, 'html.parser')
            counts = {}
            # We care about structural tags
            tags_of_interest = ['div', 'p', 'span', 'h1', 'h2', 'h3', 'table', 'ul', 'li', 'article', 'section', 'nav']
            for tag in soup.find_all(tags_of_interest):
                counts[tag.name] = counts.get(tag.name, 0) + 1
            return counts
            
        map1 = get_structure_map(html1)
        map2 = get_structure_map(html2)
        
        all_tags = set(map1.keys()).union(set(map2.keys()))
        if not all_tags:
            return 1.0
            
        total_diff = 0
        total_tags = 0
        
        for tag in all_tags:
            c1 = map1.get(tag, 0)
            c2 = map2.get(tag, 0)
            # Normalized difference per tag type?
            # Simple approach: sum of absolute differences vs sum of total tags
            total_diff += abs(c1 - c2)
            total_tags += (c1 + c2)
            
        if total_tags == 0:
            return 1.0
            
        # Similarity = 1 - (diff / total)
        # Using max possible diff would be total_tags (if completely disjoint sets of tags?)
        # Let's use 1 - diff / total_tags
        return 1.0 - (total_diff / total_tags)

    def compare_content(self, old_text: str, new_text: str, old_html: str, new_html: str) -> SimilarityMetrics:
        """
        Orchestrates the multi-algorithm comparison.
        """
        jaccard = self.compute_jaccard(old_text, new_text)
        levenshtein = self.compute_levenshtein(old_text, new_text)
        semantic = self.compute_semantic_structure(old_html, new_html)
        
        final_score = (
            (jaccard * self.WEIGHT_JACCARD) +
            (levenshtein * self.WEIGHT_LEVENSHTEIN) +
            (semantic * self.WEIGHT_SEMANTIC)
        )
        
        return SimilarityMetrics(
            jaccard=round(jaccard, 4),
            levenshtein=round(levenshtein, 4),
            semantic=round(semantic, 4),
            final_score=round(final_score, 4)
        )

    def classify_change(self, score: float) -> ChangeType:
        """
        Determines the magnitude of the change.
        """
        if score >= self.THRESHOLD_UI_TWEAK:
            return ChangeType.UI_TWEAK
        elif score >= self.THRESHOLD_CONTENT_UPDATE:
            return ChangeType.CONTENT_UPDATE
        else:
            return ChangeType.MAJOR_OVERHAUL

    def should_alert(self, score: float, user_threshold: float) -> bool:
        """
        Decides if an alert is warranted based on user preference.
        Note: The score is 'similarity'. 
        If similarity < threshold, it means 'Changed Enough' -> Alert.
        e.g. User Threshold 0.85 (85% similar).
        If Score is 0.90 (90% similar) -> No Alert (Too minor).
        If Score is 0.80 (80% similar) -> Alert.
        """
        return score < user_threshold

    def calculate_similarity(self, fp1: WeightedFingerprint, fp2: WeightedFingerprint) -> SimilarityMetrics:
        """
        Calculates similarity between two fingerprints based on their content weights (structural tags).
        Since we don't have the original text, we rely on structural similarity.
        """
        if fp1.hash == fp2.hash:
            return SimilarityMetrics(final_score=1.0, semantic=1.0)
            
        # Compare content_weights (Tag Counts)
        w1 = fp1.content_weights
        w2 = fp2.content_weights
        
        all_keys = set(w1.keys()).union(set(w2.keys()))
        if not all_keys:
            return SimilarityMetrics(final_score=1.0) # Both empty = same
            
        total_diff = 0.0
        total_count = 0.0
        
        for k in all_keys:
            v1 = w1.get(k, 0.0)
            v2 = w2.get(k, 0.0)
            total_diff += abs(v1 - v2)
            total_count += v1 + v2
            
        semantic_score = 1.0
        if total_count > 0:
            semantic_score = 1.0 - (total_diff / total_count)
            
        # Since we only have structural data here, return it as final score too?
        # Or penalize because hash is different?
        # If hashes are different but structure is identical (1.0), it means CONTENT text changed.
        # But we don't have text. So we must output a score < 1.0 to indicate change.
        # If semantic_score is 1.0 but hashes differ, we should return e.g. 0.9 (UI Tweak?) or 0.8?
        
        final = semantic_score
        if final >= 1.0 and fp1.hash != fp2.hash:
            final = 0.80 # Force drop to reflect content change without structural change (Text update)
            
        return SimilarityMetrics(
            semantic=round(semantic_score, 4),
            final_score=round(final, 4)
        )
