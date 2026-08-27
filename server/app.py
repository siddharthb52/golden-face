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
  SESSION_SECRET_KEY     -- random string used to sign the session cookie
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
                          -- Cloudflare R2 evidence storage (optional locally)

Local run:
  python server/app.py
Production (e.g. Render/Railway):
  gunicorn server.app:app
"""
import functools
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, abort, redirect, render_template_string, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from db import get_connection  # noqa: E402
from render_evidence import render_evidence, render_evidence_bytes  # noqa: E402
import r2  # noqa: E402

load_dotenv(ROOT / ".env")

TEMPLATE_PATH = ROOT / "dashboard" / "ledger_template.html"
PASSWORD_HASH = os.environ["DASHBOARD_PASSWORD_HASH"]

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
        if check_password_hash(PASSWORD_HASH, request.form.get("password", "")):
            session["authed"] = True
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


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
