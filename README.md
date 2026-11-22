# PKHosting renewals cleanup

This is my work for the TechAbout assessment. This README covers Part A, the renewals cleanup, and Part B, the TECHi reader. Part B starts further down.

## About the data

The brief talks about a supplied `renewals_raw.csv`, but I never got that file. I checked the email, the spam folder and the assessment page, and I asked the team. Nobody sent it.

So I made my own file, `renewals_sample.csv`, with 50 rows. I copied the problems the brief lists (mixed date formats, symbols in amounts, a USD line, duplicates, impossible dates) and added some extra ones. All numbers in this README and in NOTES.md come from my sample, not from the real file.

If the real file arrives, run `python clean.py renewals_raw.csv` and read the results again. The rules should stay the same, but the numbers will change.

## Setup

You need Python 3.10 or newer. I used 3.12.

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On Mac or Linux, activate with `source .venv/bin/activate`.

Part A only uses the standard library. `requests` and `beautifulsoup4` in `requirements.txt` are for Part B, and `pytest` is for the tests.

## How to run

```
python clean.py renewals_sample.csv
```

It writes three files in the same folder:

- `clean.csv`: the cleaned rows
- `issues.csv`: every row that was dropped, changed, merged or flagged
- `renewal_report.csv`: every renewal in the 2026-08-03 to 2026-09-02 window, with a reason for each

It also prints a summary: rows in, kept, dropped, flagged, totals by status, and the renewal total.

With my sample it gives: 50 rows in, 46 kept (35 of them flagged), 4 dropped.

The 4 dropped rows are R031 (bad domain), R011 and R048 (exact duplicates), and R010 (the duplicate with a different amount).

## Files

Part A:
- `clean.py`: the whole cleaning script
- `renewals_sample.csv`: my made-up input
- `clean.csv`, `issues.csv`, `renewal_report.csv`: the output
- `NOTES.md`: my rules and the renewal total, with reasons

Part B:
- `techi_audit.py`: the TECHi reader
- `techi_articles.csv`: the output
- `cache/`: saved pages, so a rerun works offline

Both parts:
- `tests/`: all the tests (`test_parsers.py` is Part A, the others are Part B)
- `pytest.ini`: lets the tests import my scripts
- `requirements.txt`: the packages I used

## How it works

The script reads each row and cleans it with small functions: `parse_date`, `parse_money`, `parse_domain` and `parse_cycle`. After that it checks each row, removes duplicates, and writes the files.

Every change goes through one `Issues` object. That way nothing can be dropped or changed without a line in `issues.csv`.

`issues.csv` has one row per problem, not one row per record. A record with several problems appears several times. Also, record_id R004 is used by two different renewals, so it shows up with two different domains.

## Decisions

The full list is in NOTES.md. These are the main ones.

**Dates.** The file mixes DD/MM and MM/DD, so I decide per row. If one part is bigger than 12, the order is clear. If not, I check the other date in the same row, and then whether registered date plus billing cycle equals the renewal date. If both readings still fit, I use day-first and mark the row `ambiguous_date`. In my sample four rows end up like this: R004, R006, R017 and R040.

**Money.** No currency sign means PKR. USD amounts are not converted, because I had no exchange rate and did not want to make one up. A number in brackets is a refund.

**Domains.** I lowercase them and remove `http://`, `www.`, paths and ports. Accented letters become punycode.

**Duplicates.** Same domain, service and renewal date means the same renewal. If the amounts match, I keep the first row. If they don't (R009 and R010), I keep the first row, flag it, and leave it out of the main total, because I can't tell which amount is right.

**Dropped and flagged.** Dropped means the row is not in `clean.csv`. Flagged means it is in `clean.csv` but has at least one line in `issues.csv`.

## Renewal total

Today is treated as 2026-08-03, and the window is 2026-08-03 to 2026-09-02, both days included.

- Main total: **Rs. 183,100**
- If I also count the two rows with guessed dates (R017 and R040): **Rs. 191,600**

NOTES.md has the full list of what is counted and what is not, and why. Examples are the cancelled rows, the USD line, the suspended row, and the Rs. 3,500,000 row that looks like a data error.

## What I do not log row by row

