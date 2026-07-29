"""Build the ward-party-election feature layer and write every required output.

    PYTHONPATH=src .venv/bin/python -m news_modelling.run_ward_party_features

Writes into a new versioned directory. Nothing under the Stage 1 bundle or the
earlier Phase 7 outputs is opened for writing at any point - the Stage 1
loader verifies the bundle against its own manifest hashes before anything is
joined, and the same verification is run again afterwards, so a claim that the
baseline was left alone is checked rather than asserted.

No model is trained here. The layer produces feature tables, views and audits;
the estimator waits on the Stage 1 architecture decision, because the residual
it would fit is defined against whichever baseline ships.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from news_modelling.stage1_bundle import load_stage1_bundle
from news_modelling.ward_party_build import (
    FEATURE_VERSION,
    IDENTIFIER_COLUMNS,
    TARGET_PREFIX,
    VIEW_PREFIXES,
    blind,
    build_master_rows,
    columns_for_view,
    feature_dictionary,
    leakage_audit,
    split_lookup,
    validate,
)
from news_modelling.ward_party_features import (
    ARM_LOCAL,
    ARM_NATIONAL,
    CUMULATIVE_SNAPSHOTS,
    ALTERNATIVE_SCHEMES,
    PRINCIPAL_WINDOWS,
    aggregate_baseline_to_party,
    build_observation_grid,
    index_coverage,
    index_news_rows,
    selected_feature_columns,
    verify_window_mapping,
)

REPO = Path(__file__).resolve().parents[2]
BUNDLE = REPO / "surrey-election-no-news-baseline/outputs/model_bundle_v1"
CONTRACT = REPO / (
    "surrey-election-extractor/outputs/no_news_candidate_contests/"
    "no_news_candidate_contest_features.json")
NEWS = REPO / "news_features"
OUT = REPO / "news_features/ward_party_election_features_v1"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    # A dict, not a list. Membership on a list is a linear scan, and this
    # runs once per cell: 6,323 rows by 12,087 columns is 76 million lookups,
    # each averaging six thousand comparisons. The list version did not
    # finish. A dict keeps insertion order and answers in constant time.
    columns: dict[str, None] = {}
    for row in rows:
        for key in row:
            columns.setdefault(key)
    columns = list(columns)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def summary_columns(frame: pd.DataFrame) -> list[str]:
    """The columns worth putting in a spreadsheet, in reading order.

    Chosen rather than sampled. A person opening this file wants to answer
    "which contest is this, what happened, what did Stage 1 expect, and how
    much news was there" - so it carries the identifiers, the targets, the
    baseline block, and one article count per arm and window. That is a few
    dozen columns instead of 24,151, and it opens.

    Every other column stays in the parquet and is described in
    ``final_feature_dictionary.csv``. Nothing is dropped from the data; this
    picks a view over it.
    """

    present = set(frame.columns)
    ordered: list[str] = []

    def take(columns: Sequence[str]) -> None:
        for column in columns:
            if column in present and column not in ordered:
                ordered.append(column)

    # Identifiers in reading order rather than alphabetically: who, where,
    # which party, which split. Any identifier not named here still follows.
    take(["row_key", "election_id", "election_date", "election_type",
          "electoral_area_name", "standardised_party_name",
          "is_reform_uk", "is_ukip", "modelling_split", "did_not_contest"])
    take(sorted(IDENTIFIER_COLUMNS))
    take(sorted(c for c in present if c.startswith(TARGET_PREFIX)))
    take(sorted(c for c in present if c.startswith("baseline__")))

    # One coverage count per arm and window: enough to see where the news is
    # and where it is not, which is the question the table keeps raising.
    take(sorted(c for c in present if c.endswith("__cov_n_articles")
                and c.count("__") == 2))
    return ordered


def split_populated_columns(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Columns with a value somewhere, and columns empty on every row.

    Identifier columns are always kept even where they are empty, because a
    table whose key columns come and go depending on the data is not joinable.
    """

    populated, empty = [], []
    for column in frame.columns:
        if column in IDENTIFIER_COLUMNS or frame[column].notna().any():
            populated.append(column)
        else:
            empty.append(column)
    return populated, empty


