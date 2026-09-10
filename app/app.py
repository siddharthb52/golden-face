"""Hosted version of the Golden Face ledger dashboard: same dashboard/
ledger_template.html as the local static build, but served live from the
database behind a single shared-password login, instead of being baked
into a static file opened from disk.

Reuses tools/db.py (works against DATABASE_URL if set, else local
SQLite) and tools/render_evidence.py (thumbnail/full-size receipt
rendering) -- the pipeline scripts (extract/categorize/match) don't
change at all, they just point at the same DATABASE_URL via .env.

Evidence images are served from Cloudflare R2 (tools/r2.py) when
R2_ACCOUNT_ID etc. are set, else fall back to reading data/real_docs/
straight off local disk -- see the /evidence route below.

Requires these environment variables (see .env.example):
  DATABASE_URL           -- Postgres connection string for the hosted DB
  DASHBOARD_PASSWORD_HASH -- output of werkzeug.security.generate_password_hash
  ADMIN_PASSWORD_HASH    -- same, for a second password that logs in with
                          admin (edit/upload/create) privileges; optional
  SESSION_SECRET_KEY     -- random string used to sign the session cookie
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
                          -- Cloudflare R2 evidence storage (optional locally)

Local run:
  python app/app.py
Deployed on Vercel: this file's location (app/app.py, exposing a
top-level `app` Flask instance) is auto-detected, no extra config needed.
"""
import functools
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, redirect, render_template_string, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
# Must run before `from db import DATABASE_URL` below -- db.py reads
# DATABASE_URL from os.environ at import time, so .env has to be loaded
# first or a local run silently falls back to sqlite even with
# DATABASE_URL set in .env (Vercel itself injects env vars before the
# process starts, so this ordering only matters for local runs).
load_dotenv(ROOT / ".env")

from constants import KNOWN_SUBCATEGORIES, REPORTING_CATEGORIES, STATUSES, expense_included_for  # noqa: E402
from db import DATABASE_URL, get_connection  # noqa: E402
from pdf_export import build_pdf  # noqa: E402
from render_evidence import render_evidence, render_evidence_bytes  # noqa: E402
import r2  # noqa: E402

TEMPLATE_PATH = ROOT / "dashboard" / "ledger_template.html"
PASSWORD_HASH = os.environ["DASHBOARD_PASSWORD_HASH"]
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")

EDITABLE_FIELDS = {"purpose", "reporting_category", "sub_category", "status"}
ALLOWED_EVIDENCE_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
REQUIRED_NEW_TXN_FIELDS = {"txn_date", "direction", "amount", "reporting_category", "status", "purpose"}

app = Flask(__name__)
app.secret_key = os.environ["SESSION_SECRET_KEY"]
limiter = Limiter(get_remote_address, app=app, default_limits=[])

LOGIN_HTML = """
<!doctype html>
<title>Golden Face — Login</title>
<style>
  body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
         background: #F5F7F0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }
  form { background: #FBFAF5; border: 1px solid #DCE3D3; border-radius: 10px; padding: 32px 36px;
         box-shadow: 0 4px 14px rgba(31,42,34,0.07); width: 280px; }
  h1 { font-family: ui-serif, Georgia, serif; font-size: 1.5rem; margin: 0 0 4px; }
  h1 .golden { color: #B8862B; }
  p.sub { color: #5B6B5C; font-size: 0.78rem; margin: 0 0 20px; }
  input { width: 100%; box-sizing: border-box; font: inherit; font-size: 0.9rem; padding: 9px 12px;
          border: 1px solid #DCE3D3; border-radius: 6px; margin-bottom: 12px; }
  button { width: 100%; font: inherit; font-size: 0.9rem; padding: 9px 12px; border-radius: 6px;
           border: none; background: #2B5E3F; color: #fff; cursor: pointer; }
  .error { color: #B0453F; font-size: 0.8rem; margin: 0 0 12px; }
</style>
<form method="post">
  <h1><span class="golden">Golden</span> Face</h1>
  <p class="sub">Sri Swarnamukhi Ashrama Ledger</p>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <input type="password" name="password" placeholder="Password" autofocus>
  <button type="submit">Enter</button>
</form>
"""


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authed"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("authed"):
                return redirect(url_for("login", next=request.path))
            if session.get("role") != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def _log_edit(conn, txn_id, field, old_value, new_value):
    conn.execute(
        "INSERT INTO edit_history (txn_id, field, old_value, new_value, edited_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (txn_id, field, str(old_value) if old_value is not None else None,
         str(new_value) if new_value is not None else None, session.get("role", "admin")),
    )


