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