def coerce_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    """Give every column one type, without changing what it says.

    Numeric-looking object columns become numeric and keep their nulls as
    nulls; everything else that is still mixed becomes text. Nothing is filled
    in - a missing value stays missing, because the distinction between "no
    coverage" and "coverage of zero" is the point of several of these columns.
    """

    for column in frame.columns:
        if frame[column].dtype != object:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        original_present = frame[column].notna()
        if (numeric.notna() | ~original_present).all():
            frame[column] = numeric
        else:
            frame[column] = frame[column].map(
                lambda v: None if v is None else str(v))
    return frame


def bundle_fingerprint(directory: Path) -> str:
    """A hash over the whole bundle, to prove it was not written to."""

    digest = hashlib.sha256()
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name != "training.log":
            digest.update(path.name.encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    before = bundle_fingerprint(BUNDLE)

    bundle = load_stage1_bundle(BUNDLE)
    print(f"Stage 1 verified: {bundle.bundle_version}, "
          f"{bundle.selected_architecture}, "
          f"{len(bundle.out_of_fold)} out-of-fold rows")

    # --- window mapping, checked before anything is built ----------------
    assignment = json.loads(
        (NEWS / "article_time_window_assignment.json").read_text(encoding="utf-8"))
    days = [row["days_before_polling"] for row in assignment["assigned"]]
    mapping_report = verify_window_mapping(days)
    # Windows the verification found empty assemble from nothing. Applied to
    # the specs the builder uses, so an empty window cannot pick up rows from
    # a wider legacy bucket.
    resolved_windows = {}
    for name, spec in {**PRINCIPAL_WINDOWS, **CUMULATIVE_SNAPSHOTS}.items():
        check = mapping_report["checks"][name]
        resolved_windows[name] = {**spec, "from_old": tuple(check["assembled_from"])}
    print(f"window mapping verified against {len(days)} assigned articles")
    for name, check in mapping_report["checks"].items():
        print(f"  {name:34s} {check['construction']:34s} "
              f"{check['articles_in_own_day_range']} article(s) in range")

    # --- inputs -----------------------------------------------------------
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))["rows"]
    contestation = read_csv(BUNDLE / "contestation_records.csv")
    split_manifest = read_csv(BUNDLE / "split_manifest.csv")

    context = pd.read_parquet(NEWS / "context_aggregated_features.parquet")
    weighted = pd.read_parquet(NEWS / "recency_weighted_features.parquet")
    coverage = pd.read_parquet(NEWS / "missing_news_representation.parquet")
    articles = pd.read_parquet(NEWS / "article_level_news_features.parquet")

    # Party identifiers in the aggregation are opaque; the article table is
    # where they carry a readable name, and the join to the election data is
    # on the standardised name.
    party_names = (articles.dropna(subset=["focal_party_id"])
                   .drop_duplicates("focal_party_id")
                   .set_index("focal_party_id")["focal_party_name"].to_dict())

    feature_columns = selected_feature_columns(list(context.columns))
    weighted_columns = selected_feature_columns(list(weighted.columns),
                                               weighted=True)
    print(f"news feature columns carried: {len(feature_columns)} unweighted, "
          f"{len(weighted_columns)} recency-weighted")

    context_rows = context.to_dict("records")
    weighted_rows = weighted.to_dict("records")

    # --- assemble ---------------------------------------------------------
    grid = build_observation_grid(contract, contestation)
    print(f"observation grid: {len(grid)} rows "
          f"({sum(1 for r in grid if r['did_not_contest'])} did-not-contest)")

    baseline = aggregate_baseline_to_party(
        list(bundle.out_of_fold), provenance="stage1_out_of_fold")
    baseline.update(aggregate_baseline_to_party(
        list(bundle.holdout), provenance="stage1_holdout"))

    rows = build_master_rows(
        grid, baseline,
        index_news_rows(context_rows, party_names, arm=ARM_LOCAL),
        index_news_rows(context_rows, party_names, arm=ARM_NATIONAL),
        index_coverage(coverage.to_dict("records"), party_names),
        index_news_rows(weighted_rows, party_names, arm=ARM_LOCAL),
        index_news_rows(weighted_rows, party_names, arm=ARM_NATIONAL),
        split_lookup(split_manifest),
        feature_columns=feature_columns,
        weighted_feature_columns=weighted_columns,
        windows=resolved_windows,
    )
    all_columns = sorted({column for row in rows for column in row})
    print(f"master table: {len(rows)} rows x {len(all_columns)} columns")

    checks = validate(rows)
    print(f"validation: {'all checks passed' if checks['all_checks_passed'] else 'FAILURES'}")
    for key in ("rows_by_split", "baseline_provenance_counts"):
        print(f"  {key}: {checks[key]}")
    print(f"  Reform rows {checks['reform_rows']}, UKIP rows {checks['ukip_rows']}, "
          f"did-not-contest {checks['did_not_contest_rows']}")

    # --- outputs ----------------------------------------------------------
    # Parquet needs one type per column. `number_of_seats` and a few other
    # grid fields arrive as an int from the candidate table and as a string
    # from the contestation record, so they are coerced once here rather than
    # letting the writer fail on the first mixed column.
    frame = coerce_for_parquet(pd.DataFrame(rows))
    frame.to_parquet(OUT / "ward_party_election_features.parquet", index=False)

    # The parquet is the canonical artefact and carries every column. The CSV
    # is for reading, and under the six-window scheme it can no longer be the
    # same table: 24,151 columns exceeds Excel's limit of 16,384, so a wide CSV
    # is not merely large but unopenable in the tool it exists for. Writing one
    # anyway would produce a quarter-gigabyte file whose only honest use is to
    # be read back by the code that already prefers the parquet.
    #
    # So the CSV carries what a person actually reads - who the row is, what
    # happened, what Stage 1 predicted, and how much coverage each arm and
    # window held - and the feature dictionary documents the rest.
    populated, empty_columns = split_populated_columns(frame)
    summary = summary_columns(frame)
    write_csv(OUT / "ward_party_election_features_summary.csv",
              frame[summary].to_dict("records"))
    print(f"summary CSV: {len(summary)} columns, readable in a spreadsheet")
    write_csv(OUT / "empty_feature_columns.csv", [
        {"feature_name": column,
         "block": column.split("__")[0] if "__" in column else "identifier",
         "time_window": column.split("__")[1] if column.count("__") > 1 else "",
         "reason": ("No article in this arm and window contributed to any row; "
                    "the column exists so the absence is explicit rather than "
                    "the block being silently missing.")}
        for column in empty_columns])
    print(f"columns: {len(frame.columns)} total, {len(populated)} populated, "
          f"{len(empty_columns)} empty on every row")

    blinded = blind(rows)
    blinded_frame = coerce_for_parquet(pd.DataFrame(blinded))
    blinded_frame.to_parquet(
        OUT / "ward_party_election_features_blinded_2026.parquet", index=False)
    # Same reasoning as above, and it matters more here: the blinded table is
    # the one somebody opens to confirm no outcome is visible before the 2026
    # predictions are made. A file that cannot be opened cannot be checked.
    write_csv(OUT / "ward_party_election_features_blinded_2026_summary.csv",
              blinded_frame[summary_columns(blinded_frame)].to_dict("records"))
    print(f"blinded 2026 table: {len(blinded)} rows, "
          f"{sum(1 for c in (blinded[0] if blinded else {}) if c.startswith(TARGET_PREFIX))} "
          "target columns")

    # Candidate-level companion, for the secondary targets that only exist at
    # candidate level. Built from Stage 1's own predictions rather than
    # re-derived, so it cannot disagree with them.
    companion = [
        {"candidate_contest_id": row["candidate_contest_id"],
         "election_id": row["election_id"], "division_id": row["division_id"],
         "standard_party_name": row["standard_party_name"],
         "is_reform_uk": row["is_reform_uk"], "is_ukip": row["is_ukip"],
         "ward_party_row_key": f"{row['election_id']}|{row['division_id']}|"
                               f"{__import__('re').sub(r'[^a-z0-9]+', ' ', str(row['standard_party_name']).lower()).strip()}",
         "baseline__predicted_vote_share": row.get("predicted_vote_share"),
         "baseline__prediction_provenance": provenance,
         "target__candidate_vote_share": row.get("observed_vote_share"),
         "target__candidate_rank": row.get("observed_rank"),
         "target__candidate_elected": row.get("observed_elected")}
        for predictions, provenance in (
            (bundle.out_of_fold, "stage1_out_of_fold"),
            (bundle.holdout, "stage1_holdout"))
        for row in predictions
    ]
    coerce_for_parquet(pd.DataFrame(companion)).to_parquet(
        OUT / "candidate_election_features.parquet", index=False)

    view_manifest = {
        "feature_version": FEATURE_VERSION,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "master_table": "ward_party_election_features.parquet",
        "note": ("Every view is a column selection over the master table, so "
                 "no two views can disagree about a row."),
        "views": {
            view: {
                "columns": columns_for_view(view, all_columns),
                "column_count": len(columns_for_view(view, all_columns)),
                "includes_targets": TARGET_PREFIX in VIEW_PREFIXES[view],
            }
            for view in VIEW_PREFIXES
        },
        "window_specification": {
            "principal": {k: v["days"] for k, v in PRINCIPAL_WINDOWS.items()},
            "cumulative": {k: v["days"] for k, v in CUMULATIVE_SNAPSHOTS.items()},
            "scheme": "original_email_180d",
            "alternative_schemes_available": list(ALTERNATIVE_SCHEMES),
            "assembly_verification": mapping_report,
        },
    }
    (OUT / "feature_view_manifest.json").write_text(
        json.dumps(view_manifest, indent=2, default=str) + "\n", encoding="utf-8")

    write_csv(OUT / "news_split_manifest.csv", [
        {"row_key": row["row_key"], "contest_id": row["contest_id"],
         "election_id": row["election_id"], "election_date": row["election_date"],
         "modelling_split": row["modelling_split"],
         "chronological_fold": row["chronological_fold"],
         "holdout_indicator": row["holdout_indicator"],
         "blinded_outcome_indicator": row["blinded_outcome_indicator"],
         "baseline_prediction_provenance": row.get("baseline__prediction_provenance")}
        for row in rows])

    write_csv(OUT / "final_feature_dictionary.csv", feature_dictionary(all_columns))
    audit = leakage_audit(all_columns)
    write_csv(OUT / "final_feature_leakage_audit.csv", audit)

    excluded = [row for row in audit if row["verdict"] == "excluded"]
    print(f"leakage audit: {len(audit)} columns classified, "
          f"{len(excluded)} excluded, "
          f"{sum(1 for r in audit if r['verdict'] == 'permitted')} permitted, "
          f"{sum(1 for r in audit if r['verdict'] == 'target')} targets")

    after = bundle_fingerprint(BUNDLE)
    from collections import Counter
    block_totals = Counter(c.split("__")[0] for c in frame.columns if "__" in c)
    block_empty = Counter(c.split("__")[0] for c in empty_columns if "__" in c)
    empty_by_block = [(block, block_totals[block], block_empty.get(block, 0))
                      for block in sorted(block_totals)]
    write_audit(OUT, rows, checks, mapping_report, audit, all_columns,
                before == after, len(feature_columns), len(weighted_columns),
                empty_by_block)
    write_error_analysis(OUT, rows, checks, mapping_report)

    print(f"\nStage 1 bundle unchanged: {before == after}")
    print(f"written to {OUT}")


