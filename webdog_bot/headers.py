import random
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class BrowserProfile:
    user_agent: str
    sec_ch_ua: str
    sec_ch_ua_platform: str
    sec_ch_ua_mobile: str = "?0"

# Strict, Coherent Profiles
PROFILES = [
    # Chrome 120 on Windows 10
    BrowserProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        sec_ch_ua='"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        sec_ch_ua_platform='"Windows"'
    ),
    # Chrome 119 on Windows 10
    BrowserProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        sec_ch_ua='"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
        sec_ch_ua_platform='"Windows"'
    ),
    # Chrome 120 on macOS
    BrowserProfile(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        sec_ch_ua='"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        sec_ch_ua_platform='"macOS"'
    ),
     # Edge 120 on Windows
    BrowserProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        sec_ch_ua='"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"',
        sec_ch_ua_platform='"Windows"'
    ),
    # Firefox 120 on Windows (No Hints usually, but let's provide consistent headers)
    # Firefox doesn't support Sec-CH-UA yet in same way, so we omit or put empty?
    # Actually for "Stealth", omitting hints for Firefox is CORRECT.
    # But to keep struct simple, we might use empty strings and filter later?
    # Or just use Chrome-like profiles for simplicity since they are most standard?
    # Let's stick to Chrome/Edge for robust Client Hints support which sites check most.
]

REFERERS = [
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    None # Direct traffic
]

def get_random_headers() -> Dict[str, str]:
    """
    Returns a dictionary of headers mimicking a real browser with synchronized hints.
    """
    profile = random.choice(PROFILES)
    referer = random.choice(REFERERS)
    
    headers = {
        "User-Agent": profile.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site" if referer else "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        # Client Hints
        "Sec-Ch-Ua": profile.sec_ch_ua,
        "Sec-Ch-Ua-Mobile": profile.sec_ch_ua_mobile,
        "Sec-Ch-Ua-Platform": profile.sec_ch_ua_platform
    }
    
    if referer:
        headers["Referer"] = referer
        
    return headers

def get_random_profile() -> BrowserProfile:
    """Returns the raw profile object if needed."""
    return random.choice(PROFILES)
