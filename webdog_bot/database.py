import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Union

# Define the path for the database file
DB_FILE = Path(__file__).resolve().parent / "db.json"

def load_all_monitors() -> Dict[str, List[dict]]:
    """
    Loads all monitors from the db.json file.
    Returns a dictionary of chat_id -> list of monitor dicts.
    """
    if not os.path.exists(DB_FILE):
        return {}

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            # Migration check: If data is in old format {chat_id: {url:..., hash:...}}
            # We convert it on the fly to new format {chat_id: [{url:..., hash:...}]}
            # This is a safe guard.
            for key, value in data.items():
                if isinstance(value, dict) and "url" in value:
                    data[key] = [value]
            return data
            
    except Exception as e:
        logging.error(f"Failed to load monitors from {DB_FILE}: {e}")
        return {}

def save_monitor(chat_id: int, url: str, fingerprint: str) -> None:
    """
    Saves or updates a monitor in the db.json file.
    Supports multiple URLs per user.
    """
    # Load current data first
    data = load_all_monitors()
    chat_key = str(chat_id)
    
    if chat_key not in data:
        data[chat_key] = []
    
    # Check if URL already exists for this user
    # If so, update the hash. If not, append.
    monitors_list = data[chat_key]
    found = False
    
    for monitor in monitors_list:
        if monitor["url"] == url:
            monitor["hash"] = fingerprint
            found = True
            break
            
    if not found:
        monitors_list.append({"url": url, "hash": fingerprint})
    
    data[chat_key] = monitors_list
    
    _write_db(data)
    logging.info(f"Saved monitor for {url} (chat_id {chat_id}) to database.")

def delete_monitor(chat_id: int, url: str) -> bool:
    """
    Removes a monitor for a specific URL.
    Returns True if removed, False if not found.
    """
    data = load_all_monitors()
    chat_key = str(chat_id)
    
    if chat_key not in data:
        return False
        
    original_count = len(data[chat_key])
    # Filter out the URL
    data[chat_key] = [m for m in data[chat_key] if m["url"] != url]
    
    if len(data[chat_key]) < original_count:
        _write_db(data)
        logging.info(f"Deleted monitor for {url} (chat_id {chat_id}).")
        return True
    
    return False

def _write_db(data: dict) -> None:
    """Helper to write data to disk."""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save to {DB_FILE}: {e}")
