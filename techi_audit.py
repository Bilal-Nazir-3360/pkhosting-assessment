"""Polite metadata reader for TECHi.com (Part B)."""
import re
from datetime import datetime, timedelta

# Rule: a month is 30 days and a year is 365 days. The site only says
# "2 months ago", so an exact calendar answer is not possible.
UNIT_DAYS = {"week": 7, "month": 30, "year": 365}

RELATIVE_RE = re.compile(
    r"(\d+)\s*(minute|hour|day|week|month|year)s?\s+ago", re.IGNORECASE
)
ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
MONTH_RE = re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})")


def parse_relative_date(text, now):
    """Turn '6 days ago' into 'YYYY-MM-DD', counted back from now."""
    if not text:
        return None
    match = RELATIVE_RE.search(text)
    if not match:
        return None
    number = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "minute":
        delta = timedelta(minutes=number)
    elif unit == "hour":
        delta = timedelta(hours=number)
    else:
        delta = timedelta(days=number * (1 if unit == "day" else UNIT_DAYS[unit]))
    return (now - delta).strftime("%Y-%m-%d")


def parse_absolute_date(text):
    """Find an ISO date or 'Month D, YYYY' in text. Return 'YYYY-MM-DD' or None."""
    if not text:
        return None
    iso = ISO_RE.search(text)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
    else:
        found = MONTH_RE.search(text)
        if not found:
            return None
        name, day, year = found.groups()
        parsed = None
        for fmt in ("%B", "%b"):          # full name, then short name
            try:
                parsed = datetime.strptime(name, fmt).month
                break
            except ValueError:
                continue
        if parsed is None:
            return None
        month, day, year = parsed, int(day), int(year)
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:                     # for example February 30
        return None