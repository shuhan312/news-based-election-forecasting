"""Ward-level news coverage probe (Kent and Surrey, May 2021).

    PYTHONPATH=.:src python -m forecast.ward_coverage contests
    PYTHONPATH=.:src python -m forecast.ward_coverage targets
    PYTHONPATH=.:src python -m forecast.ward_coverage fetch
    PYTHONPATH=.:src python -m forecast.ward_coverage match

    Add "late" after a stage (targets / fetch / match) for amendment A2's
    window, 30-1 days before polling day (6 Apr - 5 May 2021), after the
    official candidate lists were published on 9 April.

Question: in the 90-31 days before polling day, how many divisions does
local news actually cover, by naming a candidate or the place? The answer
decides, before any 2025 result is opened, whether a ward-level news
hypothesis is worth designing. Training data (2021) only.

  contests  every contested 2021 division with its candidates' names
            (Democracy Club; names and ward labels only are kept)
  targets   the outlets' archived article URLs that fall in the window,
            found via article ids, which rise with publication date
  fetch     download those articles (reuses the outlet pilot's cache, so
            nothing already fetched is fetched again)
  match     deterministic name / place matching, and coverage measures

Criteria: v2_design/ward_coverage_v1/criteria.md.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests

from v2_design import keyword_prefilter as kp
from v2_design import outlet_pilot as pilot

DC_API = "https://candidates.democracyclub.org.uk/api/next/ballots/"
ELECTIONS = {"surrey": "local.surrey.2021-05-06",
             "kent": "local.kent.2021-05-06"}
DATA = Path("data/ward_probe")                       # gitignored
OUT_DIR = Path("v2_design/ward_coverage_v1")
CONTESTS = DATA / "contests.json"
TARGETS = DATA / "targets.csv"

# Amendment A2: the campaign after nominations. Statements of persons
# nominated were dated 9 April 2021, so the original 90-31 day window
# (ending 5 April) closed before new candidates were public.
LATE_PUB_START, LATE_PUB_END = date(2021, 4, 6), date(2021, 5, 5)
# Captures are listed to 31 May so that late-April articles archived after
# polling day are still found; only articles PUBLISHED in the window count.
LATE_CAP_START, LATE_CAP_END = date(2021, 4, 6), date(2021, 5, 31)
TARGETS_LATE = DATA / "targets_late.csv"


def targets_path(window: str) -> Path:
    return TARGETS_LATE if window == "late" else TARGETS


def in_window(article: dict, window: str = "main") -> bool:
    """Publication date inside the chosen window."""
    if window != "late":
        return pilot.in_window(article)
    d = article.get("published_date")
    return bool(d) and LATE_PUB_START <= date.fromisoformat(d) <= LATE_PUB_END

# Words that name a compass point or settlement type rather than a place.
GENERIC = {"north", "south", "east", "west", "central", "rural", "town",
           "villages", "village", "valley", "hills", "hill", "park",
           "common", "green", "the", "upper", "lower", "and", "with",
           "inner", "outer", "city", "borough", "ward", "division"}


# --- 1. contests -------------------------------------------------------------------

def stage_contests() -> None:
    """Contested divisions with candidates' names. Results are not kept."""
    out = []
    for county, eid in ELECTIONS.items():
        url, params = DC_API, {"election_id": eid, "page_size": 200}
        while url:
            body = requests.get(url, params=params, timeout=120).json()
            for b in body["results"]:
                if b.get("cancelled") or ".by." in b["ballot_paper_id"]:
                    continue
                names = [(c.get("person") or {}).get("name", "")
                         for c in b["candidacies"]]
                if len(names) <= b["winner_count"]:
                    continue                 # uncontested: no campaign to cover
                out.append({"county": county, "ballot": b["ballot_paper_id"],
                            "label": b["post"]["label"], "candidates": names})
            url, params = body.get("next"), None
    DATA.mkdir(parents=True, exist_ok=True)
    CONTESTS.write_text(json.dumps(out, indent=1))
    print(f"-> {CONTESTS}: {len(out)} contested divisions")


# --- 2. targets: window articles via monotonic ids ---------------------------------

def article_id(url: str) -> int | None:
    """The numeric article id at the end of an outlet URL.

    Reach sites: ...-20290053 ; BBC: ...-56962571 ; KentOnline: ...-243433/ ;
    Newsquest (Surrey Comet): /news/19279019.slug/ . Ids rise with
    publication date on every outlet here (checked on the pilot sample).
    """
    path = urlparse(url).path
    m = (re.search(r"/(\d{6,9})\.[^/]*/?$", path)
         or re.search(r"(\d{6,9})(?:\.amp)?/?$", path))
    return int(m.group(1)) if m else None


def _norm_url(url: str) -> str:
    """One key per article: no scheme, www, query, .amp or trailing slash."""
    u = urlparse(url)
    path = re.sub(r"\.amp$", "", u.path.rstrip("/"))
    return u.netloc.removeprefix("www.") + path


