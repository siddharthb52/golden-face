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
import io
import json
import sqlite3
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "ledger.db"
TEMPLATE_PATH = ROOT / "dashboard" / "ledger_template.html"
OUTPUT_PATH = ROOT / "dashboard" / "ledger.html"

THUMB_SIZE = (220, 220)
FULL_SIZE = (1600, 1600)


def _data_uri(img, quality):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    encoded = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def render_images(evidence_path):
    """Returns (thumbnail_data_uri, full_data_uri) for a receipt file (image or PDF).
    The full version is rendered at much higher resolution for the lightbox --
    the thumbnail is not just upscaled, since that would look pixelated."""
    path = ROOT / evidence_path
    if path.suffix.lower() == ".pdf":
        doc = pymupdf.open(path)
        pix = doc[0].get_pixmap(dpi=200)
        source = Image.open(io.BytesIO(pix.tobytes("png")))
    else:
        source = Image.open(path)

    full_img = source.copy()
    full_img.thumbnail(FULL_SIZE, Image.LANCZOS)
    full_uri = _data_uri(full_img, 90)

    thumb_img = source.copy()
    thumb_img.thumbnail(THUMB_SIZE, Image.LANCZOS)
    thumb_uri = _data_uri(thumb_img, 80)

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
