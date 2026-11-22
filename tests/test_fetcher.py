from datetime import datetime

import requests

from techi_audit import USER_AGENT, PoliteFetcher

ROBOTS_URL = "https://www.techi.com/robots.txt"
ARTICLE = "https://www.techi.com/some-article-2026/"
OTHER = "https://www.techi.com/other-article-2026/"
CART = "https://www.techi.com/cart/"
ROBOTS_OK = "User-agent: *\nDisallow: /cart/\n"


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class FakeClock:
    """Time only moves when the fetcher sleeps. No real waiting in tests."""

    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class FakeSession:
    """Answers from a dict and records every real request."""

    def __init__(self, pages, clock):
        self.pages = pages
        self.clock = clock
        self.calls = []  # (url, time, headers, timeout)

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, self.clock.now, headers, timeout))
        answer = self.pages.get(url, FakeResponse(404))
        if isinstance(answer, Exception):
            raise answer
        return answer


def make_fetcher(tmp_path, pages=None):
    all_pages = {ROBOTS_URL: FakeResponse(200, ROBOTS_OK)}
    all_pages.update(pages or {})
    clock = FakeClock()
    session = FakeSession(all_pages, clock)
    fetcher = PoliteFetcher(
        session, tmp_path,
        clock=clock.time, sleep=clock.sleep,
        now=lambda: datetime(2026, 11, 22, 12, 0),
    )
    return fetcher, session, clock


def urls_requested(session):
    return [call[0] for call in session.calls]


def test_get_returns_page_and_sends_user_agent_and_timeout(tmp_path):
    fetcher, session, _ = make_fetcher(
        tmp_path, {ARTICLE: FakeResponse(200, "<html>hi</html>")})
    page = fetcher.get(ARTICLE)
    assert page == {"status": 200, "body": "<html>hi</html>",
                    "fetched_at": "2026-11-22T12:00:00"}
    for _url, _time, headers, timeout in session.calls:
        assert headers["User-Agent"] == USER_AGENT
        assert timeout is not None


def test_cache_hit_makes_no_request_and_no_wait(tmp_path):
    fetcher, session, clock = make_fetcher(
        tmp_path, {ARTICLE: FakeResponse(200, "body")})
    fetcher.get(ARTICLE)
    calls_before, sleeps_before = len(session.calls), len(clock.slept)
    again = fetcher.get(ARTICLE)
    assert again["body"] == "body"
    assert len(session.calls) == calls_before
    assert len(clock.slept) == sleeps_before


def test_rerun_with_new_fetcher_is_silent(tmp_path):
    first, _, _ = make_fetcher(tmp_path, {ARTICLE: FakeResponse(200, "body")})
    first.get(ARTICLE)
    second, session, _ = make_fetcher(tmp_path)
    page = second.get(ARTICLE)
    assert page["body"] == "body"
    assert session.calls == []  # robots.txt and the article both from disk


def test_404_is_returned_and_cached(tmp_path):
    fetcher, session, _ = make_fetcher(tmp_path)  # ARTICLE not served -> 404
    assert fetcher.get(ARTICLE)["status"] == 404
    calls_before = len(session.calls)
    assert fetcher.get(ARTICLE)["status"] == 404
    assert len(session.calls) == calls_before


def test_timeout_gives_none_and_is_not_cached(tmp_path):
    fetcher, session, _ = make_fetcher(
        tmp_path, {ARTICLE: requests.Timeout("slow")})
    assert fetcher.get(ARTICLE) is None
    session.pages[ARTICLE] = FakeResponse(200, "now ok")
    assert fetcher.get(ARTICLE)["body"] == "now ok"  # it tried again


def test_server_error_is_not_cached(tmp_path):
    fetcher, session, _ = make_fetcher(
        tmp_path, {ARTICLE: FakeResponse(503, "down")})
    assert fetcher.get(ARTICLE)["status"] == 503
    session.pages[ARTICLE] = FakeResponse(200, "back")
    assert fetcher.get(ARTICLE)["body"] == "back"


def test_robots_blocked_url_is_never_requested(tmp_path):
    fetcher, session, _ = make_fetcher(tmp_path)
    assert fetcher.get(CART) is None
    assert CART not in urls_requested(session)


def test_waits_one_second_between_real_requests(tmp_path):
    fetcher, session, _ = make_fetcher(
        tmp_path, {ARTICLE: FakeResponse(200, "a"), OTHER: FakeResponse(200, "b")})
    fetcher.get(ARTICLE)
    fetcher.get(OTHER)
    times = [call[1] for call in session.calls]  # robots, article, other
    assert len(times) == 3
    assert times[1] - times[0] >= 1.0
    assert times[2] - times[1] >= 1.0


def test_robots_bom_is_stripped(tmp_path):
    bom_robots = "\ufeffUser-agent: *\nDisallow: /cart/\n"
    fetcher, session, _ = make_fetcher(
        tmp_path, {ROBOTS_URL: FakeResponse(200, bom_robots)})
    assert fetcher.get(CART) is None


def test_missing_robots_allows_everything(tmp_path):
    fetcher, session, _ = make_fetcher(
        tmp_path, {ROBOTS_URL: FakeResponse(404)})
    assert fetcher.get(CART)["status"] == 404
    assert CART in urls_requested(session)


def test_unreachable_robots_blocks_everything(tmp_path):
    fetcher, session, _ = make_fetcher(
        tmp_path, {ROBOTS_URL: requests.ConnectionError("down"),
                   ARTICLE: FakeResponse(200, "a")})
    assert fetcher.get(ARTICLE) is None
    assert ARTICLE not in urls_requested(session)


def test_crawl_delay_is_honoured(tmp_path):
    robots = "User-agent: *\nCrawl-delay: 3\n"
    fetcher, session, _ = make_fetcher(
        tmp_path, {ROBOTS_URL: FakeResponse(200, robots),
                   ARTICLE: FakeResponse(200, "a"), OTHER: FakeResponse(200, "b")})
    fetcher.get(ARTICLE)
    fetcher.get(OTHER)
    times = [call[1] for call in session.calls]
    assert times[2] - times[1] >= 3.0
