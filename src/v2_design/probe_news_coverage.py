"""Probe N1, N2, C1: is Kent's local coverage comparable to Surrey's?

Every measurement runs identically on Surrey 2021 (calibration) and Kent
2017/2021/2025, inside the 90-31 day pre-election window. Links and titles
only: no article is fetched, and nothing after the window is requested, so no
outcome can enter. Criteria: v2_design/feasibility_probe_v1/criteria.md.

Domain classes are fixed here, before any result is seen. "Local news" is
defined by exclusion (not national press, not government, party, social or
reference sites) so that no hand-picked Kent or Surrey outlet list can tilt
the ratio.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests

from v2_design.probe_results_availability import ballots

OUT = Path("v2_design/feasibility_probe_v1/news_coverage.json")
SERPER = "https://google.serper.dev/search"
CDX = "https://web.archive.org/cdx/search/cdx"

ELECTIONS = {
    # key: (council name, polling day, Democracy Club election id)
    "surrey_2021": ("Surrey", date(2021, 5, 6), "local.surrey.2021-05-06"),
    "kent_2017": ("Kent", date(2017, 5, 4), "local.kent.2017-05-04"),
    "kent_2021": ("Kent", date(2021, 5, 6), "local.kent.2021-05-06"),
    "kent_2025": ("Kent", date(2025, 5, 1), "local.kent.2025-05-01"),
}
CALIBRATION = "surrey_2021"
PARTIES = ("Conservative", "Labour", "Liberal Democrats", "Green Party",
           "Reform UK")
PLACE_SAMPLE = 10

# Analogous outlet triples: county live site, BBC regional page, main paper.
OUTLETS = {
    "Surrey": [("surreylive.news", "domain"), ("getsurrey.co.uk", "domain"),
               ("bbc.co.uk/news/uk-england-surrey", "prefix"),
               ("surreycomet.co.uk", "domain")],
    "Kent": [("kentlive.news", "domain"),
             ("bbc.co.uk/news/uk-england-kent", "prefix"),
             ("kentonline.co.uk", "domain")],
}

NATIONAL = ("theguardian.com", "telegraph.co.uk", "independent.co.uk",
            "dailymail.co.uk", "mirror.co.uk", "express.co.uk", "thetimes.co.uk",
            "thetimes.com", "ft.com", "news.sky.com", "standard.co.uk",
            "gbnews.com", "newstatesman.com", "spectator.co.uk",
            "politicshome.com", "huffingtonpost.co.uk", "inews.co.uk",
            "metro.co.uk", "reuters.com", "thesun.co.uk", "theweek.com",
            "politico.eu", "economist.com")
NON_NEWS = ("gov.uk", "wikipedia.org", "facebook.com", "twitter.com", "x.com",
            "youtube.com", "instagram.com", "linkedin.com", "reddit.com",
            "tiktok.com", "conservatives.com", "labour.org.uk",
            "libdems.org.uk", "greenparty.org.uk", "reformparty.uk",
            "democracyclub.org.uk", "electoralcalculus.co.uk",
            "ukpollingreport.co.uk", "opencouncildata.co.uk")


def domain_class(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host.endswith("bbc.co.uk") or host.endswith("bbc.com"):
        return "local_news" if "/uk-england-" in parsed.path else "national"
    if any(host == d or host.endswith("." + d) for d in NON_NEWS):
        return "non_news"
    if any(host == d or host.endswith("." + d) for d in NATIONAL):
        return "national"
    return "local_news"


def window(polling_day: date) -> tuple[date, date]:
    return polling_day - timedelta(days=90), polling_day - timedelta(days=31)


def place_sample(dc_election_id: str) -> list[str]:
    """Deterministic division sample: lowest sha256 of the slug."""
    labels = {b["post"]["slug"]: b["post"]["label"]
              for b in ballots(dc_election_id) if not b.get("cancelled")}
    ranked = sorted(labels, key=lambda s: hashlib.sha256(s.encode()).hexdigest())
    return [labels[s] for s in ranked[:PLACE_SAMPLE]]


def queries(council: str, places: list[str]) -> list[dict]:
    rows = [{"template": "T1_council_election",
             "q": f"{council} County Council election"}]
    for p in PARTIES:
        rows.append({"template": "T2_council_party",
                     "q": f"{council} County Council {p}"})
        rows.append({"template": "T3_party_candidates",
                     "q": f"{council} council elections {p} candidates"})
    for place in places:
        rows.append({"template": "T4_division_place",
                     "q": f"{place} {council} county council"})
    return rows


def serper(q: str, start: date, end: date, key: str) -> list[dict]:
    us = lambda d: f"{d.month}/{d.day}/{d.year}"  # noqa: E731 - Google M/D/YYYY
    for attempt in range(4):
        try:
            r = requests.post(
                SERPER, timeout=60,
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
                json={"q": q, "num": 20,
                      "tbs": f"cdr:1,cd_min:{us(start)},cd_max:{us(end)}"})
            if r.status_code < 500:
                r.raise_for_status()
                time.sleep(1.0)
                return [{"url": i.get("link"), "title": i.get("title")}
                        for i in r.json().get("organic", [])]
        except (requests.Timeout, requests.ConnectionError):
            pass
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Serper failed four times for {q!r}")


def cdx_count(target: str, match: str, start: date, end: date) -> int | None:
    params = {"url": target, "matchType": match,
              "from": start.strftime("%Y%m%d"), "to": end.strftime("%Y%m%d"),
              "filter": ["statuscode:200", "mimetype:text/html"],
              "collapse": "urlkey", "output": "json", "limit": 50000}
    for attempt in range(3):
        try:
            r = requests.get(CDX, params=params, timeout=120)
            if r.status_code == 200:
                rows = r.json()[1:] if r.text.strip() else []
                return sum(1 for row in rows if _articleish(row[2]))
        except (requests.RequestException, ValueError):
            pass
        time.sleep(5 * (attempt + 1))
    return None


def _articleish(url: str) -> bool:
    # Same rule as V1's WaybackAdapter._articleish.
    if "?" in url or "#" in url:
        return False
    bad = ("/search", "/tag/", "/category/", "/all-about/", "/authors/",
           "/wp-", "robots.txt", "/feed", "/page/", "/incoming/")
    if any(b in url.lower() for b in bad):
        return False
    path = urlparse(url).path.rstrip("/")
    return path.count("/") >= 2 and len(path) > 15


def v1_local_serper_searches_per_election() -> float:
    """C1 input: V1's local-arm dated-search volume per principal election."""
    with open("news_collection/search_log.csv", encoding="utf-8") as handle:
        log = [r for r in csv.DictReader(handle)
               if r["source_id"] == "google_dated_search" and r["arm"] == "local"
               and r["election_id"] in ("SCC-2013-05", "SCC-2017-05",
                                        "SCC-2021-05", "ESWS-2026-05")]
    return len(log) / 4


