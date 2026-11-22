from datetime import datetime

import pytest

from techi_audit import parse_absolute_date, parse_relative_date

# A fixed "now" so tests never depend on today's date.
NOW = datetime(2026, 9, 12, 10, 0)


@pytest.mark.parametrize("text, expected", [
    ("6 days ago", "2026-09-06"),
    ("Updated 6 days ago", "2026-09-06"),
    ("1 day ago", "2026-09-11"),
    ("3 hours ago", "2026-09-12"),
    ("12 hours ago", "2026-09-11"),   # crosses midnight
    ("2 weeks ago", "2026-08-29"),
    ("1 month ago", "2026-08-13"),    # rule: 30 days
    ("1 year ago", "2025-09-12"),     # rule: 365 days
])
def test_relative_dates(text, expected):
    assert parse_relative_date(text, NOW) == expected


@pytest.mark.parametrize("text", ["hello", "", None, "6 apples ago"])
def test_relative_not_a_date(text):
    assert parse_relative_date(text, NOW) is None


@pytest.mark.parametrize("text, expected", [
    ("September 6, 2026", "2026-09-06"),
    ("Jul 23, 2026", "2026-07-23"),
    ("Published September 6, 2026\u00b72:17 AM EDT\u00b78 minute read", "2026-09-06"),
    ("2026-09-06T06:17:00Z", "2026-09-06"),
])
def test_absolute_dates(text, expected):
    assert parse_absolute_date(text) == expected


@pytest.mark.parametrize("text", ["not a date", "", None, "February 30, 2026"])
def test_absolute_not_a_date(text):
    assert parse_absolute_date(text) is None
