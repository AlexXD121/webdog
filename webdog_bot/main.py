import logging
import os
import asyncio
import signal
import html
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Optional
import copy

# Telegram Imports
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# Professional Components
from database import AtomicDatabaseManager, InsufficientStorageError
from request_manager import GlobalRequestManager
from fingerprinter import VersionedContentFingerprinter, BlockPageDetected
from similarity import SimilarityEngine
from models import Monitor, WeightedFingerprint, ChangeType, UserData
from logger import setup_logging
from metrics import get_metrics_tracker
from governor import get_governor
from history_manager import HistoryManager

# Interface
import interface

# --- Configuration & Setup ---

# Load environment variables
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError(f"CRITICAL: No TELEGRAM_TOKEN found! checked path: {env_path}")

setup_logging("webdog.log")
logger = logging.getLogger("WebDogBot")

# --- Health Check Server (Cloud Compatibility) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"WebDog is running")
    
    def log_message(self, format, *args):
        pass # Silence console spam

def start_health_check():
    try:
        port = int(os.environ.get("PORT", 8000))
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Health Check Server listening on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health Check Server Failed to Start: {e}")

class WebDogBot:
    """
    Central Controller for WebDog Professional.
    Manages lifecycle, integration, and high-performance scheduling.
    """
    
    def __init__(self):
        self.db_manager = AtomicDatabaseManager()
        self.request_manager = GlobalRequestManager()
        self.fingerprinter = VersionedContentFingerprinter()
        self.similarity_engine = SimilarityEngine()
        self.application: Optional[Application] = None
        self.is_running = False
        
    async def startup(self):
        """System Startup & Health Checks."""
        logger.info("Initializing WebDog Professional...")
        
        # 1. Check DB
        if not self.db_manager.db_path.exists():
            logger.warning("Database not found. Creating new...")
            
        # 2. Check Disk
        if not self.db_manager._check_disk_space():
             logger.critical("Insufficient Disk Space! Monitoring might fail.")
        
        # 3. Check Metrics
        status = get_metrics_tracker().get_system_status()
        logger.info(f"System Status at Boot: {status}")
        
    async def shutdown(self):
        """Graceful Shutdown."""
        logger.info("Shutting down WebDog...")
        self.is_running = False
        
        # 1. Close Client
        await self.request_manager.close()
        
        # 2. Stop Throttler
        await get_governor().telegram_throttler.stop()
        
        # 3. Drain DB Queue? 
        # Ideally wait for self.db_manager.write_queue.join(), but it might be infinite loop worker.
        # We rely on asyncio clean cancellation usually.
        logger.info("Shutdown complete.")

    async def run_bot(self):
        """Main Loop."""
        # Start Background Health Check (Daemon)
        threading.Thread(target=start_health_check, daemon=True).start()

        await self.startup()
        self.is_running = True
        
        self.application = Application.builder().token(TOKEN).build()
        job_queue = self.application.job_queue

        # Register Handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("watch", self.cmd_watch))
        self.application.add_handler(CommandHandler("unwatch", self.cmd_unwatch))
        self.application.add_handler(CommandHandler("list", self.cmd_list))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Schedule Patrol
        # Memory Optimization: We use a job that loads data On-Demand
        job_queue.run_repeating(self.patrol_job, interval=60, first=10)
        job_queue.run_repeating(self.cleanup_job, interval=3600, first=60)
        
        # Signal Handling (Manual since Application.run_polling handles generic ones, 
        # but we want custom shutdown logic).
        # Actually run_polling uses a blocking loop. 
        # We can register post_shutdown hook in Application? 
        # Or wrap in try/finally block.
        
        try:
            logger.info("Start Polling...")
            await self.application.initialize()
            await self.application.start()
            
            # Start Throttler
            await get_governor().telegram_throttler.start()
            
            await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            
            # Keep running until signal
            # We construct a future that never completes
            # Or wait for stop signal.
            stop_event = asyncio.Event()
            
            def signal_handler():
                stop_event.set()
                
            # Windows signal handling limitations in asyncio...
            # Python-telegram-bot run_polling() is easier for standard use.
            # But "Strict Graceful Shutdown" usually implies we handle it.
            # For simplicity in this environment, let's use the provided `run_polling` logic block from typical examples
            # but inserted into our class structure.
            # BUT `run_polling` blocks. 
            # We already started updater. So we just wait.
            
            while not stop_event.is_set():
                await asyncio.sleep(1)
                # Here we could check for Governor congestion or log stats
                
        except (KeyboardInterrupt, asyncio.CancelledError):
             pass
        except Exception as e:
             logger.critical(f"Bot Crash: {e}", exc_info=True)
        finally:
             await self.application.updater.stop()
             await self.application.stop()
             await self.application.shutdown()
             await self.shutdown()

    # --- Commands ---
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"🐶 <b>WebDog Professional</b>\nReady to guard.",
            reply_markup=interface.get_main_menu_keyboard(),
            parse_mode="HTML"
        )
        
    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if not context.args:
            await update.message.reply_text("Usage: /watch <url>")
            return
        url = context.args[0]
        if not url.startswith(("http", "https")): url = "https://" + url
        
        msg = await update.message.reply_text("🔍 Analyzing...")
        
        try:
            # 1. Fetch
            result = await self.request_manager.fetch(url)
            if result.error or not result.content:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=f"❌ Failed: {result.error}")
                return
            
            # 2. Fingerprint
            fp = self.fingerprinter.generate_fingerprint(result.content)
            
            # 3. Atomic Save
            monitor = Monitor(url=url, fingerprint=fp)
            
            all_data = await self.db_manager.load_all_monitors()
            user_data = all_data.get(chat_id, UserData())
            
            # Filter dupes
            user_data.monitors = [m for m in user_data.monitors if m.url != url]
            user_data.monitors.append(monitor)
            all_data[chat_id] = user_data
            
            await self.db_manager.atomic_write(all_data)
            
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=f"✅ Watching {url}")
            
        except Exception as e:
            logger.error(f"Watch failed: {e}")
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text="❌ Error adding site.")

    async def cmd_unwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if not context.args: return
        url = context.args[0]
        # logic duplication with delete_monitor_logic...
        await self.delete_monitor_logic(chat_id, url)
        await update.message.reply_text(f"Removed {url}")

    async def cmd_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.show_monitor_list(update, context, 0)

    # --- Core Logic ---
    
    async def patrol_job(self, context: ContextTypes.DEFAULT_TYPE):
        """
        JobBasedDataLoader Implementation.
        Iterates DB, identifying actionable tasks.
        """
        # 1. Load Data (Snapshot)
        # For Memory Optimization: efficient loading is Key.
        # But JSON db loads all into RAM.
        # True optimization requires SQLite or iterating file stream.
        # For now, we load all, but we act efficiently.
        all_data = await self.db_manager.load_all_monitors()
        updates_needed = False
        
        # 2. Governor Check
        if get_governor().is_congested:
             logger.warning("System Congested! Skipping patrol cycle.")
             return # Adaptive Backpressure
             
        for chat_id, user_data in all_data.items():
            for monitor in user_data.monitors:
                try:
                    # Resolve Config
                    config = monitor.config or user_data.user_config
                    
                    # Schedule Check
                    if monitor.metadata.snooze_until:
                        snooze = datetime.fromisoformat(monitor.metadata.snooze_until)
                        if datetime.now(timezone.utc) < snooze: continue
                        else: 
                            monitor.metadata.snooze_until = None
                            updates_needed = True
                            
                    if monitor.metadata.last_check:
                         last_ts = datetime.fromisoformat(monitor.metadata.last_check)
                         elapsed = (datetime.now(timezone.utc) - last_ts).total_seconds()
                         if elapsed < config.check_interval: continue
                    
                    # GO: Acquire Token
                    await get_governor().acquire_web_token()
                    
                    # Fetch
                    result = await self.request_manager.fetch(monitor.url)
                    monitor.metadata.check_count += 1
                    
                    # Smart 429 Handling
                    if result.status_code == 429:
                        monitor.metadata.rate_limit_count += 1
                        logger.warning(f"429 Too Many Requests for {monitor.url} (Count: {monitor.metadata.rate_limit_count})")
                        
                        if monitor.metadata.rate_limit_count >= 3:
                            # Send Notification
                            msg = (
                                f"⚠️ <b>Rate Limit Detected: {html.escape(monitor.url)}</b>\n"
                                f"Received 429 'Too Many Requests' 3 times in a row.\n"
                                f"Suggestion: Increase check interval in Settings."
                            )
                            try:
                                await get_governor().telegram_throttler.send_message(
                                    context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
                                )
                                # Reset count to avoid spamming, or maybe set to 0?
                                # Let's reset to 0 so we alert again if it persists for another 3 cycles.
                                monitor.metadata.rate_limit_count = 0 
                            except Exception as e:
                                logger.error(f"Failed to send 429 alert: {e}")
                        
                        updates_needed = True
                        continue # Skip processing
                    
                    # Reset 429 count on success (or other error) that isn't 429
                    monitor.metadata.rate_limit_count = 0
                    
                    if result.error or not result.content:
                        monitor.metadata.failure_count += 1
                        continue
                        
                    # Compare
                    new_fp = self.fingerprinter.generate_fingerprint(result.content)
                    monitor.metadata.last_check = datetime.now(timezone.utc).isoformat()
                    
                    if monitor.fingerprint and monitor.fingerprint.hash != new_fp.hash:
                         # Changed!
                         score = self.similarity_engine.calculate_similarity(monitor.fingerprint, new_fp).final_score
                         
                         if score < config.similarity_threshold:
                             # Alert
                             msg = interface.format_diff_message(
                                 monitor.url, score, "Change Detected", 
                                 "Full diff available in history." if config.include_diff else ""
                             )
                             kb = interface.get_alert_keyboard(monitor.url)
                             
                             # Throttle Send
                             await get_governor().telegram_throttler.send_message(
                                 context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=kb, parse_mode="HTML")
                             )
                             
                             HistoryManager.add_history_entry(monitor, "CHANGE", score, "Alerted")
                         else:
                             HistoryManager.add_history_entry(monitor, "MINOR", score, "Silent Update")
                             
                         monitor.fingerprint = new_fp
                         updates_needed = True

                    elif not monitor.fingerprint:
                        monitor.fingerprint = new_fp
                        updates_needed = True
                        
                except Exception as e:
                    logger.error(f"Patrol Error {monitor.url}: {e}")
                    monitor.metadata.failure_count += 1
        
        if updates_needed:
             try:
                 await self.db_manager.atomic_write(all_data)
             except Exception as e:
                 logger.critical(f"DB Write Failed: {e}")
                 # We don't crash, we just optimize to retry later or alert admin?
                 # ideally send alert to admin if configured.

    async def cleanup_job(self, context: ContextTypes.DEFAULT_TYPE):
        """Background task to clean up old exports."""
        await asyncio.to_thread(HistoryManager.cleanup_exports, 60)

    # --- UI Helpers (Similar to refactored main) ---
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        chat_id = str(update.effective_chat.id)
        
        # Navigation
        if data == "CMD_MENU":
            await query.edit_message_text("🐶 <b>Menu</b>", reply_markup=interface.get_main_menu_keyboard(), parse_mode="HTML")
        elif data.startswith("CMD_LIST_"):
            await self.show_monitor_list(update, context, int(data.split("_")[-1]), edit=True)
        elif data == "CMD_HEALTH":
            await self.show_health(update)
        elif data == "CMD_SETTINGS":
            # Global Settings
             all_data = await self.db_manager.load_all_monitors()
             ud = all_data.get(chat_id, UserData())
             await query.edit_message_text("⚙️ <b>Global Settings</b>", reply_markup=interface.get_settings_keyboard(ud.user_config, "GLOBAL"), parse_mode="HTML")
             
        # Config Actions
        elif data.startswith("SET_"):
            await self.handle_settings_action(update, data, chat_id)
            
        # Monitor Actions
        elif data.startswith("DETAILS_"):
            await self.show_monitor_details(update, data.replace("DETAILS_", ""))
        elif data.startswith("HISTORY_"):
            await self.show_history(update, data.replace("HISTORY_", ""))
        elif data.startswith("EXPORT_"):
            parts = data.split("_", 2)
            await self.export_data(update, context, parts[2], parts[1])
        elif data.startswith("OPEN_SETTINGS_"):
             await self.open_monitor_settings(update, chat_id, data.replace("OPEN_SETTINGS_", ""))
        elif data.startswith("DELETE_"):
             await self.delete_monitor_logic(chat_id, data.replace("DELETE_", ""))
             await self.show_monitor_list(update, context, 0, edit=True)
        elif data.startswith("SNOOZE_"):
            parts = data.split("_", 2)
            await self.snooze_monitor(chat_id, parts[2], int(parts[1]))
            await context.bot.send_message(chat_id, f"Snoozing {parts[2]}...")

    # ... Include reusable helper methods implemented earlier but bound to 'self' ...
    # For brevity in this tool call, I assume I will define them or inline them.
    # To keep the file valid, I will copy the logic in.
    
    async def show_monitor_list(self, update, context, page, edit=False):
        chat_id = str(update.effective_chat.id)
        all_data = await self.db_manager.load_all_monitors()
        ud = all_data.get(chat_id, UserData())
        
        kb = interface.get_monitor_list_keyboard(ud.monitors, page) if ud.monitors else interface.get_main_menu_keyboard()
        text = f"<b>Watch List ({len(ud.monitors)})</b>" if ud.monitors else "No sites watched."
        
        if edit: await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        else: await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
        
    async def show_health(self, update):
         status = get_metrics_tracker().get_system_status()
         msg = f"🏥 <b>System Health</b>\nUptime: {status['uptime_seconds']}s"
         kb = [[interface.InlineKeyboardButton("🔙 Back", callback_data="CMD_MENU")]]
         await update.callback_query.edit_message_text(msg, reply_markup=interface.InlineKeyboardMarkup(kb), parse_mode="HTML")

    async def delete_monitor_logic(self, chat_id, url):
        all_data = await self.db_manager.load_all_monitors()
        ud = all_data.get(chat_id)
        if ud:
            ud.monitors = [m for m in ud.monitors if m.url != url]
            all_data[chat_id] = ud
            await self.db_manager.atomic_write(all_data)

    async def open_monitor_settings(self, update, chat_id, url):
         all_data = await self.db_manager.load_all_monitors()
         ud = all_data.get(chat_id)
         m = next((m for m in ud.monitors if m.url == url), None)
         if m:
             if not m.config: m.config = copy.deepcopy(ud.user_config)
             await update.callback_query.edit_message_text(f"⚙️ <b>{url}</b>", reply_markup=interface.get_settings_keyboard(m.config, url), parse_mode="HTML")

    async def handle_settings_action(self, update, data, chat_id):
        # ... logic from previous main ...
        parts = data.split("_", 3)
        action = parts[1] + "_" + parts[2]
        context_id = parts[3]
        
        all_data = await self.db_manager.load_all_monitors()
        ud = all_data.get(chat_id)
        if not ud: return
        
        target_conf = ud.user_config if context_id == "GLOBAL" else next((m.config for m in ud.monitors if m.url == context_id), None)
        # Note: If context_id is url, we need to ensure config exists (handled in open_settings usually)
        if not target_conf and context_id != "GLOBAL":
             # Should not happen if opened via menu, but safety:
             m = next((m for m in ud.monitors if m.url == context_id), None)
             if m and not m.config: m.config = copy.deepcopy(ud.user_config)
             target_conf = m.config
             
        if target_conf:
             # Apply
             if action == "CYCLE_THRESH":
                 target_conf.similarity_threshold = 0.70 if target_conf.similarity_threshold >= 1.0 else target_conf.similarity_threshold + 0.05
                 if target_conf.similarity_threshold > 1.0: target_conf.similarity_threshold = 0.70 # Simple cycle
             elif action == "CYCLE_INT":
                 target_conf.check_interval = 30 if target_conf.check_interval >= 3600 else target_conf.check_interval * 2
                 if target_conf.check_interval > 3600: target_conf.check_interval = 30
             elif action == "TOGGLE_DIFF":
                 target_conf.include_diff = not target_conf.include_diff
             
             await self.db_manager.atomic_write(all_data)
             await update.callback_query.edit_message_text(f"⚙️ <b>Settings</b>", reply_markup=interface.get_settings_keyboard(target_conf, context_id), parse_mode="HTML")

    async def show_monitor_details(self, update, url):
        # Implementation similar to previous step ...
        pass # Placeholder for brevity, but real code needs it.
        # I'll inject the real implementation in valid file writing.
        # Wait, I cannot use "pass" here if I want it to work.
        # I must write full code.
        
        chat_id = str(update.effective_chat.id)
        all_data = await self.db_manager.load_all_monitors()
        ud = all_data.get(chat_id)
        m = next((x for x in ud.monitors if x.url == url), None)
        if not m: return
        
        text = f"🖥 <b>{url}</b>\nStatus: {'Online' if m.metadata.failure_count == 0 else 'Failing'}"
        kb = [
            [interface.InlineKeyboardButton("⚙️ Settings", callback_data=f"OPEN_SETTINGS_{url}")],
            [interface.InlineKeyboardButton("📜 History", callback_data=f"HISTORY_{url}"), interface.InlineKeyboardButton("🗑️ Delete", callback_data=f"DELETE_{url}")],
            [interface.InlineKeyboardButton("BACK", callback_data="CMD_LIST_0")]
        ]
        await update.callback_query.edit_message_text(text, reply_markup=interface.InlineKeyboardMarkup(kb), parse_mode="HTML")

    async def show_history(self, update, url):
        chat_id = str(update.effective_chat.id)
        all_data = await self.db_manager.load_all_monitors()
        ud = all_data.get(chat_id)
        m = next((x for x in ud.monitors if x.url == url), None)
        if m:
            txt = interface.format_history_log(m.history_log)
            await update.callback_query.edit_message_text(f"📜 {url}\n{txt}", reply_markup=interface.get_history_keyboard(url), parse_mode="HTML")

    async def export_data(self, update, context, url, fmt):
        chat_id = str(update.effective_chat.id)
        all_data = await self.db_manager.load_all_monitors()
        ud = all_data.get(chat_id)
        m = next((x for x in ud.monitors if x.url == url), None)
        if m:
            path = HistoryManager.export_to_csv(m) if fmt == "CSV" else HistoryManager.export_to_json(m)
            if path: await context.bot.send_document(chat_id, open(path, 'rb'), filename=os.path.basename(path))

    async def snooze_monitor(self, chat_id, url, mins):
        all_data = await self.db_manager.load_all_monitors()
        ud = all_data.get(chat_id)
        m = next((x for x in ud.monitors if x.url == url), None)
        if m:
            m.metadata.snooze_until = (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat()
            await self.db_manager.atomic_write(all_data)

def run():
    bot = WebDogBot()
    # Asyncio run wrapper
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(bot.run_bot())

if __name__ == "__main__":
    run()
