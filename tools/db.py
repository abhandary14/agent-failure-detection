"""Shared SQLite connection helper used by every tool."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def get_connection() -> sqlite3.Connection:
    """Open a connection to the transactions DB with dict-like row access."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn