"""Stage A of the real bank-statement pipeline: reads a raw SBI statement
PDF and extracts every transaction line into structured fields (date,
direction, amount, counterparty, the NEFT INB reference code used for
receipt matching). Categorization (reporting_category, sub_category,
status) is a separate, later stage -- this script only extracts what's
mechanically present on the statement itself.

Usage:
  python scripts/extract_bank_statements.py --dry-run <path-to-statement.pdf>
  python scripts/extract_bank_statements.py <path-to-statement.pdf>   # writes to data/ledger.db
"""
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from db import get_connection, init_db  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MODEL = "claude-opus-5"
TRUST_NAME = "Sri Swarnamukhi Ashrama"

SYSTEM_PROMPT = """You extract every individual transaction line from a State Bank of India \
(SBI) bank statement's raw PDF text. The PDF's table layout gets flattened into wrapped, \
multi-line text when extracted -- you need to reconstruct each transaction as one coherent \
record despite the wrapping.

Each real transaction line follows this column structure: Txn Date | Value Date | Description \
(a narration, often multi-line, describing the transfer type such as NEFT/RTGS/internal \
deposit-transfer and the counterparty) | Ref No./Cheque No. | Branch Code | Debit | Credit | \
Balance.

For every transaction found:
- "txn_date" and "value_date": ISO 8601 (YYYY-MM-DD), converted from DD/MM/YYYY.
- "direction": "debit" if the amount appears in the Debit column, "credit" if in the Credit \
column. Never both.
- "amount": the positive numeric value from whichever column is populated (strip commas).
- "balance_after": the running balance shown at the end of that row (strip commas).
- "counterparty": the person, business, or account this transaction is with, exactly as named \
in the narration (e.g. "Hari Krishna A", "Shanmugam Associates"). For internal SRI SWARNAMUKHI \
ASHRAM account-to-account transfers, use "SRI SWARNAMUKHI ASHRAM internal transfer".
- "bank_narration": the full raw description text for this row, verbatim, with internal \
line-wrapping collapsed into normal spacing but no words changed or omitted.
- "neft_inb_code": if the narration contains a code following "NEFT INB:", extract exactly that \
code. If there is no such code in the narration, use null. Do not confuse this with the NEFT \
UTR number -- they are different codes on the same line.
- "ref_no_cheque_no": the value from the Ref No./Cheque No. column, if present, else null.

Read the whole statement before extracting anything, since rows can span multiple wrapped lines \
and the column values (Debit/Credit/Balance) appear after the narration text. Skip the header \
block (account details) -- only extract actual transaction rows."""

TRANSACTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "txn_date": {"type": "string"},
                    "value_date": {"type": "string"},
                    "direction": {"type": "string", "enum": ["debit", "credit"]},
                    "amount": {"type": "number"},
                    "balance_after": {"type": "number"},
                    "counterparty": {"type": "string"},
                    "bank_narration": {"type": "string"},
                    "neft_inb_code": {"type": ["string", "null"]},
                    "ref_no_cheque_no": {"type": ["string", "null"]},
                },
                "required": [
                    "txn_date", "value_date", "direction", "amount", "balance_after",
                    "counterparty", "bank_narration", "neft_inb_code", "ref_no_cheque_no",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["transactions"],
    "additionalProperties": False,
}


def extract_pdf_text(pdf_path):
    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() for page in reader.pages)


def extract_from_statement(client, statement_text):
    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": TRANSACTIONS_SCHEMA}},
        messages=[{"role": "user", "content": f"Bank statement text:\n{statement_text}"}],
    ) as stream:
        response = stream.get_final_message()
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)["transactions"]


def insert_transaction(conn, txn, source_document):
    to_party = txn["counterparty"] if txn["direction"] == "debit" else TRUST_NAME
    from_party = txn["counterparty"] if txn["direction"] == "credit" else TRUST_NAME
    conn.execute(
        """INSERT INTO transactions
           (txn_date, value_date, direction, amount, balance_after, to_party, from_party,
            bank_narration, neft_inb_code, source_document)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (txn["txn_date"], txn["value_date"], txn["direction"], txn["amount"],
         txn["balance_after"], to_party, from_party, txn["bank_narration"],
         txn["neft_inb_code"], source_document),
    )


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    file_args = [a for a in args if a != "--dry-run"]

    if not file_args:
        print("Usage: python scripts/extract_bank_statements.py [--dry-run] <statement.pdf> [...]")
        sys.exit(1)

    client = anthropic.Anthropic()
    if not dry_run:
        init_db()
        conn = get_connection()

    total = 0
    for path_str in file_args:
        pdf_path = Path(path_str)
        statement_text = extract_pdf_text(pdf_path)
        txns = extract_from_statement(client, statement_text)
        print(f"{pdf_path.name}: {len(txns)} transaction(s) found")

        for t in txns:
            if dry_run:
                print(f"  [dry-run] {t['txn_date']} {t['direction']:6s} {t['amount']:>12,.2f} "
                      f"{t['counterparty']} (NEFT INB: {t['neft_inb_code']})")
            else:
                insert_transaction(conn, t, pdf_path.name)
            total += 1

    if not dry_run:
        conn.commit()
        conn.close()

    verb = "Would record" if dry_run else "Recorded"
    print(f"{verb} {total} transaction(s) across {len(file_args)} statement file(s).")


if __name__ == "__main__":
    main()
