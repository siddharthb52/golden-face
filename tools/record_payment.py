"""record_payment: the tool an extraction pipeline calls once per payment
event found in a conversation. Validates the payment against the contacts
registry and persists it to the payments ledger.

Usable as a library (import record_payment) or as a CLI:
  python record_payment.py --phone "+91 98450 11202" --date 2026-06-06 \
      --amount 3000 --category wage --description "..." \
      --source "..." --chat-file ramesh_pruning_fertilizing.txt
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTACTS_PATH = ROOT / "data" / "contacts.json"
PAYMENTS_PATH = ROOT / "data" / "payments.json"

VALID_CATEGORIES = {"wage", "bonus", "reimbursement", "advance"}


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
    phone,
    date_str,
    amount,
    category,
    description,
    source_excerpt,
    chat_file,
    currency="INR",
):
    """Validate and persist a single payment record. Returns the stored record."""
    contacts = {c["phone"]: c for c in _load_contacts()}
    if phone not in contacts:
        raise ValueError(f"Unknown phone number: {phone} — not in contacts registry")

    contact = contacts[phone]
    if contact["role"] != "employee":
        raise ValueError(
            f"{contact['name']} ({phone}) is not an employee — cannot record a payment to them"
        )
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}', must be one of {sorted(VALID_CATEGORIES)}"
        )
    if amount <= 0:
        raise ValueError("amount must be positive")
    date.fromisoformat(date_str)

    payments = _load_payments()
    record = {
        "id": len(payments) + 1,
        "phone": phone,
        "name": contact["name"],
        "category_tag": contact.get("category"),
        "category_label": contact.get("category_label"),
        "date": date_str,
        "amount": amount,
        "currency": currency,
        "payment_category": category,
        "description": description,
        "source_excerpt": source_excerpt,
        "chat_file": chat_file,
    }
    payments.append(record)
    _save_payments(payments)
    return record


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Record a single payment event")
    parser.add_argument("--phone", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--amount", required=True, type=float)
    parser.add_argument("--category", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--chat-file", required=True)
    parser.add_argument("--currency", default="INR")
    args = parser.parse_args()

    rec = record_payment(
        args.phone,
        args.date,
        args.amount,
        args.category,
        args.description,
        args.source,
        args.chat_file,
        args.currency,
    )
    print(json.dumps(rec, indent=2, ensure_ascii=False))
