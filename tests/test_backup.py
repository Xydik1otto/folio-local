# One-click DB backup/restore: /api/backup download + /api/restore upload.
import os

import pytest
from fastapi.testclient import TestClient

from backend import backup as backup_mod
from backend.main import app

client = TestClient(app)


@pytest.fixture()
def dbfile(tmp_path, monkeypatch):
    path = str(tmp_path / "folio.db")
    monkeypatch.setenv("FOLIO_DB", path)
    return path


def _seed(path: str) -> None:
    c = __import__("backend.db", fromlist=["connect"]).connect(path)
    with c:
        c.execute("INSERT INTO accounts(name, currency, cash) VALUES ('B','EUR',100)")
        c.execute("INSERT INTO transactions(account_id, type, date, amount, currency)"
                  " VALUES (1,'deposit','2024-01-05',100,'EUR')")
    c.close()


def test_backup_download_returns_sqlite_file(dbfile):
    _seed(dbfile)
    r = client.get("/api/backup")
    assert r.status_code == 200
    assert r.content.startswith(b"SQLite format 3\x00")
    assert "attachment" in r.headers["content-disposition"]
    assert "folio-backup-" in r.headers["content-disposition"]
    # snapshot opens as a valid DB with our data
    backup_mod.validate_db_bytes(r.content)


def test_restore_roundtrip(dbfile):
    _seed(dbfile)
    snapshot = client.get("/api/backup").content
    # wipe the live DB, then restore the snapshot over it
    os.unlink(dbfile)
    r = client.post("/api/restore", content=snapshot,
                    headers={"content-type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["restored"] is True and body["transactions"] == 1
    conn = __import__("backend.db", fromlist=["connect"]).connect(dbfile)
    n = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    name = conn.execute("SELECT name FROM accounts LIMIT 1").fetchone()[0]
    conn.close()
    assert n == 1 and name == "B"


def test_restore_rejects_garbage(dbfile):
    _seed(dbfile)
    r = client.post("/api/restore", content=b"not a database at all",
                    headers={"content-type": "application/octet-stream"})
    assert r.status_code == 400
    assert "SQLite" in r.json()["detail"]
    # live DB untouched
    conn = __import__("backend.db", fromlist=["connect"]).connect(dbfile)
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
    conn.close()


def test_restore_rejects_foreign_sqlite(dbfile, tmp_path):
    import sqlite3
    foreign = str(tmp_path / "other.db")
    c = sqlite3.connect(foreign)
    c.execute("CREATE TABLE other_stuff (x INT)")
    c.commit()
    c.close()
    with open(foreign, "rb") as f:
        payload = f.read()
    _seed(dbfile)
    r = client.post("/api/restore", content=payload,
                    headers={"content-type": "application/octet-stream"})
    assert r.status_code == 400
    assert "missing tables" in r.json()["detail"]


def test_backup_uses_folio_db_env(dbfile):
    # the endpoint must snapshot the ACTIVE db (FOLIO_DB), not a hard-coded path
    _seed(dbfile)
    r = client.get("/api/backup")
    import sqlite3, tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(r.content)
        p = f.name
    c = sqlite3.connect(p)
    assert c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
    c.close()
