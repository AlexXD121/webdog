import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from monitor import get_website_fingerprint
from database import load_all_monitors, save_monitor

# --- Configuration & Setup ---

# Load environment variables
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Grab the token
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError(f"CRITICAL: No TELEGRAM_TOKEN found! checked path: {env_path}")

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Global memory
# Load from database on startup
monitors = load_all_monitors()
logging.info(f"Loaded {len(monitors)} monitors from database.")

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
    
    if not context.args:
        await update.message.reply_text("Hey, you forgot the URL! Try: /watch google.com")
        return

    url = context.args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    msg = await update.message.reply_text(f"🔍 Checking {url}... hang tight.")

    fingerprint = await get_website_fingerprint(url)
    
    if fingerprint:
        # Save to memory
        monitors[str(chat_id)] = {"url": url, "hash": fingerprint}
        
        # Save to database
        save_monitor(chat_id, url, fingerprint)
        
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

# --- Background Jobs ---

async def patrol_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Background task that runs every 60 seconds.
    Checks all monitored websites for changes.
    """
    if not monitors:
        return

    # Iterate over a copy of items to avoid issues if dict changes during iteration
    for chat_id, data in list(monitors.items()):
        url = data["url"]
        old_hash = data["hash"]
        
        logging.info(f"Patrolling {url} for chat_id {chat_id}...")
        
        new_hash = await get_website_fingerprint(url)
        
        if new_hash is None:
            # Site might be down or unreachable
            logging.warning(f"Could not reach {url} during patrol.")
            continue
            
        if new_hash != old_hash:
            logging.info(f"CHANGE DETECTED for {url}!")
            
            # Alert the user
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ <b>ALERT: Change Detected!</b>\n\nWebDog noticed a change on {url}.\nCheck it out before the client complains!",
                parse_mode="HTML"
            )
            
            # Update the hash so we don't spam alerts (only alert on NEW changes)
            monitors[str(chat_id)]["hash"] = new_hash
            
            # Update database
            save_monitor(chat_id, url, new_hash)

# --- Main Execution ---

def main() -> None:
    """Entry point."""
    print("Starting WebDog Bot...")
    
    application = Application.builder().token(TOKEN).build()
    job_queue = application.job_queue

    # Register commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("watch", watch))
    
    # Schedule the patrol job to run every 60 seconds
    print("Starting Patrol Job (Every 60s)...")
    job_queue.run_repeating(patrol_job, interval=60, first=10)

    print("Bot is polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
