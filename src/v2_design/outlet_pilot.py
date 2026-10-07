"""End-to-end outlet-first pilot: Kent 2021 vs Surrey 2021.

The first run of V2's whole local-news pipeline on real, unfiltered outlet
output:

    sample    list each outlet's archived article URLs (Wayback CDX) and draw
              a fixed random sample - committed with the criteria
    fetch     download each sampled article (live page first, Wayback capture
              as fallback) and parse headline, date and text with V1's parser
    classify  keep in-window articles, apply keyword prefilter v1, then run
              V1's frozen relevance classifier on the survivors
    report    turn the sample rates into per-county, per-party projections

Run the stages in order:
  PYTHONPATH=.:src python -m v2_design.outlet_pilot sample
  PYTHONPATH=.:src python -m v2_design.outlet_pilot fetch
  PYTHONPATH=.:src python -m v2_design.outlet_pilot classify
  PYTHONPATH=.:src python -m v2_design.outlet_pilot report

Fetch and classify are resumable: finished articles are cached under
data/v2_pilot/ (gitignored, because it holds article text) and skipped on
rerun. Criteria: v2_design/outlet_pilot_v1/criteria.md.

No election outcome is read. Every capture predates polling day (6 May 2021),
so no post-election page can be fetched.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests

from news_collection.adapters import extract_html_metadata, http_get
from news_collection import llm_classifier_v2 as clf
from v2_design import keyword_prefilter as kp

OUT_DIR = Path("v2_design/outlet_pilot_v1")       # committed outputs
CACHE = Path("data/v2_pilot")                     # article text, gitignored
SAMPLE_CSV = OUT_DIR / "sample.csv"
CDX = "https://web.archive.org/cdx/search/cdx"

POLLING_DAY = date(2021, 5, 6)
# Publication window: 90 to 31 days before polling day (V2's primary window).
PUB_START, PUB_END = date(2021, 2, 5), date(2021, 4, 5)
# Capture window: from the start of the publication window up to the eve of
# polling day. Articles published in the window are often captured weeks
# later, and stopping on 5 May means no capture can postdate the vote.
CAP_START, CAP_END = date(2021, 2, 5), date(2021, 5, 5)

SAMPLE_PER_OUTLET = 100
SEED = 20261007

# Analogous outlets: the county's Reach live site, its BBC regional page and
# its main independent paper. getsurrey.co.uk is SurreyLive's 2021 domain,
# the one V1's 2021 articles were collected from.
#
# Where a site keeps its news under /news/, only that section is listed.
# Whole-domain queries also return images, sport, listings and ads, and on
# getsurrey.co.uk they timed out (HTTP 504) on Wayback. Restricting to /news/
# was 2-4x faster and is where political coverage lives. KentOnline files
# news under /<town>/news/, which no single prefix covers, and its
# whole-domain listing failed on Wayback (repeated HTTP 504), so it is listed
# section by section (KENTONLINE_SECTIONS) and merged into one outlet.
COUNCILS = {
    "surrey": {"name": "Surrey", "election_id": "local.surrey.2021-05-06",
               "outlets": [("getsurrey.co.uk/news/", "prefix"),
                           ("bbc.co.uk/news/uk-england-surrey", "prefix"),
                           ("surreycomet.co.uk/news/", "prefix")]},
    "kent": {"name": "Kent", "election_id": "local.kent.2021-05-06",
             "outlets": [("kentlive.news/news/", "prefix"),
                         ("bbc.co.uk/news/uk-england-kent", "prefix"),
                         ("kentonline.co.uk", "sections")]},
}

# KentOnline's town news sections, read from its homepage on 2026-10-07, plus
# three towns its 2021 coverage is known to have used (sevenoaks, tonbridge,
# whitstable). Excluded: whats-on (listings) and bexley-and-bromley (London
# boroughs, outside Kent County Council). A section that did not exist in
# 2021 simply returns no captures.
KENTONLINE_SECTIONS = [
    "kent", "maidstone", "dover", "thanet", "ashford", "medway", "folkestone",
    "dartford", "canterbury", "deal", "tunbridge-wells", "romney-marsh",
    "gravesend", "sittingbourne", "malling", "hythe", "herne-bay", "weald",
    "sheerness", "faversham", "sevenoaks", "tonbridge", "whitstable",
]

# Party groups for the per-party projection. These are the same surface
# forms the prefilter uses, grouped by party.
PARTY_PATTERNS = {
    "conservative": ["conservative", "conservatives", "tory", "tories"],
    "labour": ["labour"],
    "liberal_democrat": ["liberal democrat", "liberal democrats", "lib dem",
                         "lib dems", "libdem", "libdems"],
    "green": ["green party", "greens"],
    "reform_uk": ["reform uk", "reform party"],
}


# --- stage: sample ------------------------------------------------------------

def _articleish(url: str) -> bool:
    # V1's WaybackAdapter._articleish rule, unchanged, so "article-like"
    # means the same thing here as it did in V1's collection.
    from news_collection.adapters import WaybackAdapter
    return WaybackAdapter._articleish(url)


def _cdx_chunk(target: str, match: str, start: date, end: date) -> list:
    params = {"url": target, "matchType": match,
              "from": start.strftime("%Y%m%d"), "to": end.strftime("%Y%m%d"),
              "filter": ["statuscode:200", "mimetype:text/html"],
              "collapse": "urlkey", "output": "json", "limit": 100000}
    # Wayback is a free public service that throttles heavy users. Back off
    # for longer each time (1, 2, 4, 8, 16 minutes) rather than hammering it.
    for attempt in range(6):
        try:
            r = requests.get(CDX, params=params, timeout=600)
            if r.status_code == 200:
                rows = r.json()[1:] if r.text.strip() else []
                return [(row[1], row[2]) for row in rows if _articleish(row[2])]
            print(f"  CDX {r.status_code} {target} {start}", flush=True)
        except (requests.RequestException, ValueError) as exc:
            print(f"  CDX error {target} {start}: {type(exc).__name__}",
                  flush=True)
        time.sleep(60 * 2 ** attempt)
    raise RuntimeError(f"CDX failed for {target} {start}..{end}")


def cdx_list(target: str, match: str) -> list[tuple[str, str]]:
    """(timestamp, url) for every article-like capture in the capture window.

    Large domains time out when the whole window is requested at once, so the
    window is queried one week at a time and the results are merged. Every
    finished week is cached on its own, so a failure loses at most the week
    in progress, and a rerun resumes where the last one stopped.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", target)
    CACHE.mkdir(parents=True, exist_ok=True)
    if match == "sections":
        # One small prefix per town section, each fetched for the whole
        # window in a single request and cached on its own.
        captures = []
        for section in KENTONLINE_SECTIONS:
            path = CACHE / f"cdx_{slug}_{section}.json"
            if not path.exists():
                path.write_text(json.dumps(_cdx_chunk(
                    f"{target}/{section}/news/", "prefix", CAP_START, CAP_END)))
                print(f"  {target}/{section} done", flush=True)
                time.sleep(10)
            captures += [tuple(x) for x in json.loads(path.read_text())]
        return captures
    captures, start = [], CAP_START
    while start <= CAP_END:
        end = min(date.fromordinal(start.toordinal() + 6), CAP_END)
        week = CACHE / f"cdx_{slug}_{start:%Y%m%d}.json"
        if not week.exists():
            week.write_text(json.dumps(_cdx_chunk(target, match, start, end)))
            print(f"  {target} {start} done", flush=True)
            time.sleep(10)   # polite pause between weeks
        captures += [tuple(x) for x in json.loads(week.read_text())]
        start = date.fromordinal(end.toordinal() + 1)
    return captures


