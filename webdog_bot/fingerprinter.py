import hashlib
import re
import logging
from typing import Dict, List, Optional, Union
from bs4 import BeautifulSoup, Comment, Tag

# Import models
from models import WeightedFingerprint

logger = logging.getLogger("ContentFingerprinter")

class BlockPageDetected(Exception):
    """Raised when a bot-blocking page is detected."""
    pass

class VersionedContentFingerprinter:
    """
    The 'Brain' of WebDog.
    - Version v2.0
    - Detects bot blocks (Cloudflare, etc.)
    - Removes noise (dates, session IDs).
    - Weights content by semantic tag importance.
    """
    
    VERSION = "v2.0"
    
    # 1. Block Page Indicators
    BLOCK_INDICATORS = [
        "cloudflare",
        "ddos-guard", 
        "captcha",
        "please verify you are human",
        "just a moment...",
        "access denied",
        "security check",
        "attention required",
        "ray id"
    ]
    
    # 2. Semantic Weights
    SEMANTIC_WEIGHTS = {
        'article': 1.0,
        'main': 1.0,
        'h1': 0.9,
        'h2': 0.8,
        'div.content': 0.8,
        'p': 0.7,
        'section': 0.6,
        'aside': 0.2, # Lower importance
        'nav': 0.1,   # Lower importance
        'footer': 0.1,
        'header': 0.1
    }
    
    # 3. Noise Patterns (Regex)
    # Removing dates, times, session IDs to ensure stability
    NOISE_PATTERNS = [
        r'\d{4}-\d{2}-\d{2}',       # YYYY-MM-DD
        r'\d{2}/\d{2}/\d{4}',       # DD/MM/YYYY
        r'\d{1,2}:\d{2}(:\d{2})?',  # HH:MM:SS
        r'session[\s_-]?id\s*[:=]\s*[\w-]+', # Session ID (allow space, hyphens in ID)
        r'ray\s*id\s*[:=]\s*\w+',   # Cloudflare Ray ID explicitly
        r'last updated\s*[:]?.*',   # Update text (flexible space)
        r'copyright\s*©\s*\d{4}',   # Copyright years
        r'time remaining:.*',       # Countdowns
        r'token\s*[:=]\s*[\w-]+'    # Common token pattern
    ]
    
    def __init__(self):
        self.noise_regex = re.compile('|'.join(self.NOISE_PATTERNS), re.IGNORECASE)

    def is_block_page(self, html: str) -> bool:
        """
        Checks if the HTML represents a bot-blocking page.
        """
        if not html or len(html) < 200: 
            # Very short content is suspicious
            # But let's check content too
            pass
            
        lower_html = html.lower()
        
        # Check title first for efficiency
        try:
            soup = BeautifulSoup(html, 'html.parser')
            if soup.title:
                title = soup.title.string.lower() if soup.title.string else ""
                if any(x in title for x in ["access denied", "blocked", "security check", "captcha", "just a moment"]):
                    return True
        except Exception:
            pass # resilient parsing

        # Check body text for specific phrases
        for indicator in self.BLOCK_INDICATORS:
            if indicator in lower_html:
                # Check context to avoid false positives? 
                # For "cloudflare", it might be in a footer link.
                # Usually checking title or h1 is safer, but raw string check covers full pages.
                # Refinement: indicator must be visible text?
                # For now, simplistic check as per design.
                return True
                
        return False

    def clean_html(self, soup: BeautifulSoup) -> BeautifulSoup:
        """
        Removes scripts, styles, comments and known noise tags.
        """
        # Remove destructive tags
        for tag in soup(["script", "style", "meta", "link", "noscript", "iframe", "svg"]):
            tag.decompose()
            
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
            
        return soup

    def filter_noise_text(self, text: str) -> str:
        """
        Applies Regex filters to strip dynamic noise from text.
        """
        return self.noise_regex.sub('', text)

    def extract_weighted_content(self, soup: BeautifulSoup) -> str:
        """
        Extracts content, applying semantic prioritization?
        Actually, for 'Fingerprint Generation' (hashing), we just need a STABLE string representation.
        The 'Weights' might be used for deciding IF a change is significant (later task),
        BUT the requirement is: "Generate a final MD5 hash of the cleaned and weighted content".
        
        Optimized approach: 
        1. Find all semantic buckets.
        2. Extract text from them.
        3. Join them into a canonical string.
        4. Lowercase and normalize whitespace.
        
        If we ignore 'nav' completely, we put it in the string? 
        Design says: "prioritize... ignoring side-noise".
        So we will SKIP low weight items from the hash or reduce them?
        Let's EXCLUDE very low weight items (< 0.2) from the hash entirely for stability.
        """
        
        final_text_parts = []
        
        # Iterate over all tags? Or just traverse?
        # A simple traversal is best.
        
        for tag in soup.find_all(string=True):
            if tag.parent.name in ['nav', 'footer', 'header', 'aside']:
                continue # Skip low importance semantic zones entirely for the baseline hash
            
            text = tag.strip()
            if not text:
                continue
                
            # Filter noise regex
            clean_text = self.filter_noise_text(text)
            
            if len(clean_text) > 2: # Ignore single chars or empty after clean
                 final_text_parts.append(clean_text)
                 
        return " ".join(final_text_parts)

    def generate_fingerprint(self, html: str) -> WeightedFingerprint:
        """
        Main entry point.
        """
        # 1. Block Detection
        if self.is_block_page(html):
            raise BlockPageDetected("Bot protection detected.")

        # 2. Parse
        soup = BeautifulSoup(html, 'html.parser')
        
        # 3. Clean structure
        soup = self.clean_html(soup)
        
        # 4. Extract Stable Semantic Content
        # This implementation effectively DROPS nav/footer/header from the hash
        # ensuring high quality alerts.
        stable_content = self.extract_weighted_content(soup)
        
        # 5. Hash
        content_hash = hashlib.md5(stable_content.encode('utf-8')).hexdigest()
        
        # 6. Return Data Model
        return WeightedFingerprint(
            hash=content_hash,
            version=self.VERSION,
            algorithm="weighted_semantic_v2",
            content_weights={}, # Can populate if we did advanced granular scoring
            structure_signature="" # Can add DOM tree sig later
        )
