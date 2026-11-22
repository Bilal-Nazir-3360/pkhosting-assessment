from pathlib import Path
from urllib.robotparser import RobotFileParser

from techi_audit import (
    USER_AGENT,
    article_urls,
    is_article_url,
    is_post_sitemap,
    parse_sitemap,
    sitemap_lines_from_robots,
)

FIXTURES = Path(__file__).parent / "fixtures"


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8-sig")


def test_parse_sitemap_index():
    urls = parse_sitemap(read("sitemap_index.xml"))
    assert len(urls) == 5
    assert urls[0] == "https://www.techi.com/post-sitemap1.xml"


def test_parse_urlset_ignores_image_loc():
    urls = parse_sitemap(read("post_sitemap.xml"))
    assert "https://www.techi.com/a.png" not in urls
    assert urls[0] == "https://www.techi.com/palantir-ai-growth-expectations-rising-2026/"


def test_parse_sitemap_bad_xml_gives_empty_list():
    assert parse_sitemap("<urlset><url>") == []
    assert parse_sitemap("") == []


def test_is_post_sitemap_keeps_only_post_files():
    assert is_post_sitemap("https://www.techi.com/post-sitemap1.xml")
    assert is_post_sitemap("https://www.techi.com/post-sitemap12.xml")
    assert not is_post_sitemap("https://www.techi.com/page-sitemap.xml")
    assert not is_post_sitemap("https://www.techi.com/category-sitemap.xml")
    assert not is_post_sitemap("https://www.techi.com/news-sitemap.xml")


def test_is_article_url_one_flat_segment_only():
    assert is_article_url("https://www.techi.com/second-article-slug-2026/")
    assert not is_article_url("https://www.techi.com/")
    assert not is_article_url("https://www.techi.com/category/markets-equities/")
    assert not is_article_url("https://www.techi.com/quote/PLTR/")
    assert not is_article_url("https://other-site.com/some-slug/")


def test_article_urls_filters_dedupes_and_keeps_order():
    found = article_urls(parse_sitemap(read("post_sitemap.xml")))
    assert found == [
        "https://www.techi.com/palantir-ai-growth-expectations-rising-2026/",
        "https://www.techi.com/second-article-slug-2026/",
    ]


def test_sitemap_lines_from_robots():
    assert sitemap_lines_from_robots(read("robots.txt")) == [
        "https://www.techi.com/sitemap_index.xml"
    ]


def test_robots_decision_with_our_user_agent():
    rp = RobotFileParser()
    rp.parse(read("robots.txt").splitlines())
    ok = "https://www.techi.com/palantir-ai-growth-expectations-rising-2026/"
    assert rp.can_fetch(USER_AGENT, ok)
    assert not rp.can_fetch(USER_AGENT, "https://www.techi.com/cart/")
    assert not rp.can_fetch(USER_AGENT, "https://www.techi.com/my-account/")
    # Our bot is not GPTBot, so the GPTBot group must not apply to us.
    assert rp.can_fetch(USER_AGENT, "https://www.techi.com/dashboard/")