def main() -> None:
    key = os.environ["SERPER_API_KEY"]
    results = {}
    for name, (council, polling_day, dc_id) in ELECTIONS.items():
        start, end = window(polling_day)
        hits = []
        for q in queries(council, place_sample(dc_id)):
            for h in serper(q["q"], start, end, key):
                hits.append({**h, "template": q["template"],
                             "class": domain_class(h["url"])})
        unique = {h["url"]: h for h in hits}
        local = [h for h in unique.values() if h["class"] == "local_news"]
        outlets = {t: cdx_count(t, m, start, end) for t, m in OUTLETS[council]}
        results[name] = {
            "council": council, "polling_day": polling_day.isoformat(),
            "window": [start.isoformat(), end.isoformat()],
            "queries": len(queries(council, [""] * PLACE_SAMPLE)),
            "hits": len(hits), "unique_urls": len(unique),
            "by_class": dict(Counter(h["class"] for h in unique.values())),
            "local_unique_urls": len(local),
            "local_by_template": dict(Counter(h["template"] for h in local)),
            "top_local_domains": Counter(
                urlparse(h["url"]).netloc.removeprefix("www.")
                for h in local).most_common(15),
            "wayback_article_captures": outlets,
            "wayback_total": sum(v for v in outlets.values() if v is not None),
            "local_urls": sorted((h["url"], h["title"]) for h in local),
        }
        print(name, results[name]["unique_urls"], results[name]["by_class"],
              outlets)

    base = results[CALIBRATION]
    ratios = {name: {
        "N1_local_url_ratio": round(r["local_unique_urls"]
                                    / max(base["local_unique_urls"], 1), 3),
        "N2_wayback_ratio": round(r["wayback_total"]
                                  / max(base["wayback_total"], 1), 3),
    } for name, r in results.items() if name != CALIBRATION}
    payload = {
        "criteria": "v2_design/feasibility_probe_v1/criteria.md",
        "calibration": CALIBRATION,
        "ratios_vs_calibration": ratios,
        "C1_v1_local_serper_searches_per_election":
            v1_local_serper_searches_per_election(),
        "elections": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(ratios, indent=2))


if __name__ == "__main__":
    main()
