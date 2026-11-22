"""Polite metadata reader for TECHi.com (Part B)."""
import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# Rule: a month is 30 days and a year is 365 days. The site only says
# "2 months ago", so an exact calendar answer is not possible.
UNIT_DAYS = {"week": 7, "month": 30, "year": 365}

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