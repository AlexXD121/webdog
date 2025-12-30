import logging
import os
import sys
import threading
import html
import asyncio
import signal
import socket
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict
import copy

# --- CRITICAL FIX: DNS MONKEY PATCH ---
# Docker/HF DNS is failing to resolve api.telegram.org, but IP connectivity works.
# We intercept socket.getaddrinfo to return the hardcoded IP for Telegram.
# This MUST operate before any network calls or Telegram imports.

print("Applying DNS Monkey Patch for api.telegram.org...")
_original_getaddrinfo = socket.getaddrinfo

def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """
    Overrides DNS resolution for specific hosts to bypass OS-level resolver failures.
    """
    if host == "api.telegram.org":
        # Known stable IP for api.telegram.org (Telegram API)
        # We force return a valid IPv4 (AF_INET), TCP (SOCK_STREAM) socket address.
        # This acts like a hardcoded /etc/hosts entry.
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("149.154.167.220", port or 443))]
    
    # Fallback to system resolver for everything else
    return _original_getaddrinfo(host, port, family, type, proto, flags)

# Apply the patch
socket.getaddrinfo = _patched_getaddrinfo
print("DNS Monkey Patch APPLIED: api.telegram.org -> 149.154.167.220")


# --- 1. CONFIGURATION & LOGGING ---
# Force logs to stdout so they appear in Hugging Face console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger("WebDogBot")

# Load Environment Variables
# Third-party Imports (Now safe to import as DNS patch is active)
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    logger.critical("FATAL: No TELEGRAM_TOKEN found in environment variables.")
    sys.exit(1)

# Ensure import paths work
sys.path.append(str(Path(__file__).resolve().parent))

# Safe Import of Internal Modules
try:
    from database import AtomicDatabaseManager
    from request_manager import GlobalRequestManager
    from fingerprinter import VersionedContentFingerprinter
    from similarity import SimilarityEngine
    from models import Monitor, UserData
    from metrics import get_metrics_tracker
    from governor import get_governor
    from history_manager import HistoryManager
    import interface
except ImportError as e:
    logger.critical(f"Startup Import Error: {e}")
    sys.exit(1)


# --- 2. HEALTH CHECK SERVER (Keeps Bot Awake) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"WebDog is running")
    
    def log_message(self, format, *args):
        pass # Silence access logs

def start_health_check_server():
    """Starts a simple HTTP server in a daemon thread."""
    try:
        # Default to 7860 (Standard for Hugging Face Spaces)
        port = int(os.environ.get("PORT", 7860))
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Health Check Server listening on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start Health Check Server: {e}")


# --- 3. SMART NETWORK WAITER (The Fix) ---
async def wait_for_internet():
    """
    Deep Network Diagnostic:
    1. Tests direct IP connectivity (Ping Google DNS).
    2. Tests DNS resolution (Resolve Telegram API).
    Retries until successful.
    """
    logger.info("Performing deep network diagnostic...")
    
    while True:
        try:
            # CHECK 1: IP Connectivity (Can we reach the outside world?)
            # Connect to Google DNS (8.8.8.8) on port 53 to test route
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            
            # CHECK 2: DNS Resolution (Can we translate names to IPs?)
            # Even with monkey patch, this verifies our patch works or system works.
            # If patch works, this returns instantly.
            try:
                ip = socket.gethostbyname("api.telegram.org")
                logger.info(f"INTERNET & DNS ARE WORKING! Resolved to: {ip}")
                
                # VERIFICATION STEP
                # Explicitly prove the patch works by opening a socket to the resolved IP
                logger.info("Verifying DNS Patch Connectivity...")
                socket.create_connection(('api.telegram.org', 443), timeout=3)
                logger.info("DNS PATCH VERIFIED: Connected to Telegram IP via Override.")
                
                return
            except Exception as e:
                logger.warning(f"DNS/Connection Failure: {e}. Retrying...")

                
        except (OSError, socket.timeout):
            logger.warning("No Network Route (Container Network Sleeping). Retrying in 3s...")
            
        await asyncio.sleep(3)


