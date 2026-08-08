"""Regenerate dashboard/index.html from the current contacts + payments data.

Run this any time data/payments.json changes (e.g. after record_payment()
calls from a new batch of extracted messages), then re-publish
dashboard/index.html as the Artifact.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "dashboard" / "template.html"
OUTPUT_PATH = ROOT / "dashboard" / "index.html"
CONTACTS_PATH = ROOT / "data" / "contacts.json"
PAYMENTS_PATH = ROOT / "data" / "payments.json"


def main():
    contacts = json.loads(CONTACTS_PATH.read_text(encoding="utf-8"))
    payments = json.loads(PAYMENTS_PATH.read_text(encoding="utf-8"))

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.replace("/*__CONTACTS_JSON__*/", json.dumps(contacts, ensure_ascii=False))
    html = html.replace("/*__PAYMENTS_JSON__*/", json.dumps(payments, ensure_ascii=False))

    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(payments)} payments, {len(contacts)} contacts)")


if __name__ == "__main__":
    main()
