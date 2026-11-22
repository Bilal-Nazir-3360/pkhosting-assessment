"""Polite metadata reader for TECHi.com (Part B)."""
import hashlib
import csv
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("techi_audit")

# Rule: a month is 30 days and a year is 365 days. The site only says
# "2 months ago", so an exact calendar answer is not possible.
USER_AGENT = "TechAboutAssessmentBot/1.0 (bachohan786@gmail.com)"
SITE_HOST = "www.techi.com"
POST_SITEMAP_RE = re.compile(r"^post-sitemap\d*\.xml$")
UNIT_DAYS = {"week": 7, "month": 30, "year": 365}
ROBOTS_URL = "https://www.techi.com/robots.txt"
TIMEOUT = (5, 10)      # seconds: connect, read
MIN_DELAY = 1.0        # brief: one request per second
CACHED_STATUSES = (200, 404)   # timeouts and 5xx are never cached
SITEMAP_TIMEOUT = (5, 30)   # the post sitemap is large, so a longer read time
CSV_FIELDS = ["url", "slug", "title", "category",
              "author_handle", "date_text", "date_iso"]

RELATIVE_RE = re.compile(
    r"(\d+)\s*(minute|hour|day|week|month|year)s?\s+ago", re.IGNORECASE
)
ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
MONTH_RE = re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})")


def parse_relative_date(text, now):
    """Turn '6 days ago' into 'YYYY-MM-DD', counted back from now."""
    if not text:
        return None
    match = RELATIVE_RE.search(text)
    if not match:
        return None
    number = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "minute":
        delta = timedelta(minutes=number)
    elif unit == "hour":
        delta = timedelta(hours=number)
    else:
        delta = timedelta(days=number * (1 if unit == "day" else UNIT_DAYS[unit]))
    return (now - delta).strftime("%Y-%m-%d")


def parse_absolute_date(text):
    """Find an ISO date or 'Month D, YYYY' in text. Return 'YYYY-MM-DD' or None."""
    if not text:
        return None
    iso = ISO_RE.search(text)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
    else:
        found = MONTH_RE.search(text)
        if not found:
            return None
        name, day, year = found.groups()
        parsed = None
        for fmt in ("%B", "%b"):          # full name, then short name
            try:
                parsed = datetime.strptime(name, fmt).month
                break
            except ValueError:
                continue
        if parsed is None:
            return None
        month, day, year = parsed, int(day), int(year)
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:                     # for example February 30
        return None

def _meta(soup, key):
    """Content of <meta property=key> or <meta name=key>, or ''."""
    tag = (soup.find("meta", attrs={"property": key})
           or soup.find("meta", attrs={"name": key}))
    return (tag.get("content") or "").strip() if tag else ""


def _json_ld_nodes(soup):
    """All JSON-LD objects on the page. Bad JSON is skipped."""
    nodes = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text())
        except ValueError:
            continue
        items = data.get("@graph", [data]) if isinstance(data, dict) else data
        if isinstance(items, list):
            nodes.extend(item for item in items if isinstance(item, dict))
    return nodes


def _category(nodes):
    """Breadcrumb position 2, else NewsArticle.articleSection, else ''."""
    for node in nodes:
        if node.get("@type") == "BreadcrumbList":
            for item in node.get("itemListElement", []):
                if isinstance(item, dict) and item.get("position") == 2:
                    return str(item.get("name") or "").strip()
    for node in nodes:
        if node.get("@type") == "NewsArticle" and node.get("articleSection"):
            return str(node["articleSection"]).strip()
    return ""


def _author_handle(soup):
    """'https://www.techi.com/@jazib/' -> 'jazib'."""
    url = _meta(soup, "article:author")
    if not url:
        link = soup.find("link", rel="author")
        url = link.get("href", "") if link else ""
    match = re.search(r"/@([^/?#]+)", url)
    return match.group(1) if match else ""


def _date_text(soup):
    """Text of the first <time> that starts with Published or Updated."""
    for tag in soup.find_all("time"):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if re.match(r"(published|updated)\b", text, re.IGNORECASE):
            return text
    return ""


def extract_article(url, html, fetched_at):
    """Build one CSV row from a page. Missing values stay ''."""
    soup = BeautifulSoup(html, "html.parser")
    nodes = _json_ld_nodes(soup)

    title = _meta(soup, "og:title")
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
    title = re.sub(r"\s*\|\s*TECHi\s*$", "", title)

    date_text = _date_text(soup)
    date_iso = parse_absolute_date(_meta(soup, "article:published_time"))
    if not date_iso:
        for node in nodes:
            if node.get("@type") == "NewsArticle":
                date_iso = parse_absolute_date(node.get("datePublished"))
    if not date_iso:
        date_iso = (parse_absolute_date(date_text)
                    or parse_relative_date(date_text, fetched_at))

    return {
        "url": url,
        "slug": urlparse(url).path.rstrip("/").split("/")[-1],
        "title": title,
        "category": _category(nodes),
        "author_handle": _author_handle(soup),
        "date_text": date_text,
        "date_iso": date_iso or "",
    }