def stage_sample() -> None:
    rng = random.Random(SEED)
    rows, population = [], {}
    for key, cfg in COUNCILS.items():
        for target, match in cfg["outlets"]:
            captures = cdx_list(target, match)
            # Many URLs are captured several times. Keep the earliest capture
            # per URL so each article is one population unit.
            first = {}
            for ts, url in sorted(captures):
                first.setdefault(url.split("://", 1)[-1].removeprefix("www."),
                                 (ts, url))
            units = sorted(first.values())
            population[target] = len(units)
            for ts, url in rng.sample(units, min(SAMPLE_PER_OUTLET, len(units))):
                rows.append({"council": key, "outlet": target,
                             "timestamp": ts, "url": url})
            print(target, len(units), flush=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with SAMPLE_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["council", "outlet",
                                                    "timestamp", "url"])
        writer.writeheader()
        writer.writerows(rows)
    (OUT_DIR / "population.json").write_text(
        json.dumps({"capture_window": [str(CAP_START), str(CAP_END)],
                    "article_like_urls": population}, indent=2) + "\n",
        encoding="utf-8")


# --- stage: fetch -------------------------------------------------------------

def _cache_path(row: dict) -> Path:
    # One cache file per URL, named by a hash so any URL is a safe filename.
    return CACHE / (hashlib.sha256(row["url"].encode()).hexdigest()[:20] + ".json")


