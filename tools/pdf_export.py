"""Builds a structured PDF export of the ledger's current (filtered)
view for app/app.py's /export/pdf route: a financial-report-style header
and summary, a real table (not a screenshot), and an appendix of full-size
evidence images referenced from the table's Proof column as "See Appendix
p.N".

Page numbers for "See Appendix p.N" aren't known until the whole document
is laid out, and the appendix comes after the table, so this builds the
document twice: pass 1 lays out the real content once to record which
page each transaction's appendix entry lands on (via _PageAnchor markers
and _TrackingDocTemplate.afterFlowable), pass 2 rebuilds it for real using
those recorded page numbers in the Proof column.
"""
import io
from xml.sax.saxutils import escape

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image as RLImage,
                                 PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

TRUST_NAME = "Sri Swarnamukhi Ashrama"
PAGE_SIZE = landscape(A4)
MARGIN = 15 * mm

COL_WIDTHS = [18 * mm, 32 * mm, 32 * mm, 20 * mm, 28 * mm, 28 * mm, 26 * mm, 45 * mm, 20 * mm]

_styles = getSampleStyleSheet()
CELL = ParagraphStyle("cell", parent=_styles["Normal"], fontSize=7.5, leading=9.5)
HEADER_CELL = ParagraphStyle("header_cell", parent=_styles["Normal"], fontSize=7.5,
                              leading=9.5, textColor=colors.white, fontName="Helvetica-Bold")
TITLE = ParagraphStyle("title", parent=_styles["Heading1"], fontSize=18, spaceAfter=2)
SUBTITLE = ParagraphStyle("subtitle", parent=_styles["Normal"], fontSize=10,
                           textColor=colors.HexColor("#5B6B5C"), spaceAfter=10)
SUMMARY_LABEL = ParagraphStyle("summary_label", parent=_styles["Normal"], fontSize=7.5,
                                textColor=colors.HexColor("#5B6B5C"))
SUMMARY_VALUE = ParagraphStyle("summary_value", parent=_styles["Heading3"], fontSize=13, spaceBefore=1)
APPENDIX_HEADING = ParagraphStyle("appendix_heading", parent=_styles["Heading2"], fontSize=13)
APPENDIX_META = ParagraphStyle("appendix_meta", parent=_styles["Normal"], fontSize=9, spaceAfter=6)


def _esc(value):
    return escape(str(value)) if value else ""


def _fmt_inr(amount):
    return f"Rs. {round(amount):,}"


def _fmt_date(iso_date):
    try:
        y, m, d = iso_date.split("-")
        months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return f"{int(d)} {months[int(m)]} {y}"
    except Exception:
        return iso_date or ""


class _PageAnchor(Flowable):
    """Zero-size marker inserted right before each appendix entry so
    _TrackingDocTemplate.afterFlowable can record which page it landed on."""

    def __init__(self, key):
        Flowable.__init__(self)
        self.key = key
        self.width = 0
        self.height = 0

    def draw(self):
        pass


class _TrackingDocTemplate(BaseDocTemplate):
    def __init__(self, *args, **kwargs):
        BaseDocTemplate.__init__(self, *args, **kwargs)
        self.page_map = {}

    def afterFlowable(self, flowable):
        if isinstance(flowable, _PageAnchor):
            self.page_map[flowable.key] = self.canv.getPageNumber()


def _summary_figures(rows):
    income = sum(r["amount"] for r in rows if r["direction"] == "credit"
                 and r.get("reporting_category") == "Income")
    expenses = sum(r["amount"] for r in rows if r["direction"] == "debit" and r.get("expense_included"))
    with_evidence = sum(1 for r in rows if r.get("evidence_file"))
    return income, expenses, income - expenses, with_evidence, len(rows)


def _scaled_image(image_bytes, max_w, max_h):
    w, h = Image.open(io.BytesIO(image_bytes)).size
    scale = min(max_w / w, max_h / h, 1.0) if w and h else 1.0
    img = RLImage(io.BytesIO(image_bytes), width=w * scale, height=h * scale)
    return img


