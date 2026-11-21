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

def parse_money(raw):
    """Parse an amount string. Returns (amount or None, currency or None, note)."""
    text = (raw or "").strip()
    if not text:
        return None, None, "blank amount"

    # 1. Currency: USD if "USD" or "$" appears, otherwise assume PKR.
    currency = "USD" if ("USD" in text.upper() or "$" in text) else "PKR"

    # 2. Sign: parentheses mean a refund, a leading minus means negative.
    in_parens = text.startswith("(") and text.endswith(")")
    negative = in_parens or text.startswith("-")

    # 3. Keep only digits, commas and dots, then trim stray ones.
    #    This removes "Rs.", "PKR", "₨", "/-" and spaces. The strip handles
    #    the leftover dot from "Rs." so "Rs.12000" becomes "12000".
    num = re.sub(r"[^\d.,]", "", text).strip(".,")
    if not any(c.isdigit() for c in num):
        return None, None, "no number found"

    # 4. Decide which of "," and "." is the decimal separator.
    if "," in num and "." in num:
        if num.rfind(",") > num.rfind("."):      # 1.200,00 (European)
            num = num.replace(".", "").replace(",", ".")
        else:                                    # 18,000.00
            num = num.replace(",", "")
    elif "," in num:
        tail = num.rsplit(",", 1)[1]
        # 1,200 -> thousands separator. 1200,50 -> decimal comma.
        num = num.replace(",", "") if len(tail) == 3 else num.replace(",", ".")
    elif "." in num:
        tail = num.rsplit(".", 1)[1]
        # 1.200 -> thousands separator (PKR is whole rupees). 1200.50 -> decimal.
        if len(tail) == 3:
            num = num.replace(".", "")

    try:
        value = float(num)
    except ValueError:
        return None, None, "unparseable amount"

    note = ""
    if negative:
        value = -value
        note = "refund (parentheses)" if in_parens else "negative amount"
    return value, currency, note

def parse_domain(raw):
    """Return (canonical domain or None, note)."""
    text = (raw or "").strip().lower()
    if not text:
        return None, "blank domain"

    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)   # scheme
    text = re.split(r"[/?#]", text, maxsplit=1)[0]       # path, query, fragment
    text = re.sub(r":\d+$", "", text)                    # port
    text = text.strip(".")                               # stray dots
    if text.startswith("www."):
        text = text[4:]

    if not text or "." not in text:
        return None, "invalid domain (no dot)"

    # Non-ASCII (e.g. cafe with an accent): convert to punycode, the form DNS uses.
    try:
        text = text.encode("idna").decode("ascii")
    except UnicodeError:
        return None, "invalid domain (cannot encode)"

    for label in text.split("."):
        if (not label
                or label.startswith("-") or label.endswith("-")
                or not re.fullmatch(r"[a-z0-9-]+", label)):
            return None, "invalid domain"
    return text, ""