def _store_evidence(txn_id, file_storage):
    """Saves an uploaded evidence file to R2 (pre-rendering thumb/full JPEGs
    the same way scripts/upload_evidence_to_r2.py does, so the /evidence
    route's fast R2 path works immediately) or, without R2 configured, to a
    local data/uploaded/ folder for render_evidence() to handle on demand.
    Returns the evidence_file key to store on the transaction row."""
    ext = Path(file_storage.filename).suffix.lower()
    if ext not in ALLOWED_EVIDENCE_EXT:
        raise ValueError(f"Unsupported file type: {ext or '(none)'}")
    data = file_storage.read()
    safe_name = secure_filename(file_storage.filename) or f"upload{ext}"
    key = f"data/uploaded/{txn_id}_{int(time.time())}_{safe_name}"
    if r2.is_configured():
        r2.upload_object(key, data)
        for size in ("thumb", "full"):
            rendered, _ = render_evidence_bytes(data, ext, size)
            r2.upload_object(f"{key}.{size}.jpg", rendered)
    else:
        local_path = ROOT / key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
    return key


def _fetch_full_image(key):
    """Same lookup /evidence/<id>/full does, reused for PDF appendix images."""
    try:
        if r2.is_configured():
            try:
                return r2.fetch_object(f"{key}.full.jpg")
            except r2.NotFound:
                data, _ = render_evidence_bytes(r2.fetch_object(key), Path(key).suffix, "full")
                return data
        data, _ = render_evidence(ROOT / key, "full")
        return data
    except Exception:
        return None


@app.after_request
def no_index(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "")
        if ADMIN_PASSWORD_HASH and check_password_hash(ADMIN_PASSWORD_HASH, pw):
            session["authed"] = True
            session["role"] = "admin"
            return redirect(request.args.get("next") or url_for("dashboard"))
        if check_password_hash(PASSWORD_HASH, pw):
            session["authed"] = True
            session["role"] = "viewer"
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Incorrect password."
    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    is_admin = session.get("role") == "admin"
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM transactions ORDER BY txn_date, id")]
    conn.close()

    for r in rows:
        if r.get("evidence_file"):
            r["thumbnail"] = url_for("evidence", txn_id=r["id"], size="thumb")
            r["full_image"] = url_for("evidence", txn_id=r["id"], size="full")
        else:
            r["thumbnail"], r["full_image"] = None, None

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.replace("/*__TRANSACTIONS_JSON__*/", json.dumps(rows, ensure_ascii=False))
    html = html.replace("/*__IS_ADMIN__*/", "true" if is_admin else "false")
    html = html.replace("/*__HAS_BACKEND__*/", "true")
    html = html.replace("/*__REPORTING_CATEGORIES_JSON__*/", json.dumps(REPORTING_CATEGORIES))
    html = html.replace("/*__STATUSES_JSON__*/", json.dumps(STATUSES))
    html = html.replace("/*__SUBCATEGORIES_JSON__*/", json.dumps(KNOWN_SUBCATEGORIES))
    return Response(html, mimetype="text/html")


@app.route("/evidence/<int:txn_id>/<size>")
@login_required
def evidence(txn_id, size):
    if size not in ("thumb", "full"):
        abort(404)
    conn = get_connection()
    row = conn.execute(
        "SELECT evidence_file FROM transactions WHERE id = ?", (txn_id,)
    ).fetchone()
    conn.close()
    if not row or not row["evidence_file"]:
        abort(404)

    key = row["evidence_file"]
    if r2.is_configured():
        try:
            # Pre-rendered by scripts/upload_evidence_to_r2.py -- avoids
            # doing CPU-bound PDF rendering on every request.
            return Response(r2.fetch_object(f"{key}.{size}.jpg"), mimetype="image/jpeg")
        except r2.NotFound:
            data, mimetype = render_evidence_bytes(r2.fetch_object(key), Path(key).suffix, size)
    else:
        data, mimetype = render_evidence(ROOT / key, size)
    return Response(data, mimetype=mimetype)


@app.route("/export/pdf", methods=["POST"])
@login_required
def export_pdf():
    payload = request.get_json(silent=True) or {}
    ids = [i for i in (payload.get("ids") or []) if isinstance(i, int)]
    filter_summary = (payload.get("filter_summary") or "All transactions").strip() or "All transactions"
    if not ids:
        return jsonify({"error": "No transactions to export."}), 400

    conn = get_connection()
    placeholders = ",".join("?" for _ in ids)
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM transactions WHERE id IN ({placeholders})", tuple(ids)
    )]
    conn.close()
    if not rows:
        return jsonify({"error": "No transactions to export."}), 400

    order = {txn_id: i for i, txn_id in enumerate(ids)}
    rows.sort(key=lambda r: order.get(r["id"], len(ids)))

    pdf_bytes = build_pdf(rows, filter_summary, _fetch_full_image)
    return Response(
        pdf_bytes, mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=golden-face-ledger.pdf"},
    )