def id_bounds() -> dict[str, tuple[int, int]]:
    """Per outlet: (last sampled id before the window, first after it).

    Taken from the pilot's fetched sample, whose publication dates are
    known, so every id between the bounds is a window candidate.
    """
    sample = [json.loads(p.read_text()) for p in pilot.CACHE.glob("*.json")
              if not p.name.startswith(("cdx_", "batch_"))]
    bounds = {}
    for outlet in {s["outlet"] for s in sample}:
        before, after, inside = [], [], []
        for s in sample:
            if s["outlet"] != outlet or not s.get("published_date"):
                continue
            aid = article_id(s["url"])
            if aid is None:
                continue
            d = date.fromisoformat(s["published_date"])
            (before if d < pilot.PUB_START
             else after if d > pilot.PUB_END else inside).append(aid)
        lo = max(before) if before else min(inside)
        hi = min(after) if after else max(inside)
        bounds[outlet] = (lo, hi)
    return bounds


def stage_targets() -> None:
    bounds = id_bounds()
    rows, seen = [], set()
    for key, cfg in pilot.COUNCILS.items():
        for target, match in cfg["outlets"]:
            lo, hi = bounds[target]
            for ts, url in pilot.cdx_list(target, match):   # cached lists
                aid, norm = article_id(url), _norm_url(url)
                if aid is None or not lo <= aid <= hi or norm in seen:
                    continue
                seen.add(norm)
                rows.append({"council": key, "outlet": target,
                             "timestamp": ts, "url": url})
    DATA.mkdir(parents=True, exist_ok=True)
    with TARGETS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by = defaultdict(int)
    for r in rows:
        by[r["outlet"]] += 1
    print(f"-> {TARGETS}: {len(rows)} candidate articles", dict(by))


def _late_cdx_list(target: str, match: str) -> list[tuple[str, str]]:
    """Archived URLs for the late capture window, cached separately from
    the original window's lists (weekly chunks; KentOnline by section)."""
    slug = re.sub(r"[^a-z0-9]+", "_", target)
    pilot.CACHE.mkdir(parents=True, exist_ok=True)
    if match == "sections":
        out = []
        for section in pilot.KENTONLINE_SECTIONS:
            path = pilot.CACHE / f"cdx_{slug}_{section}_late.json"
            if not path.exists():
                path.write_text(json.dumps(pilot._cdx_chunk(
                    f"{target}/{section}/news/", "prefix",
                    LATE_CAP_START, LATE_CAP_END)))
            out += [tuple(x) for x in json.loads(path.read_text())]
        return out
    out, start = [], LATE_CAP_START
    while start <= LATE_CAP_END:
        end = min(date.fromordinal(start.toordinal() + 6), LATE_CAP_END)
        path = pilot.CACHE / f"cdx_{slug}_late_{start:%Y%m%d}.json"
        if not path.exists():
            path.write_text(json.dumps(pilot._cdx_chunk(target, match,
                                                        start, end)))
        out += [tuple(x) for x in json.loads(path.read_text())]
        start = date.fromordinal(end.toordinal() + 1)
    return out


def late_id_bounds() -> dict[str, tuple[int, int]]:
    """Per outlet: (last sampled id published before 6 April, highest
    sampled id). The pilot sample's captures end on 5 May, so its highest
    id is about polling eve; later (post-election) ids are not fetched."""
    sample = [json.loads(p.read_text()) for p in pilot.CACHE.glob("*.json")
              if not p.name.startswith(("cdx_", "batch_"))
              and not p.name.endswith("_late.json")]
    bounds = {}
    for outlet in {s.get("outlet") for s in sample if s.get("outlet")}:
        before, all_ids = [], []
        for s in sample:
            if s.get("outlet") != outlet or not s.get("published_date"):
                continue
            aid = article_id(s["url"])
            if aid is None:
                continue
            all_ids.append(aid)
            if date.fromisoformat(s["published_date"]) < LATE_PUB_START:
                before.append(aid)
        if all_ids:
            bounds[outlet] = (max(before) if before else min(all_ids),
                              max(all_ids))
    return bounds


def stage_targets_late() -> None:
    bounds = late_id_bounds()
    rows, seen = [], set()
    for key, cfg in pilot.COUNCILS.items():
        for target, match in cfg["outlets"]:
            lo, hi = bounds[target]
            for ts, url in _late_cdx_list(target, match):
                aid, norm = article_id(url), _norm_url(url)
                if aid is None or not lo <= aid <= hi or norm in seen:
                    continue
                seen.add(norm)
                rows.append({"council": key, "outlet": target,
                             "timestamp": ts, "url": url})
    with TARGETS_LATE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by = defaultdict(int)
    for r in rows:
        by[r["outlet"]] += 1
    print(f"-> {TARGETS_LATE}: {len(rows)} candidate articles", dict(by))


# --- 3. fetch (shared, resumable cache) ------------------------------------------------

WORKERS = 4      # concurrent downloads; each still pauses between requests


def _fetch_and_cache(row: dict) -> None:
    path = pilot._cache_path(row)
    if not path.exists():
        path.write_text(json.dumps(pilot.fetch_one(row)), encoding="utf-8")


