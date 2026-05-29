from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def connect_sqlite(
    db_path: str | Path,
    *,
    timeout: float = 10.0,
    row_factory: Any | None = None,
) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=timeout)
    if row_factory is not None:
        conn.row_factory = row_factory
    configure_sqlite_connection(conn, db_path=db_path, timeout=timeout)
    return conn


def configure_sqlite_connection(
    conn: sqlite3.Connection,
    *,
    db_path: str | Path | None = None,
    timeout: float = 10.0,
) -> None:
    busy_timeout_ms = max(1, int(timeout * 1000))
    conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
    try:
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()
    except sqlite3.DatabaseError as exc:
        logger.warning("sqlite WAL unavailable for %s: %s", db_path or "<memory>", exc)
    else:
        if mode is not None and str(mode[0]).lower() != "wal":
            logger.debug("sqlite WAL not enabled for %s: journal_mode=%s", db_path or "<memory>", mode[0])
    conn.execute("PRAGMA synchronous=NORMAL")