@app.route("/admin/transactions", methods=["POST"])
@role_required("admin")
def admin_create_transaction():
    payload = request.get_json(silent=True) or {}
    missing = REQUIRED_NEW_TXN_FIELDS - payload.keys()
    if missing:
        return jsonify({"error": f"Missing required field(s): {', '.join(sorted(missing))}"}), 400
    if payload["direction"] not in ("debit", "credit"):
        return jsonify({"error": "direction must be 'debit' or 'credit'."}), 400
    if payload["reporting_category"] not in REPORTING_CATEGORIES:
        return jsonify({"error": "Invalid reporting_category."}), 400
    if payload["status"] not in STATUSES:
        return jsonify({"error": "Invalid status."}), 400
    try:
        amount = float(payload["amount"])
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid amount."}), 400

    txn_date = payload["txn_date"]
    expense_included = int(expense_included_for(payload["reporting_category"], payload["direction"]))
    insert_sql = """INSERT INTO transactions
           (txn_date, value_date, direction, amount, to_party, from_party, reporting_category,
            sub_category, expense_included, status, purpose, bank_narration, source_document)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    params = (
        txn_date, payload.get("value_date") or txn_date, payload["direction"], amount,
        payload.get("to_party") or None, payload.get("from_party") or None,
        payload["reporting_category"], payload.get("sub_category") or None, expense_included,
        payload["status"], payload["purpose"], "Manually entered by admin", "manual",
    )

    conn = get_connection()
    if DATABASE_URL:
        cur = conn.execute(insert_sql + " RETURNING id", params)
        new_id = cur.fetchone()["id"]
    else:
        cur = conn.execute(insert_sql, params)
        new_id = cur.lastrowid
    _log_edit(conn, new_id, "created", None, "Transaction created by admin")
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": new_id})


@app.route("/admin/transactions/<int:txn_id>", methods=["POST"])
@role_required("admin")
def admin_edit_transaction(txn_id):
    payload = request.get_json(silent=True) or {}
    updates = {k: v for k, v in payload.items() if k in EDITABLE_FIELDS}
    if not updates:
        return jsonify({"error": "No editable fields provided."}), 400
    if "reporting_category" in updates and updates["reporting_category"] not in REPORTING_CATEGORIES:
        return jsonify({"error": "Invalid reporting_category."}), 400
    if "status" in updates and updates["status"] not in STATUSES:
        return jsonify({"error": "Invalid status."}), 400

    conn = get_connection()
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
    if not row:
        conn.close()
        abort(404)
    row = dict(row)

    if "reporting_category" in updates:
        updates["expense_included"] = int(expense_included_for(updates["reporting_category"], row["direction"]))

    changed = {f: v for f, v in updates.items() if str(row.get(f)) != str(v)}
    for field, new_value in changed.items():
        _log_edit(conn, txn_id, field, row.get(field), new_value)

    if changed:
        set_clause = ", ".join(f"{f} = ?" for f in changed) + ", updated_at = datetime('now')"
        conn.execute(f"UPDATE transactions SET {set_clause} WHERE id = ?", (*changed.values(), txn_id))
        conn.commit()
    conn.close()
    return jsonify({"ok": True, "fields": changed})


@app.route("/admin/transactions/<int:txn_id>/evidence", methods=["POST"])
@role_required("admin")
def admin_upload_evidence(txn_id):
    file_storage = request.files.get("file")
    if not file_storage or not file_storage.filename:
        return jsonify({"error": "No file provided."}), 400

    conn = get_connection()
    row = conn.execute("SELECT id, evidence_file FROM transactions WHERE id = ?", (txn_id,)).fetchone()
    if not row:
        conn.close()
        abort(404)

    try:
        key = _store_evidence(txn_id, file_storage)
    except ValueError as e:
        conn.close()
        return jsonify({"error": str(e)}), 400

    old_value = row["evidence_file"]
    conn.execute(
        "UPDATE transactions SET evidence_file = ?, evidence_source = 'uploaded', "
        "updated_at = datetime('now') WHERE id = ?",
        (key, txn_id),
    )
    _log_edit(conn, txn_id, "evidence_file", old_value, key)
    conn.commit()
    conn.close()
    return jsonify({
        "ok": True,
        "thumbnail": url_for("evidence", txn_id=txn_id, size="thumb"),
        "full_image": url_for("evidence", txn_id=txn_id, size="full"),
    })


@app.route("/admin/transactions/<int:txn_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_transaction(txn_id):
    conn = get_connection()
    row = conn.execute("SELECT id FROM transactions WHERE id = ?", (txn_id,)).fetchone()
    if not row:
        conn.close()
        abort(404)
    conn.execute("DELETE FROM edit_history WHERE txn_id = ?", (txn_id,))
    conn.execute("DELETE FROM transactions WHERE id = ?", (txn_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
