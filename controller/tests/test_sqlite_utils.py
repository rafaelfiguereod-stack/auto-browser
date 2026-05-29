from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.sqlite_utils import connect_sqlite


class SQLiteUtilsTests(unittest.TestCase):
    def test_connect_sqlite_applies_operational_pragmas(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "state.db"
            conn = connect_sqlite(db_path, timeout=7)
            try:
                journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
                synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
            finally:
                conn.close()

            self.assertEqual(str(journal_mode).lower(), "wal")
            self.assertEqual(busy_timeout, 7000)
            self.assertEqual(synchronous, 1)
