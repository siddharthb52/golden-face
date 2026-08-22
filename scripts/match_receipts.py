"""Stage C of the bank-statement pipeline: matches each file in the checks/
folder to the transaction it's evidence for, via the shared NEFT INB
reference code (e.g. "CNAEXBMZK3") that appears on both the bank statement
narration and the receipt/check image or PDF itself.

PDF checks: the code is extracted directly from the PDF's text layer.
Image checks (png/jpg): read via vision, since the code is only visible as
rendered text in the image, not present as machine-readable text.

Transactions with no matching file are left with evidence_file = NULL, by
design -- not every bank transaction has a corresponding check on file.

Usage:
  python scripts/match_receipts.py --dry-run
  python scripts/match_receipts.py
"""
import base64
import json
import re
import sys
from pathlib import Path

import io

import anthropic
import pymupdf
from dotenv import load_dotenv
from PIL import Image
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from db import get_connection  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CHECKS_DIR = ROOT / "data" / "real_docs" / "SandBox-FI" / "checks"
load_dotenv(ROOT / ".env")

MODEL = "claude-opus-5"
CODE_PATTERN = re.compile(r"\bCNA[EF][A-Z0-9]{6}\b")

IMAGE_BATCH_SIZE = 8
MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

CODE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "code": {"type": ["string", "null"]},
                },
                "required": ["filename", "code"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["results"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Each image is a digital payment confirmation slip or receipt. Find the \
10-character reference code printed on it, matching the pattern CNAE or CNAF followed by 6 more \
letters/digits (e.g. "CNAEXBMZK3"). It's usually near the bottom of the slip, sometimes in \
quotes. If no such code is visible anywhere on the image, return null for that file. Return one \
result per image, in the order given, using the exact filename provided for each."""


def code_from_pdf_text(pdf_path):
    """Try the fast path: search the PDF's text layer directly. Returns None
    if the PDF has no usable text layer (a scanned image saved as PDF)."""
    reader = PdfReader(pdf_path)
    text = "\n".join(page.extract_text() for page in reader.pages)
    if len(text.strip()) < 20:
        return "NO_TEXT_LAYER"
    match = CODE_PATTERN.search(text)
    return match.group(0) if match else None


MAX_IMAGE_BYTES = 4 * 1024 * 1024  # stay well under the API's 10 MB limit


def render_pdf_first_page(pdf_path):
    """Render a scanned/text-less PDF's first page to image bytes for vision."""
    doc = pymupdf.open(pdf_path)
    pix = doc[0].get_pixmap(dpi=150)
    return shrink_if_needed(pix.tobytes("png"), "image/png")


def shrink_if_needed(data_bytes, media_type):
    """Downscale an image if it's too large for the API's per-image limit.
    Returns (bytes, media_type) -- media_type changes to JPEG if shrunk."""
    if len(data_bytes) <= MAX_IMAGE_BYTES:
        return data_bytes, media_type
    img = Image.open(io.BytesIO(data_bytes))
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def codes_from_images(client, items):
    """items: list of (display_name, media_type, image_bytes)."""
    content = []
    for name, media_type, data_bytes in items:
        data = base64.standard_b64encode(data_bytes).decode("utf-8")
        content.append({"type": "text", "text": f"Filename: {name}"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})

    with client.messages.stream(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": CODE_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        response = stream.get_final_message()
    text = next(b.text for b in response.content if b.type == "text")
    return {r["filename"]: r["code"] for r in json.loads(text)["results"]}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dry_run = "--dry-run" in sys.argv[1:]

    all_files = sorted(CHECKS_DIR.glob("**/*"))
    pdfs = [p for p in all_files if p.suffix.lower() == ".pdf"]
    images = [p for p in all_files if p.suffix.lower() in MEDIA_TYPES]

    file_codes = {}  # path -> code or None
    needs_vision = []  # (path, display_name, media_type, bytes)

    for p in pdfs:
        result = code_from_pdf_text(p)
        if result == "NO_TEXT_LAYER":
            data_bytes, media_type = render_pdf_first_page(p)
            needs_vision.append((p, p.name, media_type, data_bytes))
        else:
            file_codes[p] = result

    for p in images:
        data_bytes, media_type = shrink_if_needed(p.read_bytes(), MEDIA_TYPES[p.suffix.lower()])
        needs_vision.append((p, p.name, media_type, data_bytes))

    print(f"{len(needs_vision)} file(s) need vision (scanned PDFs + images), "
          f"{len(file_codes)} resolved from PDF text directly.")

    client = anthropic.Anthropic()
    for i in range(0, len(needs_vision), IMAGE_BATCH_SIZE):
        batch = needs_vision[i:i + IMAGE_BATCH_SIZE]
        print(f"Reading {len(batch)} file(s) via vision ({i + len(batch)}/{len(needs_vision)})...")
        results = codes_from_images(client, [(name, mt, data) for _, name, mt, data in batch])
        for p, name, _, _ in batch:
            file_codes[p] = results.get(name)

    conn = get_connection()
    known_codes = {r["neft_inb_code"]: r["id"] for r in conn.execute(
        "SELECT id, neft_inb_code FROM transactions WHERE neft_inb_code IS NOT NULL"
    )}

    matched, unmatched_files, code_not_found = [], [], []
    for path, code in file_codes.items():
        if code is None:
            unmatched_files.append(path)
        elif code in known_codes:
            matched.append((path, code, known_codes[code]))
        else:
            code_not_found.append((path, code))

    print()
    print(f"Matched: {len(matched)} / {len(file_codes)} files")
    print(f"No code found in file: {len(unmatched_files)}")
    print(f"Code found but no matching transaction: {len(code_not_found)}")

    if code_not_found:
        print("\nCodes found with no matching transaction (worth a look):")
        for path, code in code_not_found:
            print(f"  {code}  {path.name}")

    if unmatched_files:
        print("\nFiles with no code detected:")
        for path in unmatched_files:
            print(f"  {path.name}")

    if not dry_run:
        for path, code, txn_id in matched:
            rel_path = str(path.relative_to(ROOT)).replace("\\", "/")
            conn.execute(
                "UPDATE transactions SET evidence_file = ?, evidence_source = 'matched', "
                "updated_at = datetime('now') WHERE id = ?",
                (rel_path, txn_id),
            )
        conn.commit()
        print(f"\nWrote evidence_file for {len(matched)} transaction(s).")
    conn.close()


if __name__ == "__main__":
    main()