def parse_sitemap(xml_text):
    """Return the page URLs of a <urlset> or the sitemap URLs of a <sitemapindex>.

    Only <loc> inside <url> or <sitemap> counts. The <image:loc> inside
    <image:image> is skipped. Bad XML gives an empty list.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    urls = []
    for entry in root:
        if entry.tag.split("}")[-1] not in ("url", "sitemap"):
            continue
        for child in entry:
            if child.tag.split("}")[-1] == "loc" and child.text:
                urls.append(child.text.strip())
    return urls


def is_post_sitemap(url):
    """True for post-sitemap1.xml, post-sitemap12.xml and so on."""
    name = urlparse(url).path.rsplit("/", 1)[-1]
    return bool(POST_SITEMAP_RE.match(name))


def is_article_url(url):
    """True if the URL is on techi.com with exactly one path segment."""
    parts = urlparse(url)
    segments = [part for part in parts.path.split("/") if part]
    return parts.netloc == SITE_HOST and len(segments) == 1


def article_urls(urls):
    """Keep article-looking URLs, drop duplicates, keep the sitemap order."""
    seen = set()
    result = []
    for url in urls:
        if is_article_url(url) and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def sitemap_lines_from_robots(robots_text):
    """Return the URLs on 'Sitemap:' lines of a robots.txt text."""
    found = []
    for line in robots_text.splitlines():
        match = re.match(r"\s*sitemap\s*:\s*(\S+)", line, re.IGNORECASE)
        if match:
            found.append(match.group(1))
    return found
class PoliteFetcher:
    """The only place that touches the network."""

    def __init__(self, session, cache_dir, clock=time.monotonic,
                 sleep=time.sleep, now=datetime.now):
        self.session = session
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.sleep = sleep
        self.now = now
        self._last_request = None   # clock value when the last request ended
        self._delay = MIN_DELAY
        self._robots = None         # RobotFileParser once loaded
        self._block_all = False
        self._robots_loaded = False

    # --- cache ---
    def _cache_path(self, url):
        name = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / (name + ".json")

    def _read_cache(self, url):
        path = self._cache_path(url)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            log.warning("Bad cache file for %s, fetching again", url)
            return None

    def _write_cache(self, url, page):
        text = json.dumps(page, ensure_ascii=False)
        self._cache_path(url).write_text(text, encoding="utf-8")

    # --- network ---
    def _wait(self):
        if self._last_request is None:
            return
        gap = self.clock() - self._last_request
        if gap < self._delay:
            self.sleep(self._delay - gap)

    def _request(self, url, timeout):
        """One real request. Returns a page dict or None on network error."""
        self._wait()
        try:
            response = self.session.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        except requests.RequestException as error:
            log.warning("Request failed for %s: %s", url, error)
            return None
        finally:
            self._last_request = self.clock()
        page = {
            "status": response.status_code,
            "body": response.text,
            "fetched_at": self.now().isoformat(timespec="seconds"),
        }
        if page["status"] in CACHED_STATUSES:
            self._write_cache(url, page)
        return page

    # --- robots ---
    def _load_robots(self):
        self._robots_loaded = True
        page = self._read_cache(ROBOTS_URL) or self._request(ROBOTS_URL, TIMEOUT)
        if page is None or page["status"] not in (200, 404):
            log.warning("robots.txt not readable, blocking all fetches")
            self._block_all = True
        elif page["status"] == 200:
            parser = RobotFileParser()
            parser.parse(page["body"].lstrip("\ufeff").splitlines())
            self._robots = parser
            delay = parser.crawl_delay(USER_AGENT)
            self._delay = max(MIN_DELAY, float(delay or 0))
        # 404: no robots.txt, so everything is allowed

    def _allowed(self, url):
        if not self._robots_loaded:
            self._load_robots()
        if self._block_all:
            return False
        return self._robots is None or self._robots.can_fetch(USER_AGENT, url)

    # --- public ---
    def get(self, url, timeout=TIMEOUT):
        """Page dict (status, body, fetched_at), or None if skipped or failed."""
        cached = self._read_cache(url)
        if cached:
            return cached
        if not self._allowed(url):
            log.warning("Blocked by robots.txt: %s", url)
            return None
        return self._request(url, timeout)

def is_published_article(html):
    """True if the page says og:type=article and has a published time."""
    soup = BeautifulSoup(html, "html.parser")
    return (_meta(soup, "og:type") == "article"
            and bool(_meta(soup, "article:published_time")))


def _fetch_text(fetcher, url, timeout=None):
    """Body of a 200 page, or '' (the reason is logged)."""
    page = fetcher.get(url, timeout) if timeout else fetcher.get(url)
    if page is None:
        log.warning("Skipped (not fetched): %s", url)
        return ""
    if page["status"] != 200:
        log.warning("Skipped (status %s): %s", page["status"], url)
        return ""
    return page["body"]


def collect_articles(fetcher, limit=20):
    """Find up to `limit` published articles, starting from robots.txt."""
    robots_text = _fetch_text(fetcher, ROBOTS_URL).lstrip("\ufeff")
    rows = []
    seen = set()
    for sitemap_url in sitemap_lines_from_robots(robots_text):
        index_urls = parse_sitemap(
            _fetch_text(fetcher, sitemap_url, SITEMAP_TIMEOUT))
        post_files = [u for u in index_urls if is_post_sitemap(u)]
        for post_url in post_files:
            urls = article_urls(parse_sitemap(
                _fetch_text(fetcher, post_url, SITEMAP_TIMEOUT)))
            for url in urls:
                if len(rows) >= limit:
                    return rows
                if url in seen:
                    continue
                seen.add(url)
                body = _fetch_text(fetcher, url)
                if not body:
                    continue
                if not is_published_article(body):
                    log.warning("Skipped (not a published article): %s", url)
                    continue
                page = fetcher.get(url)   # cache hit: gives fetched_at
                fetched_at = datetime.fromisoformat(page["fetched_at"])
                rows.append(extract_article(url, body, fetched_at))
            if len(rows) >= limit:
                return rows
    return rows


def write_csv(path, rows):
    """Write rows as UTF-8 CSV. newline='' stops blank lines on Windows."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(message)s")
    fetcher = PoliteFetcher(requests.Session(), "cache")
    rows = collect_articles(fetcher, limit=20)
    write_csv("techi_articles.csv", rows)
    log.info("Wrote %d articles to techi_articles.csv", len(rows))


if __name__ == "__main__":
    main()