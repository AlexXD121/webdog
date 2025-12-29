import json
import logging
import os
from pathlib import Path
from typing import Dict

# Define the path for the database file
DB_FILE = Path(__file__).resolve().parent / "db.json"

def load_all_monitors() -> Dict[str, dict]:
    """
    Loads all monitors from the db.json file.
    Returns a dictionary.
    """
    if not os.path.exists(DB_FILE):
        return {}

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load monitors from {DB_FILE}: {e}")
        return {}

def save_monitor(chat_id: int, url: str, fingerprint: str) -> None:
    """
    Saves or updates a monitor in the db.json file.
    """
    # Load current data first
    data = load_all_monitors()
    
    # Update the dictionary (convert chat_id to string for JSON compatibility)
    data[str(chat_id)] = {"url": url, "hash": fingerprint}
    
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logging.info(f"Saved monitor for chat_id {chat_id} to database.")
    except Exception as e:
        logging.error(f"Failed to save monitor to {DB_FILE}: {e}")
