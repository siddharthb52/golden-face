"""One-time migration: copies every row from the local SQLite ledger
(data/ledger.db) into the hosted Postgres database at DATABASE_URL. Run
once when standing up the hosted deployment. After this, the pipeline
scripts (extract/categorize/match) write directly to DATABASE_URL, so
this shouldn't need to run again except to re-seed a fresh Postgres
instance from a local backup.

Usage:
  Set DATABASE_URL in .env to the hosted Postgres connection string, then:
  python scripts/migrate_to_postgres.py
"""
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "tools"))
from db import get_connection, init_db  # noqa: E402

SQLITE_PATH = ROOT / "data" / "ledger.db"

COLUMNS = [
    "txn_date", "value_date", "direction", "amount", "balance_after",
    "to_party", "from_party", "reporting_category", "sub_category",
    "expense_included", "status", "purpose", "bank_narration",
    "neft_inb_code", "evidence_file", "evidence_source", "source_document",
    "created_at", "updated_at",
]


def main():
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is not set -- refusing to run (this would silently "
              "write into the local SQLite file instead of Postgres).")
        sys.exit(1)

    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    rows = [dict(r) for r in src.execute(f"SELECT {', '.join(COLUMNS)} FROM transactions ORDER BY id")]
    src.close()
    print(f"Read {len(rows)} transaction(s) from {SQLITE_PATH}")

    init_db()
    dst = get_connection()
    placeholders = ", ".join("?" for _ in COLUMNS)
    for r in rows:
        dst.execute(
            f"INSERT INTO transactions ({', '.join(COLUMNS)}) VALUES ({placeholders})",
            tuple(r[c] for c in COLUMNS),
        )
    dst.commit()
    dst.close()
    print(f"Migrated {len(rows)} transaction(s) to the hosted Postgres database.")


if __name__ == "__main__":
    main()
