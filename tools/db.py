"""Ledger database connection. Defaults to a local SQLite file
(data/ledger.db) for local development; if DATABASE_URL is set (the
hosted deployment), connects to that Postgres database instead. Both
paths expose the same '?'-placeholder, dict-row-returning interface so
the pipeline scripts (extract/categorize/match) and app/app.py don't
need to know which backend they're talking to.

Never commit the resulting .db file -- it holds real financial data, see
.gitignore. The hosted Postgres database holds the same kind of data and
must only ever be reached via DATABASE_URL from an environment variable,
never hardcoded or committed.
"""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "ledger.db"
DATABASE_URL = os.environ.get("DATABASE_URL")

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_date            TEXT NOT NULL,
    value_date          TEXT NOT NULL,
    direction           TEXT NOT NULL CHECK (direction IN ('debit', 'credit')),
    amount              REAL NOT NULL,
    balance_after       REAL,
    to_party            TEXT,
    from_party          TEXT,
    reporting_category  TEXT,
    sub_category        TEXT,
    expense_included    INTEGER CHECK (expense_included IN (0, 1)),
    status              TEXT,
    purpose             TEXT,
    bank_narration      TEXT NOT NULL,
    neft_inb_code       TEXT,
    evidence_file       TEXT,
    evidence_source     TEXT CHECK (evidence_source IN ('matched', 'uploaded') OR evidence_source IS NULL),
    source_document     TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (txn_date);
CREATE INDEX IF NOT EXISTS idx_transactions_neft_code ON transactions (neft_inb_code);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id                  SERIAL PRIMARY KEY,
    txn_date            TEXT NOT NULL,
    value_date          TEXT NOT NULL,
    direction           TEXT NOT NULL CHECK (direction IN ('debit', 'credit')),
    amount              DOUBLE PRECISION NOT NULL,
    balance_after       DOUBLE PRECISION,
    to_party            TEXT,
    from_party          TEXT,
    reporting_category  TEXT,
    sub_category        TEXT,
    expense_included    INTEGER CHECK (expense_included IN (0, 1)),
    status              TEXT,
    purpose             TEXT,
    bank_narration      TEXT NOT NULL,
    neft_inb_code       TEXT,
    evidence_file       TEXT,
    evidence_source     TEXT CHECK (evidence_source IN ('matched', 'uploaded') OR evidence_source IS NULL),
    source_document     TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (NOW()::text),
    updated_at          TEXT NOT NULL DEFAULT (NOW()::text)
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (txn_date);
CREATE INDEX IF NOT EXISTS idx_transactions_neft_code ON transactions (neft_inb_code);
"""


class _PGConnection:
    """Wraps a psycopg connection so callers can keep writing '?' placeholders
    and datetime('now') exactly as they do against SQLite, unchanged."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        sql = sql.replace("datetime('now')", "NOW()::text").replace("?", "%s")
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def executescript(self, sql):
        cur = self._conn.cursor()
        cur.execute(sql)
        cur.close()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_connection():
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        return _PGConnection(conn)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(POSTGRES_SCHEMA if DATABASE_URL else SQLITE_SCHEMA)
    conn.commit()
    conn.close()
    print(f"Initialized {'hosted Postgres database' if DATABASE_URL else DB_PATH}")


if __name__ == "__main__":
    init_db()
