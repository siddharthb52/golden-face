"""One-off extraction run over the sample WhatsApp exports in
data/sample_chats/. This plays the role an LLM-driven pipeline would play:
read each conversation, identify payment events, and call record_payment()
once per event with structured fields pulled from the message context.

Where a single message bundles a wage with a reimbursement/bonus (e.g.
"Sending Rs. 2200 for the work plus Rs. 800 for supplies, Rs. 3000 total"),
it is split into separate records so the dashboard's category breakdown
is meaningful. Where a bonus/deduction is folded into one number without an
explicit split (e.g. "Sending 3200, added a bit extra"), the wage portion is
inferred from that employee's established base rate and the remainder is
recorded as a bonus. Money handed to third parties out of petty cash (e.g.
Lakshmi paying the tank-cleaning workers) is not a payment to the employee
and is intentionally excluded.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from record_payment import record_payment  # noqa: E402

RAMESH = "+91 98450 11202"
SURESH = "+91 98450 11203"
LAKSHMI = "+91 98450 11204"

RAMESH_FILE = "ramesh_pruning_fertilizing.txt"
SURESH_FILE = "suresh_spraying_pest_control.txt"
LAKSHMI_FILE = "lakshmi_general_maintenance.txt"

records = [
    # --- Ramesh: pruning & fertilizing ---
    (RAMESH, "2026-06-06", 3000, "wage",
     "Weekly pruning + fertilizing (hedge, 6 guava trees)",
     "Sending ₹3000 for this week's pruning and fertilizing work", RAMESH_FILE),
    (RAMESH, "2026-06-13", 3000, "wage",
     "Weekly pruning (roses, mango saplings)",
     "Sending ₹3000 for the week", RAMESH_FILE),
    (RAMESH, "2026-06-27", 3000, "wage",
     "Backlog pruning + fertilizing + composting after leave",
     "Sending ₹3000 for the week plus ₹500 for the manure you bought, total ₹3500", RAMESH_FILE),
    (RAMESH, "2026-06-27", 500, "reimbursement",
     "Cow dung manure bought out of pocket while stock was low",
     "Also bought extra cow dung manure since we were low, spent ₹500 from my pocket", RAMESH_FILE),
    (RAMESH, "2026-07-04", 3000, "wage",
     "Pruning + fertilizing rose beds ahead of trust visit",
     "Sending ₹3000 for the week", RAMESH_FILE),
    (RAMESH, "2026-07-11", 3000, "wage",
     "Regular weekly pruning/fertilizing",
     "Sending ₹3200 for the week, added a bit extra for the hibiscus", RAMESH_FILE),
    (RAMESH, "2026-07-11", 200, "bonus",
     "Bonus for hibiscus row praised by visiting trust members",
     "Trust members loved the hibiscus row, they mentioned it specifically", RAMESH_FILE),
    (RAMESH, "2026-07-18", 3000, "wage",
     "Neem oil treatment on mango tree bases + guava pruning",
     "Sending ₹3000 for the week", RAMESH_FILE),
    (RAMESH, "2026-07-25", 3000, "wage",
     "Regular pruning/fertilizing + boundary hedge",
     "Sending ₹3000 for this week", RAMESH_FILE),
    (RAMESH, "2026-08-01", 3000, "wage",
     "Drainage clearing near rose beds + rose pruning + guava fertilizing",
     "Sending ₹3000 for the week", RAMESH_FILE),

    # --- Suresh: spraying & pest control ---
    (SURESH, "2026-06-07", 2500, "wage",
     "Mosquito fogging (pond/compost/shed) + detergent spray (roses, hibiscus); includes fogging fuel",
     "Sending Rs. 2500 for the fogging fuel and spraying this week", SURESH_FILE),
    (SURESH, "2026-06-14", 2200, "wage",
     "Detergent spray on mango saplings and guava trees",
     "Sending Rs. 2200 for the week", SURESH_FILE),
    (SURESH, "2026-06-21", 2200, "wage",
     "Regular detergent spraying",
     "Sending Rs. 2200 for the work plus Rs. 800 for supplies, Rs. 3000 total", SURESH_FILE),
    (SURESH, "2026-06-21", 800, "reimbursement",
     "Detergent concentrate (2 bottles) + mosquito coils bought out of pocket",
     "Bought 2 bottles of detergent concentrate and coils, Rs. 800", SURESH_FILE),
    (SURESH, "2026-06-28", 2200, "wage",
     "Regular spraying; found and cleared standing water near shed",
     "Sending Rs. 2200 for the week", SURESH_FILE),
    (SURESH, "2026-07-07", 2200, "wage",
     "Double-dose spraying + extra fogging after rain delay",
     "Sending Rs. 2800 for the week, extra for the overtime and double dose", SURESH_FILE),
    (SURESH, "2026-07-07", 600, "bonus",
     "Overtime for covering the property twice + extra pond fogging after the rain delay",
     "Sending Rs. 2800 for the week, extra for the overtime and double dose", SURESH_FILE),
    (SURESH, "2026-07-12", 2200, "wage",
     "Regular spraying, checked shed for standing water",
     "Sending Rs. 2200 for the week", SURESH_FILE),
    (SURESH, "2026-07-19", 1700, "wage",
     "Regular spraying; reduced by Rs. 500, splitting cost of the fogging machine nozzle he broke",
     "Sending Rs. 1700 this week instead of Rs. 2200, we'll settle the rest later", SURESH_FILE),
    (SURESH, "2026-07-26", 2200, "wage",
     "Regular spraying; nozzle cost now settled",
     "Sending Rs. 2200 for the week, we're settled on the nozzle now", SURESH_FILE),
    (SURESH, "2026-08-02", 2200, "wage",
     "Regular spraying + extra fogging near the pond",
     "Sending Rs. 2200 for the week", SURESH_FILE),

    # --- Lakshmi: general maintenance & reporting ---
    (LAKSHMI, "2026-06-08", 2800, "wage",
     "Weekly walkthrough, watered potted plants, flagged loose gate lock and broken bench plank",
     "sending 2800 for the week", LAKSHMI_FILE),
    (LAKSHMI, "2026-06-15", 2800, "wage",
     "Visitor logging (12 visitors, nature club group)",
     "Sending 2960 this week, 2800 as usual plus 160 for the lock", LAKSHMI_FILE),
    (LAKSHMI, "2026-06-15", 160, "reimbursement",
     "Replacement gate lock bought and fitted (160 vs. 150 estimated)",
     "Bought the new gate lock and fitted it, spent 160 instead of 150", LAKSHMI_FILE),
    (LAKSHMI, "2026-06-23", 2800, "wage",
     "Prepared for and handled a surprise trust member visit",
     "Sending 3200 this week, added a bit extra for how the visit went", LAKSHMI_FILE),
    (LAKSHMI, "2026-06-23", 400, "bonus",
     "Bonus for how well the surprise trust visit was handled",
     "One of the trust members said everything looked really organized", LAKSHMI_FILE),
    (LAKSHMI, "2026-06-29", 2800, "wage",
     "Walkthrough, confirmed bench repair, watered potted plants",
     "sending 2800 for the week", LAKSHMI_FILE),
    (LAKSHMI, "2026-07-08", 2800, "wage",
     "Prior week's payment, delayed a few days due to a bank issue",
     "Sorted now, sending 2800 for last week", LAKSHMI_FILE),
    (LAKSHMI, "2026-07-13", 2800, "wage",
     "Walkthrough; flagged water tank needing cleaning (algae buildup)",
     "Sending 2800 for this week's work", LAKSHMI_FILE),
    (LAKSHMI, "2026-07-20", 2800, "wage",
     "Walkthrough; flagged stray dogs near the compost area",
     "sending 2800 for the week", LAKSHMI_FILE),
    (LAKSHMI, "2026-07-27", 2800, "wage",
     "Walkthrough, watered plants, visitor log updated (8 visitors)",
     "sending 2800 for the week", LAKSHMI_FILE),
    (LAKSHMI, "2026-08-03", 2800, "wage",
     "Walkthrough, no issues this week",
     "sending 2950 this week, 2800 as usual plus 150 for supplies", LAKSHMI_FILE),
    (LAKSHMI, "2026-08-03", 150, "reimbursement",
     "New broom + cleaning supplies bought",
     "Need to buy a new broom and some cleaning supplies, around 150", LAKSHMI_FILE),

    # Note: the Rs. 900 Lakshmi paid the two tank-cleaning workers on 2026-07-15
    # is deliberately excluded — it was drawn from petty cash Anand had already
    # given her earlier, not a new payment from Anand to Lakshmi.
]

if __name__ == "__main__":
    for phone, date_str, amount, category, description, source, chat_file in records:
        record_payment(phone, date_str, amount, category, description, source, chat_file)
    print(f"Recorded {len(records)} payment events.")
