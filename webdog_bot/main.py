import logging
import hashlib
import os
import aiohttp
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Configuration & Setup ---

# Load environment variables
# We need to explicitly point to the .env file in the parent dir
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Grab the token
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    # Stop everything if we don't have a token
    raise ValueError(f"CRITICAL: No TELEGRAM_TOKEN found! checked path: {env_path}")

# Set up logging for debugging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Global memory (simpler than a DB for now)
monitors = {}

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

# --- Bot Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Simple Hello World command."""
    user_name = update.effective_user.first_name
    await update.message.reply_text(f"Hello {user_name}! WebDog is online and ready to watch.")

async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: /watch <url>
    Sets the baseline for a website.
    """
    chat_id = update.effective_chat.id
    
    # Check if user actually sent a URL
    if not context.args:
        await update.message.reply_text("Hey, you forgot the URL! Try: /watch google.com")
        return

    url = context.args[0]
    
    # Quick fix if user forgets http://
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Notify user we are working on it
    msg = await update.message.reply_text(f"🔍 Checking {url}... hang tight.")

    # Get the initial baseline
    fingerprint = await get_website_fingerprint(url)
    
    if fingerprint:
        # Save to memory (TODO: move this to a real database later)
        monitors[chat_id] = {"url": url, "hash": fingerprint}
        await context.bot.edit_message_text(
            chat_id=chat_id, 
            message_id=msg.message_id, 
            text=f"✅ Done! WebDog is now watching {url}.\nI'll let you know if anything changes."
        )
    else:
        await context.bot.edit_message_text(
            chat_id=chat_id, 
            message_id=msg.message_id, 
            text=f"❌ Oops, couldn't access {url}. Is the site down?"
        )

# --- Main Execution ---

def main() -> None:
    """Entry point."""
    print("Starting WebDog Bot...")
    
    application = Application.builder().token(TOKEN).build()

    # Register commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("watch", watch))

    print("Bot is polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
