import logging
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict

# Telegram Imports
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Professional Components
from database import AtomicDatabaseManager, InsufficientStorageError
from request_manager import GlobalRequestManager
from fingerprinter import VersionedContentFingerprinter, BlockPageDetected
from similarity import SimilarityEngine
from models import Monitor, WeightedFingerprint, ChangeType, UserData

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
logger = logging.getLogger("WebDogController")

# --- Global Managers ---
# Instantiated once for the lifecycle of the bot
db_manager = AtomicDatabaseManager()
request_manager = GlobalRequestManager()
fingerprinter = VersionedContentFingerprinter()
similarity_engine = SimilarityEngine()

# --- Helpers ---

async def get_or_create_user_data(chat_id: str) -> UserData:
    """Helper to get user data from DB or create fresh."""
    all_data = await db_manager.load_all_monitors()
    if chat_id not in all_data:
        return UserData()
    return all_data[chat_id]

# --- Bot Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Simple Hello World command."""
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"Hello {user_name}! WebDog Professional is online.\n"
        "Commands:\n"
        "/watch <url> - Add a site to watch\n"
        "/unwatch <url> - Stop watching a site\n"
        "/list - See all watched sites"
    )

async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: /watch <url>
    Adds a website to the user's watch list using the new architecture.
    """
    chat_id = str(update.effective_chat.id)
    
    if not context.args:
        await update.message.reply_text("Hey, you forgot the URL! Try: /watch google.com")
        return

    url = context.args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    msg = await update.message.reply_text(f"🔍 Checking {url}... hang tight.")

    try:
        # 1. Fetch using Global Request Manager (Deduplicated & Timeout protected)
        result = await request_manager.fetch(url)
        
        if result.error or not result.content:
            await context.bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg.message_id, 
                text=f"❌ Oops, couldn't access {url}.\nErr: {result.error}"
            )
            return

        # 2. Fingerprint using the Brain
        fingerprint = fingerprinter.generate_fingerprint(result.content)
        
        # 3. Update Database (Atomic)
        # Load current state
        all_data = await db_manager.load_all_monitors()
        user_data = all_data.get(chat_id, UserData())
        
        # Check duplicates
        existing_monitor = next((m for m in user_data.monitors if m.url == url), None)
        
        if existing_monitor:
            existing_monitor.fingerprint = fingerprint
            # Reset metadata for re-watch? Or keep history?
            # Let's update check time
            existing_monitor.metadata.last_check = fingerprint.version # Using version placeholder or timestamp?
            # Creating new monitor is cleaner for "Watch" command to reset state
            user_data.monitors = [m for m in user_data.monitors if m.url != url]
            
        # Create new Monitor
        new_monitor = Monitor(url=url, fingerprint=fingerprint)
        user_data.monitors.append(new_monitor)
        
        # Save back
        all_data[chat_id] = user_data
        await db_manager.atomic_write(all_data)
        
        await context.bot.edit_message_text(
            chat_id=chat_id, 
            message_id=msg.message_id, 
            text=f"✅ Done! WebDog is watching {url}.\nBaseline set!"
        )

    except BlockPageDetected:
         await context.bot.edit_message_text(
            chat_id=chat_id, 
            message_id=msg.message_id, 
            text=f"🛑 access denied by Bot Protection (Cloudflare/Captcha) on {url}."
        )
    except Exception as e:
        logger.error(f"Watch failed: {e}", exc_info=True)
        await context.bot.edit_message_text(
            chat_id=chat_id, 
            message_id=msg.message_id, 
            text=f"❌ Internal Error: {e}"
        )

async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: /unwatch <url>
    """
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text("Which URL? Try: /unwatch google.com")
        return

    target_url = context.args[0]
    # Simple normalization for matching
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    # DB Op
    all_data = await db_manager.load_all_monitors()
    user_data = all_data.get(chat_id)
    
    if not user_data:
        await update.message.reply_text("You aren't watching any sites.")
        return

    initial_count = len(user_data.monitors)
    # Filter out
    # Note: This is an exact string match. A production bot might normalize URLs strictly.
    user_data.monitors = [m for m in user_data.monitors if m.url != target_url]
    
    if len(user_data.monitors) < initial_count:
        all_data[chat_id] = user_data
        await db_manager.atomic_write(all_data)
        await update.message.reply_text(f"🗑️ Stopped watching {target_url}.")
    else:
        await update.message.reply_text(f"❓ You aren't watching {target_url}.")

