import calendar
import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date

TODAY = date(2026, 8, 3)   # the brief says to treat today as 2026-08-03
WINDOW_START, WINDOW_END = date(2026, 8, 3), date(2026, 9, 2)   # inclusive
YEAR_MIN, YEAR_MAX = 2000, 2035
OUTLIER_PKR = 1_000_000    # assumption: no single renewal above this is normal
COUNTED = {"active", "pending"}   # statuses that count toward the headline total

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

STATUS_MAP = {
    "active": "active", "cancelled": "cancelled", "canceled": "cancelled",
    "suspended": "suspended", "expired": "expired",
    "pending": "pending", "refunded": "refunded",
}
SERVICE_MAP = {"vps": "VPS", "shared hosting": "Shared Hosting",
               "domain .pk": "Domain .pk", "ssl": "SSL"}
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


# ---------------------------------------------------------------- parsers

def _make_date(year, month, day):
    """Return a date, or None if it isn't a real calendar date."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(raw, order=None):
    """Parse a date string. Returns (date or None, was_ambiguous, note).

    order may force "dmy" or "mdy" for slash dates; it is decided by the
    caller from the rest of the row (see resolve_dates).
    """
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
    if order == "dmy":
        month_first = None
    elif order == "mdy":
        day_first = None

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

    # Non-ASCII (e.g. an accented letter): convert to punycode, the form DNS uses.
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


def parse_cycle(raw):
    """Return (months or None, note)."""
    text = (raw or "").strip().lower()
    if not text:
        return None, "blank cycle"
    if text.isdigit():
        return int(text), ""
    words = {
        "annual": 12, "yearly": 12,
        "monthly": 1,
        "quarterly": 3,
        "half year": 6, "half-year": 6, "halfyear": 6,
        "semi-annual": 6, "semiannual": 6, "biannual": 6,
    }
    if text in words:
        return words[text], ""
    m = re.fullmatch(r"(\d+)\s*(year|yr|month|mo)s?", text)
    if m:
        n = int(m.group(1))
        return (n * 12 if m.group(2) in ("year", "yr") else n), ""
    return None, "unrecognised cycle"


# ------------------------------------------------------------ issues log

class Issues:
    """Every drop, change or flag goes through log(), so nothing is silent."""

    def __init__(self):
        self.rows = []

    def log(self, record_id, field, raw_value, problem, action):
        self.rows.append({"record_id": record_id, "field": field,
                          "raw_value": raw_value, "problem": problem,
                          "action_taken": action})


# ----------------------------------------------------------- date helpers

def add_months(d, n):
    """d plus n months, clamping the day (29 Feb + 12 months = 28 Feb)."""
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def months_between(reg, ren):
    """Whole months from reg to ren, or None if it isn't an exact number."""
    n = (ren.year - reg.year) * 12 + ren.month - reg.month
    return n if n > 0 and add_months(reg, n) == ren else None


