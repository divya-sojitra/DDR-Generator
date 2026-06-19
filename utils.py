"""
utils.py
Utility helpers for the DDR Generator.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def get_api_key(provided_key: str = "") -> str:
    """Return API key from argument, env var, or raise."""
    key = provided_key.strip() or os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "GEMINI_API_KEY not found. Please enter it in the sidebar or set it in your .env file."
        )
    return key


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024**2):.1f} MB"


def safe_get(data: dict, *keys, default="Not Available"):
    """Safely traverse nested dict keys."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data if data not in (None, "", []) else default
