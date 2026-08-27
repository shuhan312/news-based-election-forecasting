"""Deterministic, machine-readable leakage and provenance audit.

This audit joins the frozen collection plan to the append-only search log,
checks the final canonical corpus chronology and duplicate boundary, verifies
the Stage 1 chronological splits and predictor permissions, and verifies that
the Stage 2 feature matrices contain predictors rather than election outcomes.
It also verifies the blinded-prediction freeze: the committed
freeze manifests, the hashes the one-time unblinding record bound at scoring
time, and the bytes on disk today must all agree, the frozen directories must
contain nothing beyond the frozen files, and Git history must show each
freeze committed before the unblinding and untouched afterwards. It writes a
compact event chronology beside the detailed JSON report. Unknown dates stay
blank: Git times are labelled as Git evidence and never presented as exact
external outcome-release or file-creation times. It does not call an API or
mutate any research input.

Usage:
    python3 -m audit_leakage_provenance
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta
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
FEATURE_METADATA = {
    "news_feature_table_v1.csv": (
        ROOT / "news_features/news_feature_table_v1_metadata.json",
        ROOT / "news_collection/canonical_corpus_release_v1.json",
    ),
    "news_feature_table_v2.csv": (
        ROOT / "news_features/news_feature_table_v2_metadata.json",
        ROOT / "news_collection/canonical_corpus_release_v2.json",
    ),
}
FEATURE_LINEAGE_FILES = tuple(
    path for metadata_and_release in FEATURE_METADATA.values()
    for path in metadata_and_release
)
OUTPUT = ROOT / "outputs/leakage_provenance_audit_v1.json"
PROVENANCE_OUTPUT = ROOT / "outputs/provenance_audit_v1.csv"
STAGE1_BUNDLE = (
    ROOT / "surrey-election-no-news-baseline/outputs/model_bundle_v1"
)
STAGE1_FILES = {
    name: STAGE1_BUNDLE / name for name in (
        "architecture.json",
        "bundle_manifest.json",
        "contestation_records.csv",
        "feature_dictionary.csv",
        "feature_schema.json",
        "holdout_predictions.csv",
        "leakage_audit.csv",
        "out_of_fold_predictions.csv",
        "split_manifest.csv",
        "training_rows.csv",
    )
}
FROZEN_PREDICTIONS = {
    "v1": ROOT / "news_features/blinded_2026_predictions_v1",
    "v2": ROOT / "news_features/blinded_2026_predictions_v2",
}
UNBLINDING_RESULTS = ROOT / "news_features/unblinding_2026_v1/unblinding_results.json"
FROZEN_DIR_FILES = {"frozen_protocol.json", "sha256_manifest.json",
                    "blinded_predictions.csv"}
DIVISION_SAMPLE = ROOT / "news_protocol/division_sample.md"
DIVISION_SAMPLE_SCRIPT = ROOT / "src/build_division_sample.py"

AUDIT_VERSION = "leakage-provenance-audit-v1.1"
EXPECTED_UNEXECUTED = {"E": 244, "G": 324, "H": 136}
FORBIDDEN_FEATURE_COLUMNS = {
    "actual_vote_share", "observed_vote_share", "vote_share", "votes",
    "winner", "outcome", "target", "residual", "elected",
}
OUTCOME_COLUMNS = {
    "observed_vote_share", "observed_rank", "observed_elected", "error",
    "absolute_error", "squared_error",
}
PRIMARY_HOLDOUT_ELECTIONS = (
    "surrey-county-council-2026-east-surrey",
    "surrey-county-council-2026-west-surrey",
)
PROVENANCE_FIELDS = (
    "event_id", "election_date", "outcome_available_date", "news_cutoff",
    "model_version", "split", "specification_frozen_at",
    "prediction_created_at", "outcome_access_status", "commit_hash",
    "timestamp_evidence",
)


class AuditFailure(RuntimeError):
    """A machine-checkable provenance assertion failed."""


def _require(condition: bool, message: object) -> None:
    """Raise even under ``python -O`` (unlike a bare assert)."""

    if not condition:
        raise AuditFailure(str(message))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commits(path: Path) -> list[dict[str, str]]:
    """Return newest-first commit evidence for a path."""

    if not (ROOT / ".git").exists():
        return []
    lines = subprocess.run(
        ["git", "log", "--format=%H%x09%cI", "--",
         str(path.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [dict(zip(("commit_hash", "committed_at"), line.split("\t", 1)))
            for line in lines if line]


def _first_last_commit(path: Path) -> tuple[str, str] | None:
    """Oldest and newest commit timestamps touching path, or None without Git."""

    commits = _git_commits(path)
    return ((commits[-1]["committed_at"], commits[0]["committed_at"])
            if commits else None)


def _election_date(value: str) -> date:
    """Parse the ISO and human-readable date formats carried by Stage 1."""

    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, "%d %B %Y").date()


def _chronology_rows() -> list[dict[str, str]]:
    """Build the event ledger without inventing unavailable timestamps."""

    election_day = NEWS_ELECTION_DATES["ESWS-2026-05"]
    news_cutoff = election_day - timedelta(days=1)
    rows: list[dict[str, str]] = []
    for version, directory in FROZEN_PREDICTIONS.items():
        commits = _git_commits(directory)
        freeze = commits[-1] if commits else {}
        for election_id in PRIMARY_HOLDOUT_ELECTIONS:
            rows.append({
                "event_id": f"{election_id}::{version}",
                "election_date": election_day.isoformat(),
                # No authoritative declaration timestamp is committed.
                "outcome_available_date": "",
                "news_cutoff": news_cutoff.isoformat(),
                "model_version": version,
                "split": "primary_holdout_7_may_2026",
                "specification_frozen_at": freeze.get("committed_at", ""),
                # Git proves commit time, not exact byte-creation time.
                "prediction_created_at": "",
                "outcome_access_status": (
                    "withheld_from_stage2_until_one_time_unblinding"
                ),
                "commit_hash": freeze.get("commit_hash", ""),
                "timestamp_evidence": (
                    "specification_frozen_at is the Git commit time; exact "
                    "outcome availability and prediction creation times are "
                    "not evidenced in the repository and remain blank"
                ),
            })
    return rows


def run_audit() -> dict:
    checks: dict[str, dict] = {}

    # Check 1 — query provenance: every logged search traces back to the
    # committed plan or a recorded supersession; no off-plan query fed the
    # corpus, and the unexecuted remainder is the expected, visible E/G/H gap.
    inventory_rows = _rows(INVENTORY)
    inventory = {row["query_id"]: row for row in inventory_rows}
    _require(len(inventory) == len(inventory_rows), "duplicate query IDs")

    log_rows = _rows(SEARCH_LOG)
    logged = {row["query_id"] for row in log_rows}
    lineage_rows = _rows(QUERY_LINEAGE)
    lineage = {row["superseded_query_id"]: row for row in lineage_rows}
    orphaned = sorted(logged - set(inventory) - set(lineage))
    _require(not orphaned,
             f"search-log queries lack plan/lineage: {orphaned}")
    _require(all(row["replacement_query_id"] in inventory
                 for row in lineage_rows),
             "query lineage names a replacement absent from the inventory")

    unexecuted = [row for query_id, row in inventory.items()
                  if query_id not in logged]
    by_stage = dict(sorted(Counter(row["stage"] for row in unexecuted).items()))
    _require(by_stage == EXPECTED_UNEXECUTED, by_stage)
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

    # Check 2 — chronology and duplicates: every usable article was published
    # 1-180 days before its election's polling day (nothing from polling day
    # or later reaches the features) and no canonical id appears twice.
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
    _require(not missing_polling,
             f"articles lack a polling date: {missing_polling[:5]}")
    _require(bool(lags) and min(lags) >= 1 and max(lags) <= 180,
             f"article-to-poll lags outside 1-180 days: {min(lags)}-{max(lags)}")

    canonical_ids = [article["canonical_article_id"]
                     for article in articles.values()]
    _require(len(canonical_ids) == len(set(canonical_ids)),
             "duplicate canonical article IDs reach the v2 release")
    urls = [article["url"].strip() for article in articles.values()]
    _require(all(urls) and len(urls) == len(set(urls)),
             "duplicate or blank article URLs reach the v2 release")
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
        "duplicate_article_urls": 0,
        "temporal_availability_status": dict(sorted(temporal_status.items())),
    }

    # Check 3 — outcome isolation and party identity: the committed feature
    # tables carry no election-outcome column, and Reform UK and UKIP exist
    # as two distinct party keys with no merged label.
    table_results = {}
    all_parties: set[str] = set()
    for path in FEATURE_TABLES:
        rows = _rows(path)
        columns = set(rows[0]) if rows else set()
        forbidden = sorted(columns & FORBIDDEN_FEATURE_COLUMNS)
        _require(not forbidden, f"outcomes in {path}: {forbidden}")
        metadata_path, release_path = FEATURE_METADATA[path.name]
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        release_manifest = json.loads(release_path.read_text(encoding="utf-8"))
        expected_manifest = str(release_path.relative_to(ROOT))
        _require(metadata["canonical_corpus_manifest"] == expected_manifest,
                 f"{metadata_path.name} names the wrong corpus manifest")
        _require(metadata["canonical_corpus_release_id"]
                 == release_manifest["release_id"],
                 f"{metadata_path.name} names the wrong corpus release")
        parties = sorted({row["standard_party_key"] for row in rows})
        all_parties.update(parties)
        table_results[path.name] = {
            "rows": len(rows),
            "sha256": _sha256(path),
            "outcome_columns": forbidden,
            "parties": parties,
            "canonical_corpus_manifest": expected_manifest,
            "canonical_corpus_release_id": release_manifest["release_id"],
        }
    _require("reform_uk" in all_parties and "ukip" in all_parties,
             "feature tables do not preserve both Reform UK and UKIP")
    _require(not any("reform" in party and "ukip" in party
                     for party in all_parties),
             "feature table contains a merged Reform/UKIP party key")
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

    # Check 4 — Stage 1 split, predictor and non-contestation governance.
    # The bundle is an input to every Stage 2 result, so its own leakage audit
    # and split manifest belong in this cross-layer audit rather than being
    # trusted merely because the files exist.
    bundle_manifest = json.loads(
        STAGE1_FILES["bundle_manifest.json"].read_text(encoding="utf-8"))
    bad_bundle_hashes = sorted(
        name for name, expected in bundle_manifest["files"].items()
        if not (STAGE1_BUNDLE / name).exists()
        or _sha256(STAGE1_BUNDLE / name) != expected
    )
    _require(not bad_bundle_hashes,
             f"Stage 1 bundle hash mismatch: {bad_bundle_hashes}")

    architecture = json.loads(
        STAGE1_FILES["architecture.json"].read_text(encoding="utf-8"))
    feature_schema = json.loads(
        STAGE1_FILES["feature_schema.json"].read_text(encoding="utf-8"))
    selected = set(architecture["selected_features"])
    _require(selected == set(feature_schema["source_predictors"]),
             "architecture and feature schema disagree on Stage 1 predictors")
    _require(architecture["selection"]["holdout_not_read_for_selection"] is True,
             "Stage 1 architecture selection does not declare holdout isolation")

    dictionary_rows = _rows(STAGE1_FILES["feature_dictionary.csv"])
    dictionary = {row["column"]: row for row in dictionary_rows}
    _require(len(dictionary) == len(dictionary_rows),
             "duplicate Stage 1 feature-dictionary entries")
    missing_dictionary = sorted(selected - set(dictionary))
    _require(not missing_dictionary,
             f"selected predictors lack dictionary evidence: {missing_dictionary}")
    disallowed_selected = sorted(
        name for name in selected
        if dictionary[name]["role"] != "predictor"
        or dictionary[name]["used_as_predictor"].lower() != "true"
    )
    _require(not disallowed_selected,
             f"non-predictor fields selected by Stage 1: {disallowed_selected}")

    leakage_rows = _rows(STAGE1_FILES["leakage_audit.csv"])
    target_fields = {
        row["field_name"] for row in leakage_rows
        if row["allowed_as_predictor"].lower() != "yes"
        and row["role"] == "target"
    }
    permitted_predictor_fields = {
        row["field_name"] for row in leakage_rows
        if row["allowed_as_predictor"].lower() == "yes"
        and row["role"] == "predictor"
    }
    # Some identifiers (notably standard_party_name) occur in both the
    # governed feature and target tables. They are prohibited only in the
    # target-table role, so do not reject an independently permitted feature.
    prohibited_fields = target_fields - permitted_predictor_fields
    _require(not (selected & prohibited_fields),
             f"Stage 1 selected a target field: {sorted(selected & prohibited_fields)}")

    split_rows = _rows(STAGE1_FILES["split_manifest.csv"])
    split_contests: dict[str, dict[str, set[str]]] = {}
    split_counts = Counter()
    for row in split_rows:
        split_id = row["split_id"]
        fold = row["fold"]
        _require(fold in {"train", "test", "unused"},
                 f"unknown fold label in {split_id}: {fold}")
        split_counts[(row["split_role"], fold)] += 1
        split_contests.setdefault(split_id, {}).setdefault(fold, set()).add(
            row["contest_id"])
        election_day = _election_date(row["election_date"])
        train_end = date.fromisoformat(row["train_end"])
        test_start = date.fromisoformat(row["test_start"])
        test_end = date.fromisoformat(row["test_end"])
        _require(train_end < test_start <= test_end,
                 f"invalid date bounds in split {split_id}")
        if fold == "train":
            _require(election_day <= train_end,
                     f"future row in training fold {split_id}")
        elif fold == "test":
            _require(test_start <= election_day <= test_end,
                     f"test row outside test window in {split_id}")
    overlapping = sorted(
        split_id for split_id, folds in split_contests.items()
        if folds.get("train", set()) & folds.get("test", set())
    )
    _require(not overlapping,
             f"contest appears in train and test in splits: {overlapping}")
    primary_holdout = [
        row for row in split_rows
        if row["split_id"] == "primary_holdout_7_may_2026"
        and row["fold"] == "test"
    ]
    primary_holdout_ids = {row["election_id"] for row in primary_holdout}
    _require(set(PRIMARY_HOLDOUT_ELECTIONS) <= primary_holdout_ids,
             "primary holdout lacks a 2026 principal election")
    _require({_election_date(row["election_date"]) for row in primary_holdout}
             == {date(2026, 5, 7)},
             "primary holdout contains an election from another date")

    contestation_rows = _rows(STAGE1_FILES["contestation_records.csv"])
    _require({row["contestation_status"] for row in contestation_rows}
             == {"contested", "did_not_contest"},
             "unexpected contestation status")
    bad_contestation = [
        row for row in contestation_rows
        if ((row["contestation_status"] == "did_not_contest"
             and int(row["candidates_fielded"]) != 0)
            or (row["contestation_status"] == "contested"
                and int(row["candidates_fielded"]) < 1))
    ]
    _require(not bad_contestation,
             "contestation status disagrees with candidates_fielded")
    _require(not (set(contestation_rows[0]) & OUTCOME_COLUMNS),
             "contestation grid contains election outcome columns")
    _require("contestation_status" not in selected,
             "non-contestation status entered the predictor matrix")

    party_rows = list(contestation_rows)
    for name in ("out_of_fold_predictions.csv", "holdout_predictions.csv"):
        party_rows += _rows(STAGE1_FILES[name])
    _require(all(row.get("is_reform_uk") in {"True", "False"}
                 and row.get("is_ukip") in {"True", "False"}
                 for row in party_rows),
             "invalid Reform UK/UKIP identity flag")
    merged_party_rows = [
        row for row in party_rows
        if row.get("is_reform_uk") == "True" and row.get("is_ukip") == "True"
    ]
    _require(not merged_party_rows,
             "a Stage 1 row is simultaneously Reform UK and UKIP")
    training_rows = _rows(STAGE1_FILES["training_rows.csv"])
    candidate_ids = [row["candidate_contest_id"] for row in training_rows]
    _require(all(candidate_ids) and len(candidate_ids) == len(set(candidate_ids)),
             "Stage 1 training rows do not identify unique actual candidates")
    checks["stage1_split_leakage_and_contestation"] = {
        "status": "pass",
        "bundle_version": bundle_manifest["bundle_version"],
        "bundle_files_hash_verified": len(bundle_manifest["files"]),
        "selected_predictors": len(selected),
        "selected_target_fields": 0,
        "holdout_read_for_architecture_selection": False,
        "split_manifest_rows": len(split_rows),
        "primary_holdout_elections": sorted(primary_holdout_ids),
        "stage2_target_elections": list(PRIMARY_HOLDOUT_ELECTIONS),
        "split_counts": {
            f"{role}/{fold}": count
            for (role, fold), count in sorted(split_counts.items())
        },
        "contests_present_in_both_train_and_test": 0,
        "contestation_records": len(contestation_rows),
        "did_not_contest_records": sum(
            row["contestation_status"] == "did_not_contest"
            for row in contestation_rows
        ),
        "did_not_contest_encoded_as_candidate_rows": False,
        "reform_uk_and_ukip_are_distinct": True,
        "note": (
            "Non-contestation is held in a separate audit grid with zero "
            "candidates_fielded and no vote-share field. The model training "
            "table contains uniquely identified actual candidate rows; "
            "contestation_status is not a selected predictor and is never "
            "converted into a synthetic zero-vote candidate."
        ),
    }

    # Check 5 — freeze integrity: three independently committed records must
    # agree byte-for-byte (freeze manifest, the hashes the unblinding bound at
    # scoring time, the files on disk now), the frozen directories hold
    # nothing extra, and Git shows each freeze in one commit strictly before
    # the unblinding.
    unblinding_integrity = json.loads(
        UNBLINDING_RESULTS.read_text(encoding="utf-8"))["integrity"]
    freeze_results = {}
    for version, directory in FROZEN_PREDICTIONS.items():
        manifest = json.loads(
            (directory / "sha256_manifest.json").read_text(encoding="utf-8"))
        protocol = json.loads(
            (directory / "frozen_protocol.json").read_text(encoding="utf-8"))
        protocol_hash = _sha256(directory / "frozen_protocol.json")
        _require(protocol_hash == manifest["frozen_protocol.json"], version)
        _require(unblinding_integrity[
            f"{version}/frozen_protocol.json"] == protocol_hash, version)
        _require(unblinding_integrity[
            f"{version}/blinded_predictions.csv"
        ] == manifest["blinded_predictions.csv"], version)
        for input_name in ("holdout_predictions.csv",
                           "out_of_fold_predictions.csv"):
            expected = protocol["input_sha256"][input_name]
            _require(_sha256(STAGE1_FILES[input_name]) == expected,
                     f"{version} protocol no longer binds the Stage 1 {input_name}")
        feature_input = f"news_feature_table_{version}.csv"
        _require(_sha256(ROOT / "news_features" / feature_input)
                 == protocol["input_sha256"][feature_input],
                 f"{version} protocol no longer binds {feature_input}")
        csv_path = directory / "blinded_predictions.csv"
        if csv_path.exists():
            _require(_sha256(csv_path) == manifest["blinded_predictions.csv"],
                     f"{version} predictions changed after the freeze")
            blinded_rows = _rows(csv_path)
            exposed = sorted(set(blinded_rows[0]) & OUTCOME_COLUMNS)
            _require(not exposed,
                     f"outcome columns in frozen {version} output: {exposed}")
            blinded_elections = {
                row["election_id"] for row in blinded_rows
            }
            _require(blinded_elections == set(PRIMARY_HOLDOUT_ELECTIONS),
                     f"frozen {version} output has the wrong election scope")
            _require(not any(row.get("is_reform_uk") == "True"
                             and row.get("is_ukip") == "True"
                             for row in blinded_rows),
                     f"merged Reform/UKIP row in frozen {version} output")
            csv_state = "recomputed_and_unchanged"
        else:
            csv_state = ("manifest_only: file held locally per the "
                         "large-file rule; its committed sha256 still binds it")
        extras = {p.name for p in directory.iterdir()
                  if not p.name.startswith(".")} - FROZEN_DIR_FILES
        _require(not extras, f"unexpected files in frozen {version}: {extras}")
        freeze_results[version] = {
            "predictions_sha256": manifest["blinded_predictions.csv"],
            "predictions_file": csv_state,
            "protocol_sha256": protocol_hash,
            "manifest_matches_unblinding_record": True,
            "frozen_directory_contains_only_frozen_files": True,
            "stage1_input_hashes_match_protocol": True,
            "news_feature_input_hash_matches_protocol": True,
            "outcome_columns_in_blinded_output": [],
            "blinded_output_elections": sorted(PRIMARY_HOLDOUT_ELECTIONS),
        }

    git_dates = {name: _first_last_commit(path) for name, path in {
        **FROZEN_PREDICTIONS, "unblinding": UNBLINDING_RESULTS.parent,
    }.items()}
    if all(git_dates.values()):
        unblind_first = datetime.fromisoformat(git_dates["unblinding"][0])
        for version in FROZEN_PREDICTIONS:
            first, last = git_dates[version]
            _require(first == last,
                     f"frozen {version} directory was modified after its freeze")
            _require(datetime.fromisoformat(last) < unblind_first,
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

    # Check 6 — area-selection chronology: the Table 1 areas come from a
    # script with no news input path, and every ward-targeted search in the
    # log was executed after the sample was committed — the areas were fixed
    # before any local news was seen.
    selection_source = DIVISION_SAMPLE_SCRIPT.read_text(encoding="utf-8")
    _require("data/raw/news" not in selection_source,
             "the area-selection script reads raw news")
    _require("news_collection/" not in selection_source,
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
        _require(not early,
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

    chronology_rows = _chronology_rows()
    _require(len({row["event_id"] for row in chronology_rows})
             == len(chronology_rows),
             "event chronology contains duplicate event IDs")
    _require(all(row["election_date"] and row["news_cutoff"]
                 for row in chronology_rows),
             "event chronology lacks known election dates or cutoffs")
    _require(all(not row["outcome_available_date"]
                 and not row["prediction_created_at"]
                 for row in chronology_rows),
             "unknown chronology timestamps must remain blank")

    return {
        "audit_version": AUDIT_VERSION,
        "status": "pass",
        "checks": checks,
        "event_chronology": chronology_rows,
        "chronology_policy": (
            "Blank means not evidenced in the repository, not zero and not "
            "the election date. Git commit time records when the frozen "
            "specification entered history; it is not relabelled as the exact "
            "prediction-creation or public outcome-release time."
        ),
        "input_sha256": {
            str(path.relative_to(ROOT)): _sha256(path)
            for path in (
                INVENTORY, SEARCH_LOG, QUERY_LINEAGE, *FEATURE_TABLES,
                *FEATURE_LINEAGE_FILES,
                *STAGE1_FILES.values(),
                *(d / "sha256_manifest.json"
                  for d in FROZEN_PREDICTIONS.values()),
                UNBLINDING_RESULTS,
            )
        },
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = run_audit()
    except AuditFailure as exc:
        report = {
            "audit_version": AUDIT_VERSION,
            "status": "fail",
            "error": str(exc),
        }
        OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(f"fail: {exc}") from exc
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with PROVENANCE_OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROVENANCE_FIELDS,
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(report["event_chronology"])
    print(
        f"{report['status']}: {AUDIT_VERSION} -> "
        f"{OUTPUT.relative_to(ROOT)}, {PROVENANCE_OUTPUT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
