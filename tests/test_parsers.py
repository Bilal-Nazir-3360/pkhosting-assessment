from datetime import date
from clean import parse_date, parse_money

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

def test_iso_date():
    d, ambiguous, note = parse_date("2025-08-10")
    assert d == date(2025, 8, 10)
    assert ambiguous is False


def test_year_first_slashes():
    d, ambiguous, note = parse_date("2025/09/01")
    assert d == date(2025, 9, 1)
    assert ambiguous is False

def test_month_name():
    d, ambiguous, note = parse_date("03-Aug-2025")
    assert d == date(2025, 8, 3)
    assert ambiguous is False


def test_two_digit_year():
    d, ambiguous, note = parse_date("25/12/25")
    assert d == date(2025, 12, 25)

def test_two_digit_year_is_always_2000s():
    d, ambiguous, note = parse_date("01/01/99")
    assert d == date(2099, 1, 1)  # documented assumption, flagged later as implausible

def test_money_plain_number():
    assert parse_money("3500") == (3500.0, "PKR", "")

def test_money_rs_prefix_and_commas():
    assert parse_money("Rs. 3,500") == (3500.0, "PKR", "")

def test_money_pkr_with_decimals():
    assert parse_money("PKR 18,000.00") == (18000.0, "PKR", "")

def test_money_parentheses_is_negative():
    assert parse_money("(2,500)") == (-2500.0, "PKR", "refund (parentheses)")

def test_money_blank():
    assert parse_money("") == (None, None, "blank amount")

def test_money_usd():
    assert parse_money("USD 45") == (45.0, "USD", "")

def test_money_trailing_dash():
    assert parse_money("Rs 1200/-") == (1200.0, "PKR", "")

def test_money_european_format():
    assert parse_money("1.200,00") == (1200.0, "PKR", "")