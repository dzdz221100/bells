"""One place that knows how to open the Bells database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

try:
    from config import DB_PATH as DEFAULT_DB_PATH
except ImportError:  # pragma: no cover - standalone use
    DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bells.db"


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or DEFAULT_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
