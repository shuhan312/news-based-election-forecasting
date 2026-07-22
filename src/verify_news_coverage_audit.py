"""Verify the pending rows of news_protocol/historical_coverage_audit.csv.

This is the Task-1 tool of the News Retrieval Framework Validation stage.
For every source in the News Source Registry it runs small, polite,
read-only probes and writes a machine-readable evidence file that the
audit CSV's `evidence` column can point at:

    news_protocol/evidence/coverage_verification_<date>.json

What is probed, per source type
-------------------------------
* Publisher websites  : robots.txt (may we crawl at all? is search
                        blocked?), one site-search request (does search
                        exist and answer?), and Wayback CDX capture
                        counts for each election's 180-day window (how
                        dense is the archive fallback?).
* Guardian API        : one 1-result query per election window, which
                        simultaneously tests authentication, date
                        filtering and archive depth.
* NewsAPI             : not re-probed; already verified as blocked on
                        2026-07-14 (data/raw/newsapi/coverage_check.txt).
* BNA / History Centre: reachability of the public entry page only —
                        their holdings cannot be verified without an
                        account / a visit, and that fact is itself the
                        audit finding.
* Google dated search : deliberately NOT probed by script.  Automated
                        querying of Google is against its terms of
                        service; the audit records it as a manual-only
                        discovery tool.

The script only reads; it never writes to any remote service, sends a
descriptive User-Agent, and sleeps between requests.  Total request
count is ~50, comparable to loading a couple of web pages.

Usage:
    python3 src/verify_news_coverage_audit.py
"""

import json
import time
import urllib.robotparser
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

load_dotenv()

# Identify ourselves honestly, as the protocol's ethics section requires.
USER_AGENT = ("Surrey-IRP-research-validator/1.0 "
              "(academic research; contact: shuhanliu44@gmail.com)")
HEADERS = {"User-Agent": USER_AGENT}
PAUSE = 1.5          # seconds between remote requests (politeness)
TIMEOUT = 30         # per-request timeout in seconds
CDX_LIMIT = 2000     # cap CDX responses; we need density, not every row

OUT_PATH = Path("news_protocol/evidence/coverage_verification_2026-07-22.json")

# The four elections and their 180-day windows, copied from the protocol
# (news_research_protocol.md §2) — the windows are [start, polling day).
ELECTIONS = {
    "SCC-2013-05":  (date(2012, 11, 3), date(2013, 5, 2)),
    "SCC-2017-05":  (date(2016, 11, 5), date(2017, 5, 4)),
    "SCC-2021-05":  (date(2020, 11, 7), date(2021, 5, 6)),
    "ESWS-2026-05": (date(2025, 11, 8), date(2026, 5, 7)),
}

# For each publisher: the CDX prefix that best matches *article* pages,
# and one live site-search URL to test whether on-site search works.
# BBC uses its article URL prefix (uk-england-surrey-NNNN) rather than
# the whole domain, so CDX counts reflect Surrey articles specifically.
PUBLISHERS = {
    "surreylive": {
        "cdx_url": "getsurrey.co.uk", "cdx_match": "domain",
        "search_url": "https://www.getsurrey.co.uk/search/?q=election",
        "robots": "https://www.getsurrey.co.uk/robots.txt",
    },
    "bbc_surrey": {
        "cdx_url": "bbc.co.uk/news/uk-england-surrey", "cdx_match": "prefix",
        "search_url": "https://www.bbc.co.uk/search?q=Surrey+council+election",
        "robots": "https://www.bbc.co.uk/robots.txt",
    },
    "woking_news_mail": {
        "cdx_url": "wokingnewsandmail.co.uk", "cdx_match": "domain",
        "search_url": "https://www.wokingnewsandmail.co.uk/?s=election",
        "robots": "https://www.wokingnewsandmail.co.uk/robots.txt",
    },
    "farnham_herald": {
        "cdx_url": "farnhamherald.com", "cdx_match": "domain",
        "search_url": "https://www.farnhamherald.com/search/?query=election",
        "robots": "https://www.farnhamherald.com/robots.txt",
    },
    "guildford_dragon": {
        "cdx_url": "guildford-dragon.com", "cdx_match": "domain",
        "search_url": "https://guildford-dragon.com/?s=election",
        "robots": "https://guildford-dragon.com/robots.txt",
    },
    "epsom_ewell_times": {
        "cdx_url": "epsomandewelltimes.com", "cdx_match": "domain",
        "search_url": "https://epsomandewelltimes.com/?s=election",
        "robots": "https://epsomandewelltimes.com/robots.txt",
    },
    "surrey_comet": {
        "cdx_url": "surreycomet.co.uk", "cdx_match": "domain",
        "search_url": "https://www.surreycomet.co.uk/search/?search=election",
        "robots": "https://www.surreycomet.co.uk/robots.txt",
    },
}

# Entry pages for the two archive services we can only check reachability
# of (holdings need an account / an in-person visit).
ARCHIVE_PAGES = {
    "british_newspaper_archive":
        "https://www.britishnewspaperarchive.co.uk/",
    "surrey_history_centre":
        "https://www.surreycc.gov.uk/culture-and-leisure/history-centre/"
        "researchers/guides/newspaper-back-issues",
}


