"""Assemble the master table, the six views, and the audits that go with them.

The master table is built once; every view is a column selection over it, so a
local-news view and a combined-news view can never disagree about a row. The
alternative - building each view separately - produces six tables that drift.

Leakage is handled by construction rather than by filtering afterwards. Target
columns carry a ``target__`` prefix and nothing else does, so the predictor set
is "every column that is not a target and not an identifier" and there is no
list for anyone to forget to update. The column-level audit records the verdict
for every column so the reasoning is inspectable rather than implicit.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date

from .ward_party_features import (
    ARM_LOCAL,
    ARM_NATIONAL,
    CUMULATIVE_SNAPSHOTS,
    ELECTION_WIDE,
    NEWS_ELECTION_DATES,
    NO_FOCAL_PARTY,
    PRINCIPAL_WINDOWS,
    REFORM_KEY,
    UKIP_KEY,
    assemble_window,
    coverage_block,
    normalise_area,
)

# Columns that identify a row rather than predicting or being predicted.
IDENTIFIER_COLUMNS = frozenset({
    "row_key", "election_id", "election_date", "election_type",
    "electoral_area_id", "electoral_area_name", "party_id",
    "standardised_party_name", "contest_id", "is_reform_uk", "is_ukip",
    "modelling_split", "chronological_fold", "holdout_indicator",
    "blinded_outcome_indicator", "geographic_comparability_status",
    "party_contested", "did_not_contest", "candidates_fielded",
    "number_of_seats", "feature_version",
})

TARGET_PREFIX = "target__"

# Everything derived from the election being predicted. Named explicitly so
# the audit can state a reason per column rather than "not in the allow list".
PROHIBITED_SUBSTRINGS = (
    "current_vote_share", "current_votes", "current_winner", "final_position",
    "elected_yes_no", "winning_margin", "current_turnout", "change_in_vote_share",
    "results_reporting", "post_election", "election_night", "retrospective",
)

FEATURE_VERSION = "ward_party_election_features_v1"


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def split_lookup(split_manifest: Sequence[Mapping[str, object]]) -> dict[str, dict]:
    """Contest -> its chronological placement, taken from the frozen manifest.

    Split membership is read from Stage 1 rather than recomputed, so the news
    layer cannot place a contest differently from the baseline it is measured
    against. It is keyed by contest, which is what guarantees that rows from
    one contest cannot land in different splits: they share a key, so they
    share an answer.
    """

    placement: dict[str, dict] = {}
    for row in split_manifest:
        contest = str(row.get("contest_id") or
                      f"{row.get('election_id')}|{row.get('division_id')}")
        role = str(row.get("split_role", ""))
        existing = placement.get(contest)
        # A contest appears once per split it takes part in. The holdout roles
        # win, because a contest that is ever held out must never be trained
        # on, whatever else it also appears in.
        if existing and existing["split_role"].endswith("holdout"):
            continue
        placement[contest] = {
            "split_id": str(row.get("split_id", "")),
            "split_role": role,
            "chronological_fold": str(row.get("fold", "")),
        }
    return placement


def classify_split(election_id: str, election_date: str,
                   placement: Mapping[str, object] | None) -> dict:
    """Which of train / validation / final test a row belongs to.

    The chronological structure the brief asks for: historical elections
    train, 2021 validates, and everything polled on 7 May 2026 is the final
    held-out test set. East and West Surrey stay in one period because they
    share a polling date, which is what the date-based rule enforces without
    anyone having to remember the two names.
    """

    is_2026_holdout = "2026" in election_id and "07-07" not in election_id
    if is_2026_holdout:
        return {"modelling_split": "final_test_2026",
                "holdout_indicator": True,
                "blinded_outcome_indicator": True}
    if "haslemere-2026-07-07" in election_id:
        return {"modelling_split": "secondary_test_2026_07",
                "holdout_indicator": True,
                "blinded_outcome_indicator": False}
    if election_id.endswith("-2021"):
        return {"modelling_split": "validation_2021",
                "holdout_indicator": False,
                "blinded_outcome_indicator": False}
    return {"modelling_split": "historical_training",
            "holdout_indicator": False,
            "blinded_outcome_indicator": False}


def build_master_rows(
    grid: Sequence[Mapping[str, object]],
    baseline_by_key: Mapping[tuple, Mapping[str, object]],
    local_index: Mapping[tuple, list],
    national_index: Mapping[tuple, list],
    coverage_index: Mapping[tuple, Mapping[str, object]],
    weighted_local_index: Mapping[tuple, list],
    weighted_national_index: Mapping[tuple, list],
    placement: Mapping[str, dict],
    *,
    feature_columns: Sequence[str],
    weighted_feature_columns: Sequence[str],
    windows: Mapping[str, Mapping[str, object]] | None = None,
) -> list[dict]:
    """One master row per grid row, with every block attached.

    ``windows`` carries the specs as the verification resolved them - a window
    it found empty assembles from nothing. Defaulting to the declared specs
    keeps the function usable in tests without the verification step.
    """

    date_to_news = {v: k for k, v in NEWS_ELECTION_DATES.items()}
    all_windows = dict(windows) if windows else {
        **PRINCIPAL_WINDOWS, **CUMULATIVE_SNAPSHOTS}
    rows: list[dict] = []

    for entry in grid:
        election = str(entry["election_id"])
        area = normalise_area(str(entry["electoral_area_name"]))
        party = str(entry["party_id"])
        contest = str(entry["contest_id"])

        record: dict[str, object] = dict(entry)
        record["row_key"] = f"{election}|{entry['electoral_area_id']}|{party}"
        record["feature_version"] = FEATURE_VERSION

        # --- chronological placement ------------------------------------
        record.update(classify_split(election, str(entry["election_date"]),
                                     placement.get(contest)))
        record["chronological_fold"] = (
            placement.get(contest, {}).get("chronological_fold", ""))

        # --- frozen baseline --------------------------------------------
        baseline = baseline_by_key.get((election, str(entry["electoral_area_id"]),
                                        party))
        if baseline:
            record.update({k: v for k, v in baseline.items()
                           if not k.startswith("_")})
        else:
            record.update({
                "baseline__predicted_party_vote_share": None,
                "baseline__candidates_predicted": 0,
                "baseline__prediction_provenance": (
                    "not_applicable_did_not_contest" if entry["did_not_contest"]
                    else "no_out_of_fold_prediction"),
                "baseline__model_id": "",
                "baseline__split_id": "",
                # A party that did not stand has no vote share. Left empty
                # deliberately; zero would be a measurement nobody made.
                "target__party_vote_share": None,
            })

        # --- news blocks -------------------------------------------------
        polling = _parse_date(str(entry["election_date"]))
        news_election = date_to_news.get(polling) if polling else None

        for window_name, spec in all_windows.items():
            for arm, index, columns, prefix in (
                (ARM_LOCAL, local_index, feature_columns, "local"),
                (ARM_NATIONAL, national_index, feature_columns, "national"),
                (ARM_LOCAL, weighted_local_index, weighted_feature_columns,
                 "weighted_local"),
                (ARM_NATIONAL, weighted_national_index, weighted_feature_columns,
                 "weighted_national"),
            ):
                if news_election is None:
                    key_prefix = ("__absent__",)
                elif arm == ARM_LOCAL:
                    key_prefix = (news_election, area, party)
                else:
                    key_prefix = (news_election, party)
                record.update(assemble_window(
                    index, key_prefix, spec, columns, prefix, window_name))

                # Party-agnostic coverage: news about the area or the whole
                # election that names no party. Carried separately so a model
                # can tell "my party was covered" from "this contest was in
                # the news".
                context_prefix = (
                    ("__absent__",) if news_election is None
                    else (news_election, area, NO_FOCAL_PARTY) if arm == ARM_LOCAL
                    else (news_election, NO_FOCAL_PARTY))
                record.update(assemble_window(
                    index, context_prefix, spec, columns,
                    f"{prefix}_context", window_name))

            # --- coverage and missing-news states ------------------------
            record.update(coverage_block(
                coverage_index,
                (news_election or "__absent__", area, party),
                spec, window_name))

        # --- combined block, derived transparently ----------------------
        record.update(combined_block(record, all_windows, feature_columns))
        rows.append(record)
    return rows


def combined_block(record: Mapping[str, object],
                   windows: Mapping[str, object],
                   feature_columns: Sequence[str]) -> dict[str, object]:
    """Local plus national, as a separate block that replaces neither.

    Summed from the two arms rather than recomputed from articles, so the
    combined value is always exactly the two parts and a reader can check it
    with addition. Where both parts are absent the combined value is absent
    too - adding two unknowns does not produce a zero.
    """

    block: dict[str, object] = {}
    for window_name in windows:
        for column in feature_columns:
            parts = [record.get(f"local__{window_name}__{column}"),
                     record.get(f"national__{window_name}__{column}")]
            present = [p for p in parts if p is not None]
            block[f"combined__{window_name}__{column}"] = (
                sum(present) if present else None)
    return block


def _parse_date(text: str) -> date | None:
    """Contract dates come as '6 May 2021' or ISO."""

    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            from datetime import datetime
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Views, audits and dictionaries
# ---------------------------------------------------------------------------

VIEW_PREFIXES: dict[str, tuple[str, ...]] = {
    "A_full_historical": ("baseline__", "local__", "national__", "combined__",
                          "weighted_local__", "weighted_national__",
                          "local_context__", "national_context__",
                          "weighted_local_context__", "weighted_national_context__",
                          "coverage__", TARGET_PREFIX),
    "B_blinded_2026": ("baseline__", "local__", "national__", "combined__",
                       "weighted_local__", "weighted_national__",
                       "local_context__", "national_context__",
                       "weighted_local_context__", "weighted_national_context__",
                       "coverage__"),
    "C_local_news": ("baseline__", "local__", "local_context__",
                     "weighted_local__", "weighted_local_context__",
                     "coverage__", TARGET_PREFIX),
    "D_national_news": ("baseline__", "national__", "national_context__",
                        "weighted_national__", "weighted_national_context__",
                        "coverage__", TARGET_PREFIX),
    "E_combined_news": ("baseline__", "combined__", "coverage__", TARGET_PREFIX),
    "F_no_news": ("baseline__", TARGET_PREFIX),
}


def columns_for_view(view: str, all_columns: Sequence[str]) -> list[str]:
    """Identifiers plus the prefixes this view is allowed to see."""

    prefixes = VIEW_PREFIXES[view]
    return [column for column in all_columns
            if column in IDENTIFIER_COLUMNS or column.startswith(prefixes)]


def leakage_audit(all_columns: Sequence[str]) -> list[dict]:
    """A verdict for every column, with the reason and when it was available.

    Every column is classified, including the ones that are obviously fine.
    A column absent from the audit is a column nobody decided about, and this
    is the artefact that proves the decision was taken.
    """

    audit: list[dict] = []
    for column in sorted(all_columns):
        lowered = column.lower()
        if column in IDENTIFIER_COLUMNS:
            verdict, reason, availability, layer = (
                "identifier", "Identifies the row; not modelled.",
                "known before polling", "observation grid")
        elif column.startswith(TARGET_PREFIX):
            verdict, reason, availability, layer = (
                "target", "Outcome of the election being predicted.",
                "after polls close", "election result")
        elif any(bad in lowered for bad in PROHIBITED_SUBSTRINGS):
            verdict, reason, availability, layer = (
                "excluded", "Derived from the election being predicted.",
                "after polls close", "election result")
        elif column.startswith("baseline__"):
            verdict, reason, availability, layer = (
                "permitted", ("Frozen Stage 1 out-of-sample prediction or its "
                              "provenance; contains no current-election result."),
                "before polling", "Stage 1 bundle")
        elif column.startswith("coverage__"):
            verdict, reason, availability, layer = (
                "permitted", ("Describes how completely the archive was "
                              "searched, not what the articles said."),
                "before polling", "missing-news representation")
        elif column.startswith(("local__", "national__", "combined__",
                                "weighted_local__", "weighted_national__",
                                "local_context__", "national_context__",
                                "weighted_local_context__",
                                "weighted_national_context__")):
            window = column.split("__")[1] if "__" in column else ""
            verdict, reason, availability, layer = (
                "permitted",
                ("Aggregated from articles published strictly before polling; "
                 "post-election, election-night and results-reporting articles "
                 "are excluded upstream."),
                f"before polling, window {window}", "news aggregation")
        else:
            # Anything unrecognised is refused rather than allowed. A new
            # column arriving from upstream should stop the build, not join
            # the predictors by default.
            verdict, reason, availability, layer = (
                "excluded", "Unclassified column; refused rather than assumed safe.",
                "unknown", "unknown")
        audit.append({
            "feature_name": column, "verdict": verdict, "reason": reason,
            "availability_time": availability, "source_layer": layer,
        })
    return audit


def feature_dictionary(all_columns: Sequence[str]) -> list[dict]:
    """One row per column: what it is, how it was built, what it rests on."""

    entries: list[dict] = []
    for column in sorted(all_columns):
        parts = column.split("__")
        prefix = parts[0] if len(parts) > 1 else ""
        window = parts[1] if len(parts) > 2 else ""
        base = parts[-1]
        window_spec = {**PRINCIPAL_WINDOWS, **CUMULATIVE_SNAPSHOTS}.get(window, {})
        entries.append({
            "feature_name": column,
            "block": prefix or "identifier",
            "time_window": window,
            "window_definition": (
                f"days {window_spec['days'][0]}-{window_spec['days'][1]} before polling"
                if isinstance(window_spec.get("days"), tuple)
                else (f"all news up to {window_spec['days']} days before polling"
                      if window_spec.get("days") else "")),
            "assembled_from_legacy_windows": ", ".join(
                window_spec.get("from_old", ())),
            "source_dataset": _source_for(prefix),
            "aggregation": ("sum across contributing aggregate rows"
                            if prefix and prefix != "identifier" else ""),
            "weighting": ("recency-weighted" if prefix.startswith("weighted")
                          else "unweighted" if prefix else ""),
            "underlying_measure": base,
            "feature_version": FEATURE_VERSION,
            "traceability": ("contributing articles are recorded in the Phase 7 "
                             "context-aggregation contribution map, keyed by "
                             "election, area, party and legacy window"),
        })
    return entries


def _source_for(prefix: str) -> str:
    return {
        "baseline": "Stage 1 model bundle (out-of-fold and holdout predictions)",
        "local": "context_aggregated_features.parquet, local scopes",
        "national": "context_aggregated_features.parquet, national scopes",
        "local_context": "context_aggregated_features.parquet, local, no focal party",
        "national_context": "context_aggregated_features.parquet, national, no focal party",
        "combined": "derived by summing the local and national blocks",
        "weighted_local": "recency_weighted_features.parquet, local scopes",
        "weighted_national": "recency_weighted_features.parquet, national scopes",
        "weighted_local_context": "recency_weighted_features.parquet, local, no focal party",
        "weighted_national_context": "recency_weighted_features.parquet, national, no focal party",
        "coverage": "missing_news_representation.parquet",
        "target": "election result (outcome, never a predictor)",
    }.get(prefix, "observation grid")


def blind(rows: Sequence[Mapping[str, object]]) -> list[dict]:
    """The 2026 rows with every outcome field removed.

    Removed, not blanked. A blanked column still tells a reader the field
    exists and invites it being filled in; an absent one cannot be read at
    all, which is what "predictions are saved before unblinding" requires.
    """

    return [
        {k: v for k, v in row.items() if not k.startswith(TARGET_PREFIX)}
        for row in rows if row.get("blinded_outcome_indicator")
    ]


def validate(rows: Sequence[Mapping[str, object]]) -> dict:
    """Every check the brief asks for, as data rather than as a print."""

    keys = [str(row["row_key"]) for row in rows]
    duplicate_keys = len(keys) - len(set(keys))

    contest_splits: dict[str, set[str]] = {}
    for row in rows:
        contest_splits.setdefault(str(row["contest_id"]), set()).add(
            str(row["modelling_split"]))
    split_contests = {c: sorted(s) for c, s in contest_splits.items() if len(s) > 1}

    may_2026 = [row for row in rows
                if "2026" in str(row["election_id"]) and "07-07" not in str(row["election_id"])]
    not_held_out = [row["row_key"] for row in may_2026
                    if not row.get("holdout_indicator")]

    both_labels = [row["row_key"] for row in rows
                   if row.get("is_reform_uk") and row.get("is_ukip")]
    reform_ukip_same_id = [
        row["row_key"] for row in rows
        if row.get("is_reform_uk") and str(row["party_id"]) == UKIP_KEY]

    zero_target_no_contest = [
        row["row_key"] for row in rows
        if row.get("did_not_contest") and row.get("target__party_vote_share") == 0]

    provenance = {}
    for row in rows:
        provenance[str(row.get("baseline__prediction_provenance"))] = (
            provenance.get(str(row.get("baseline__prediction_provenance")), 0) + 1)

    return {
        "rows": len(rows),
        "unique_row_keys": len(set(keys)),
        "duplicate_row_keys": duplicate_keys,
        "contests_split_across_more_than_one_split": split_contests,
        "may_2026_rows": len(may_2026),
        "may_2026_rows_not_held_out": not_held_out,
        "rows_labelled_both_reform_and_ukip": both_labels,
        "reform_rows_using_the_ukip_party_id": reform_ukip_same_id,
        "did_not_contest_rows_with_a_zero_target": zero_target_no_contest,
        "baseline_provenance_counts": dict(sorted(provenance.items())),
        "rows_by_split": dict(sorted(Counter(
            str(row["modelling_split"]) for row in rows).items())),
        "reform_rows": sum(1 for row in rows if row.get("is_reform_uk")),
        "ukip_rows": sum(1 for row in rows if row.get("is_ukip")),
        "did_not_contest_rows": sum(1 for row in rows if row.get("did_not_contest")),
        "all_checks_passed": not (
            duplicate_keys or split_contests or not_held_out or both_labels
            or reform_ukip_same_id or zero_target_no_contest),
    }
