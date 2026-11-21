from datetime import date


def _make_date(year, month, day):
    """Return a date, or None if it isn't a real calendar date."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(raw):
    """Parse a DD/MM/YYYY or MM/DD/YYYY string.

    Returns (date or None, was_ambiguous, note).
    """
    text = (raw or "").strip()
    parts = text.split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None, False, "unrecognised format"

    a, b, year = (int(p) for p in parts)
    day_first = _make_date(year, b, a)     # a is the day, b is the month
    month_first = _make_date(year, a, b)   # a is the month, b is the day

    if day_first and month_first and day_first != month_first:
        return day_first, True, "ambiguous, assumed day-first"

    result = day_first or month_first
    if result is None:
        return None, False, "impossible date"
    return result, False, ""