def _build_story(rows, filter_summary, image_cache, fetch_full_image, page_map):
    story = []

    story.append(Paragraph("Golden Face &#183; Financial Report", TITLE))
    story.append(Paragraph(f"{_esc(TRUST_NAME)} &#183; {_esc(filter_summary)}", SUBTITLE))

    income, expenses, balance, with_evidence, total = _summary_figures(rows)
    summary_data = [
        [Paragraph("Income", SUMMARY_LABEL), Paragraph("Expenses", SUMMARY_LABEL),
         Paragraph("Balance", SUMMARY_LABEL), Paragraph("With Proof", SUMMARY_LABEL)],
        [Paragraph(_fmt_inr(income), SUMMARY_VALUE), Paragraph(_fmt_inr(expenses), SUMMARY_VALUE),
         Paragraph(_fmt_inr(balance), SUMMARY_VALUE), Paragraph(f"{with_evidence} / {total}", SUMMARY_VALUE)],
    ]
    summary_table = Table(summary_data, colWidths=[65 * mm] * 4)
    summary_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#B8862B")),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10 * mm))

    header = [Paragraph(h, HEADER_CELL) for h in
              ["Date", "To", "From", "Amount", "Category", "Sub-category", "Status", "Purpose", "Proof"]]
    table_rows = [header]
    for r in rows:
        if r.get("evidence_file"):
            proof_text = f"See Appendix p.{page_map[r['id']]}" if r["id"] in page_map else "See Appendix"
        else:
            proof_text = "—"
        amount_text = f"{'+' if r['direction'] == 'credit' else '-'}{_fmt_inr(r['amount'])}"
        table_rows.append([
            Paragraph(_fmt_date(r["txn_date"]), CELL),
            Paragraph(_esc(r.get("to_party")) or "—", CELL),
            Paragraph(_esc(r.get("from_party")) or "—", CELL),
            Paragraph(amount_text, CELL),
            Paragraph(_esc(r.get("reporting_category")) or "—", CELL),
            Paragraph(_esc(r.get("sub_category")) or "—", CELL),
            Paragraph(_esc(r.get("status")) or "—", CELL),
            Paragraph(_esc(r.get("purpose") or r.get("bank_narration")) or "", CELL),
            Paragraph(proof_text, CELL),
        ])

    table = Table(table_rows, colWidths=COL_WIDTHS, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B5E3F")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DCE3D3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7F0")]),
    ]))
    story.append(table)

    evidence_rows = [r for r in rows if r.get("evidence_file")]
    if evidence_rows:
        story.append(PageBreak())
        story.append(Paragraph("Appendix &#183; Proof of Payment", APPENDIX_HEADING))
        story.append(Spacer(1, 4 * mm))
        for i, r in enumerate(evidence_rows):
            story.append(_PageAnchor(r["id"]))
            ref = r.get("neft_inb_code") or f"TXN {r['id']}"
            meta = (f"Ref {_esc(ref)} &#183; {_fmt_date(r['txn_date'])} &#183; "
                    f"{_esc(r.get('to_party') or r.get('from_party'))} &#183; {_fmt_inr(r['amount'])}")
            story.append(Paragraph(meta, APPENDIX_META))
            key = r["evidence_file"]
            if key not in image_cache:
                image_cache[key] = fetch_full_image(key)
            image_bytes = image_cache[key]
            if image_bytes:
                available_w = PAGE_SIZE[0] - 2 * MARGIN
                available_h = PAGE_SIZE[1] - 2 * MARGIN - 25 * mm
                story.append(_scaled_image(image_bytes, available_w, available_h))
            if i < len(evidence_rows) - 1:
                story.append(PageBreak())

    return story


def _make_doc(buf):
    doc = _TrackingDocTemplate(
        buf, pagesize=PAGE_SIZE,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
        title="Golden Face Financial Report",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame])])
    return doc


def build_pdf(rows, filter_summary, fetch_full_image):
    """rows: list of transaction dicts (already scoped to the caller's active
    filters). filter_summary: human-readable description of those filters for
    the header. fetch_full_image: callable(evidence_file_key) -> jpeg bytes or
    None, used to pull each appendix image (see app.py's evidence route for
    the equivalent R2/local logic this should reuse)."""
    image_cache = {}

    pass1_buf = io.BytesIO()
    doc1 = _make_doc(pass1_buf)
    doc1.build(_build_story(rows, filter_summary, image_cache, fetch_full_image, page_map={}))

    pass2_buf = io.BytesIO()
    doc2 = _make_doc(pass2_buf)
    doc2.build(_build_story(rows, filter_summary, image_cache, fetch_full_image, page_map=doc1.page_map))

    return pass2_buf.getvalue()
