"""record_payment: the tool an extraction pipeline calls once per transaction
event found in a source (WhatsApp chat, bank statement, receipt). Validates
the transaction and persists it to the ledger.

Usable as a library (import record_payment) or as a CLI:
  python record_payment.py --transaction-type worker_payment --date 2026-06-06 \
      --amount 3000 --category wage --phone "+91 98450 11202" \
      --description "..." --source whatsapp --source-file ramesh_pruning_fertilizing.txt

  python record_payment.py --transaction-type expense --date 2026-06-10 \
      --amount 4500 --category supplies --to "Sri Ganesh Hardware" \
      --description "..." --source receipt --source-file receipt_2026-06-10.jpg

  python record_payment.py --transaction-type income --date 2026-06-01 \
      --amount 50000 --category donation --from "SBI Deposit -- Ref #4471" \
      --description "..." --source bank_statement --source-file sbi_june_2026.pdf
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTACTS_PATH = ROOT / "data" / "contacts.json"
PAYMENTS_PATH = ROOT / "data" / "payments.json"

TRUST_NAME = "Golden Face Trust"

# Category sets below are provisional for "expense" and "income" -- the
# exact categories the Trust actually uses for these haven't been confirmed
# yet (open question as of the Golden Face next-phase scoping). "worker_payment"
# categories are confirmed and unchanged from the prototype.
WORKER_PAYMENT_CATEGORIES = {"wage", "bonus", "reimbursement", "advance"}
EXPENSE_CATEGORIES = {"supplies", "utilities", "vendor_services", "other"}
INCOME_CATEGORIES = {"donation", "grant", "bank_interest", "other"}

CATEGORIES_BY_TYPE = {
    "worker_payment": WORKER_PAYMENT_CATEGORIES,
    "expense": EXPENSE_CATEGORIES,
    "income": INCOME_CATEGORIES,
}
VALID_TRANSACTION_TYPES = set(CATEGORIES_BY_TYPE)
VALID_SOURCES = {"whatsapp", "bank_statement", "receipt"}


def _load_contacts():
    return json.loads(CONTACTS_PATH.read_text(encoding="utf-8"))


def _load_payments():
    if PAYMENTS_PATH.exists():
        return json.loads(PAYMENTS_PATH.read_text(encoding="utf-8"))
    return []


def _save_payments(payments):
    PAYMENTS_PATH.write_text(
        json.dumps(payments, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def record_payment(
    transaction_type,
    date_str,
    amount,
    category,
    description,
    source,
    source_file,
    to=None,
    from_=None,
    phone=None,
    source_excerpt=None,
    evidence_thumbnail=None,
    currency="INR",
):
    """Validate and persist a single transaction record. Returns the stored record."""
    if transaction_type not in VALID_TRANSACTION_TYPES:
        raise ValueError(
            f"Invalid transaction_type '{transaction_type}', must be one of {sorted(VALID_TRANSACTION_TYPES)}"
        )
    valid_categories = CATEGORIES_BY_TYPE[transaction_type]
    if category not in valid_categories:
        raise ValueError(
            f"Invalid category '{category}' for transaction_type '{transaction_type}', "
            f"must be one of {sorted(valid_categories)}"
        )
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source '{source}', must be one of {sorted(VALID_SOURCES)}")
    if amount <= 0:
        raise ValueError("amount must be positive")
    date.fromisoformat(date_str)

    worker_category_tag = None
    worker_category_label = None

    if transaction_type == "worker_payment":
        if not phone:
            raise ValueError("worker_payment requires phone")
        contacts = {c["phone"]: c for c in _load_contacts()}
        if phone not in contacts:
            raise ValueError(f"Unknown phone number: {phone} — not in contacts registry")
        contact = contacts[phone]
        if contact["role"] != "employee":
            raise ValueError(
                f"{contact['name']} ({phone}) is not an employee — cannot record a payment to them"
            )
        worker_category_tag = contact.get("category")
        worker_category_label = contact.get("category_label")
        resolved_to = contact["name"]
        resolved_from = from_ or TRUST_NAME
    elif transaction_type == "expense":
        if not to:
            raise ValueError("expense requires 'to' (the vendor/payee)")
        resolved_to = to
        resolved_from = from_ or TRUST_NAME
    else:  # income
        if not from_:
            raise ValueError("income requires 'from' (the depositor/source of funds)")
        resolved_from = from_
        resolved_to = to or TRUST_NAME

    payments = _load_payments()
    record = {
        "id": len(payments) + 1,
        "date": date_str,
        "amount": amount,
        "currency": currency,
        "transaction_type": transaction_type,
        "category": category,
        "to": resolved_to,
        "from": resolved_from,
        "phone": phone,
        "worker_category_tag": worker_category_tag,
        "worker_category_label": worker_category_label,
        "description": description,
        "source": source,
        "source_excerpt": source_excerpt,
        "source_file": source_file,
        "evidence_thumbnail": evidence_thumbnail,
    }
    payments.append(record)
    _save_payments(payments)
    return record


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Record a single transaction event")
    parser.add_argument("--transaction-type", required=True, choices=sorted(VALID_TRANSACTION_TYPES))
    parser.add_argument("--date", required=True)
    parser.add_argument("--amount", required=True, type=float)
    parser.add_argument("--category", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--source", required=True, choices=sorted(VALID_SOURCES))
    parser.add_argument("--source-file", required=True)
    parser.add_argument("--to", default=None)
    parser.add_argument("--from", dest="from_", default=None)
    parser.add_argument("--phone", default=None)
    parser.add_argument("--source-excerpt", default=None)
    parser.add_argument("--evidence-thumbnail", default=None)
    parser.add_argument("--currency", default="INR")
    args = parser.parse_args()

    rec = record_payment(
        transaction_type=args.transaction_type,
        date_str=args.date,
        amount=args.amount,
        category=args.category,
        description=args.description,
        source=args.source,
        source_file=args.source_file,
        to=args.to,
        from_=args.from_,
        phone=args.phone,
        source_excerpt=args.source_excerpt,
        evidence_thumbnail=args.evidence_thumbnail,
        currency=args.currency,
    )
    print(json.dumps(rec, indent=2, ensure_ascii=False))
