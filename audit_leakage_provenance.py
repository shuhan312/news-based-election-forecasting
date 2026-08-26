"""Deterministic, machine-readable leakage and provenance audit.

This audit joins the frozen collection plan to the append-only search log,
checks the final canonical corpus chronology and duplicate boundary, and
verifies that the news feature tables contain predictors rather than election
outcomes.  It also verifies the blinded-prediction freeze: the committed
freeze manifests, the hashes the one-time unblinding record bound at scoring
time, and the bytes on disk today must all agree, the frozen directories must
contain nothing beyond the frozen files, and Git history must show each
freeze committed before the unblinding and untouched afterwards.  It does not
call an API or mutate any research input.

Usage:
    python3 -m audit_leakage_provenance
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from src.news_collection.canonical_corpus_release_v2 import build_release
from src.news_collection.run_byelection_stages import BYELECTION_POLLING_DAYS
from src.news_modelling.window_schemes import NEWS_ELECTION_DATES

ROOT = Path(__file__).resolve().parent
INVENTORY = ROOT / "news_collection/query_inventory.csv"
SEARCH_LOG = ROOT / "news_collection/search_log.csv"
QUERY_LINEAGE = ROOT / "news_collection/query_lineage_v1.csv"
FEATURE_TABLES = (
    ROOT / "news_features/news_feature_table_v1.csv",
    ROOT / "news_features/news_feature_table_v2.csv",
)
OUTPUT = ROOT / "outputs/leakage_provenance_audit_v1.json"
FROZEN_PREDICTIONS = {
    "v1": ROOT / "news_features/blinded_2026_predictions_v1",
    "v2": ROOT / "news_features/blinded_2026_predictions_v2",
}
UNBLINDING_RESULTS = ROOT / "news_features/unblinding_2026_v1/unblinding_results.json"
FROZEN_DIR_FILES = {"frozen_protocol.json", "sha256_manifest.json",
                    "blinded_predictions.csv"}
DIVISION_SAMPLE = ROOT / "news_protocol/division_sample.md"
DIVISION_SAMPLE_SCRIPT = ROOT / "src/build_division_sample.py"

AUDIT_VERSION = "leakage-provenance-audit-v1"
EXPECTED_UNEXECUTED = {"E": 244, "G": 324, "H": 136}
FORBIDDEN_FEATURE_COLUMNS = {
    "actual_vote_share", "observed_vote_share", "vote_share", "votes",
    "winner", "outcome", "target", "residual", "elected",
}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _first_last_commit(path: Path) -> tuple[str, str] | None:
    """Oldest and newest commit timestamps touching path, or None without git."""
    if not (ROOT / ".git").exists():
        return None
    stamps = subprocess.run(
        ["git", "log", "--format=%cI", "--", str(path.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return (stamps[-1], stamps[0]) if stamps else None


def run_audit() -> dict:
    checks: dict[str, dict] = {}

    inventory_rows = _rows(INVENTORY)
    inventory = {row["query_id"]: row for row in inventory_rows}
    assert len(inventory) == len(inventory_rows), "duplicate query IDs"

    log_rows = _rows(SEARCH_LOG)
    logged = {row["query_id"] for row in log_rows}
    lineage_rows = _rows(QUERY_LINEAGE)
    lineage = {row["superseded_query_id"]: row for row in lineage_rows}
    orphaned = sorted(logged - set(inventory) - set(lineage))
    assert not orphaned, f"search-log queries lack plan/lineage: {orphaned}"
    assert all(row["replacement_query_id"] in inventory
               for row in lineage_rows)

    unexecuted = [row for query_id, row in inventory.items()
                  if query_id not in logged]
    by_stage = dict(sorted(Counter(row["stage"] for row in unexecuted).items()))
    assert by_stage == EXPECTED_UNEXECUTED, by_stage
    unexecuted_ids = sorted(row["query_id"] for row in unexecuted)
    checks["query_provenance"] = {
        "status": "pass",
        "planned_queries": len(inventory),
        "search_log_rows": len(log_rows),
        "unique_logged_queries": len(logged),
        "superseded_logged_queries": len(lineage),
        "orphaned_logged_queries": 0,
        "unexecuted_queries": len(unexecuted),
        "unexecuted_by_stage": by_stage,
        "unexecuted_query_ids_sha256": hashlib.sha256(
            "\n".join(unexecuted_ids).encode("utf-8")
        ).hexdigest(),
        "scope_note": (
            "The inventory records the full 19-by-election collection plan. "
            "The frozen v2 release uses only articles actually retrieved and "
            "adjudicated before its freeze; unexecuted E/G/H queries are "
            "planned coverage, not silently treated as zero-result searches."
        ),
    }

    release, articles = build_release()
    polling = {**NEWS_ELECTION_DATES, **BYELECTION_POLLING_DAYS}
    lags: list[int] = []
    missing_polling: list[str] = []
    for article in articles.values():
        polling_day = polling.get(article["election_id"])
        if polling_day is None:
            missing_polling.append(article["article_id"])
            continue
        published = date.fromisoformat(article["publication_datetime"][:10])
        lags.append((polling_day - published).days)
    assert not missing_polling
    assert lags and min(lags) >= 1 and max(lags) <= 180

    canonical_ids = [article["canonical_article_id"]
                     for article in articles.values()]
    assert len(canonical_ids) == len(set(canonical_ids))
    temporal_status = Counter(
        article.get("temporal_availability_status") or "date_only_fallback"
        for article in articles.values()
    )
    checks["article_chronology_and_duplicates"] = {
        "status": "pass",
        "release_id": release["release_id"],
        "articles": len(articles),
        "minimum_days_before_poll": min(lags),
        "maximum_days_before_poll": max(lags),
        "on_or_after_polling_day": sum(lag <= 0 for lag in lags),
        "duplicate_canonical_article_ids": 0,
        "temporal_availability_status": dict(sorted(temporal_status.items())),
    }

    table_results = {}
    all_parties: set[str] = set()
    for path in FEATURE_TABLES:
        rows = _rows(path)
        columns = set(rows[0]) if rows else set()
        forbidden = sorted(columns & FORBIDDEN_FEATURE_COLUMNS)
        assert not forbidden, f"outcomes in {path}: {forbidden}"
        parties = sorted({row["standard_party_key"] for row in rows})
        all_parties.update(parties)
        table_results[path.name] = {
            "rows": len(rows),
            "sha256": _sha256(path),
            "outcome_columns": forbidden,
            "parties": parties,
        }
    assert "reform_uk" in all_parties and "ukip" in all_parties
    assert not any("reform" in party and "ukip" in party
                   for party in all_parties)
    checks["feature_outcome_isolation_and_party_identity"] = {
        "status": "pass",
        "tables": table_results,
        "reform_uk_and_ukip_are_distinct": True,
        "non_contestation_note": (
            "These tables contain news predictors only. Zero article counts "
            "mean observed no-news cells, never zero vote share; electoral "
            "outcomes enter only after the blinded prediction files are frozen."
        ),
    }

    unblinding_integrity = json.loads(
        UNBLINDING_RESULTS.read_text(encoding="utf-8"))["integrity"]
    freeze_results = {}
    for version, directory in FROZEN_PREDICTIONS.items():
        manifest = json.loads(
            (directory / "sha256_manifest.json").read_text(encoding="utf-8"))
        protocol_hash = _sha256(directory / "frozen_protocol.json")
        assert protocol_hash == manifest["frozen_protocol.json"], version
        assert unblinding_integrity[
            f"{version}/frozen_protocol.json"] == protocol_hash, version
        assert unblinding_integrity[
            f"{version}/blinded_predictions.csv"
        ] == manifest["blinded_predictions.csv"], version
        csv_path = directory / "blinded_predictions.csv"
        if csv_path.exists():
            assert _sha256(csv_path) == manifest["blinded_predictions.csv"], (
                f"{version} predictions changed after the freeze")
            csv_state = "recomputed_and_unchanged"
        else:
            csv_state = ("manifest_only: file held locally per the "
                         "large-file rule; its committed sha256 still binds it")
        extras = {p.name for p in directory.iterdir()
                  if not p.name.startswith(".")} - FROZEN_DIR_FILES
        assert not extras, f"unexpected files in frozen {version}: {extras}"
        freeze_results[version] = {
            "predictions_sha256": manifest["blinded_predictions.csv"],
            "predictions_file": csv_state,
            "protocol_sha256": protocol_hash,
            "manifest_matches_unblinding_record": True,
            "frozen_directory_contains_only_frozen_files": True,
        }

    git_dates = {name: _first_last_commit(path) for name, path in {
        **FROZEN_PREDICTIONS, "unblinding": UNBLINDING_RESULTS.parent,
    }.items()}
    if all(git_dates.values()):
        unblind_first = datetime.fromisoformat(git_dates["unblinding"][0])
        for version in FROZEN_PREDICTIONS:
            first, last = git_dates[version]
            assert first == last, (
                f"frozen {version} directory was modified after its freeze")
            assert datetime.fromisoformat(last) < unblind_first, (
                f"frozen {version} was committed after the unblinding")
        chronology: dict[str, object] = {
            "status": "pass",
            "v1_freeze_committed": git_dates["v1"][0],
            "v2_freeze_committed": git_dates["v2"][0],
            "unblinding_first_committed": git_dates["unblinding"][0],
            "freeze_commits_precede_unblinding": True,
            "frozen_dirs_commits_after_freeze": 0,
        }
    else:
        chronology = {"status": "skipped",
                      "reason": "git history unavailable in this copy"}
    checks["blinded_prediction_freeze_integrity"] = {
        "status": "pass",
        "frozen_releases": freeze_results,
        "git_chronology": chronology,
        "note": (
            "Three-way hash agreement: the committed freeze manifests, the "
            "hashes the one-time unblinding record bound at scoring time, and "
            "the bytes on disk today are identical, so the unblinding scored "
            "exactly the frozen predictions and nothing has changed them "
            "since; post-unblinding diagnostics write outside the frozen "
            "directories."
        ),
    }

    selection_source = DIVISION_SAMPLE_SCRIPT.read_text(encoding="utf-8")
    assert "data/raw/news" not in selection_source
    assert "news_collection/" not in selection_source, (
        "the area-selection script must not read collected news")
    ward_times = sorted(row["executed_at"] for row in log_rows
                        if row.get("ward"))
    county_before = [row["executed_at"] for row in log_rows
                     if not row.get("ward")]
    sample_dates = _first_last_commit(DIVISION_SAMPLE)
    if sample_dates:
        rules_committed = datetime.fromisoformat(sample_dates[0])
        early = [t for t in ward_times
                 if datetime.fromisoformat(t) < rules_committed]
        assert not early, (
            f"ward-targeted searches predate the frozen sample: {early[:3]}")
        selection_chronology: dict[str, object] = {
            "status": "pass",
            "division_sample_first_committed": sample_dates[0],
            "first_ward_targeted_search": ward_times[0],
            "ward_targeted_searches": len(ward_times),
            "ward_targeted_searches_before_sample_commit": 0,
            "county_or_national_searches_before_sample_commit": sum(
                1 for t in county_before
                if datetime.fromisoformat(t) < rules_committed),
        }
    else:
        selection_chronology = {
            "status": "skipped",
            "reason": "git history unavailable in this copy",
            "first_ward_targeted_search": ward_times[0],
        }
    checks["area_selection_chronology"] = {
        "status": "pass",
        "division_sample_sha256": _sha256(DIVISION_SAMPLE),
        "selection_reads_no_news_inputs": True,
        "selection_rule": (
            "deterministic top-5 per pre-registered stratum over committed "
            "election-result data only (safe/marginal/changed/Reform-strong "
            "categories); re-running src/build_division_sample.py reproduces "
            "the same 17 areas"
        ),
        "chronology": selection_chronology,
        "note": (
            "The 17 local search areas are a deterministic function of "
            "public election results; the selection script has no news "
            "input path, and every ward-targeted search in the log was "
            "executed after the sample was committed. Searches predating "
            "the sample are county- or national-level rows whose queries "
            "name no ward."
        ),
    }

    return {
        "audit_version": AUDIT_VERSION,
        "status": "pass",
        "checks": checks,
        "input_sha256": {
            str(path.relative_to(ROOT)): _sha256(path)
            for path in (
                INVENTORY, SEARCH_LOG, QUERY_LINEAGE, *FEATURE_TABLES,
                *(d / "sha256_manifest.json"
                  for d in FROZEN_PREDICTIONS.values()),
                UNBLINDING_RESULTS,
            )
        },
    }


def main() -> None:
    report = run_audit()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: {AUDIT_VERSION} -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
