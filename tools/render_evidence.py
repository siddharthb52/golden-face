"""Renders a receipt/check file (image or PDF) to JPEG bytes at either
thumbnail or full-view size. Shared by scripts/build_ledger_dashboard.py
(the static, local-only build) and server/app.py (the hosted deployment's
on-demand /evidence route), so both produce the same-looking images from
one place.
"""
import io

import pymupdf
from PIL import Image

THUMB_SIZE = (220, 220)
FULL_SIZE = (1600, 1600)
SIZES = {"thumb": (THUMB_SIZE, 80), "full": (FULL_SIZE, 90)}


def render_evidence(path, size):
    """path: filesystem Path to the evidence file. size: 'thumb' or 'full'.
    Returns (jpeg_bytes, mimetype). For local files only -- see
    render_evidence_bytes for evidence fetched from R2."""
    return render_evidence_bytes(path.read_bytes(), path.suffix, size)


def render_evidence_bytes(data, suffix, size):
    """data: raw file bytes. suffix: e.g. '.pdf' or '.jpg', to tell a scanned
    PDF from a plain image. size: 'thumb' or 'full'. Returns (jpeg_bytes, mimetype)."""
    max_size, quality = SIZES[size]

    if suffix.lower() == ".pdf":
        doc = pymupdf.open(stream=data, filetype="pdf")
        pix = doc[0].get_pixmap(dpi=200)
        source = Image.open(io.BytesIO(pix.tobytes("png")))
    else:
        source = Image.open(io.BytesIO(data))

    img = source.copy()
    img.thumbnail(max_size, Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue(), "image/jpeg"
