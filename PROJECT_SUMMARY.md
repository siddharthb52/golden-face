# Golden Mouth Payments Project — Summary

## What this is

A system for keeping track of what the Golden Mouth manager pays the people
who work on the preserve — pruning and fertilizing, spraying and pest
control, and general upkeep — based on the WhatsApp conversations where
those payments get mentioned. The end result is a dashboard showing who's
been paid, how much, for what, and when, with every number traceable back to
the exact message it came from.

Right now the whole thing runs on made-up example conversations, written to
look like real WhatsApp exports. The goal was to build and prove out the
full process — reading a conversation, pulling out the payments, and turning
that into a working dashboard — before connecting it to anything real.

## How it works, step by step

1. A conversation between the manager and a worker gets read, message by
   message.
2. Any time a payment is mentioned, it gets pulled out as a record: who it
   went to, how much, what kind of payment it was (regular pay, a bonus,
   money paid back for supplies bought out of pocket, or an advance), a
   short note on what it was for, and the exact line from the chat it came
   from.
3. Each of those records gets checked before it's accepted — rejected if the
   phone number isn't recognized, if it's somehow being sent to the manager
   instead of a worker, if the payment type isn't one of the four allowed
   kinds, or if the amount isn't a real positive number.
4. Accepted records pile up into a running list — the ledger. This is the
   single source of truth: nothing shows up on the dashboard that isn't in
   this list.
5. The dashboard is built from that list: total paid, a breakdown per
   worker, a breakdown by payment type, a week-by-week spending chart, and a
   full table of every individual payment with its source line attached so
   it can be double-checked against the original conversation.

**Important limitation right now:** step 2 — actually reading the
conversation and deciding what counts as a payment — is being done by hand
(by me, reading the example chats). Nothing in the project does that
automatically yet. That's a separate piece of work from the message
retrieval question below, and worth deciding on once retrieval is settled.

## The pieces, in plain terms

- **Contacts list** — a simple lookup of everyone involved: phone number,
  name, whether they're the manager or a worker, and which job a worker
  does. This exists because real WhatsApp identifies people by phone
  number, not by the name saved in a contact list, so everything downstream
  keys off phone number.

- **The recording step** — takes one payment's details and checks it against
  the rules above before adding it to the ledger. This is the one part of
  the project meant to stay exactly as-is even after everything upstream of
  it changes — whether the payment details come from me reading a chat by
  hand, or from something automated later, this step doesn't change.

- **Example conversations** — three fake but realistic WhatsApp exports
  standing in for real ones, used to prove the process works end to end.

- **The ledger** — the running list of every accepted payment. Starts empty
  and only grows through the recording step above.

- **The dashboard builder** — takes the contacts list and the ledger and
  produces the actual dashboard page. This step is cheap to re-run — it
  doesn't re-read any conversations, it just re-draws the dashboard from
  whatever is currently in the ledger. Run it any time the ledger changes,
  and the dashboard is caught up.

- **The dashboard itself** — the page the manager or trust members would
  actually look at.

## What's proven vs. what's still a placeholder

**Proven and working:** the recording rules, the ledger, and the dashboard.
These would work the same way on real data as they do on the made-up
example.

**Still a placeholder:** the very first step — getting messages out of
WhatsApp in the first place, and reading through them to spot payments.
Right now that's entirely manual, done once, on fake data.

## What's needed to move forward

The single biggest open decision is **how we actually get real messages out
of WhatsApp.** This decides how the "reading" step gets built, so nothing
past that point can be finalized until it's picked. Three realistic ways to
do it:

1. **Manual export** — someone (the manager) periodically uses WhatsApp's
   built-in "export chat" feature and hands over the text file. Simplest
   and safest option, no setup required, but it's a manual step someone has
   to remember to do and it isn't live — the dashboard is only ever as
   current as the last export.

2. **WhatsApp's official business tools** — the legitimate, sanctioned way
   to send and receive WhatsApp messages through code. The catch is it's
   built for a business messaging its customers, not for reading an
   existing personal or group conversation, so using it here would mean
   setting up a registered business account and likely having everyone
   involved message a new number — a lot of setup for what we need.

3. **Unofficial automation** — software that logs into a real WhatsApp
   account (via a QR code scan, the same way WhatsApp Web works) and reads
   messages as they arrive, automatically, no export needed. Much easier to
   set up than the official route, but it goes against WhatsApp's terms of
   service, and carries a small risk of that phone number getting flagged.
   Reasonable for a prototype, riskier as something to depend on long-term.

**Why this decision matters beyond just "how do messages arrive":** once
real messages are flowing in, the reading step needs to know which messages
it's already gone through, so it doesn't re-read the same conversation from
the beginning every time and accidentally record the same payment twice.
How that gets built depends entirely on the shape of the answer above — a
manual export needs a different approach (each export is the whole history
again, so we need to know where we left off) than a live automated feed
would (new messages arrive one at a time, so a duplicate could happen for a
different reason — a message getting delivered twice). This piece is
deliberately not built yet, since building it before knowing which of the
three above applies would mean guessing.

## Suggested next step

Decide which of the three retrieval methods to use — and it's fine for that
to start as the manual export while everything else gets proven out further,
then move to something automated later once the rest of the system has been
trusted with real data.