Changing dates to ISO format and removing `Rs.`, commas and `/-` from amounts. This happens on almost every row, so logging it would hide the real problems. Changes to domain, status, service, billing cycle and email are logged.

## Tests

```
pytest
```

Part A has 47 tests, all offline. Part B has 48 more, see the Part B section. They cover the date, money, domain and billing cycle parsers with awkward inputs (impossible dates, `(2,500)`, `1.200,00`, `shop..com.pk`, blank values), plus the date resolving and the header names.

## Tradeoffs

- The day-first default for guessed dates is a guess. I show the total with and without those rows so the effect is visible.
- The Rs. 1,000,000 limit for "outlier" is my own number. I had no real data to pick it from.
- Treating `www.example.pk` and `example.pk` as the same site is an assumption.
- The script accepts a few different column names (for example `domain`, `domain_name`, `website`), because I did not know the real headers. If `domain` or `renews_on` is missing, it stops with an error. If the file is not UTF-8, it tries cp1252.
- Sanity checks run before duplicates are removed, so a row that is dropped later can still have a line in `issues.csv`.

## What I would improve

- Run it on the real `renewals_raw.csv` and fix whatever my sample missed.
- Ask for an exchange rate so the USD line can be counted.
- Ask what the real outlier limit should be.
- Add tests for `clean_row`, the duplicate step and the renewal report. Right now the tests mostly cover the small parsing functions.
- Add a column in `issues.csv` that tells apart the two R004 rows more clearly.

---

# Part B: TECHi metadata reader

`techi_audit.py` collects info for 20 published TECHi.com articles and writes `techi_articles.csv` with these columns: url, slug, title, category, author_handle, date_text, date_iso.

## Setup and run

Same venv as Part A. It needs `requests` and `beautifulsoup4`, which are already in `requirements.txt`.

```
python techi_audit.py
```

The first run makes 23 requests: robots.txt, the sitemap index, one post sitemap and 20 articles. They are one second apart, so it takes at least that long. I did not time the first run.

A rerun took about 1.5 seconds. The `cache/` folder is committed (23 files, 5.3 MB), so you can run it offline. I cloned the repo into a new folder and ran it there: 2 seconds. I also ran it with all network connections blocked, and it still wrote 20 articles with no warnings. So a rerun makes no requests.

To crawl fresh, delete `cache/` first.

## How it finds articles

1. Read `robots.txt` and take the `Sitemap:` line.
2. Read the sitemap index and keep only the `post-sitemap*.xml` files. The other sitemaps are pages, categories and tools, not articles.
3. Go through the URLs in order (newest first). Fetch each page and keep it only if it is a published article.

No paths are hardcoded. If robots.txt has no `Sitemap:` line, the script returns nothing. It does not guess.

Sitemap files are read one at a time, and only if I still need more URLs. I got 20 articles from `post-sitemap1.xml`, so I never read the others.

## What counts as a published article

All four must be true:

- the URL comes from a `post-sitemap*.xml` and has one path segment, like `/some-slug/`
- the status is 200
- `og:type` is `article`
- `article:published_time` is there

The URL alone cannot tell a news article from an evergreen page, so I check the page too. A skipped page is logged with the reason. In the real run nothing was skipped, so I only tested this with fake pages.

## How I read each field

- **title:** `og:title`. If it ends with " | TECHi", I remove that. If `og:title` is missing, I use `<title>`.
- **category:** the JSON-LD `BreadcrumbList`, item 2. Fallback is `articleSection`. I do not use the first `/category/` link, because those are in the top menu.
- **author_handle:** from `article:author`, the part after `/@`. Fallback is `<link rel="author">`.
- **date_text:** the text of the first `<time>` tag that starts with "Published" or "Updated".
- **date_iso:** the **published** date as `YYYY-MM-DD`. Order: `article:published_time`, then JSON-LD `datePublished`, then the visible date text.
- If a value is missing, it is left blank. The script does not crash.

## Dates

- `date_iso` is the UTC date of the timestamp. In all 20 rows it matched the date shown on the page. A post made late in the evening in the US could be one day different, but none of mine were.
- Relative dates ("6 days ago", "Updated 6 days ago") are counted back from the time the page was fetched. That time is saved in the cache, so a cached page gives the same answer on every run.
- I count a month as 30 days and a year as 365. The site only says "2 months ago", so I cannot be exact.
- None of the 20 article pages used a relative date. They all said "Published ...". The relative parser is only tested offline.

