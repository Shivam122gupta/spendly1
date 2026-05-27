"""tests/conftest.py

Shared pytest fixtures for Spendly.

Patches get_db() at every import site so all tests run against a fresh
per-test SQLite file instead of spendly.db.
"""

import sqlite3
import pytest
from unittest.mock import patch


def _make_db_factory(db_path):
    """Return a get_db() function that always opens *db_path*."""
    def _get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    return _get_db


def _bootstrap_schema(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def use_in_memory_db(tmp_path):
    """Redirect every get_db() call to a fresh per-test SQLite file.

    Patches both database.db.get_db and database.queries.get_db so the
    mock reaches every import site.
    """
    db_path  = str(tmp_path / "test.db")
    _bootstrap_schema(db_path)
    factory  = _make_db_factory(db_path)

    # Patch all sites where get_db is used
    with patch("database.db.get_db",      side_effect=factory), \
         patch("database.queries.get_db", side_effect=factory):
        yield