# --- 4. WEBDOG BOT LOGIC ---
class WebDogBot:
    def __init__(self):
        self.db_manager = AtomicDatabaseManager()
        self.request_manager = GlobalRequestManager()
        self.fingerprinter = VersionedContentFingerprinter()
        self.similarity_engine = SimilarityEngine()
        self.application: Optional[Application] = None
        
    async def startup(self):
        logger.info("WebDog Professional System Startup...")
        await self.db_manager.startup()
        await self.request_manager.startup()
        
        if not self.db_manager._check_disk_space():
             logger.critical("Insufficient Disk Space!")
        
        status = get_metrics_tracker().get_system_status()
        logger.info(f"System Status: {status}")

        await get_governor().telegram_throttler.start()
        logger.info("Core Systems Initialized")

    async def shutdown(self):
        logger.info("Shutting down WebDog Bot...")
        if self.request_manager:
            await self.request_manager.close()
        await get_governor().telegram_throttler.stop()

    # --- Handlers ---
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"<b>WebDog Professional</b>\nReady to guard.",
            reply_markup=interface.get_main_menu_keyboard(),
            parse_mode="HTML"
        )
        
    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if not context.args:
            await update.message.reply_text("Usage: /watch <url>")
            return
        
        url = context.args[0]
        if not url.startswith(("http", "https")): 
            url = "https://" + url
        
        msg = await update.message.reply_text("Analyzing...")
        
        try:
            result = await self.request_manager.fetch(url)
            if result.error or not result.content:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=f"Failed: {result.error}")
                return
            
            fp = self.fingerprinter.generate_fingerprint(result.content)
            monitor = Monitor(url=url, fingerprint=fp)
            
            all_data = await self.db_manager.load_all_monitors()
            user_data = all_data.get(chat_id, UserData())
            
            user_data.monitors = [m for m in user_data.monitors if m.url != url]
            user_data.monitors.append(monitor)
            all_data[chat_id] = user_data
            
            await self.db_manager.atomic_write(all_data)
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=f"Watching {url}")
            
        except Exception as e:
            logger.error(f"Watch failed: {e}", exc_info=True)
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text="Error adding site.")

    async def cmd_unwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if not context.args: return
        url = context.args[0]
        await self.delete_monitor_logic(chat_id, url)
        await update.message.reply_text(f"Removed {url}")

    async def cmd_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.show_monitor_list(update, context, 0)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if data == "CMD_MENU":
            await query.edit_message_text("<b>Menu</b>", reply_markup=interface.get_main_menu_keyboard(), parse_mode="HTML")
        elif data.startswith("CMD_LIST_"):
            await self.show_monitor_list(update, context, int(data.split("_")[-1]), edit=True)
        elif data == "CMD_HEALTH":
            await self.show_health(update)
        elif data == "CMD_SETTINGS":
             chat_id = str(update.effective_chat.id)
             all_data = await self.db_manager.load_all_monitors()
             ud = all_data.get(chat_id, UserData())
             await query.edit_message_text("<b>Global Settings</b>", reply_markup=interface.get_settings_keyboard(ud.user_config, "GLOBAL"), parse_mode="HTML")
        elif data.startswith("SET_"):
            await self.handle_settings_action(update, data, str(update.effective_chat.id))
        elif data.startswith("DETAILS_"):
            await self.show_monitor_details(update, data.replace("DETAILS_", ""))
        elif data.startswith("HISTORY_"):
            await self.show_history(update, data.replace("HISTORY_", ""))
        elif data.startswith("EXPORT_"):
            parts = data.split("_", 2)
            await self.export_data(update, context, parts[2], parts[1])
        elif data.startswith("OPEN_SETTINGS_"):
             await self.open_monitor_settings(update, str(update.effective_chat.id), data.replace("OPEN_SETTINGS_", ""))
        elif data.startswith("DELETE_"):
             await self.delete_monitor_logic(str(update.effective_chat.id), data.replace("DELETE_", ""))
             await self.show_monitor_list(update, context, 0, edit=True)
        elif data.startswith("SNOOZE_"):
            parts = data.split("_", 2)
            await self.snooze_monitor(str(update.effective_chat.id), parts[2], int(parts[1]))
            await context.bot.send_message(str(update.effective_chat.id), f"Snoozing {parts[2]} for {parts[1]}m")

    # --- Job Queue Tasks ---
    async def patrol_job(self, context: ContextTypes.DEFAULT_TYPE):
        if get_governor().is_congested:
             return 

        try:
            all_data = await self.db_manager.load_all_monitors()
            updates_needed = False
            
            for chat_id, user_data in all_data.items():
                for monitor in user_data.monitors:
                    try:
                        config = monitor.config or user_data.user_config
                        
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
                        
                        await get_governor().acquire_web_token()
                        
                        result = await self.request_manager.fetch(monitor.url)
                        monitor.metadata.check_count += 1
                        
                        if result.status_code == 429:
                            monitor.metadata.rate_limit_count += 1
                            if monitor.metadata.rate_limit_count >= 3:
                                try:
                                    await get_governor().telegram_throttler.send_message(
                                        context.bot.send_message(chat_id=chat_id, text=f"Rate Limit: {html.escape(monitor.url)}", parse_mode="HTML")
                                    )
                                    monitor.metadata.rate_limit_count = 0 
                                except Exception: pass
                            updates_needed = True
                            continue 
                        
                        monitor.metadata.rate_limit_count = 0
                        
                        if result.error or not result.content:
                            monitor.metadata.failure_count += 1
                            continue
                            
                        new_fp = self.fingerprinter.generate_fingerprint(result.content)
                        monitor.metadata.last_check = datetime.now(timezone.utc).isoformat()
                        
                        if monitor.fingerprint and monitor.fingerprint.hash != new_fp.hash:
                             score = self.similarity_engine.calculate_similarity(monitor.fingerprint, new_fp).final_score
                             if score < config.similarity_threshold:
                                 msg = interface.format_diff_message(monitor.url, score, "Change Detected", "")
                                 kb = interface.get_alert_keyboard(monitor.url)
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
                        logger.error(f"Error checking {monitor.url}: {e}")
                        monitor.metadata.failure_count += 1
                        updates_needed = True

            if updates_needed:
                 await self.db_manager.atomic_write(all_data)
        except Exception as e:
            logger.critical(f"Fatal Patrol Error: {e}", exc_info=True)

    async def cleanup_job(self, context: ContextTypes.DEFAULT_TYPE):
        await asyncio.to_thread(HistoryManager.cleanup_exports, 60)

    # --- Helper methods ---
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
         msg = f"<b>System Health</b>\nUptime: {status['uptime_seconds']}s"
         kb = [[interface.InlineKeyboardButton("Back", callback_data="CMD_MENU")]]
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
             await update.callback_query.edit_message_text(f"<b>{url}</b>", reply_markup=interface.get_settings_keyboard(m.config, url), parse_mode="HTML")

    async def handle_settings_action(self, update, data, chat_id):
        parts = data.split("_", 3)
        action = parts[1] + "_" + parts[2]
        context_id = parts[3]
        
        all_data = await self.db_manager.load_all_monitors()
        ud = all_data.get(chat_id)
        if not ud: return
        
        target_conf = ud.user_config if context_id == "GLOBAL" else next((m.config for m in ud.monitors if m.url == context_id), None)
        if not target_conf and context_id != "GLOBAL":
             m = next((m for m in ud.monitors if m.url == context_id), None)
             if m and not m.config: m.config = copy.deepcopy(ud.user_config)
             target_conf = m.config
             
        if target_conf:
             if action == "CYCLE_THRESH":
                 target_conf.similarity_threshold = 0.70 if target_conf.similarity_threshold >= 1.0 else target_conf.similarity_threshold + 0.05
                 if target_conf.similarity_threshold > 1.0: target_conf.similarity_threshold = 0.70
             elif action == "CYCLE_INT":
                 target_conf.check_interval = 30 if target_conf.check_interval >= 3600 else target_conf.check_interval * 2
                 if target_conf.check_interval > 3600: target_conf.check_interval = 30
             elif action == "TOGGLE_DIFF":
                 target_conf.include_diff = not target_conf.include_diff
             
             await self.db_manager.atomic_write(all_data)
             await update.callback_query.edit_message_text(f"⚙️ <b>Settings</b>", reply_markup=interface.get_settings_keyboard(target_conf, context_id), parse_mode="HTML")

    async def show_monitor_details(self, update, url):
        chat_id = str(update.effective_chat.id)
        all_data = await self.db_manager.load_all_monitors()
        ud = all_data.get(chat_id)
        m = next((x for x in ud.monitors if x.url == url), None)
        if not m: return
        text = f"<b>{url}</b>\nStatus: {'Online' if m.metadata.failure_count == 0 else 'Failing'}"
        kb = [
            [interface.InlineKeyboardButton("Settings", callback_data=f"OPEN_SETTINGS_{url}")],
            [interface.InlineKeyboardButton("History", callback_data=f"HISTORY_{url}"), interface.InlineKeyboardButton("Delete", callback_data=f"DELETE_{url}")],
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
            await update.callback_query.edit_message_text(f"{url}\n{txt}", reply_markup=interface.get_history_keyboard(url), parse_mode="HTML")

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


# --- 5. MAIN EXECUTION ---
async def main():
    logger.info("System entry point reached.")

    # 1. Start Health Check (Daemon)
    threading.Thread(target=start_health_check_server, daemon=True).start()
    
    # 2. WAIT FOR INTERNET (Smart Fix)
    await wait_for_internet()
    
    # 3. Instantiate and Startup Bot
    bot_logic = WebDogBot()
    await bot_logic.startup()
    
    # 4. Build Application
    logger.info("Building Telegram Application...")
    application = Application.builder().token(TOKEN).build()
    
    if not application.job_queue:
        logger.critical("JobQueue failed to initialize! Check requirements.txt.")
        sys.exit(1)

    # 5. Register Handlers
    application.add_handler(CommandHandler("start", bot_logic.cmd_start))
    application.add_handler(CommandHandler("watch", bot_logic.cmd_watch))
    application.add_handler(CommandHandler("unwatch", bot_logic.cmd_unwatch))
    application.add_handler(CommandHandler("list", bot_logic.cmd_list))
    application.add_handler(CallbackQueryHandler(bot_logic.handle_callback))
    
    # 6. Schedule Jobs
    application.job_queue.run_repeating(bot_logic.patrol_job, interval=60, first=10)
    application.job_queue.run_repeating(bot_logic.cleanup_job, interval=3600, first=60)
    
    # 7. Start Polling Loop
    logger.info("Initializing Updater...")
    await application.initialize()
    await application.start()
    
    logger.info("Starting Polling...")
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    try:
        # Wait forever
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Stopping received...")
    finally:
        try:
            if application.updater.running:
                await application.updater.stop()
        except Exception: pass
        
        try:
            if application.running:
                await application.stop()
                await application.shutdown()
        except Exception: pass
        
        await bot_logic.shutdown()
        logger.info("Bye!")

if __name__ == "__main__":
    try:
        if os.name == 'nt':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass 
    except Exception as e:
        logger.critical(f"BLOCKING CRASH: {e}", exc_info=True)
        sys.stderr.write(f"BLOCKING CRASH: {e}\n")
        sys.exit(1)