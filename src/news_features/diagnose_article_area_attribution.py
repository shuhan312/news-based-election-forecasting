"""Can a news article be attributed to a division, or only to an election?

## Why this decides the shape of the news layer

The baseline predicts one row per election x area x party - 1,613 of them. If a
news feature can only be computed per election, then every area within an
election receives the identical value, the feature has four or nineteen distinct
values applied to 1,613 rows, and it can explain differences *between* elections
but nothing *within* one. Since the prediction problem is which area a party
does well in, that is close to no explanatory power at all.

It also decides whether one of the supervisor's stated hypotheses is testable:

    "Whether national Reform UK momentum identifies its general growth, while
     local coverage identifies the Surrey wards where that support is most
     likely to convert into votes or seats"

The first half needs only election-level features. The second half needs
area-level ones, and cannot be tested without them.

## What the search log already gives, and what it does not

Every article record carries `retrieval.search_query_id`, and the search log
carries a `ward` column per query, so an article inherits whatever area its
query named. The counts are computed from the canonical usable corpus at run
time. This matters because the main eligibility table is only one of three
adjudication streams; reading it alone produced the older 120-local figure.

That is the problem this module measures a way around.

## The three questions

1. **Can body text recover an area?** An article found by a county-wide search
   may still name a town or division in its text. Matching the 164 published
   area names against the body would raise attribution from 2.5% to whatever the
   text supports. This module measures that rate rather than assuming it.
2. **Where do the canonical local-arm articles sit?** If they concentrate in a
   few areas, those areas can carry genuine local-news features even if the
   rest cannot.
3. **What survives of the local/national comparison?** The current imbalance
   is measured and recorded by release rather than copied into this docstring.

## What this module deliberately does not do

It does not attribute anything. It measures how much attribution is available
and by what route, so the feature table can be designed on a measured rate
instead of a hope. A name match is also not a claim that the article is *about*
that area - "Woking" in a national story about housing policy is a mention, not
local coverage - and separating those is a judgement the extraction layer's
`local_impact` frame already addresses. This is the ceiling, not the answer.

Usage:
    python3 -m src.news_features.diagnose_article_area_attribution
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

RECORDS = Path("data/raw/news/records")
SEARCH_LOG = Path("news_collection/search_log.csv")
FUNDAMENTALS = Path("surrey-election-no-news-baseline/outputs/"
                    "electoral_fundamentals/electoral_fundamentals_features.csv")
# The summary is committed; the per-article detail is not. Every figure that
# matters is in the summary, so the split follows the same rule the batch
# manifests do: keep what a reader needs to check a claim, leave row-level
# detail on disk.
OUT = Path("news_features/article_area_attribution_summary.json")
OUT_DETAIL = Path("news_features/article_area_attribution_per_article.json")

# Suffixes the published names carry but a news article never would. "Addlestone
# Ward" and "Addlestone" are the same place to a journalist, so both published
# forms collapse to one search key.
NAME_SUFFIXES = (" Ward", " Division")

# Names too short or too generic to match on. "Ash" would match "ashes",
# "cash", "Ashford"; "Ewell" appears inside "Sewell". A false attribution is
# worse than none, because it puts an article's coverage in the wrong contest.
TOO_GENERIC = {"Ash", "Ewell", "Horley", "Hale"}


def area_names() -> dict[str, set[str]]:
    """Published area names, collapsed to a search key -> the ids that share it.

    Keyed by name rather than id because the same place appears under a 2013-21
    division id and a 2026 ward id; an article naming it is evidence for both,
    and which one applies is decided by the election the article belongs to.
    """
    by_name: dict[str, set[str]] = defaultdict(set)
    with FUNDAMENTALS.open(newline="") as handle:
        for r in csv.DictReader(handle):
            raw = (r.get("area_name") or "").strip()
            if not raw:
                continue
            name = raw
            for suffix in NAME_SUFFIXES:
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
            by_name[name.strip()].add(r["area_id"])
    return dict(by_name)


def build_patterns(names: dict[str, set[str]]) -> list[tuple[str, re.Pattern]]:
    """One word-boundary pattern per usable name, longest first.

    Longest first so that "Camberley West" is tested before "Camberley": a
    compound name is more specific, and crediting the shorter one when the
    longer is present would lose the distinction between two real divisions.
    Ampersands are matched as "and" too, because published names use "&" and
    prose does not.
    """
    usable = [n for n in names if n not in TOO_GENERIC and len(n) >= 5]
    out = []
    for name in sorted(usable, key=len, reverse=True):
        variants = {name}
        if "&" in name:
            variants.add(name.replace("&", "and"))
        alternation = "|".join(re.escape(v) for v in sorted(variants))
        out.append((name, re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE)))
    return out


def main() -> None:
    # Import here to keep the light-weight pattern helpers usable in isolation.
    # The canonical builder unions all three terminal-decision streams and
    # applies exactly the date/window/text rules used by feature construction.
    from src.news_collection.canonical_corpus_release import build_release

    release, included = build_release()
    log = {r["query_id"]: r for r in csv.DictReader(SEARCH_LOG.open())}
    names = area_names()
    patterns = build_patterns(names)

    print(f"published area names: {len(names)} distinct, "
          f"{len(patterns)} usable as patterns "
          f"({len(names) - len(patterns)} too short or too generic)")
    print(f"canonical release: {release['release_id']}")
    print(f"usable articles: {len(included)} "
          f"{release['usable_feature_corpus']['by_arm']}\n")

    from_query = Counter()          # how the search log attributes each article
    from_body = Counter()           # how many areas the body names
    areas_per_arm: dict[str, Counter] = {"local": Counter(), "national": Counter()}
    local_area_hits = Counter()     # which areas the local arm actually covers
    body_missing = 0
    rows_out = []

    for aid, article in included.items():
        record_path = RECORDS / f"{aid}.json"
        if not record_path.exists():
            continue
        record = json.loads(record_path.read_text())
        query = log.get((record.get("retrieval") or {}).get("search_query_id"))
        # Arm and election come from the canonical release. Query/record values
        # are retrieval evidence only and must not silently redefine the corpus.
        arm = article.get("arm") or "unknown"
        query_ward = ((query or {}).get("ward") or "").strip()
        from_query["specific_ward" if query_ward else "election_level_only"] += 1

        body = article.get("body") or ""
        if not body:
            body_missing += 1
            body_areas: list[str] = []
        else:
            head = (record.get("identity") or {}).get("headline") or ""
            haystack = f"{head}\n{body}"
            # Longest-first, and a matched compound removes its components so
            # "Camberley West" does not also count as "Camberley".
            body_areas = []
            for name, pattern in patterns:
                if pattern.search(haystack):
                    if not any(name in found for found in body_areas):
                        body_areas.append(name)

        from_body[min(len(body_areas), 4) if body_areas else 0] += 1
        for name in body_areas:
            areas_per_arm[arm if arm in areas_per_arm else "national"][name] += 1
        if arm == "local":
            for name in body_areas or ([query_ward] if query_ward else []):
                local_area_hits[name] += 1

        rows_out.append({
            "article_id": aid, "arm": arm,
            "election_id": article["election_id"],
            "query_ward": query_ward,
            "body_areas": body_areas,
            "attribution": ("query_ward" if query_ward
                            else "body_single" if len(body_areas) == 1
                            else "body_multiple" if body_areas
                            else "election_level_only"),
        })

    resolved = Counter(r["attribution"] for r in rows_out)
    total = len(rows_out)

    print("=== 1. What route attributes an article to an area ===")
    for route in ("query_ward", "body_single", "body_multiple",
                  "election_level_only"):
        n = resolved[route]
        print(f"  {route:22s} {n:5d}  {100*n/total:5.1f}%")
    single = resolved["query_ward"] + resolved["body_single"]
    print(f"\n  unambiguous single area: {single} of {total} = "
          f"{100*single/total:.1f}%   (was {resolved['query_ward']} = "
          f"{100*resolved['query_ward']/total:.1f}% from the query alone)")
    if body_missing:
        print(f"  articles with no text file: {body_missing}")

    print("\n=== 2. Where the local arm sits ===")
    arms = Counter(r["arm"] for r in rows_out)
    print(f"  arm split: {dict(arms)}")
    local_rows = [r for r in rows_out if r["arm"] == "local"]
    local_attr = Counter(r["attribution"] for r in local_rows)
    print(f"  local arm attribution: {dict(local_attr)}")
    print(f"  distinct areas the local arm names: {len(local_area_hits)}")
    for name, n in local_area_hits.most_common(10):
        print(f"      {name:34s} {n}")

    print("\n=== 3. What the local/national comparison has to work with ===")
    for arm in ("national", "local"):
        rs = [r for r in rows_out if r["arm"] == arm]
        with_area = sum(1 for r in rs
                        if r["attribution"] in ("query_ward", "body_single"))
        print(f"  {arm:9s} {len(rs):5d} articles, {with_area:5d} with a single "
              f"area ({100*with_area/max(len(rs),1):.1f}%), "
              f"{len({a for r in rs for a in r['body_areas']})} distinct areas named")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "canonical_corpus_release_id": release["release_id"],
        "canonical_corpus_manifest":
            "news_collection/canonical_corpus_release_v1.json",
        "articles": total,
        "published_area_names": len(names),
        "usable_patterns": len(patterns),
        "excluded_as_generic": sorted(TOO_GENERIC),
        "attribution_routes": dict(resolved),
        "arm_split": dict(arms),
        "local_arm_attribution": dict(local_attr),
        "local_arm_areas": dict(local_area_hits),
        "note": ("A name match is a ceiling on attribution, not a claim the "
                 "article is about that area. Deciding that is what the "
                 "local_impact frame is for."),
    }, indent=2))
    OUT_DETAIL.write_text(json.dumps({"per_article": rows_out}, indent=2))
    print(f"\n-> {OUT}\n-> {OUT_DETAIL} (per-article detail, gitignored)")


if __name__ == "__main__":
    main()
