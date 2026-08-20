"""Placeholder extraction for bank statements -- NOT real parsing.

Exists to validate that record_payment() correctly handles
transaction_type="income" and "expense" now that the schema supports them.
Reads a simple, hand-invented pipe-delimited mock format
(date | CREDIT/DEBIT | category | counterparty | amount | description),
not anything resembling a real SBI statement.

Real bank-statement parsing (PDF layout, most likely needing an LLM or a
PDF table-extraction step) is deferred until Kiran's real sample data
arrives -- see PROJECT_SUMMARY.md.

Usage:
  python scripts/extract_bank_statements.py                  # process every file in data/sample_bank_statements/
  python scripts/extract_bank_statements.py sbi_june_2026.txt
  python scripts/extract_bank_statements.py --dry-run
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from record_payment import record_payment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATEMENTS_DIR = ROOT / "data" / "sample_bank_statements"


def parse_statement(text):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        date_str, entry_type, category, counterparty, amount, description = [
            part.strip() for part in line.split("|")
        ]
        rows.append(
            {
                "date": date_str,
                "entry_type": entry_type.upper(),
                "category": category,
                "counterparty": counterparty,
                "amount": float(amount),
                "description": description,
            }
        )
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    file_args = [a for a in args if a != "--dry-run"]

    if file_args:
        statement_files = [STATEMENTS_DIR / name for name in file_args]
    else:
        statement_files = sorted(STATEMENTS_DIR.glob("*.txt"))

    total = 0
    for path in statement_files:
        rows = parse_statement(path.read_text(encoding="utf-8"))
        print(f"{path.name}: {len(rows)} transaction(s) found")

        for row in rows:
            if row["entry_type"] == "CREDIT":
                transaction_type, to, from_ = "income", None, row["counterparty"]
            else:
                transaction_type, to, from_ = "expense", row["counterparty"], None

            if dry_run:
                print(
                    f"  [dry-run] {row['date']} {transaction_type} {row['category']} "
                    f"{row['amount']} -- {row['description']}"
                )
            else:
                record_payment(
                    transaction_type=transaction_type,
                    date_str=row["date"],
                    amount=row["amount"],
                    category=row["category"],
                    description=row["description"],
                    source="bank_statement",
                    source_file=path.name,
                    to=to,
                    from_=from_,
                    source_excerpt=None,
                )
            total += 1

    verb = "Would record" if dry_run else "Recorded"
    print(f"{verb} {total} transaction(s) across {len(statement_files)} statement file(s).")


if __name__ == "__main__":
    main()
