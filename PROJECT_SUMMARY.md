# Golden Face Payments Project Summary

## What this is

A system for keeping track of the Golden Face trust's money: what it pays
the people who work on the preserve (pruning and fertilizing, spraying and
pest control, and general upkeep), what it spends on other things
(supplies, vendors, utilities), and what comes in (deposits, donations). The
end result is a dashboard showing a running balance, a breakdown of
payments and expenses, and every transaction traceable back to whatever
document or message it came from.

The project started as a prototype scoped to a single question: payments to
workers, sourced only from WhatsApp conversations where those payments get
mentioned. That prototype is done and preserved as-is (see "Where this
came from" below). The current phase widens it: two new input sources
(bank statements and photographed receipts), and a broader idea of what the
ledger tracks (money in as well as money out, and expenses that have
nothing to do with a worker).

## Where things stand right now

Mid-transition. Specifically:

- **The ledger's shape has been redesigned** but not yet repopulated. Every
  record now has a `transaction_type` (`worker_payment`, `expense`, or
  `income`), a `source` (`whatsapp`, `bank_statement`, or `receipt`), and
  generic `to`/`from` fields instead of assuming every payment goes from
  the manager to a known worker. `tools/record_payment.py` validates
  against this new shape. The categories used for `expense` and `income`
  (e.g. "supplies," "donation") are placeholders; the trust hasn't
  confirmed what categories it actually wants for these yet.
- **`data/payments.json` still holds the old-shape records** from the
  prototype (worker payments only, old field names). It hasn't been
  cleared and regenerated against the new schema yet.
- **The dashboard** (`dashboard/template.html`, built by
  `scripts/build_dashboard.py`) still expects the old field names and will
  need rework once the ledger is regenerated: a balance view (year-to-date
  and since-inception, starting from a zero opening balance), a
  transactions table with `to | from | source | thumbnail` columns, and a
  date-range PDF export are all planned but not built.
- **Only WhatsApp extraction exists** (`scripts/extract_payments.py`).
  There's no extraction pipeline yet for bank statements or receipts,
  because no real sample data for either has arrived yet.
- **Not built at all yet:** an admin view where someone can edit/correct
  records directly (and the audit trail that would need, since this is a
  trust's financial record), and any logic for reconciling the same
  real-world payment if it shows up in more than one source.

## How it's meant to work, step by step

1. A source document gets read: a WhatsApp conversation, a bank statement,
   or a receipt.
2. Any transaction found in it gets pulled out as a record: what kind it
   is (a worker payment, another kind of expense, or incoming money), who
   it went to and came from, how much, a short note on what it was for,
   and a pointer back to exactly where in the source document it came
   from.
3. Each record gets checked before it's accepted: the transaction type and
   category have to be a recognized combination, a worker payment has to
   go to someone in the contacts registry who's actually an employee, and
   the amount has to be a real positive number.
4. Accepted records pile up into a running list, the ledger. This is the
   single source of truth: nothing shows up on the dashboard that isn't in
   this list.
5. The dashboard is built from that list: running balance, totals by
   transaction type, a breakdown per worker and per category, and a full
   table of every transaction with its source attached so it can be
   double-checked against the original document.

## The pieces, in plain terms

- **Contacts list**: a lookup of everyone involved (phone number, name,
  whether they're the manager or a worker, and which job a worker does).
  Only used to validate worker payments; expenses and income don't need
  the person or business on the other end to already be in this list.

- **The extraction step(s)**: reads one source document and pulls out
  every transaction in it. Right now this only exists for WhatsApp;
  bank-statement and receipt extraction haven't been built because there's
  no real sample data yet to design against.

- **The recording step**: takes one transaction's details and checks it
  against the rules above before adding it to the ledger. This is the one
  part of the project meant to stay stable even as everything upstream of
  it changes, whether the details come from a person reading a document by
  hand or from an extraction step.

- **Example conversations**: three fake but realistic WhatsApp exports,
  used to prove the original process worked end to end. No equivalent fake
  bank statements or receipts exist yet.

- **The ledger**: the running list of every accepted transaction. Only
  grows through the recording step above.

- **The dashboard builder**: takes the contacts list and the ledger and
  produces the actual dashboard page. Cheap to re-run: it doesn't re-read
  any source documents, it just re-draws the dashboard from whatever is
  currently in the ledger.

- **The dashboard itself**: the page the manager or trust members would
  actually look at, plus a planned admin version of it that allows edits.

## Where this came from

The original prototype (WhatsApp-only, worker payments only, real LLM
extraction proven against fabricated chat exports) is frozen and
untouched, tagged `v0.1-prototype` and preserved on the `prototype`
branch. All work described above is happening on `main`.

## What's needed to move forward

- **Sample data from Kiran** (bank statements, receipts) — without this,
  extraction logic for those two sources would just be guessing at a
  format.
- **What actually distinguishes an "expense" from a worker "payment"** as
  categories, beyond the placeholder categories currently in
  `record_payment.py`.
- **Whether the same real payment showing up in more than one source**
  (e.g. a WhatsApp message and a matching bank transfer) should become one
  ledger entry or two, and which source wins if they disagree.
- **Whether the planned PDF date-range report is meant to satisfy** the
  Andhra Pradesh tax-purposes requirement mentioned earlier, or if that's
  still a separate, later piece of work.
