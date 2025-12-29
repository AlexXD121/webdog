import logging
import math
from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

# Constants
ITEMS_PER_PAGE = 5

logger = logging.getLogger("Interface")

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the primary dashboard menu.
    """
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Site", callback_data="CMD_ADD"),
            InlineKeyboardButton("📂 List Sites", callback_data="CMD_LIST_0")
        ],
        [
            InlineKeyboardButton("🏥 System Health", callback_data="CMD_HEALTH"),
            InlineKeyboardButton("⚙️ Settings", callback_data="CMD_SETTINGS")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_monitor_list_keyboard(monitors: list, page: int = 0) -> InlineKeyboardMarkup:
    """
    Returns a paginated list of sites with management buttons.
    """
    total_pages = math.ceil(len(monitors) / ITEMS_PER_PAGE)
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_batch = monitors[start:end]
    
    keyboard = []
    
    # Render Item Rows
    for m in current_batch:
        # Format: [ URL (Status) ] -> [ ⚙️ ] [ ❌ ]
        # Telegram buttons have limited width. 
        # Better: Single button "google.com 🟢" -> Opens submenu for that site?
        # Or: "google.com" [Check] [Delete]
        
        # Let's try: Row 1: Site Name. Row 2: Check | Config | Delete
        # That takes too much vertical space.
        
        # Compact: [ google.com ] [ 🗑️ ]
        # Clicking google.com triggers details/refresh.
        url_label = m.url.replace("https://", "").replace("http://", "").rstrip("/")
        if len(url_label) > 20:
            url_label = url_label[:17] + "..."
            
        row = [
            InlineKeyboardButton(f"🔗 {url_label}", callback_data=f"DETAILS_{m.url}"),
            InlineKeyboardButton("🗑️", callback_data=f"DELETE_{m.url}")
        ]
        keyboard.append(row)

    # Navigation Row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"CMD_LIST_{page-1}"))
    
    nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages if total_pages > 0 else 1}", callback_data="NOOP"))
    
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"CMD_LIST_{page+1}"))
        
    keyboard.append(nav_row)
    
    # Back to Menu
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="CMD_MENU")])
    
    return InlineKeyboardMarkup(keyboard)

def get_alert_keyboard(url: str) -> InlineKeyboardMarkup:
    """
    Actions for checking an alert.
    """
    keyboard = [
        [
            InlineKeyboardButton("💤 Snooze 1h", callback_data=f"SNOOZE_60_{url}"),
            InlineKeyboardButton("💤 6h", callback_data=f"SNOOZE_360_{url}"),
            InlineKeyboardButton("💤 24h", callback_data=f"SNOOZE_1440_{url}")
        ],
        [
             InlineKeyboardButton("🗑️ Stop Watching", callback_data=f"DELETE_{url}")
        ]
        # Maybe "Mark as Recognized" (Update Baseline) is default behavior on similarity logic? 
        # Current logic auto-updates baseline.
    ]
    return InlineKeyboardMarkup(keyboard)

from models import Config

# ... existing imports ...

def get_settings_keyboard(config: Config, context_id: str = "GLOBAL") -> InlineKeyboardMarkup:
    """
    Generates settings menu. 
    context_id is "GLOBAL" or a URL string.
    """
    # Formatting
    thresh_pct = int(config.similarity_threshold * 100)
    int_sec = config.check_interval
    diff_state = "ON" if config.include_diff else "OFF"
    
    keyboard = [
        [
            InlineKeyboardButton(f"Sensitivity: {thresh_pct}% 🔄", callback_data=f"SET_CYCLE_THRESH_{context_id}"),
            InlineKeyboardButton(f"Interval: {int_sec}s 🔄", callback_data=f"SET_CYCLE_INT_{context_id}")
        ],
        [
             InlineKeyboardButton(f"Visual Diffs: {diff_state} 🔄", callback_data=f"SET_TOGGLE_DIFF_{context_id}")
        ],
        [
            InlineKeyboardButton("🔙 Done", callback_data="CMD_MENU" if context_id == "GLOBAL" else "CMD_LIST_0")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

import html

# ... existing imports ...

def escape_html(text: str) -> str:
    """Helper to escape HTML special characters."""
    return html.escape(str(text))

# Alias for strict requirement compliance
sanitize_html = escape_html

# ... existing code ...

def format_diff_message(url: str, score: float, classification: str, diff_text: str = "") -> str:
    """
    Formats the alert message with markdown.
    """
    # Escape for HTML safety
    safe_url = escape_html(url)
    safe_class = escape_html(classification)
    
    msg = (
        f"🚨 <b>Change Detected: {safe_url}</b>\n"
        f"Similarity: {int(score*100)}%\n"
        f"Type: <i>{safe_class}</i>\n"
    )
    
    if diff_text:
        # Truncate if MASSIVE even for telegram (max 4096 char msg)
        # diff_text should already be truncated by `change_detector` (3000 chars).
        # Sanitize the diff block content!
        safe_diff = escape_html(diff_text)
        msg += f"\n<pre language='diff'>{safe_diff}</pre>"
        
    return msg

def get_history_keyboard(url: str) -> InlineKeyboardMarkup:
    """
    Actions for history view.
    """
    keyboard = [
        [
            InlineKeyboardButton("📄 Export CSV", callback_data=f"EXPORT_CSV_{url}"),
            InlineKeyboardButton("💾 Export JSON", callback_data=f"EXPORT_JSON_{url}")
        ],
        [
            InlineKeyboardButton("🔙 Back to List", callback_data="CMD_LIST_0")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_history_log(history: List, limit: int = 5) -> str:
    """
    Text summary of recent history.
    """
    if not history:
        return "<i>No history recorded yet.</i>"
        
    # Sort distinct? Actually list is append-only so usually sorted asc.
    # We want newest first.
    recent = list(reversed(history))[:limit]
    
    lines = []
    for entry in recent:
        # entry is HistoryEntry object (or dict if not parsed? Models ensures obj)
        ts = entry.timestamp[:16].replace("T", " ") # YYYY-MM-DD HH:MM
        lines.append(f"• <code>{ts}</code> - <b>{entry.change_type}</b> ({int(entry.similarity_score*100)}%)")
        
    return "\n".join(lines)