def stage_fetch(window: str = "main") -> None:
    """Download every target article, four at a time.

    At about 3-4 s per article (page load plus the polite pause in
    http_get), 10,000 articles one by one would take ten hours. Four workers
    keep each outlet's load to a few requests at a time. The cache makes the
    stage resumable: an interrupted run restarts where it stopped.
    """
    from concurrent.futures import ThreadPoolExecutor
    with targets_path(window).open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    pilot.CACHE.mkdir(parents=True, exist_ok=True)
    todo = [r for r in rows if not pilot._cache_path(r).exists()]
    print(f"{len(rows) - len(todo)} cached, {len(todo)} to fetch", flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i, _ in enumerate(pool.map(_fetch_and_cache, todo)):
            if i % 250 == 0:
                print(f"fetched {i}/{len(todo)}", flush=True)


# --- 4. match ----------------------------------------------------------------------

def place_tokens(label: str) -> list[str]:
    """Distinctive place names in a division label.

    'Bagshot, Windlesham & Chobham' -> ['bagshot', 'windlesham', 'chobham'];
    'Tunbridge Wells East' -> ['tunbridge wells']. Generic words are
    dropped and anything shorter than 4 letters is ignored.
    """
    out = []
    for part in re.split(r",|&|\band\b", label, flags=re.IGNORECASE):
        words = [w for w in re.findall(r"[A-Za-z'’-]+", part)
                 if w.lower() not in GENERIC]
        phrase = " ".join(words).strip().lower()
        if len(phrase.replace(" ", "")) >= 4:
            out.append(phrase)
    return out


def _has(text: str, phrase: str) -> bool:
    return re.search(r"\b" + re.escape(phrase) + r"\b", text,
                     re.IGNORECASE) is not None


def coverage(contests: list[dict], articles: list[dict]) -> dict:
    """Per-division covering articles and the W1-W4 measures."""
    hits = {c["ballot"]: {"C": set(), "P": set()} for c in contests}
    for a in articles:
        text = kp.article_text(a["headline"], a["text"])
        political = kp.passes(text)
        for c in contests:
            if c["county"] != a["council"]:
                continue
            if any(len(n.split()) >= 2 and _has(text, n)
                   for n in c["candidates"]):
                hits[c["ballot"]]["C"].add(a["url"])
            if political and any(_has(text, t)
                                 for t in place_tokens(c["label"])):
                hits[c["ballot"]]["P"].add(a["url"])

    def measures(subset):
        n = len(subset)
        if n == 0:                       # e.g. a county with no contests
            return {"divisions": 0}
        both = [len(hits[c["ballot"]]["C"] | hits[c["ballot"]]["P"])
                for c in subset]
        cand = [len(hits[c["ballot"]]["C"]) for c in subset]
        covered = sorted(x for x in both if x)
        return {"divisions": n,
                "W1_any": round(sum(x >= 1 for x in both) / n, 3),
                "W2_candidate": round(sum(x >= 1 for x in cand) / n, 3),
                "W3_three_plus": round(sum(x >= 3 for x in both) / n, 3),
                "W4_median_articles_if_covered":
                    covered[len(covered) // 2] if covered else 0}

    per_county = {k: measures([c for c in contests if c["county"] == k])
                  for k in ELECTIONS}
    return {"pooled": measures(contests), "per_county": per_county,
            "per_division": {c["ballot"]: {"label": c["label"],
                                           "C": len(hits[c["ballot"]]["C"]),
                                           "P": len(hits[c["ballot"]]["P"])}
                             for c in contests}}


def stage_match(window: str = "main") -> None:
    contests = json.loads(CONTESTS.read_text())
    with targets_path(window).open(encoding="utf-8") as handle:
        targets = list(csv.DictReader(handle))
    articles = []
    for row in targets:
        path = pilot._cache_path(row)
        if not path.exists():
            continue
        a = json.loads(path.read_text())
        if a.get("text") and in_window(a, window):
            articles.append(a)
    result = coverage(contests, articles)
    W1 = result["pooled"]["W1_any"]
    verdict = ("viable" if W1 >= 0.50 else "marginal" if W1 >= 0.25
               else "not viable")
    payload = {"criteria": "v2_design/ward_coverage_v1/criteria.md",
               "targets": len(targets), "window_articles": len(articles),
               "articles_by_council": {k: sum(a["council"] == k
                                              for a in articles)
                                       for k in ELECTIONS},
               **{k: v for k, v in result.items() if k != "per_division"},
               "verdict": verdict}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "_late" if window == "late" else ""
    payload["window"] = window
    (OUT_DIR / f"coverage_results{suffix}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / f"coverage_per_division{suffix}.json").write_text(
        json.dumps(result["per_division"], indent=1) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    stage, window = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2
                                  else "main")
    if stage == "targets":
        stage_targets_late() if window == "late" else stage_targets()
    elif stage == "fetch":
        stage_fetch(window)
    elif stage == "match":
        stage_match(window)
    else:
        {"contests": stage_contests}[stage]()
