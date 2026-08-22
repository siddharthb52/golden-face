"""Stage B of the bank-statement pipeline: assigns reporting_category,
sub_category, expense_included, and status to every transaction already
extracted into data/ledger.db, using only the narration/counterparty/amount
already on each row -- the same information (and no more) that will be
available for future months once there's no CA-prepared register to check
against.

Usage:
  python scripts/categorize_transactions.py --dry-run
  python scripts/categorize_transactions.py
"""
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from db import get_connection  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MODEL = "claude-opus-5"

KNOWN_SUBCATEGORIES = [
    "Architecture", "Bank Charges", "Construction Supplies",
    "Documentation / Photography", "Ecological Inputs", "Failed Bank Transfer",
    "Fencing Infrastructure", "Fencing Labour", "Field Labour",
    "Food & Hospitality", "Food & Welfare", "Gate / Welding Infrastructure",
    "Guest Logistics", "Infrastructure", "Institutional Learning",
    "Intern Accommodation", "Internship / Student Support",
    "Irrigation Infrastructure", "Local Travel & Logistics", "Painting Labour",
    "Painting Material", "Plantation Event Support",
    "Professional Travel / Stay / Food", "Research / Field Support",
    "Salary / Field Staff", "Sapling Logistics", "Saplings Procurement",
    "Site Development", "Travel & Logistics", "Treasury Movement", "Utilities",
]

SYSTEM_PROMPT = f"""You categorize transactions from the bank account of Sri Swarnamukhi \
Ashrama (SSA), a charitable trust, using only the information given for each transaction \
(date, direction, amount, counterparty, and the raw bank narration text). You do not have \
access to any other document -- if the narration alone doesn't make the purpose clear, say so \
honestly through the status field rather than guessing confidently.

Reporting Category -- choose exactly one:
- "2A - Phase-0 Pragya": direct ecological, site, and infrastructure work for the Phase-0 \
Pragya project (fencing, irrigation, saplings, site development, construction).
- "2B - Architecture": architecture and master-planning services.
- "2C - Operating/Admin": general operating costs -- salaries and field staff wages, travel and \
logistics, utilities, bank charges, institutional learning, internship/stipend support, event \
support, food and hospitality.
- "Internal Transfer": money moving between SSA's own bank accounts. Recognizable by narration \
like "TRF FRM ... TO ..." or "SRI SWARNAMUKHI ASHRAM" appearing as both account holder and \
counterparty. Never counted as expense or income.
- "Reversal": a failed or returned transfer, recognizable by narration containing "NEFTRR" \
(NEFT return) or similar reversal language. Never counted as expense.
- "Income": real incoming funds from outside SSA -- donations, grants, interest credits. Only \
for credit-direction transactions that are not Internal Transfer or Reversal.

Sub-category: a short, specific label for what the money was actually for. Prefer one of these \
existing labels if it genuinely fits: {", ".join(KNOWN_SUBCATEGORIES)}. If none fit -- \
particularly likely for Income-direction transactions, which this list doesn't cover -- propose \
a new, similarly short and specific label (e.g. "Donation", "Interest Credit").

expense_included: true only if this transaction represents real expenditure that should count \
toward SSA's total spending. Always false for Internal Transfer and Reversal. True for \
essentially all 2A/2B/2C debits unless the narration suggests otherwise.

status -- be honest about your confidence, choose exactly one:
- "Supported": the narration plus counterparty name gives a clear, specific, credible picture \
of both the reporting category and the purpose.
- "Purpose confirmation recommended": the transaction is understandable but the specific \
purpose is a reasonable guess, not clearly stated in the narration.
- "Purpose support to attach": the category is fairly clear (e.g. an obvious vendor name) but \
nothing in the narration proves the specific purpose.
- "Support note recommended": very little narration detail exists (e.g. a bare account number \
or an ambiguous name) and a human would need to explain this transaction.
- "Reversed": use only for Reversal-category transactions.

purpose: a short, specific description of what this transaction was for, phrased the way a \
bookkeeper would write it -- not just a restatement of the counterparty's name."""

CATEGORIZATION_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "reporting_category": {
                        "type": "string",
                        "enum": ["2A - Phase-0 Pragya", "2B - Architecture", "2C - Operating/Admin",
                                  "Internal Transfer", "Reversal", "Income"],
                    },
                    "sub_category": {"type": "string"},
                    "expense_included": {"type": "boolean"},
                    "status": {
                        "type": "string",
                        "enum": ["Supported", "Purpose confirmation recommended",
                                  "Purpose support to attach", "Support note recommended", "Reversed"],
                    },
                    "purpose": {"type": "string"},
                },
                "required": ["id", "reporting_category", "sub_category", "expense_included",
                             "status", "purpose"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["results"],
    "additionalProperties": False,
}


def fetch_uncategorized(conn):
    rows = conn.execute(
        "SELECT id, txn_date, direction, amount, to_party, from_party, bank_narration, "
        "neft_inb_code FROM transactions WHERE reporting_category IS NULL"
    ).fetchall()
    return [dict(r) for r in rows]


def categorize(client, txns):
    payload = [
        {
            "id": t["id"],
            "date": t["txn_date"],
            "direction": t["direction"],
            "amount": t["amount"],
            "counterparty": t["to_party"] or t["from_party"],
            "bank_narration": t["bank_narration"],
            "neft_inb_code": t["neft_inb_code"],
        }
        for t in txns
    ]
    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": CATEGORIZATION_SCHEMA}},
        messages=[{"role": "user", "content": f"Transactions:\n{json.dumps(payload, ensure_ascii=False)}"}],
    ) as stream:
        response = stream.get_final_message()
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)["results"]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dry_run = "--dry-run" in sys.argv[1:]

    conn = get_connection()
    txns = fetch_uncategorized(conn)
    if not txns:
        print("Nothing to categorize.")
        return

    client = anthropic.Anthropic()
    results = categorize(client, txns)
    if len(results) != len(txns):
        raise RuntimeError(
            f"Model returned {len(results)} result(s) for {len(txns)} transaction(s) -- "
            f"refusing to write a partial batch. Re-run the script; nothing was persisted."
        )
    result_ids = {r["id"] for r in results}
    input_ids = {t["id"] for t in txns}
    if result_ids != input_ids:
        raise RuntimeError(
            f"Model returned results for different ids than requested. "
            f"Missing: {input_ids - result_ids}, unexpected: {result_ids - input_ids}. "
            f"Refusing to write a partial batch."
        )
    print(f"Categorized {len(results)} of {len(txns)} transaction(s).")

    for r in results:
        if dry_run:
            print(f"  [dry-run] id={r['id']} {r['reporting_category']:20s} {r['sub_category']:28s} "
                  f"included={r['expense_included']} status={r['status']}")
        else:
            conn.execute(
                """UPDATE transactions
                   SET reporting_category = ?, sub_category = ?, expense_included = ?,
                       status = ?, purpose = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (r["reporting_category"], r["sub_category"], int(r["expense_included"]),
                 r["status"], r["purpose"], r["id"]),
            )

    if not dry_run:
        conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
