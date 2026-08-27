# Golden Face

Golden Face turns a forest and garden sanctuary's real financial records into a
reviewable dashboard. It reads the sanctuary's SBI bank statements as the
source of truth for every transaction, categorizes each one, and matches it
back to its supporting check or receipt wherever one exists, so anyone
reviewing the ledger can see not just what was paid but the actual proof
behind it, one click away.

## What's in the repo

- `tools/db.py` sets up the SQLite ledger.
- `scripts/extract_bank_statements.py` reads a raw SBI statement PDF and
  extracts every transaction line.
- `scripts/categorize_transactions.py` assigns each transaction a category
  from the bank narration alone.
- `scripts/match_receipts.py` matches transactions to their check/receipt
  files in `data/real_docs/`, via the reference code shared by both.
- `scripts/build_ledger_dashboard.py` builds the dashboard as a single
  self-contained HTML file, with thumbnails of matched receipts embedded
  directly in it.

## Setup

1. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

2. Add your Anthropic API key. Copy `.env.example` to `.env` and fill in
   `ANTHROPIC_API_KEY`.

3. Get the real financial documents. These are not in the repo (they contain
   real account numbers and other financial details for an actual trust, so
   they're intentionally gitignored). Place them at:

   ```
   data/real_docs/SandBox-FI/
   ```

   `scripts/match_receipts.py` specifically expects a `checks/` folder at
   `data/real_docs/SandBox-FI/checks/` (it searches that folder and its
   subfolders recursively, so how you organize things underneath it doesn't
   matter). Bank statement PDFs can live anywhere, since you pass their path
   directly to the extraction script.

## Building the dashboard

Run these in order:

```
python scripts/extract_bank_statements.py <path-to-statement-1.pdf> <path-to-statement-2.pdf> ...
python scripts/categorize_transactions.py
python scripts/match_receipts.py
python scripts/build_ledger_dashboard.py
```

The first command creates `data/ledger.db` automatically if it doesn't exist
yet. Each script can be run with `--dry-run` first to preview what it would
do without writing anything.

Then open `dashboard/ledger.html` directly in a browser. No server needed.

`data/ledger.db` and `dashboard/ledger.html` are also gitignored, since both
end up holding real financial data once built. Rebuilding is cheap: rerun
`build_ledger_dashboard.py` any time `ledger.db` changes.

## Hosting a shared, password-protected copy

`server/app.py` serves the same dashboard live from a database, behind a
login, instead of a static file you build and open locally. Use this when
the dashboard needs to be reachable at a URL by people other than you. The
deployment stack is Vercel (runs the app), Neon (Postgres), and Cloudflare
(DNS/CDN in front of the domain, plus R2 for storing the receipt/check
files themselves).

1. Provision a Postgres database on Neon and set `DATABASE_URL` in `.env`
   to its connection string.
2. Pick a password and set `DASHBOARD_PASSWORD_HASH` in `.env`:
   ```
   python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('yourpassword'))"
   ```
3. Set `SESSION_SECRET_KEY` in `.env`:
   ```
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
4. If you already have data in the local `data/ledger.db`, copy it into the
   new Postgres database once:
   ```
   python scripts/migrate_to_postgres.py
   ```
   From this point on, run the pipeline scripts (`extract_bank_statements.py`,
   `categorize_transactions.py`, `match_receipts.py`) with `DATABASE_URL` set
   and they'll write directly to the hosted database instead of the local
   file -- no separate sync step.
5. Create a Cloudflare R2 bucket and an R2 API token (Cloudflare dashboard
   -> R2 -> Manage R2 API Tokens), then set `R2_ACCOUNT_ID`,
   `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET_NAME` in
   `.env`. Upload the existing receipt/check files once (this also
   pre-renders each file's thumbnail and full-size preview locally and
   uploads those too, so the hosted server never has to do that CPU-bound
   work per-request):
   ```
   python scripts/upload_evidence_to_r2.py
   ```
   `server/app.py`'s `/evidence` route reads from R2 automatically once
   those four variables are set; leave them unset for local runs and it
   reads `data/real_docs/` off disk instead, so R2 is opt-in and doesn't
   affect local pipeline runs or `build_ledger_dashboard.py`.
6. Run the server locally to test:
   ```
   python server/app.py
   ```
   and open `http://localhost:5000`.
7. To deploy: import the repo into Vercel. `pyproject.toml`'s
   `[tool.vercel] entrypoint` tells Vercel where the Flask `app` object
   lives (`server/app.py`); no `Procfile` or gunicorn needed, Vercel runs
   the WSGI app directly as a Vercel Function. Set `ANTHROPIC_API_KEY`,
   `DATABASE_URL`, `DASHBOARD_PASSWORD_HASH`, `SESSION_SECRET_KEY`, and
   the four `R2_*` variables in the project's Environment Variables
   settings. Then point a domain at it through Cloudflare for HTTPS/CDN.

The hosted app is intentionally not indexable (`robots.txt`, `noindex`
headers) and rate-limits login attempts, but a shared password over the
open internet is still weaker than per-person accounts -- treat the
password itself as sensitive, and rotate it if it's ever shared beyond the
people who should have it. Note that on Vercel specifically, the login
rate limit relies on in-memory state that Vercel's Fluid compute doesn't
strictly guarantee is shared across every request (it usually is, for a
low-traffic app, since idle instances get reused, but it's not a hard
guarantee the way it was on a single persistent server process) -- the
real protection is still the password hash itself, not the rate limit.

Admin features (editing transactions, uploading evidence from the browser)
aren't built yet -- this is read-only. Corrections still happen the same
way they do locally: fix the row in the database, or fix it upstream in the
pipeline and re-run.
