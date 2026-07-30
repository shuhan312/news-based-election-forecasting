"""Build the single, auditable input release for the principal-election news layer.

Why this file exists
--------------------
The repository contains several truthful but different article counts:

* the main eligibility decision table;
* the pilot and validation sheets that were adjudicated earlier; and
* the subset of their union that has a date, falls in the six confirmed
  windows, and has usable text.

Those are different stages of the same funnel, not competing estimates.  A
downstream script that reads only the main decision table sees fewer local
articles than the extraction and feature pipelines.  This module makes the
union and the final usable subset explicit, hashes the inputs, and assigns a
stable release id.  Feature builders and diagnostics can then prove that they
used the same corpus instead of relying on a filename or a remembered count.

Usage:
    PYTHONPATH=src .venv/bin/python -m news_collection.canonical_corpus_release
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from src.llm_extraction.run_corpus_extraction import (
    DECISIONS,
    EFFECTIVE_DATES,
    PILOT_SHEET,
    VALIDATION_SHEET,
    eligible_articles,
    load_tranche,
)
from src.news_modelling.window_schemes import ORIGINAL_EMAIL

REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / "news_collection/canonical_corpus_release_v1.json"
SOURCE_FILES = (DECISIONS, PILOT_SHEET, VALIDATION_SHEET, EFFECTIVE_DATES)


def _repo_path(path: Path) -> Path:
    """Resolve paths whether the caller runs from the repository root or not."""

    return path if path.is_absolute() else REPO / path


def _sha256(path: Path) -> str:
    """Hash an input so a release can be reproduced from exact source bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _main_decision_counts() -> dict:
    """Count the main decision table without pretending it is the full union."""

    included = []
    with _repo_path(DECISIONS).open(encoding="utf-8-sig", newline="") as handle:
        included = [
            row for row in csv.DictReader(handle)
            if row.get("overall_decision") == "include"
        ]
    arms = Counter((row.get("arm") or "unknown") for row in included)
    return {"articles": len(included), "by_arm": dict(sorted(arms.items()))}


def build_release() -> tuple[dict, dict[str, dict]]:
    """Return release metadata and the articles usable by feature builders.

    ``eligible_articles`` is the terminal-decision union. ``load_tranche`` then
    applies the principal-election scope, effective dates, the supervisor-
    confirmed six-window scheme and text availability. Keeping both numbers is
    intentional: it explains why 1,638 eligible records become 1,632 usable
    records without silently dropping six articles.
    """

    terminal = eligible_articles()
    usable, raw_text_fallback_ids, census = load_tranche(
        "all", only_ids=set(terminal)
    )

    by_arm = Counter((article.get("arm") or "unknown")
                     for article in usable.values())
    by_election = Counter(article["election_id"] for article in usable.values())
    by_window = Counter(article["window"] for article in usable.values())
    by_election_arm: dict[str, Counter] = defaultdict(Counter)
    for article in usable.values():
        by_election_arm[article["election_id"]][
            article.get("arm") or "unknown"
        ] += 1

    hashes = {
        str(_repo_path(path).relative_to(REPO)): _sha256(_repo_path(path))
        for path in SOURCE_FILES
    }
    identity_payload = {
        "rules_version": "canonical-principal-news-v1",
        "window_scheme": ORIGINAL_EMAIL.key,
        "source_sha256": hashes,
    }
    release_id = "canonical-news-v1-" + hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]

    missing_text_ids = sorted(census.get("no_extracted_text_ids") or [])
    report = {
        "release_id": release_id,
        "rules_version": identity_payload["rules_version"],
        "window_scheme": ORIGINAL_EMAIL.key,
        "scope": (
            "Principal elections only; terminal include decisions from the "
            "main, pilot and validation adjudication streams; usable date; "
            "1-180 days before polling; usable article text."
        ),
        # This is the source of the old 120-local figure. It remains useful,
        # but is labelled as one input stream rather than the final corpus.
        "main_decision_table_only": _main_decision_counts(),
        "terminal_include_union": {
            "articles": len(terminal),
            "by_arm": dict(sorted(Counter(
                (row.get("arm") or "unknown") for row in terminal.values()
            ).items())),
        },
        "usable_feature_corpus": {
            "articles": len(usable),
            "by_arm": dict(sorted(by_arm.items())),
            "by_election": dict(sorted(by_election.items())),
            "by_window": dict(sorted(by_window.items())),
            "by_election_and_arm": {
                election: dict(sorted(counts.items()))
                for election, counts in sorted(by_election_arm.items())
            },
        },
        "excluded_after_terminal_include": {
            "articles": len(terminal) - len(usable),
            "no_effective_date": census.get("no_effective_date", 0),
            "not_a_principal_election": census.get(
                "not_a_principal_election", 0
            ),
            "outside_all_windows": census.get("outside_all_windows", 0),
            "no_extracted_text": census.get("no_extracted_text", 0),
            "no_extracted_text_ids": missing_text_ids,
        },
        "raw_text_fallback_articles": len(raw_text_fallback_ids),
        "source_sha256": hashes,
        "article_ids_sha256": hashlib.sha256(
            "\n".join(sorted(usable)).encode("utf-8")
        ).hexdigest(),
        "article_ids": sorted(usable),
        "count_interpretation": {
            "120_local": (
                "Local includes in the main decision table only; not the "
                "canonical union used by extraction and full-corpus features."
            ),
            "188_local": (
                "Local articles in the current usable canonical feature corpus."
            ),
        },
    }

    # These invariants are deliberately fatal. A feature build should stop
    # before writing a mixed-version table, not merely log that counts differ.
    assert sum(by_arm.values()) == len(usable)
    assert set(usable).issubset(terminal)
    assert len(terminal) == len(usable) + sum(
        census.get(key, 0)
        for key in (
            "no_effective_date",
            "not_a_principal_election",
            "outside_all_windows",
            "no_extracted_text",
        )
    )
    return report, usable


def write_release(path: Path = OUTPUT) -> dict:
    """Write and return the canonical manifest."""

    report, _ = build_release()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = write_release()
    corpus = report["usable_feature_corpus"]
    print(f"release: {report['release_id']}")
    print(f"terminal include union: "
          f"{report['terminal_include_union']['articles']:,}")
    print(f"usable feature corpus: {corpus['articles']:,} "
          f"{corpus['by_arm']}")
    print(f"-> {OUTPUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
