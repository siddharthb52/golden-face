"""Placeholder extraction for receipts -- NOT real parsing.

Exists to validate that record_payment() correctly handles source="receipt"
with transaction_type="expense". Reads a simple hand-invented key: value
mock format, not anything resembling real OCR/vision output on a
photographed receipt.

Real receipt extraction (almost certainly vision-based, reading an actual
photo) is deferred until Kiran's real sample data arrives -- see
PROJECT_SUMMARY.md.

Usage:
  python scripts/extract_receipts.py                  # process every file in data/sample_receipts/
  python scripts/extract_receipts.py hardware_receipt_2026-06-10.txt
  python scripts/extract_receipts.py --dry-run
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from record_payment import record_payment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RECEIPTS_DIR = ROOT / "data" / "sample_receipts"


def parse_receipt(text):
    fields = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    file_args = [a for a in args if a != "--dry-run"]

    if file_args:
        receipt_files = [RECEIPTS_DIR / name for name in file_args]
    else:
        receipt_files = sorted(RECEIPTS_DIR.glob("*.txt"))

    total = 0
    for path in receipt_files:
        fields = parse_receipt(path.read_text(encoding="utf-8"))
        amount = float(fields["amount"])

        if dry_run:
            print(
                f"[dry-run] {path.name}: {fields['date']} expense {fields['category']} "
                f"{amount} -- {fields['item']}"
            )
        else:
            record_payment(
                transaction_type="expense",
                date_str=fields["date"],
                amount=amount,
                category=fields["category"],
                description=fields["item"],
                source="receipt",
                source_file=path.name,
                to=fields["vendor"],
                source_excerpt=None,
                evidence_thumbnail=path.name,
            )
        total += 1

    verb = "Would record" if dry_run else "Recorded"
    print(f"{verb} {total} receipt(s) across {len(receipt_files)} receipt file(s).")


if __name__ == "__main__":
    main()