def get(url, **kw):
    """One polite GET: shared headers, timeout, pause afterwards.
    Returns the response, or None on network failure (the failure is
    still evidence, so callers record it rather than crash)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        r = None
        print(f"    request failed: {url} ({e.__class__.__name__})")
    time.sleep(PAUSE)
    return r


def check_robots(robots_url):
    """Fetch robots.txt and answer two questions our retrieval ladder
    cares about: may a polite crawler fetch article pages, and may it
    use the on-site search path?"""
    r = get(robots_url)
    if r is None or r.status_code != 200:
        return {"fetched": False,
                "status": getattr(r, "status_code", None)}
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())
    return {
        "fetched": True,
        "status": 200,
        "allows_article_pages": rp.can_fetch(USER_AGENT, "/"),
        "allows_search_path": rp.can_fetch(USER_AGENT, "/search/?q=test"),
    }


def check_site_search(url):
    """Hit the publisher's own search once.  We only record the HTTP
    status and page size — enough to know whether a search interface
    exists and responds, without scraping results."""
    r = get(url)
    if r is None:
        return {"reachable": False}
    return {"reachable": True, "status": r.status_code,
            "bytes": len(r.content),
            "final_url": r.url}          # records login/anti-bot redirects


def cdx_count(cdx_url, match_type, start, end):
    """Count Wayback captures (HTTP 200, text/html) of a site inside one
    election window.  This is the audit's quantitative evidence for how
    viable the Wayback fallback is per source per year.  Counts are
    capped at CDX_LIMIT: '2000' really means 'at least 2000'."""
    r = get("https://web.archive.org/cdx/search/cdx", params={
        "url": cdx_url, "matchType": match_type,
        "from": start.strftime("%Y%m%d"), "to": end.strftime("%Y%m%d"),
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "urlkey",            # count distinct pages, not re-crawls
        "limit": CDX_LIMIT, "output": "json",
    })
    if r is None or r.status_code != 200:
        return {"ok": False, "status": getattr(r, "status_code", None)}
    try:
        rows = r.json()
    except ValueError:
        return {"ok": False, "status": r.status_code, "note": "non-JSON"}
    n = max(len(rows) - 1, 0)            # first row is the header
    return {"ok": True, "distinct_pages": n, "capped": n >= CDX_LIMIT}


def check_guardian():
    """One minimal query per election window.  A page-size-1 request is
    enough to verify (a) the key authenticates, (b) from/to date
    filtering is honoured, (c) the archive actually holds content in
    that window — `total` tells us how much."""
    key = os.getenv("GUARDIAN_KEY")
    out = {}
    for eid, (start, end) in ELECTIONS.items():
        r = get("https://content.guardianapis.com/search", params={
            "q": "Surrey", "from-date": start.isoformat(),
            "to-date": end.isoformat(), "page-size": 1, "api-key": key,
        })
        if r is None:
            out[eid] = {"ok": False}
            continue
        body = r.json().get("response", {})
        first = (body.get("results") or [{}])[0]
        out[eid] = {
            "ok": body.get("status") == "ok",
            "total_results_in_window": body.get("total"),
            # keep one example date so date filtering is visibly honoured
            "example_publication_date": first.get("webPublicationDate"),
        }
    return out


def main():
    evidence = {
        "run_date": "2026-07-22",
        "purpose": ("Evidence for updating historical_coverage_audit.csv "
                    "from pending to verified/blocked "
                    "(News Retrieval Framework Validation, Task 1)"),
        "user_agent": USER_AGENT,
        "windows": {k: [v[0].isoformat(), v[1].isoformat()]
                    for k, v in ELECTIONS.items()},
        "publishers": {}, "guardian_api": {}, "archive_services": {},
        "google_dated_search": {
            "probed": False,
            "reason": ("Automated querying of Google violates its terms "
                       "of service; recorded as a manual-only discovery "
                       "tool.  Manual procedure documented in the "
                       "retrieval validation report."),
        },
        "newsapi_org": {
            "probed": False,
            "reason": ("Already verified blocked on 2026-07-14; see "
                       "data/raw/newsapi/coverage_check.txt (all four "
                       "windows refused, plan floor 2026-06-12)."),
        },
    }

    print("Guardian API: one probe per election window")
    evidence["guardian_api"] = check_guardian()
    for eid, res in evidence["guardian_api"].items():
        print(f"  {eid}: {res}")

    for src, cfg in PUBLISHERS.items():
        print(f"{src}: robots, site search, CDX windows")
        rec = {"robots": check_robots(cfg["robots"]),
               "site_search": check_site_search(cfg["search_url"]),
               "wayback_windows": {}}
        for eid, (start, end) in ELECTIONS.items():
            rec["wayback_windows"][eid] = cdx_count(
                cfg["cdx_url"], cfg["cdx_match"], start, end)
            print(f"  {eid}: {rec['wayback_windows'][eid]}")
        evidence["publishers"][src] = rec

    print("Archive services: reachability only")
    for src, url in ARCHIVE_PAGES.items():
        r = get(url)
        evidence["archive_services"][src] = {
            "reachable": r is not None,
            "status": getattr(r, "status_code", None),
            "note": ("Holdings not verifiable remotely; requires "
                     "subscription/visit — this is the audit finding."),
        }
        print(f"  {src}: {evidence['archive_services'][src]}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(evidence, indent=2))
    print(f"\nEvidence written to {OUT_PATH}")


if __name__ == "__main__":
    main()