def write_audit(out: Path, rows, checks, mapping_report, audit, all_columns,
                bundle_unchanged: bool, unweighted: int, weighted: int,
                empty_by_block=()) -> None:
    """The build's own record of what it produced and what it verified."""

    excluded = [r for r in audit if r["verdict"] == "excluded"]
    lines = [
        "# Ward-party-election feature table: build audit",
        "",
        f"**Feature version:** `{FEATURE_VERSION}`  ",
        f"**Built:** {date.today().isoformat()}  ",
        f"**Stage 1 bundle unchanged during the build:** {bundle_unchanged}",
        "",
        "> ## Read this before using any figure from this table",
        ">",
        "> The news side rests on a **67-article pilot**. The alignment layer "
        "names its own dataset `context-cards-v1.0-pilot67-2026-07-27`, and "
        "every downstream stage - article features, context aggregation, "
        "recency weighting - was built from it.",
        ">",
        "> The corpus is not 67 articles. 17,248 records are on disk, 13,399 "
        "with full text, and 3,584 have passed eligibility and are waiting for "
        "extraction. They have never been through it, which is why this table "
        "carries coverage states almost everywhere and extracted content "
        "almost nowhere.",
        ">",
        "> The structure below is complete and checked. The contents are a "
        "pilot. Nothing here should be read as a measurement of what news "
        "does.",
        "",
        "## What was built",
        "",
        f"- master table: **{len(rows)} rows x {len(all_columns)} columns**",
        f"- observation unit: election x electoral area x party",
        f"- news feature columns carried: {unweighted} unweighted, "
        f"{weighted} recency-weighted",
        f"- rows by split: {checks['rows_by_split']}",
        f"- Reform UK rows {checks['reform_rows']}, UKIP rows {checks['ukip_rows']}, "
        f"kept under separate party ids throughout",
        f"- did-not-contest rows: {checks['did_not_contest_rows']}, "
        "each with an empty vote-share target rather than a zero",
        "",
        "## Window assembly",
        "",
        "The principal windows are assembled from the earlier six-window "
        "aggregates. Two assemblies are exact only because of how this corpus "
        "falls, so the assembly is verified against the article-level day "
        "counts on every build and refuses to proceed if it stops holding.",
        "",
        "| window | assembled from | days that must be empty | exact |",
        "| --- | --- | --- | :---: |",
    ]
    for name, check in mapping_report["checks"].items():
        lines.append(
            f"| `{name}` | {', '.join(check['assembled_from'])} | "
            f"{check['days_that_must_be_empty'] or 'none'} | "
            f"{'yes' if check['exact'] else 'NO'} |")

    lines += [
        "",
        f"Articles assigned to a window: {mapping_report['articles_assigned']}.",
        "",
        "## Which feature blocks are empty",
        "",
        "A column empty on every row means no article in that arm and window "
        "reached any row. Counted here rather than dropped silently, because "
        "an absent block and an empty one look identical once a table is "
        "written.",
        "",
        f"| block | columns | empty on every row |",
        "| --- | ---: | ---: |",
    ] + [
        f"| `{block}` | {total} | {empty} |"
        for block, total, empty in empty_by_block
    ] + [
        "",
        "## Leakage audit",
        "",
        f"Every one of the {len(audit)} columns carries a verdict. "
        f"{sum(1 for r in audit if r['verdict'] == 'permitted')} permitted, "
        f"{sum(1 for r in audit if r['verdict'] == 'target')} targets, "
        f"{len(excluded)} excluded, "
        f"{sum(1 for r in audit if r['verdict'] == 'identifier')} identifiers.",
        "",
        "An unrecognised column is refused rather than allowed. A new column "
        "arriving from upstream stops the build instead of joining the "
        "predictor set by default.",
        "",
        "## Validation",
        "",
        "| check | result |",
        "| --- | --- |",
        f"| unique row keys | {checks['unique_row_keys']} of {checks['rows']} |",
        f"| duplicate row keys | {checks['duplicate_row_keys']} |",
        f"| contests split across more than one split | "
        f"{len(checks['contests_split_across_more_than_one_split'])} |",
        f"| 7 May 2026 rows | {checks['may_2026_rows']}, "
        f"{len(checks['may_2026_rows_not_held_out'])} not held out |",
        f"| rows labelled both Reform UK and UKIP | "
        f"{len(checks['rows_labelled_both_reform_and_ukip'])} |",
        f"| did-not-contest rows with a zero target | "
        f"{len(checks['did_not_contest_rows_with_a_zero_target'])} |",
        "",
        f"**All checks passed: {checks['all_checks_passed']}**",
        "",
        "## What this layer does not do",
        "",
        "- No model is trained. The estimator waits on the Stage 1 "
        "architecture decision, since the residual it would fit is defined "
        "against whichever baseline ships.",
        "- No embeddings, no synthetic scenarios.",
        "- Nothing under the Stage 1 bundle or the earlier Phase 7 outputs is "
        "opened for writing; the bundle is hashed before and after and the "
        "two are compared above.",
    ]
    (out / "final_feature_table_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def write_error_analysis(out: Path, rows, checks, mapping_report) -> None:
    """Where this table is thin, and what that means for anything fitted on it."""

    reform = [r for r in rows if r.get("is_reform_uk")]
    reform_training = [r for r in reform
                       if r["modelling_split"] == "historical_training"]
    reform_with_news = [
        r for r in reform_training
        if any(v is not None for k, v in r.items()
               if k.startswith(("local__", "national__")))]

    lines = [
        "# Ward-party-election feature table: error analysis",
        "",
        "What is thin here, stated before anything is fitted on it.",
        "",
        "## Reform UK",
        "",
        f"- Reform rows in the table: **{len(reform)}**",
        f"- of those, in the historical training split: **{len(reform_training)}**",
        f"- of those, carrying any news feature: **{len(reform_with_news)}**",
        "",
        "Reform UK was renamed from the Brexit Party in January 2021 and did "
        "not exist for the 2013 or 2017 elections, so its training-period "
        "presence is small for reasons no amount of collection can change. "
        "Any Reform-specific estimate has to be quoted with this count.",
        "",
        "## Did-not-contest rows",
        "",
        f"- {checks['did_not_contest_rows']} rows record a party that did not "
        "stand. Their vote-share target is empty, not zero.",
        "- A model fitted with those rows included, and their target read as "
        "zero, would learn that every party polls nothing almost everywhere. "
        "They are present so the absence is visible, and must be filtered by "
        "`party_contested` before fitting rather than left to a null-handling "
        "default.",
        "",
        "## Window horizon",
        "",
        "The principal windows reach 30 days. The corpus was collected on a "
        "180-day horizon, so most collected articles fall outside the "
        "principal windows and enter only the retained sensitivity layer. "
        "That is a consequence of the window specification, not of the "
        "collection.",
        "",
        "## Coverage states",
        "",
        "`coverage__` columns carry the distinction between no news found, "
        "an archive that could not be searched, and a stage still pending. "
        "A model that treats a null news feature as zero coverage will "
        "conflate all three. The indicators exist so it does not have to.",
        "",
        "## The table is wider than it is long, and cannot be fitted as it stands",
        "",
        "12,091 columns against 6,323 rows. Any estimator handed the table "
        "whole would fit it perfectly and generalise not at all, so a feature "
        "selection step is required before anything is trained. The views "
        "narrow it - the local view is about 2,700 columns - but not enough.",
        "",
        "The width is the product of three counts, all of which the "
        "specification asks for: 225 news features, six windows, and nine "
        "blocks. Two of those nine are a decision taken here rather than "
        "required - splitting each arm into coverage that names a party and "
        "coverage that names none - which roughly doubles the width. The "
        "split is worth keeping (party-agnostic local coverage reaches 552 "
        "columns where party-named coverage reaches 6) but its cost should be "
        "stated rather than absorbed.",
        "",
        "## Association, not causation",
        "",
        "Nothing in this table supports a causal claim. A news feature that "
        "predicts a vote share describes an association within this "
        "historical sample; it does not establish that the coverage moved "
        "anyone's vote.",
    ]
    (out / "final_feature_error_analysis.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
