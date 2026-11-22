import csv
from datetime import datetime

import requests

from techi_audit import (
    CSV_FIELDS,
    PoliteFetcher,
    collect_articles,
    is_published_article,
    write_csv,
)
from tests.test_fetcher import FakeClock, FakeResponse, FakeSession

ROBOTS = "User-agent: *\nDisallow: /cart/\nSitemap: https://www.techi.com/sitemap_index.xml\n"
INDEX = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.techi.com/post-sitemap1.xml</loc></sitemap>
<sitemap><loc>https://www.techi.com/page-sitemap.xml</loc></sitemap></sitemapindex>"""


def urlset(*slugs):
    items = "".join(f"<url><loc>https://www.techi.com/{s}/</loc></url>" for s in slugs)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'


def article_html(title, kind="article", date="2026-09-06T06:17:13.785Z"):
    return (f'<html><head><meta property="og:title" content="{title}"/>'
            f'<meta property="og:type" content="{kind}"/>'
            f'<meta property="article:published_time" content="{date}"/>'
            f'<meta property="article:author" content="https://www.techi.com/@jazib/"/>'
            f'</head></html>')


def make_fetcher(tmp_path, pages):
    base = {
        "https://www.techi.com/robots.txt": FakeResponse(200, ROBOTS),
        "https://www.techi.com/sitemap_index.xml": FakeResponse(200, INDEX),
    }
    base.update(pages)
    clock = FakeClock()
    session = FakeSession(base, clock)
    fetcher = PoliteFetcher(session, tmp_path, clock=clock.time, sleep=clock.sleep,
                            now=lambda: datetime(2026, 11, 22, 12, 0))
    return fetcher, session


def test_is_published_article():
    assert is_published_article(article_html("A"))
    assert not is_published_article(article_html("A", kind="website"))
    assert not is_published_article(article_html("A", date=""))
    assert not is_published_article("<html></html>")


def test_collects_only_published_articles_up_to_limit(tmp_path):
    pages = {
        "https://www.techi.com/post-sitemap1.xml":
            FakeResponse(200, urlset("one", "evergreen", "two", "gone", "three")),
        "https://www.techi.com/one/": FakeResponse(200, article_html("One")),
        "https://www.techi.com/evergreen/": FakeResponse(200, article_html("E", kind="website")),
        "https://www.techi.com/two/": FakeResponse(200, article_html("Two")),
        "https://www.techi.com/three/": FakeResponse(200, article_html("Three")),
    }  # "gone" is not served, so it is a 404
    fetcher, session = make_fetcher(tmp_path, pages)
    rows = collect_articles(fetcher, limit=2)
    assert [r["title"] for r in rows] == ["One", "Two"]
    requested = [call[0] for call in session.calls]
    assert "https://www.techi.com/page-sitemap.xml" not in requested
    assert "https://www.techi.com/three/" not in requested   # stopped at the limit


def test_timeout_on_one_page_does_not_stop_the_run(tmp_path):
    pages = {
        "https://www.techi.com/post-sitemap1.xml": FakeResponse(200, urlset("slow", "fine")),
        "https://www.techi.com/slow/": requests.Timeout("slow"),
        "https://www.techi.com/fine/": FakeResponse(200, article_html("Fine")),
    }
    fetcher, _ = make_fetcher(tmp_path, pages)
    rows = collect_articles(fetcher, limit=5)
    assert [r["title"] for r in rows] == ["Fine"]


def test_no_robots_sitemap_line_gives_no_rows(tmp_path):
    pages = {"https://www.techi.com/robots.txt": FakeResponse(200, "User-agent: *\n")}
    fetcher, _ = make_fetcher(tmp_path, pages)
    assert collect_articles(fetcher, limit=5) == []


def test_write_csv_header_and_utf8(tmp_path):
    row = dict.fromkeys(CSV_FIELDS, "")
    row.update(url="https://www.techi.com/x/", title="Palantir\u2019s growth")
    out = tmp_path / "out.csv"
    write_csv(out, [row])
    with open(out, encoding="utf-8", newline="") as f:
        data = list(csv.DictReader(f))
    assert list(data[0].keys()) == ["url", "slug", "title", "category",
                                    "author_handle", "date_text", "date_iso"]
    assert data[0]["title"] == "Palantir\u2019s growth"
