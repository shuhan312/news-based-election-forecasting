"""Cut canonical news release v2: principal corpus plus by-elections.

    python3 -m src.news_collection.canonical_corpus_release_v2

Release v1 (`canonical-news-v1-59d113bb9c28`) froze the principal-election
corpus at 1,632 articles and is left byte-identical: every pre-enrichment
result cites it and must stay reproducible against it. Release v2 is the
enrichment corpus - the same frozen selection machinery run twice:

1. once with pristine globals, reproducing the v1 principal selection
   exactly (its release id is recorded and asserted unchanged); then
2. once with the extraction module's inputs pointed at the by-election
   decisions and dates and the eight pre-holdout by-elections added to
   the polling registry, selecting the by-election articles under the
   same date, window and text rules.

The patch is applied inside a ``try/finally`` that restores every global
it touched, because ``canonical_corpus_release`` (v1) and the by-election
wrappers share ``run_corpus_extraction``'s module state: a v1 release cut
after an unrestored patch would silently read by-election inputs, which
is exactly the mixed-version corpus the release system exists to prevent.

``mentions_reform`` is stamped on by-election articles with the same rule
the normalised layer applies to principal articles - the substring
"reform uk" in the lower-cased title plus body (`run_pilot.py`). Without
it every by-election article would count as not mentioning Reform,
because they all ride the raw-text fallback that skips that layer.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from src.llm_extraction import run_corpus_extraction as frozen
from src.news_collection import canonical_corpus_release as v1
from src.news_collection.run_byelection_stages import BYELECTION_POLLING_DAYS

REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / "news_collection/canonical_corpus_release_v2.json"

BYELECTION_DECISIONS = REPO / "news_collection/byelection_eligibility_decisions.csv"
BYELECTION_DATES = REPO / "news_collection/byelection_effective_dates_v1.csv"

RULES_VERSION = "canonical-principal-plus-byelection-news-v2"


def _byelection_articles() -> tuple[dict[str, dict], dict]:
    """Select usable by-election articles with the frozen machinery.

    Saves, patches and restores the shared module globals; nothing outside
    this function ever sees the patched state.
    """

    saved = {
        "DECISIONS": frozen.DECISIONS,
        "EFFECTIVE_DATES": frozen.EFFECTIVE_DATES,
        "PILOT_SHEET": frozen.PILOT_SHEET,
        "VALIDATION_SHEET": frozen.VALIDATION_SHEET,
    }
    added_polling = [
        election_id for election_id in BYELECTION_POLLING_DAYS
        if election_id not in frozen.POLLING
    ]
    try:
        frozen.DECISIONS = BYELECTION_DECISIONS
        frozen.EFFECTIVE_DATES = BYELECTION_DATES
        # The pilot/validation sheets carry principal includes only; an empty
        # stream keeps them out of the by-election union without editing v1.
        frozen.PILOT_SHEET = Path("/dev/null")
        frozen.VALIDATION_SHEET = Path("/dev/null")
        frozen.POLLING.update(BYELECTION_POLLING_DAYS)

        terminal = frozen.eligible_articles()
        usable, fallback_ids, census = frozen.load_tranche(
            "byelectionrelease", only_ids=set(terminal)
        )
    finally:
        for name, value in saved.items():
            setattr(frozen, name, value)
        for election_id in added_polling:
            frozen.POLLING.pop(election_id, None)

    for article in usable.values():
        text = ((article.get("title") or "") + " "
                + (article.get("body") or "")).lower()
        article["mentions_reform"] = "reform uk" in text
    census["terminal_includes"] = len(terminal)
    census["raw_text_fallback"] = len(fallback_ids)
    return usable, census


def build_release() -> tuple[dict, dict[str, dict]]:
    """Return the v2 release metadata and the union article map."""

    principal_report, principal = v1.build_release()

    byelection, byelection_census = _byelection_articles()

    overlap = set(principal) & set(byelection)
    assert not overlap, (
        f"{len(overlap)} article ids appear in both corpora; the release "
        "families must stay disjoint"
    )
    union = {**principal, **byelection}

    def counts(articles: dict[str, dict]) -> dict:
        by_arm = Counter((a.get("arm") or "unknown") for a in articles.values())
        by_election = Counter(a["election_id"] for a in articles.values())
        by_window = Counter(a["window"] for a in articles.values())
        by_election_arm: dict[str, Counter] = defaultdict(Counter)
        for a in articles.values():
            by_election_arm[a["election_id"]][a.get("arm") or "unknown"] += 1
        return {
            "articles": len(articles),
            "by_arm": dict(sorted(by_arm.items())),
            "by_election": dict(sorted(by_election.items())),
            "by_window": dict(sorted(by_window.items())),
            "by_election_and_arm": {
                election: dict(sorted(arms.items()))
                for election, arms in sorted(by_election_arm.items())
            },
        }

    byelection_hashes = {
        str(path.relative_to(REPO)): v1._sha256(path)
        for path in (BYELECTION_DECISIONS, BYELECTION_DATES)
    }
    identity_payload = {
        "rules_version": RULES_VERSION,
        "principal_release_id": principal_report["release_id"],
        "byelection_source_sha256": byelection_hashes,
    }
    release_id = "canonical-news-v2-" + hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]

    report = {
        "release_id": release_id,
        "rules_version": RULES_VERSION,
        "window_scheme": principal_report["window_scheme"],
        "scope": (
            "Principal elections plus the eight pre-holdout by-elections; "
            "terminal include decisions, usable date, 1-180 days before "
            "each election's own polling day, usable article text. The two "
            "by-elections inside the 2026 holdout period are excluded."
        ),
        "principal_release": {
            "release_id": principal_report["release_id"],
            "articles": principal_report["usable_feature_corpus"]["articles"],
        },
        "byelection_census": byelection_census,
        # The feature builder reads this block; its shape matches v1's.
        "usable_feature_corpus": counts(union),
        "by_family": {
            "principal": counts(principal),
            "byelection": counts(byelection),
        },
        "terminal_include_union": {
            "articles": (principal_report["terminal_include_union"]["articles"]
                         + byelection_census["terminal_includes"]),
        },
        "excluded_after_terminal_include":
            principal_report["excluded_after_terminal_include"],
        "byelection_source_sha256": byelection_hashes,
        "article_ids_sha256": hashlib.sha256(
            "\n".join(sorted(union)).encode("utf-8")
        ).hexdigest(),
        "article_ids": sorted(union),
    }
    return report, union


def main() -> None:
    report, union = build_release()
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    corpus = report["usable_feature_corpus"]
    print(f"release: {report['release_id']}")
    print(f"articles: {corpus['articles']} "
          f"(principal {report['by_family']['principal']['articles']}, "
          f"byelection {report['by_family']['byelection']['articles']})")
    print(f"by arm: {corpus['by_arm']}")
    print(f"-> {OUTPUT}")


if __name__ == "__main__":
    main()