## Politeness

| Brief says | What I did | Test |
|---|---|---|
| Respect robots.txt | Every URL is checked before fetching. Sitemaps too. A missing robots.txt (404) allows everything. One I cannot read blocks everything for that run. I strip a BOM before parsing. | `test_fetcher.py` |
| One request per second | The fetcher waits at least 1 second after the last real request. It would wait longer if robots.txt had a Crawl-delay. Cache hits do not wait. | `test_fetcher.py` |
| Real User-Agent | `TechAboutAssessmentBot/1.0 (bachohan786@gmail.com)`. The same text is used for the robots check. | `test_fetcher.py` |
| Disk cache | Files in `cache/`, named by a hash of the URL. Each one has the body, status and fetch time. | `test_fetcher.py` |
| Timeouts, 404s, odd markup | Timeout is 5 seconds to connect and 10 to read (30 to read for sitemaps). A failed page is skipped and logged. Missing fields become blank. | `test_fetcher.py`, `test_collect.py`, `test_extract.py` |

Cache rules: 200 and 404 answers are saved. Timeouts and 5xx errors are not, so the next run tries them again. All network calls go through one class, `PoliteFetcher`.

I never met a real timeout or 404 in the live run. Those cases are tested with a fake session.

## Part B tests

```
pytest
```

95 tests in total, all offline. 48 are for Part B:

- `test_dates.py`: 20 (relative and absolute dates, bad input)
- `test_extract.py`: 3 (a saved HTML sample, empty page, relative date)
- `test_discovery.py`: 8 (sitemap parsing, post-sitemap filter, article URL rule, robots)
- `test_fetcher.py`: 12 (cache, robots, delay, 404, timeout, 5xx)
- `test_collect.py`: 5 (whole run with a fake session, CSV output)

The tests use a fake clock and a fake session, so there is no real network and no real waiting. The HTML sample in `tests/fixtures/` is a small copy I wrote from the real page structure.

## Findings

Things I found on the site, from the pages I looked at:

- `og:title` has no " | TECHi" at the end on the pages I checked. I still strip it in case other pages have it.
- The top menu has 24 `/category/` links on every page. The first one is not the article's category.
- A page has 5 JSON-LD blocks. The first is a `Corporation` (the company in the story), not the article. So I pick blocks by `@type`, not by position.
- The date text has `<!-- -->` comments inside it from React. BeautifulSoup removes them. A plain text search for "Published " on the raw HTML found nothing, so I use BeautifulSoup only.
- The page content is in the raw HTML, so I did not need JavaScript.
- Author handles can have a hyphen, like `omer-sheikh`.
- All 20 articles had a category, an author and a date. No blank values.
- All 20 were in one category, `Markets & Equities`. The breadcrumb method is only proven on that one.
- All 20 had absolute "Published" dates. I saw no "Updated" text and no relative dates on article pages.
- The sitemap also has evergreen-looking URLs, like `/spacex-ipo/`. They were not in the first 20, so my real run never reached one.

One problem of my own: my robots.txt test file was saved with a hidden BOM character, and the first rule group was ignored, so `/cart/` looked allowed. That is why the fetcher strips it.

## Part B tradeoffs

- The cache is checked before robots.txt. If robots.txt changes later, old cached pages are not checked again.
- Cached pages never expire. For fresh data, delete `cache/`.
- 20 newest articles of one category is a small sample.
- The UTC rule and the 30-day month are simple choices, not exact.
- My email is in the User-Agent so the site owner can contact me. It will be visible if the repo is public.
- I committed the whole cache untouched, including the big sitemap. It is 5.3 MB, but cutting the XML would break it.

## What I would improve in Part B

- Run it on more categories and more sitemap files, and look for pages that are skipped.
- Add an expiry time for cached pages.
- Check cached pages again if robots.txt changes.
- Read the timezone in the date text, so `date_iso` follows the date the reader sees.
- Log every real request, so a quiet rerun can be shown directly and not only by timing.