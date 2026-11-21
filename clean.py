import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _make_date(year, month, day):
    """Return a date, or None if it isn't a real calendar date."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(raw):
    """Parse a date string. Returns (date or None, was_ambiguous, note)."""
    text = (raw or "").strip()

    # Year first: YYYY-MM-DD or YYYY/MM/DD. Order is certain.
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        year, month, day = (int(g) for g in m.groups())
        result = _make_date(year, month, day)
        return (result, False, "") if result else (None, False, "impossible date")

    # Day, month name, year: 03-Aug-2025. Order is certain.
    m = re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", text)
    if m:
        month = MONTHS.get(m.group(2).lower())
        result = _make_date(int(m.group(3)), month, int(m.group(1))) if month else None
        return (result, False, "") if result else (None, False, "impossible date")

    # DD/MM/YYYY, MM/DD/YYYY, or either with a 2-digit year.
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", text)
    if not m:
        return None, False, "unrecognised format"

    a, b, year = (int(g) for g in m.groups())
    if year < 100:
        year += 2000  # assumption: all records are from the 2000s

    day_first = _make_date(year, b, a)     # a is the day, b is the month
    month_first = _make_date(year, a, b)   # a is the month, b is the day

    if day_first and month_first and day_first != month_first:
        return day_first, True, "ambiguous, assumed day-first"

    result = day_first or month_first
    if result is None:
        return None, False, "impossible date"
    return result, False, ""