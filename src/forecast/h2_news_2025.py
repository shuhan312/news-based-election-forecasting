"""H2 news collection, 2025: local coverage of Reform UK in the 23 councils.

    PYTHONPATH=.:src python -m forecast.h2_news_2025 probe     # pick outlets
    PYTHONPATH=.:src python -m forecast.h2_news_2025 targets   # list URLs
    PYTHONPATH=.:src python -m forecast.h2_news_2025 fetch     # download
    PYTHONPATH=.:src python -m forecast.h2_news_2025 count     # per council

Why this exists. The H2 power gate first found no council-level error to
correct (tau^2 = 0), but that figure came from 2023, when Reform polled
about 6%. Every party with a 13-42% share shows council-level error of
2.6-9.4 pp (power gate amendment A3). H2 is therefore reopened at council
level, and needs each 2025 council's local news about Reform.

Leakage rules, all enforced here:

  - Only Wayback captures taken BEFORE polling day (captures 1-30 April
    2025) are used, and each URL is read from its EARLIEST capture. The
    live page is never fetched: an article online today may have been
    edited after 1 May 2025 (results added), which would leak the outcome.
  - Only articles published 1-30 April 2025 (30-1 days before polling day)
    count; the publication date is read from the archived page.
  - No 2025 result is read by this module.

Outlet choice is mechanical and made before any article is read: for each
council, the first outlet in its candidate list (largest local daily,
Reach "Live" titles first) with at least PROBE_MIN article captures in the
week 1-7 April 2025. One outlet per council.

Criteria: v2_design/direction1_power/criteria.md (A3) and
v2_design/direction1_design.md (A4).
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

from forecast import ward_coverage as wc
from news_collection.adapters import http_get
from news_collection.schema import extract_html_metadata
from v2_design import outlet_pilot as pilot

DATA = Path("data/h2_2025")                         # gitignored
CACHE = DATA / "articles"                           # one file per URL
OUT_DIR = Path("v2_design/direction1_h2")           # committed outputs

PUB_START, PUB_END = date(2025, 4, 1), date(2025, 4, 30)   # 30-1 days
CAP_START, CAP_END = date(2025, 4, 1), date(2025, 4, 30)   # before polling day
PROBE_END = date(2025, 4, 7)
PROBE_MIN = 100            # article captures in the probe week
FETCH_WORKERS = 2

# Candidate outlets per council, in priority order (Reach "Live" title or
# the largest local daily first). Each is a URL prefix covering news only.
CANDIDATES = {
    "buckinghamshire": ["bucksfreepress.co.uk/news/", "bucksherald.co.uk/news/"],
    "cambridgeshire": ["cambridge-news.co.uk/news/"],
    "cornwall": ["cornwalllive.com/news/"],
    "county-durham": ["chroniclelive.co.uk/news/", "thenorthernecho.co.uk/news/"],
    "derbyshire": ["derbytelegraph.co.uk/news/"],
    "devon": ["devonlive.com/news/"],
    "doncaster": ["doncasterfreepress.co.uk/news/", "yorkshirelive.co.uk/news/",
                  "thestar.co.uk/news/"],
    "gloucestershire": ["gloucestershirelive.co.uk/news/"],
    # Herts: HertsLive (Mercury) had only 36 captures in the probe week, so
    # the Newsquest/Archant dailies were added as fallbacks (probe log).
    "hertfordshire": ["hertfordshiremercury.co.uk/news/",
                      "watfordobserver.co.uk/news/", "hertsad.co.uk/news/",
                      "thecomet.net/news/"],
    "kent": ["kentlive.news/news/"],
    "lancashire": ["lancs.live/news/", "lancashiretelegraph.co.uk/news/",
                   "lep.co.uk/news/"],
    "leicestershire": ["leicestermercury.co.uk/news/"],
    "lincolnshire": ["lincolnshirelive.co.uk/news/"],
    "north-northamptonshire": ["northantslive.news/news/",
                               "northamptonchron.co.uk/news/"],
    "northumberland": ["chroniclelive.co.uk/news/",
                       "northumberlandgazette.co.uk/news/"],
    "nottinghamshire": ["nottinghampost.com/news/"],
    "oxfordshire": ["oxfordmail.co.uk/news/"],
    "shropshire": ["shropshirestar.com/news/"],
    "staffordshire": ["stokesentinel.co.uk/news/", "expressandstar.com/news/"],
    "warwickshire": ["coventrytelegraph.net/news/",
                     "leamingtoncourier.co.uk/news/"],
    "west-northamptonshire": ["northantslive.news/news/",
                              "northamptonchron.co.uk/news/"],
    "wiltshire": ["wiltshirelive.co.uk/news/", "wiltshiretimes.co.uk/news/",
                  "gazetteandherald.co.uk/news/"],
    "worcestershire": ["worcesternews.co.uk/news/"],
}

# Only URLs whose slug suggests politics are downloaded: fetching every
# article from 23 outlets would take days. The same rule applies to every
# council, so it cannot favour one. Later stages filter by article text.
#
# Widened after the first download, before any H2 feature was computed:
# Reach sites (the "Live" titles) cut URLs to the headline's first 4-5
# words ("accusation-kent-county-council-bottled-10010872"), so the first,
# narrower list found far fewer of their political articles than of
# Newsquest's (full-headline URLs). That made counts depend on the media
# group, not the news. The added words catch council and party politics.
SLUG = re.compile(r"reform|farage|elect|candidat|vote|voting|ballot|hustings|"
                  r"polling|manifesto|campaign|councillor|"
                  r"council|county|party|labour|tory|tories|conservative|"
                  r"lib-dem|libdem|green-party|greens|politic|mp-|-mp-|"
                  r"minister|starmer|badenoch|government|parliament",
                  re.IGNORECASE)


def _cdx(target: str, start: date, end: date) -> list[tuple[str, str]]:
    """Article-like captures of one prefix, one week at a time, cached.
    Wayback's collapse=urlkey keeps each URL's first (earliest) capture."""
    DATA.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", target)
    out, s = [], start
    while s <= end:
        e = min(date.fromordinal(s.toordinal() + 6), end)
        path = DATA / f"cdx_{slug}_{s:%Y%m%d}_{e:%Y%m%d}.json"
        if not path.exists():
            path.write_text(json.dumps(pilot._cdx_chunk(target, "prefix", s, e)))
            print(f"  {target} {s} done", flush=True)
        out += [tuple(x) for x in json.loads(path.read_text())]
        s = date.fromordinal(e.toordinal() + 1)
    return out


def stage_probe() -> None:
    """Choose one outlet per council by the PROBE_MIN rule; write the choice."""
    chosen, report = {}, {}
    for council, options in CANDIDATES.items():
        report[council] = {}
        for target in options:
            n = len({u for _, u in _cdx(target, CAP_START, PROBE_END)})
            report[council][target] = n
            if n >= PROBE_MIN:
                chosen[council] = target
                break
        print(council, report[council], "->", chosen.get(council), flush=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "outlets.json").write_text(json.dumps(
        {"rule": f"first candidate with >= {PROBE_MIN} article captures, "
                 f"{CAP_START}..{PROBE_END}",
         "chosen": chosen, "probe_counts": report,
         "no_outlet": sorted(set(CANDIDATES) - set(chosen))},
        indent=2) + "\n", encoding="utf-8")


def stage_targets() -> None:
    """Every politics-slug URL captured 1-30 April 2025 by a chosen outlet,
    with its earliest capture timestamp. Also records each outlet's total
    article URLs (the denominator for coverage volume)."""
    chosen = json.loads((OUT_DIR / "outlets.json").read_text())["chosen"]
    rows, totals, seen = [], {}, set()
    for target in sorted(set(chosen.values())):
        caps = {}
        for ts, url in _cdx(target, CAP_START, CAP_END):
            norm = wc._norm_url(url)
            if norm not in caps or ts < caps[norm][0]:
                caps[norm] = (ts, url)          # earliest capture per URL
        totals[target] = len(caps)
        for norm, (ts, url) in caps.items():
            if SLUG.search(url) and norm not in seen:
                seen.add(norm)
                rows.append({"outlet": target, "timestamp": ts, "url": url})
        print(target, "article URLs", len(caps), "politics slugs",
              sum(r["outlet"] == target for r in rows), flush=True)
    with (DATA / "targets.csv").open("w", newline="", encoding="utf-8") as h:
        writer = csv.DictWriter(h, fieldnames=["outlet", "timestamp", "url"])
        writer.writeheader()
        writer.writerows(rows)
    (OUT_DIR / "outlet_totals.json").write_text(
        json.dumps(totals, indent=2) + "\n", encoding="utf-8")
    print(f"{len(rows)} URLs to fetch")


def cache_path(row: dict) -> Path:
    return CACHE / (hashlib.sha256(row["url"].encode()).hexdigest()[:20]
                    + ".json")


def fetch_archived(row: dict) -> None:
    """Read the pre-polling-day Wayback capture only (never the live page)."""
    path = cache_path(row)
    if path.exists():
        return
    archive = f"https://web.archive.org/web/{row['timestamp']}/{row['url']}"
    # Wayback refuses connections when hit too fast. A refused or throttled
    # request (no response, 429, 5xx) is NOT cached, so a rerun retries it;
    # only a real answer (200, or a permanent 404/410) is stored. Caching
    # failures would silently drop articles, as happened on the first run
    # (201 of 339 lost to refused connections).
    resp = None
    for attempt in range(4):
        resp = http_get(archive, archive=True)
        if resp is not None and resp.status_code in (200, 404, 410):
            break
        time.sleep(30 * 2 ** attempt)          # 30 s, 1, 2, 4 min
    else:
        return
    ok = resp.status_code == 200
    meta = extract_html_metadata(resp.text) if ok else {"dates": []}
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        **row, "route": "wayback_capture",
        "http_status": getattr(resp, "status_code", None),
        "headline": meta.get("headline"),
        "published_date": pilot._parse_date(meta),
        "text": meta.get("text") or ""}), encoding="utf-8")


def stage_fetch() -> None:
    from concurrent.futures import ThreadPoolExecutor
    with (DATA / "targets.csv").open(encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    todo = [r for r in rows if not cache_path(r).exists()]
    print(f"{len(rows) - len(todo)} cached, {len(todo)} to fetch", flush=True)
    # Two workers, not four: Wayback refused connections at four.
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        for i, _ in enumerate(pool.map(fetch_archived, todo)):
            if i % 250 == 0:
                print(f"fetched {i}/{len(todo)}", flush=True)


def in_window(article: dict) -> bool:
    d = article.get("published_date")
    return bool(d) and PUB_START <= date.fromisoformat(d) <= PUB_END


# --- 4. attribution and counts (design A4) ------------------------------------------

# The name an article must contain to count for a council. County Durham's
# articles say "Durham"; the two Northamptonshire councils share an outlet,
# so each needs its own full name.
AREA = {c: c.replace("-", " ").title() for c in CANDIDATES}
AREA.update({"county-durham": "Durham",
             "north-northamptonshire": "North Northamptonshire",
             "west-northamptonshire": "West Northamptonshire"})
REFORM_RE = re.compile(r"\bReform UK\b|\bFarage\b")


def window_articles() -> list[dict]:
    """Fetched articles (HTTP 200, with text) published 1-30 April 2025."""
    with (DATA / "targets.csv").open(encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    out = []
    for r in rows:
        path = cache_path(r)
        if path.exists():
            a = json.loads(path.read_text())
            if a.get("http_status") == 200 and a.get("text") and in_window(a):
                out.append(a)
    return out


def attribute(articles: list[dict]) -> dict[str, dict]:
    """council -> {"all": [...], "reform": [...]}: articles from the
    council's outlet whose headline + text names its area, and the subset
    mentioning Reform UK or Farage."""
    chosen = json.loads((OUT_DIR / "outlets.json").read_text())["chosen"]
    out = {}
    for council, outlet in chosen.items():
        name = re.compile(r"\b" + re.escape(AREA[council]) + r"\b")
        mine = [a for a in articles if a["outlet"] == outlet
                and name.search((a.get("headline") or "") + " " + a["text"])]
        out[council] = {"all": mine,
                        "reform": [a for a in mine
                                   if REFORM_RE.search((a.get("headline") or "")
                                                       + " " + a["text"])]}
    return out


def stage_count() -> None:
    """Per-council article counts and coverage volume V_c. Counts only; no
    article text is printed."""
    by = attribute(window_articles())
    table = {c: {"articles": len(v["all"]), "reform_articles": len(v["reform"]),
                 "V_reform_share": round(len(v["reform"]) / len(v["all"]), 3)
                 if v["all"] else None}
             for c, v in sorted(by.items())}
    n = [t["reform_articles"] for t in table.values()]
    summary = {"councils": len(table), "reform_articles_total": sum(n),
               "median_per_council": float(sorted(n)[len(n) // 2]),
               "councils_under_5": sum(x < 5 for x in n),
               "councils_under_10": sum(x < 10 for x in n)}
    (OUT_DIR / "coverage_counts.json").write_text(json.dumps(
        {"summary": summary, "per_council": table}, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, indent=2))
    for c, t in table.items():
        print(f"{c:24} {t['articles']:4} {t['reform_articles']:4} "
              f"{t['V_reform_share']}")


if __name__ == "__main__":
    {"probe": stage_probe, "targets": stage_targets,
     "fetch": stage_fetch, "count": stage_count}[sys.argv[1]]()
