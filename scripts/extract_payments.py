"""Real extraction pipeline: reads a WhatsApp chat export, sends it to Claude
with a structured-output schema, and records every payment event it finds by
calling record_payment() -- exactly the same downstream call a human reading
the chat by hand would make.

This replaces extract_sample_payments.py, which was a hardcoded stand-in for
this step. record_payment() itself is unchanged: it doesn't know or care
whether the structured fields it receives came from a human or from here.

Usage:
  python scripts/extract_payments.py                     # process every file in data/sample_chats/
  python scripts/extract_payments.py ramesh_pruning_fertilizing.txt
  python scripts/extract_payments.py --dry-run            # print what would be recorded, don't write

Not yet built: tracking which messages have already been processed. Running
this twice on the same chat file will record every payment a second time.
That's a deliberate deferral -- see PROJECT_SUMMARY.md -- since the right
approach depends on whether messages arrive as full re-exports or a live
incremental feed.
"""
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from record_payment import record_payment, VALID_CATEGORIES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONTACTS_PATH = ROOT / "data" / "contacts.json"
CHATS_DIR = ROOT / "data" / "sample_chats"

load_dotenv(ROOT / ".env")

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You extract payment records from a WhatsApp conversation between the manager \
of a forest and garden preserve (Golden Mouth) and one of its workers.

Payments are always manager -> worker. A message where the worker mentions paying someone else \
out of petty cash they were already holding (e.g. paying other workers, buying something for a \
third party) is NOT a payment from the manager and must be excluded.

Categorize every payment you find into exactly one of these four types:
- wage: regular payment for work done that period.
- bonus: an extra amount on top of wages, tied to praise, good performance, or overtime -- not \
tied to a specific out-of-pocket expense.
- reimbursement: money paid back for something the worker bought out of their own pocket \
(supplies, materials, repairs).
- advance: money given ahead of work being done or ahead of an expense being incurred.

Splitting bundled amounts:
- If a single message states an amount that explicitly bundles a wage with a separate cost or \
bonus (e.g. "sending 2200 for the work plus 800 for supplies, 3000 total"), split it into \
separate records -- one per category -- each with the amount that applies to it.
- If a payment is a round-up with no explicit breakdown (e.g. "sending 3200, added a bit extra"), \
infer the regular wage portion from that worker's typical/established amount elsewhere in this \
same conversation, and record the remainder as a bonus.
- If a payment is reduced from the usual amount with a stated reason (e.g. deducting for broken \
equipment), record the actual amount sent under "wage" with a description noting the deduction \
and reason -- don't record the withheld amount as a separate negative record.

For every payment record:
- "phone" must be the exact phone number string from the contacts list below for the worker who \
received the payment. Never use the manager's own phone number.
- "date" is the calendar date (ISO 8601, YYYY-MM-DD) of the message where the payment amount is \
stated, converted from whatever date format the chat export uses.
- "amount" is a positive number in the chat's currency.
- "source_excerpt" is the exact message text (verbatim, not paraphrased) that states the payment \
amount -- this is what a person double-checking your work will search for in the original chat.
- "description" is a short, specific note on what the payment was for, using details mentioned \
nearby in the conversation (what work was done, what was bought, why a bonus was given).

Read the whole conversation before extracting anything, since later messages can explain or \
adjust amounts mentioned earlier (e.g. "we're settled on the nozzle now" refers back to an \
earlier deduction)."""

PAYMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "payments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Exact phone number of the worker paid, from the contacts list",
                    },
                    "date": {
                        "type": "string",
                        "description": "ISO 8601 date (YYYY-MM-DD) the payment was sent",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Positive payment amount",
                    },
                    "category": {
                        "type": "string",
                        "enum": sorted(VALID_CATEGORIES),
                    },
                    "description": {
                        "type": "string",
                        "description": "Short, specific note on what this payment was for",
                    },
                    "source_excerpt": {
                        "type": "string",
                        "description": "Verbatim chat text stating the payment amount",
                    },
                },
                "required": ["phone", "date", "amount", "category", "description", "source_excerpt"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["payments"],
    "additionalProperties": False,
}


def _load_contacts():
    return json.loads(CONTACTS_PATH.read_text(encoding="utf-8"))


def extract_from_chat(client, chat_text, contacts):
    contacts_text = json.dumps(contacts, indent=2, ensure_ascii=False)
    user_message = (
        f"Contacts (phone number, name, role, job category):\n{contacts_text}\n\n"
        f"Chat export:\n{chat_text}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": PAYMENTS_SCHEMA}},
        messages=[{"role": "user", "content": user_message}],
    )

    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)["payments"]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    file_args = [a for a in args if a != "--dry-run"]

    if file_args:
        chat_files = [CHATS_DIR / name for name in file_args]
    else:
        chat_files = sorted(CHATS_DIR.glob("*.txt"))

    contacts = _load_contacts()
    client = anthropic.Anthropic()

    total = 0
    for chat_path in chat_files:
        chat_text = chat_path.read_text(encoding="utf-8")
        payments = extract_from_chat(client, chat_text, contacts)
        print(f"{chat_path.name}: {len(payments)} payment event(s) found")

        for p in payments:
            if dry_run:
                print(f"  [dry-run] {p['date']} {p['phone']} {p['category']} {p['amount']} -- {p['description']}")
            else:
                record_payment(
                    phone=p["phone"],
                    date_str=p["date"],
                    amount=p["amount"],
                    category=p["category"],
                    description=p["description"],
                    source_excerpt=p["source_excerpt"],
                    chat_file=chat_path.name,
                )
            total += 1

    verb = "Would record" if dry_run else "Recorded"
    print(f"{verb} {total} payment event(s) across {len(chat_files)} chat file(s).")


if __name__ == "__main__":
    main()
