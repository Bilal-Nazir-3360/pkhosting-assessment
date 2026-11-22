from datetime import datetime
from pathlib import Path

from techi_audit import extract_article

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://www.techi.com/palantir-ai-growth-expectations-rising-2026/"
FETCHED = datetime(2026, 11, 22, 12, 0)


def test_full_article():
    html = (FIXTURES / "article_sample.html").read_text(encoding="utf-8")
    row = extract_article(URL, html, FETCHED)
    assert row == {
        "url": URL,
        "slug": "palantir-ai-growth-expectations-rising-2026",
        "title": "Palantir\u2019s AI Growth Is Accelerating\u2014but Expectations Are Rising",
        "category": "Markets & Equities",   # not "AI" from the nav menu
        "author_handle": "jazib",
        "date_text": "Published September 6, 2026 \u00b7 2:17 AM EDT",
        "date_iso": "2026-09-06",
    }


def test_odd_markup_gives_blanks_not_a_crash():
    row = extract_article(URL, "<html><body>nothing useful</body></html>", FETCHED)
    assert row["url"] == URL
    assert row["slug"] == "palantir-ai-growth-expectations-rising-2026"
    for field in ("title", "category", "author_handle", "date_text", "date_iso"):
        assert row[field] == ""


def test_relative_date_uses_fetch_time():
    html = "<html><body><time>Updated 6 days ago</time></body></html>"
    row = extract_article(URL, html, FETCHED)
    assert row["date_text"] == "Updated 6 days ago"
    assert row["date_iso"] == "2026-11-16"