async def list_monitors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: /list
    """
    chat_id = str(update.effective_chat.id)
    
    all_data = await db_manager.load_all_monitors()
    user_data = all_data.get(chat_id)
    
    if not user_data or not user_data.monitors:
        await update.message.reply_text("You aren't watching any sites yet.")
        return
        
    text = "<b>👀 Currently Watching:</b>\n"
    for m in user_data.monitors:
        text += f"• {m.url}\n"
        
    await update.message.reply_text(text, parse_mode="HTML")

# --- Background Jobs ---

async def patrol_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Master Patrol Loop:
    - Iterates all monitors.
    - Fetches via Manager.
    - Fingerprints via Brain.
    - Detects Similarity.
    - Updates Metadata.
    """
    # 1. Load State (Snapshot)
    # Note: In a massive scale system, we wouldn't load ALL at once every 60s.
    # We would use a cursor or generator. For <1000 sites, this is fine.
    all_data = await db_manager.load_all_monitors()
    
    if not all_data:
        return

    updates_needed = False
    
    # 2. Iterate
    for chat_id, user_data in all_data.items():
        for monitor in user_data.monitors:
            url = monitor.url
            # Update check count metadata
            monitor.metadata.check_count += 1
            
            logging.info(f"Patrolling {url} for {chat_id}...")
            
            try:
                # A. Fetch
                result = await request_manager.fetch(url)
                
                if result.error or not result.content:
                    monitor.metadata.failure_count += 1
                    logging.warning(f"Patrol failed for {url}: {result.error}")
                    continue

                # B. Fingerprint
                new_print = fingerprinter.generate_fingerprint(result.content)
                
                # C. Compare
                if monitor.fingerprint:
                    old_print = monitor.fingerprint
                    
                    # If hash matches exactly, skip expensive similarity check
                    if new_print.hash == old_print.hash:
                         monitor.metadata.last_check = result.timestamp # Or ISO string
                         continue
                         
                    # Hash Changed -> Run Similarity Engine
                    metrics = similarity_engine.compare_content(
                       old_text="", # We don't store text, so we assume "Previous" is unknown content for text metric? 
                       # Wait, if we don't store the content, we can't do Jaccard/Diff on OLD content!
                       # The design requires store Forensics?
                       # Or are we just comparing Hash? 
                       # "Use the SimilarityEngine to compare the old_fingerprint with the new_fingerprint"
                       # SimilarityEngine inputs are Strings (content). 
                       # Models store `structure_signature`?
                       # Issue: We cannot compute Jaccard without the old text.
                       # Design assumption: We might fetch the latest snapshot? Or we only use Hash for now?
                       # Task 5 "compare_content(old_text, ...)" requires text.
                       # Implication: We need to store the "Last Known Good Content" or "Baseline".
                       # But `Monitor` only stores `fingerprint` (hash) and `forensic_snapshots`.
                       # Forensics might have the content (compressed).
                       
                       # FIX: Get content from latest forensic snapshot if available, or just Alert if basic hash mismatch?
                       # For "Professional" level, we should decompress the last snapshot to compare.
                       # If no snapshot, it's a change or baseline reset.
                       
                       # Let's try to retrieve old content from snapshots.
                       # If no snapshots, we can't do deep diff, so we default to "Unmeasured Change".
                       new_text = result.content # Raw HTML
                       old_text = ""
                       old_html = ""
                       
                       if monitor.forensic_snapshots:
                           last_snap = monitor.forensic_snapshots[-1]
                           try:
                               old_content = last_snap.decompress()
                               old_text = old_content
                               old_html = old_content
                           except:
                               pass
                               
                       if old_text:
                            # Run Similarity
                            sim_metrics = similarity_engine.compare_content(old_text, new_text, old_html, new_text)
                            score = sim_metrics.final_score
                            
                            # D. Alert Logic
                            threshold = user_data.user_config.similarity_threshold
                            if similarity_engine.should_alert(score, threshold):
                                logging.info(f"CHANGE DETECTED for {url}. Score: {score}")
                                
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=(
                                        f"⚠️ <b>Change Detected: {url}</b>\n"
                                        f"Similarity: {int(score*100)}%\n"
                                        f"Type: {similarity_engine.classify_change(score).value}"
                                    ),
                                    parse_mode="HTML"
                                )
                                
                                # Update Baseline
                                monitor.fingerprint = new_print
                                updates_needed = True
                                
                                # Create Snapshot? (Ideally yes, for history/next diff)
                                # Only if change is significant? Or always on new baseline?
                                # Usually on Alert.
                            else:
                                logging.info(f"Change ignored (Score {score} >= {threshold})")
                                # Silent update of baseline? Or keep old baseline?
                                # Usually keep old baseline to detect "drift" or update?
                                # If we update, we lose the "original" reference. 
                                # If we don't, we compare against really old version next time.
                                # "Silent Baseline Reset" logic usually implies update.
                                monitor.fingerprint = new_print
                                updates_needed = True

                       else:
                            # No history to compare, but hash changed. 
                            # Baseline invalid or legacy?
                            # Just Alert generic or Silent update?
                            # First time we see V2, it might differ from "Legacy".
                            # Safety: Alert.
                            logging.info("Hash mismatch without history. Alerting.")
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"⚠️ <b>Change Detected: {url}</b>\n(No history for detailed comparison)",
                                parse_mode="HTML"
                            )
                            monitor.fingerprint = new_print
                            updates_needed = True

                else:
                    # First run?
                    monitor.fingerprint = new_print
                    updates_needed = True

            except BlockPageDetected:
                logging.warning(f"Block page on {url} during patrol.")
            except Exception as e:
                logging.error(f"Error patrolling {url}: {e}")
    
    # E. Batch Save
    if updates_needed:
        await db_manager.atomic_write(all_data)


# --- Main Execution ---

def main() -> None:
    """Entry point."""
    print("Starting WebDog Professional...")
    
    application = Application.builder().token(TOKEN).build()
    job_queue = application.job_queue

    # Register commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("watch", watch))
    application.add_handler(CommandHandler("unwatch", unwatch))
    application.add_handler(CommandHandler("list", list_monitors))
    
    # Schedule the patrol job to run every 60 seconds
    print("Starting Professional Patrol Job...")
    job_queue.run_repeating(patrol_job, interval=60, first=10)

    print("Bot is polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