def order_hint(raw):
    """'dmy' or 'mdy' if a slash date has a part above 12, else None."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", (raw or "").strip())
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return "dmy" if a > 12 else "mdy" if b > 12 else None


def _fits_cycle(raw_reg, raw_ren, months, order):
    reg = parse_date(raw_reg, order)[0]
    ren = parse_date(raw_ren, order)[0]
    return bool(months and reg and ren and add_months(reg, months) == ren)


def resolve_dates(rid, raw_reg, raw_ren, months, issues):
    """Settle ambiguous dates: other date in the row first, then the cycle.

    If both readings still fit, default to day-first and log it.
    """
    raws = {"registered_on": raw_reg, "renews_on": raw_ren}
    plain = {f: parse_date(r) for f, r in raws.items()}
    order, how = None, ""
    if any(amb for _, amb, _ in plain.values()):
        hint = order_hint(raw_reg) or order_hint(raw_ren)
        if hint:
            order, how = hint, "the other date in the row"
        else:
            fits = [o for o in ("dmy", "mdy")
                    if _fits_cycle(raw_reg, raw_ren, months, o)]
            if len(fits) == 1:
                order, how = fits[0], "the billing cycle"
    result = {}
    for field, raw in raws.items():
        d, amb, note = plain[field]
        if amb and order:
            d = parse_date(raw, order)[0]
            issues.log(rid, field, raw, "ambiguous_date",
                       f"resolved using {how}, read as {order}")
        elif amb:
            issues.log(rid, field, raw, "ambiguous_date",
                       "assumed day-first (both readings fit)")
        elif d is None:
            issues.log(rid, field, raw, note, "left blank")
        result[field] = d
    return result["registered_on"], result["renews_on"]


# ------------------------------------------------------------- row logic

def clean_row(raw, issues):
    """Return a clean dict, or None if the row is dropped."""
    rid = (raw.get("record_id") or "").strip()

    domain_raw = raw.get("domain") or ""
    domain, note = parse_domain(domain_raw)
    if domain is None:
        issues.log(rid, "domain", domain_raw, note, "row dropped")
        return None
    if domain != domain_raw.strip():
        issues.log(rid, "domain", domain_raw, "normalised", f"changed to {domain}")

    status_raw = (raw.get("status") or "").strip()
    status = STATUS_MAP.get(status_raw.lower(), "unknown")
    if status == "unknown":
        issues.log(rid, "status", status_raw, "blank or unrecognised status", "set to unknown")
    elif status_raw != status:
        issues.log(rid, "status", status_raw, "normalised", f"changed to {status}")

    service_raw = (raw.get("service") or "").strip()
    service = SERVICE_MAP.get(service_raw.lower(), service_raw)
    if service != service_raw:
        issues.log(rid, "service", service_raw, "normalised", f"changed to {service}")

    amount, currency, note = parse_money(raw.get("amount"))
    if currency == "USD":
        issues.log(rid, "amount", raw.get("amount"), "USD amount",
                   "amount_pkr left blank, not converted")
        amount = None
    elif note:
        issues.log(rid, "amount", raw.get("amount"), note,
                   "kept as parsed" if amount is not None else "left blank")
    if amount is not None and amount == int(amount):
        amount = int(amount)   # whole rupees print as 3500, not 3500.0

    months, note = parse_cycle(raw.get("billing_cycle"))
    cycle_raw = (raw.get("billing_cycle") or "").strip()
    if months is not None and cycle_raw != str(months):
        issues.log(rid, "billing_cycle", cycle_raw, "normalised", f"changed to {months}")

    n_before = len(issues.rows)
    reg, ren = resolve_dates(rid, raw.get("registered_on"),
                             raw.get("renews_on"), months, issues)
    # True if either date had to be guessed (both readings fit)
    date_guess = any("both readings" in r["action_taken"]
                     for r in issues.rows[n_before:])

    if months is None:
        inferred = months_between(reg, ren) if reg and ren else None
        if inferred:
            months = inferred
            issues.log(rid, "billing_cycle", cycle_raw, note,
                       f"inferred {months} months from the dates")
        else:
            issues.log(rid, "billing_cycle", cycle_raw, note, "left blank")

    email_raw = raw.get("contact_email") or ""
    email = email_raw.strip().lower()
    if email and not EMAIL_RE.fullmatch(email):
        issues.log(rid, "contact_email", email_raw, "invalid email", "left blank")
        email = ""
    elif not email:
        issues.log(rid, "contact_email", email_raw, "blank email", "left blank")
    elif email != email_raw:
        issues.log(rid, "contact_email", email_raw, "normalised", f"changed to {email}")

    cust = (raw.get("customer_id") or "").strip()
    if not cust:
        issues.log(rid, "customer_id", raw.get("customer_id"), "blank customer_id", "kept, flagged")

    return {
        "record_id": rid, "customer_id": cust, "canonical_domain": domain,
        "service": service,
        "billing_cycle_months": months, "amount_pkr": amount,
        "registered_on": reg, "renews_on": ren,
        "status": status, "contact_email": email,
        "_date_guess": date_guess,   # helper only, not written to clean.csv
    }


def check_row(c, issues):
    """Per-row sanity checks. Flags only, never changes or drops."""
    rid = c["record_id"]
    reg, ren = c["registered_on"], c["renews_on"]

    for field, d in (("registered_on", reg), ("renews_on", ren)):
        if d and not (YEAR_MIN <= d.year <= YEAR_MAX):
            issues.log(rid, field, str(d), "implausible_year", "kept, flagged")

    if reg and ren and ren <= reg:
        issues.log(rid, "renews_on", f"{reg} -> {ren}",
                   "renews_on not after registered_on", "kept, flagged")

    months = c["billing_cycle_months"]
    if reg and ren and months and ren > reg and add_months(reg, months) != ren:
        issues.log(rid, "billing_cycle_months", str(months),
                   f"cycle does not match dates ({reg} to {ren})", "kept, flagged")

    amt = c["amount_pkr"]
    if amt is not None:
        if amt == 0:
            issues.log(rid, "amount_pkr", str(amt), "zero amount", "kept, flagged")
        elif amt < 0 and c["status"] != "refunded":
            issues.log(rid, "amount_pkr", str(amt),
                       "negative amount, status is not refunded", "kept, flagged")
        elif amt > OUTLIER_PKR:
            issues.log(rid, "amount_pkr", str(amt), "outlier amount", "kept, flagged")

    if ren and ren < TODAY and c["status"] == "active":
        issues.log(rid, "renews_on", str(ren),
                   "renewal date already passed but status is active", "kept, flagged")


# ----------------------------------------------------------------- dedupe

def dedupe(kept, issues):
    """Return (rows_kept, conflict_ids). Drops later duplicates, logs everything."""
    # 1. Reused record_ids: different renewals sharing one id.
    id_counts = Counter(c["record_id"] for c in kept)
    for c in kept:
        if id_counts[c["record_id"]] > 1:
            issues.log(c["record_id"], "record_id",
                       f"{c['record_id']} ({c['canonical_domain']})",
                       "duplicate_record_id (different renewals share this id)",
                       "kept, flagged")

    # 2. Duplicate renewals: same (domain, service, renews_on).
    seen = {}
    out, conflicts = [], set()
    for c in kept:
        if c["renews_on"] is None:      # no date, so we cannot safely match it
            out.append(c)
            continue
        key = (c["canonical_domain"], c["service"].lower(), c["renews_on"])
        first = seen.get(key)
        if first is None:
            seen[key] = c
            out.append(c)
        elif first["amount_pkr"] == c["amount_pkr"]:
            issues.log(c["record_id"], "row", c["record_id"],
                       f"duplicate of {first['record_id']}",
                       f"row dropped, merged into {first['record_id']}")
        else:
            conflicts.add(first["record_id"])
            issues.log(first["record_id"], "amount_pkr", str(first["amount_pkr"]),
                       f"conflicting_duplicate: {c['record_id']} says {c['amount_pkr']}",
                       "kept first row, flagged, excluded from headline total")
            issues.log(c["record_id"], "row", c["record_id"],
                       f"conflicting_duplicate of {first['record_id']}",
                       "row dropped, amount logged")
    return out, conflicts


def check_customers(kept, issues):
    """Flag customers that appear with more than one contact email."""
    by_cust = defaultdict(list)
    for c in kept:
        if c["customer_id"] and c["contact_email"]:
            by_cust[c["customer_id"]].append(c)
    for cust, rows in by_cust.items():
        emails = sorted({r["contact_email"] for r in rows})
        if len(emails) > 1:
            for r in rows:
                issues.log(r["record_id"], "contact_email", r["contact_email"],
                           f"customer {cust} has several contact emails: {', '.join(emails)}",
                           "kept, flagged")


# --------------------------------------------------------- renewal report

def renewal_report(kept, conflict_ids):
    """Return a list of (record_id, domain, renews_on, amount, bucket, reason)."""
    out = []
    for c in kept:
        ren, amt, st = c["renews_on"], c["amount_pkr"], c["status"]
        rid, dom = c["record_id"], c["canonical_domain"]
        if ren is None or not (WINDOW_START <= ren <= WINDOW_END):
            continue   # no usable date (see issues.csv) or outside the window
        if amt is None:
            bucket, why = "excluded", "no PKR amount (blank or USD)"
        elif st == "suspended":
            bucket, why = "at_risk", "suspended, may be reinstated"
        elif st not in COUNTED:
            bucket, why = "excluded", f"status is {st}"
        elif amt <= 0:
            bucket, why = "excluded", "zero or negative amount"
        elif amt > OUTLIER_PKR:
            bucket, why = "outlier", "amount above Rs. 1,000,000, needs checking"
        elif rid in conflict_ids:
            bucket, why = "conflict", "duplicate with two amounts"
        elif c["_date_guess"]:
            bucket, why = "included_ambiguous", "included, but date was a guess"
        else:
            bucket, why = "included", "counted"
        out.append((rid, dom, ren, amt, bucket, why))
    return out


# ----------------------------------------------------------------- output

def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main(path):
    issues = Issues()
    with open(path, newline="", encoding="utf-8-sig") as f:   # utf-8-sig skips a BOM
        rows = list(csv.DictReader(f))
    cleaned = [clean_row(r, issues) for r in rows]
    kept = [c for c in cleaned if c]

    for c in kept:
        check_row(c, issues)

    kept, conflict_ids = dedupe(kept, issues)
    check_customers(kept, issues)

    issues.rows.sort(key=lambda r: r["record_id"])   # stable: keeps each record's issues together

    write_csv("issues.csv",
              ["record_id", "field", "raw_value", "problem", "action_taken"],
              issues.rows)
    write_csv("clean.csv",
              ["record_id", "customer_id", "canonical_domain", "service",
               "billing_cycle_months", "amount_pkr", "registered_on",
               "renews_on", "status", "contact_email"],
              kept)

    flagged_ids = {i["record_id"] for i in issues.rows}
    kept_flagged = [c for c in kept if c["record_id"] in flagged_ids]
    print(f"rows in: {len(rows)}")
    print(f"kept: {len(kept)}  (of which flagged: {len(kept_flagged)})")
    print(f"dropped: {len(rows) - len(kept)}")
    print("totals by status:")
    for status, n in sorted(Counter(c["status"] for c in kept).items()):
        print(f"  {status}: {n}")

    # Renewal total for the window (rules are in NOTES.md)
    report = renewal_report(kept, conflict_ids)
    totals = defaultdict(int)
    print(f"\nrenewals due {WINDOW_START} to {WINDOW_END}:")
    for rid, dom, ren, amt, bucket, why in report:
        totals[bucket] += amt or 0
        print(f"  {bucket:18} {rid} {dom} {ren} {amt}  ({why})")
    sure = totals["included"]
    with_amb = sure + totals["included_ambiguous"]
    print(f"headline total (certain dates): Rs. {sure:,}")
    print(f"total including guessed dates:  Rs. {with_amb:,}")
    print(f"at risk (suspended): Rs. {totals['at_risk']:,}")
    print(f"conflicting duplicate: Rs. {totals['conflict']:,}")
    print(f"outlier (excluded, needs checking): Rs. {totals['outlier']:,}")


if __name__ == "__main__":
    main(sys.argv[1])