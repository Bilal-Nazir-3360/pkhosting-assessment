from datetime import date
from clean import parse_date


def test_day_first_certain():
    d, ambiguous, note = parse_date("25/12/2025")
    assert d == date(2025, 12, 25)
    assert ambiguous is False


def test_month_first_certain():
    d, ambiguous, note = parse_date("12/25/2025")
    assert d == date(2025, 12, 25)
    assert ambiguous is False


def test_impossible_date():
    d, ambiguous, note = parse_date("31/02/2025")
    assert d is None
    assert "impossible" in note

def test_ambiguous_defaults_day_first():
    d, ambiguous, note = parse_date("05/06/2025")
    assert d == date(2025, 6, 5)
    assert ambiguous is True


def test_empty_string_does_not_crash():
    d, ambiguous, note = parse_date("")
    assert d is None