def _parse_date(meta: dict) -> str | None:
    """First parseable ISO date among V1's extracted date candidates."""
    for d in meta.get("dates") or []:
        value = str(d.get("value", ""))[:10]
        try:
            date.fromisoformat(value)
            return value
        except ValueError:
            continue
    return None


def fetch_one(row: dict) -> dict:
    """Live page first; Wayback capture as fallback (V1's access policy)."""
    resp, route = http_get(row["url"]), "live_page"
    if resp is None or resp.status_code != 200:
        archive = f"https://web.archive.org/web/{row['timestamp']}/{row['url']}"
        resp, route = http_get(archive, archive=True), "wayback_capture"
    ok = resp is not None and resp.status_code == 200
    meta = extract_html_metadata(resp.text) if ok else {"dates": []}
    return {**row, "route": route,
            "http_status": getattr(resp, "status_code", None),
            "headline": meta.get("headline"),
            "published_date": _parse_date(meta),
            "text": meta.get("text") or ""}


def stage_fetch() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    with SAMPLE_CSV.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for i, row in enumerate(rows):
        path = _cache_path(row)
        if path.exists():
            continue
        path.write_text(json.dumps(fetch_one(row)), encoding="utf-8")
        if i % 25 == 0:
            print(f"fetched {i}/{len(rows)}", flush=True)


# --- stage: classify ----------------------------------------------------------

def _county_reason_codes(county: str) -> dict:
    """V1's reason-code texts with the county name substituted, nothing else.

    The L3 and L4 definitions name "Surrey" literally. For Kent articles that
    one word becomes "Kent". Every other character of the frozen v2 prompt
    is unchanged.
    """
    patched = copy.deepcopy(clf.REASON_CODE_DEFINITIONS)
    for codes in patched.values():
        for code, text in codes.items():
            codes[code] = text.replace("Surrey", county)
    return patched


def classify_one(cached: dict, council: dict) -> dict:
    article = {
        "article_id": "PILOT-" + _cache_path(cached).stem,
        "headline": cached["headline"] or "",
        "text": cached["text"],
        "text_source": "outlet_pilot_fetch",
        "source_id": cached["outlet"],
        "election_id": council["election_id"],
        "arm": "local",
        "day_index_from_polling_day":
            (POLLING_DAY - date.fromisoformat(cached["published_date"])).days,
        "needs_reform_disambiguation": "no",
        "search_query_id": "", "ward": "",
        "query_text": "outlet-first enumeration (no search query)",
        "query_family": "outlet_pilot",
        "geographic_scope": f"{council['name']}-wide outlet",
    }
    # Swap the definitions in for this call only. The prompt builder reads
    # the module-level name, so patching it is enough; restoring it in
    # `finally` guarantees V1 code never sees the patched text afterwards.
    original = clf.REASON_CODE_DEFINITIONS
    clf.REASON_CODE_DEFINITIONS = _county_reason_codes(council["name"])
    try:
        result = clf.classify_article_v2(article)
    finally:
        clf.REASON_CODE_DEFINITIONS = original
    return {"status": result.get("status"),
            "e5_decision": result.get("e5_decision"),
            "e5_reason_code": result.get("e5_reason_code")}


