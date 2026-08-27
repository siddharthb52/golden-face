"""Builds a self-contained, local-only HTML dashboard from data/ledger.db.

This embeds thumbnails of real receipt/check images as base64 data URIs
directly in the output file so it can be opened straight from disk with no
server needed. The output file (like ledger.db and real_docs/) must never
be committed or published anywhere -- it contains real financial documents
for an actual charitable trust. See .gitignore.

Usage:
  python scripts/build_ledger_dashboard.py
"""
import base64
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from render_evidence import render_evidence  # noqa: E402

DB_PATH = ROOT / "data" / "ledger.db"
TEMPLATE_PATH = ROOT / "dashboard" / "ledger_template.html"
OUTPUT_PATH = ROOT / "dashboard" / "ledger.html"


def render_images(evidence_path):
    """Returns (thumbnail_data_uri, full_data_uri) for a receipt file (image or PDF).
    The full version is rendered at much higher resolution for the lightbox --
    the thumbnail is not just upscaled, since that would look pixelated."""
    path = ROOT / evidence_path
    thumb_bytes, _ = render_evidence(path, "thumb")
    full_bytes, _ = render_evidence(path, "full")
    thumb_uri = "data:image/jpeg;base64," + base64.standard_b64encode(thumb_bytes).decode("ascii")
    full_uri = "data:image/jpeg;base64," + base64.standard_b64encode(full_bytes).decode("ascii")
    return thumb_uri, full_uri


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM transactions ORDER BY txn_date, id")]
    conn.close()

    print(f"Loaded {len(rows)} transactions.")

    with_evidence = [r for r in rows if r["evidence_file"]]
    print(f"Rendering {len(with_evidence)} thumbnail(s)...")
    for i, r in enumerate(with_evidence, 1):
        try:
            r["thumbnail"], r["full_image"] = render_images(r["evidence_file"])
        except Exception as e:
            print(f"  Failed to render {r['evidence_file']}: {e}")
            r["thumbnail"], r["full_image"] = None, None
        if i % 20 == 0:
            print(f"  {i}/{len(with_evidence)}")
    for r in rows:
        r.setdefault("thumbnail", None)
        r.setdefault("full_image", None)

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.replace("/*__TRANSACTIONS_JSON__*/", json.dumps(rows, ensure_ascii=False))
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(rows)} transactions, {len(with_evidence)} with thumbnails)")


if __name__ == "__main__":
    main()
