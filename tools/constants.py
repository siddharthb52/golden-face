"""Shared closed vocabularies for transaction fields, used by both the
categorization pipeline (scripts/categorize_transactions.py) and the
hosted app's admin edit routes/UI (app/app.py), so the two can never
drift apart on what counts as a valid reporting_category or status.

sub_category is intentionally not a closed enum here -- the pipeline is
allowed to propose new labels when none of KNOWN_SUBCATEGORIES fit (see
categorize_transactions.py's prompt), and the admin UI offers this list
as suggestions (e.g. a <datalist>) rather than a hard restriction.
"""

REPORTING_CATEGORIES = [
    "2A - Phase-0 Pragya",
    "2B - Architecture",
    "2C - Operating/Admin",
    "Internal Transfer",
    "Reversal",
    "Income",
]

STATUSES = [
    "Supported",
    "Purpose confirmation recommended",
    "Purpose support to attach",
    "Support note recommended",
    "Reversed",
]

# expense_included is never itself an admin/pipeline-chosen enum value --
# it's derived from reporting_category + direction, see expense_included_for().
NON_EXPENSE_CATEGORIES = {"Internal Transfer", "Reversal"}

KNOWN_SUBCATEGORIES = [
    "Architecture", "Bank Charges", "Construction Supplies",
    "Documentation / Photography", "Ecological Inputs", "Failed Bank Transfer",
    "Fencing Infrastructure", "Fencing Labour", "Field Labour",
    "Food & Hospitality", "Food & Welfare", "Gate / Welding Infrastructure",
    "Guest Logistics", "Infrastructure", "Institutional Learning",
    "Intern Accommodation", "Internship / Student Support",
    "Irrigation Infrastructure", "Local Travel & Logistics", "Painting Labour",
    "Painting Material", "Plantation Event Support",
    "Professional Travel / Stay / Food", "Research / Field Support",
    "Salary / Field Staff", "Sapling Logistics", "Saplings Procurement",
    "Site Development", "Travel & Logistics", "Treasury Movement", "Utilities",
]


def expense_included_for(reporting_category, direction):
    """Same rule scripts/categorize_transactions.py's prompt already asks the
    model to follow: never an expense for Internal Transfer/Reversal or for
    credits, true for debits in every other category."""
    if reporting_category in NON_EXPENSE_CATEGORIES:
        return False
    return direction == "debit"