def in_window(cached: dict) -> bool:
    d = cached.get("published_date")
    return bool(d) and PUB_START <= date.fromisoformat(d) <= PUB_END


def stage_classify() -> None:
    for path in sorted(CACHE.glob("*.json")):
        cached = json.loads(path.read_text(encoding="utf-8"))
        if "classified" in cached or not in_window(cached):
            continue
        text = kp.article_text(cached["headline"], cached["text"])
        cached["prefilter_pass"] = kp.passes(text)
        if cached["prefilter_pass"]:
            cached["classified"] = classify_one(cached,
                                                COUNCILS[cached["council"]])
        else:
            cached["classified"] = None   # dropped by the prefilter, no call
        path.write_text(json.dumps(cached), encoding="utf-8")


# --- stage: report ------------------------------------------------------------

def _mentions(text: str, forms: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(f) + r"\b", text, re.IGNORECASE)
               for f in forms)


def stage_report() -> None:
    population = json.loads((OUT_DIR / "population.json").read_text())
    cached = [json.loads(p.read_text()) for p in CACHE.glob("*.json")]
    report = {}
    for key, cfg in COUNCILS.items():
        outlets, totals = {}, Counter()
        for target, _ in cfg["outlets"]:
            rows = [c for c in cached if c["outlet"] == target]
            fetched = [c for c in rows if c["text"]]
            window = [c for c in fetched if in_window(c)]
            passed = [c for c in window if c.get("prefilter_pass")]
            ok = [c for c in passed if (c.get("classified") or {}).get("status") == "ok"]
            included = [c for c in ok if c["classified"]["e5_decision"] == "include"]
            n_pop = population["article_like_urls"][target]
            # Projection: population x share of sampled URLs that are
            # in-window articles x prefilter pass x classifier include.
            scale = n_pop / len(rows) if rows else 0
            proj = {"in_window": len(window) * scale,
                    "relevant": len(included) * scale}
            for party, forms in PARTY_PATTERNS.items():
                hits = sum(_mentions(kp.article_text(c["headline"], c["text"]),
                                     forms) for c in included)
                proj[f"party_{party}"] = hits * scale
            totals.update(proj)
            outlets[target] = {
                "population_urls": n_pop, "sampled": len(rows),
                "fetched_with_text": len(fetched), "in_window": len(window),
                "prefilter_pass": len(passed), "classified_ok": len(ok),
                "classifier_include": len(included),
                "projected": {k: round(v, 1) for k, v in proj.items()},
            }
        # The four parties that stood across both counties in 2021. Reform
        # is reported but left out of the median: it fielded few candidates
        # in 2021, so its coverage measures party size, not outlet depth.
        main = sorted(totals[f"party_{p}"] for p in
                      ("conservative", "labour", "liberal_democrat", "green"))
        report[key] = {"outlets": outlets,
                       "projected_total": {k: round(v, 1)
                                           for k, v in totals.items()},
                       "median_main_party": round((main[1] + main[2]) / 2, 1)}
    s, k = report["surrey"], report["kent"]
    report["ratio_kent_to_surrey_median_main_party"] = (
        round(k["median_main_party"] / s["median_main_party"], 3)
        if s["median_main_party"] else None)
    (OUT_DIR / "pilot_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    {"sample": stage_sample, "fetch": stage_fetch,
     "classify": stage_classify, "report": stage_report}[sys.argv[1]]()
