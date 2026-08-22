"""SQLite ledger for real bank-statement-derived transactions.

Separate from the old data/payments.json (fabricated WhatsApp prototype
data, now retired). This database holds real transactions extracted from
the SSA bank statements. Never commit the resulting .db file -- it holds
real financial data, see .gitignore.
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "ledger.db"

SCHEMA = """
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


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"Initialized {DB_PATH}")


if __name__ == "__main__":
    init_db()
