import logging
import hashlib
import aiohttp
from bs4 import BeautifulSoup

# --- Helper Functions ---

async def get_website_fingerprint(url: str) -> str:
    """
    Downloads the page, strips out dynamic junk (scripts/styles),
    and returns a unique hash (MD5) of the text content.
    """
    try:
        # Use aiohttp for async requests (faster than requests library)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.warning(f"Failed to fetch {url} - Status: {response.status}")
                    return None
                
                html = await response.text()
                
                # Parse HTML to get just the text
                soup = BeautifulSoup(html, "html.parser")
                
                # Kill all script and style elements
                # We don't care about CSS or JS changes, only content
                for rubbish in soup(["script", "style", "meta"]):
                    rubbish.decompose()
                
                # Get clean text
                text = soup.get_text(separator=" ", strip=True)
                
                # Generate a hash so we don't have to store the whole page text
                return hashlib.md5(text.encode("utf-8")).hexdigest()
                
    except Exception as e:
        logging.error(f"Something went wrong while fingerprinting {url}: {e}")
        return None
