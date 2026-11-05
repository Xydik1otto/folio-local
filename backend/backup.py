# One-click SQLite backup/restore: download a consistent snapshot, restore
# from an uploaded .db file (validated before it replaces the live database).
from __future__ import annotations

import os
import sqlite3
import tempfile

EXPECTED_TABLES = {"accounts", "assets", "transactions", "price_snapshots", "fx_rates"}


class RestoreError(ValueError):
    pass


def backup_bytes(db_path: str) -> bytes:
    """Consistent snapshot of the SQLite database as bytes (online backup API)."""
    src = sqlite3.connect(db_path)
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        dst = sqlite3.connect(tmp_path)
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
        with open(tmp_path, "rb") as f:
            data = f.read()
        return data
    finally:
        src.close()
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def validate_db_bytes(data: bytes) -> None:
    """Raise RestoreError unless the payload is a folio-local SQLite database."""
    if not data.startswith(b"SQLite format 3\x00"):
        raise RestoreError("not a SQLite database file")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
        conn = sqlite3.connect(tmp_path)
        try:
            names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            conn.close()
        missing = EXPECTED_TABLES - names
        if missing:
            raise RestoreError(
                "not a folio-local database: missing tables " + ", ".join(sorted(missing)))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def restore_bytes(db_path: str, data: bytes) -> int:
    """Atomically replace the live database with an uploaded snapshot.

    Returns the number of transactions in the restored database.
    Raises RestoreError for any file that is not a folio-local DB.
    """
    validate_db_bytes(data)
    directory = os.path.dirname(os.path.abspath(db_path)) or "."
    fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=directory)
    os.close(fd)
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
        conn = sqlite3.connect(tmp_path)
        try:
            n = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        finally:
            conn.close()
        os.replace(tmp_path, db_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return int(n)
