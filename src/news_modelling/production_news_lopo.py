"""Leave-one-party-out robustness check for the production news experiment.

The main experiment has five independent 2017 fitting rows: one for each
supported party.  This check removes each party in turn, refits the unchanged
two-feature ridge model on the remaining four rows, and re-evaluates all 18
confirmed arm-window comparisons on the same 2021 candidates.

This is a stability test, not another model-selection exercise.  It does not
rank omissions, choose a better window, retune the fixed penalty, inspect the
six cumulative sensitivities or read the 2026 holdout.  If deleting one party
changes a non-improving comparison into an improvement, the correct conclusion
is that the result is sensitive to a single training party—not that the
omission discovered a better model.
"""

from __future__ import annotations

import json
from pathlib import Path

from news_modelling.production_news_experiment import (
    _feature_index,
    _read_csv,
    aggregate_fitting_residuals,
    run_one,
    validate_inputs,
)


class LopoAuditError(RuntimeError):
    """The LOPO inputs differ from the frozen production experiment."""


def _sign(value: float, tolerance: float = 1e-12) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def _coefficient_sign_flips(full: dict, omitted: dict) -> list[str]:
    """Name coefficients whose direction changes after removing one party."""

    flips = []
    for column, full_value in full["standardised_coefficients"].items():
        omitted_value = omitted["standardised_coefficients"][column]
        if _sign(float(full_value)) != _sign(float(omitted_value)):
            flips.append(column)
    return flips


def run_lopo(
    feature_table_path: str | Path,
    audit_path: str | Path,
    oof_path: str | Path,
    primary_results_path: str | Path,
) -> dict:
    """Run all five omissions against all 18 confirmed-window comparisons."""

    audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    primary = json.loads(Path(primary_results_path).read_text(encoding="utf-8"))
    features = _read_csv(feature_table_path)
    oof_rows = _read_csv(oof_path)
    validate_inputs(oof_rows, audit)

    if primary.get("stage1_holdout_file_read") is not False:
        raise LopoAuditError("Primary experiment did not record holdout isolation.")
    if primary.get("canonical_release_id") != audit["canonical_release"]["release_id"]:
        raise LopoAuditError("Primary result and estimability audit use different releases.")

    full_fitting = aggregate_fitting_residuals(oof_rows)
    if sorted(full_fitting) != sorted(primary["training_parties"]):
        raise LopoAuditError("Current fitting parties differ from the primary result.")

    # Only the six supervisor-confirmed windows belong to the primary analysis.
    # Cumulative periods were declared sensitivities and are intentionally not
    # allowed to influence this stability verdict.
    confirmed_windows = list(audit["feature_table"]["windows"])
    feature_index = _feature_index(features)
    primary_by_key = {
        (result["analysis"], result["period"]): result
        for result in primary["specification_results"]
        if result["period_role"] == "confirmed_window"
    }

    expected_keys = {
        (analysis, period)
        for analysis in audit["frozen_feature_sets"]
        for period in confirmed_windows
    }
    if set(primary_by_key) != expected_keys:
        raise LopoAuditError("Primary result does not contain exactly 18 comparisons.")

    comparisons = []
    for omitted_party in sorted(full_fitting):
        reduced = {
            party: row for party, row in full_fitting.items()
            if party != omitted_party
        }
        for analysis, specification in audit["frozen_feature_sets"].items():
            for period in confirmed_windows:
                omitted_result, _ = run_one(
                    oof_rows,
                    feature_index,
                    reduced,
                    period=period,
                    feature_columns=list(specification["columns"]),
                    analysis_name=analysis,
                    analysis_role=specification["analysis_role"],
                    calculate_bootstrap=False,
                )
                full_result = primary_by_key[(analysis, period)]
                full_delta = full_result["metrics"]["all_supported_parties"][
                    "news_vs_recalibrated_mae"
                ]
                omitted_delta = omitted_result["metrics"][
                    "all_supported_parties"
                ]["news_vs_recalibrated_mae"]
                comparisons.append({
                    "omitted_party": omitted_party,
                    "remaining_training_parties": sorted(reduced),
                    "training_party_rows": len(reduced),
                    "analysis": analysis,
                    "analysis_role": specification["analysis_role"],
                    "period": period,
                    "full_model_news_vs_recalibrated_mae": full_delta,
                    "lopo_news_vs_recalibrated_mae": omitted_delta,
                    "change_from_full_model": omitted_delta - full_delta,
                    "lopo_news_vs_raw_baseline_mae": omitted_result["metrics"][
                        "all_supported_parties"
                    ]["news_vs_raw_baseline_mae"],
                    "lopo_reform_news_mae": omitted_result["metrics"][
                        "reform_uk"
                    ]["news_enhanced"]["mae"],
                    "lopo_reform_news_vs_recalibrated_mae": omitted_result[
                        "metrics"
                    ]["reform_uk"]["news_vs_recalibrated_mae"],
                    "coefficient_sign_flips": _coefficient_sign_flips(
                        full_result, omitted_result
                    ),
                    "negative_raw_shares_clipped": omitted_result[
                        "negative_raw_shares_clipped"
                    ]["news_enhanced"],
                    "parties_outside_training_feature_range": omitted_result[
                        "validation_parties_outside_training_feature_range"
                    ],
                    "creates_overall_improvement": omitted_delta > 0,
                })

    by_omission = {}
    for party in sorted(full_fitting):
        rows = [row for row in comparisons if row["omitted_party"] == party]
        by_omission[party] = {
            "comparisons": len(rows),
            "overall_improvements": sum(
                row["creates_overall_improvement"] for row in rows
            ),
            "coefficient_sign_flips": sum(
                len(row["coefficient_sign_flips"]) for row in rows
            ),
            "minimum_news_vs_recalibrated_mae": min(
                row["lopo_news_vs_recalibrated_mae"] for row in rows
            ),
            "maximum_news_vs_recalibrated_mae": max(
                row["lopo_news_vs_recalibrated_mae"] for row in rows
            ),
        }

    improvements = [row for row in comparisons if row["creates_overall_improvement"]]
    verdict = (
        "stable_no_confirmed_window_improvement"
        if not improvements
        else "unstable_single_party_omissions_create_improvements"
    )
    return {
        "status": "completed_leave_one_party_out_robustness",
        "canonical_release_id": audit["canonical_release"]["release_id"],
        "stage1_holdout_file_read": False,
        "fit_election": primary["fit_election"],
        "validation_election": primary["validation_election"],
        "ridge_penalty": primary["ridge_penalty"],
        "penalty_selection": "unchanged from primary; no tuning",
        "omitted_parties": sorted(full_fitting),
        "training_rows_per_refit": 4,
        "confirmed_windows_only": confirmed_windows,
        "comparisons_per_omission": len(expected_keys),
        "total_comparisons": len(comparisons),
        "overall_improvements_after_omission": len(improvements),
        "robustness_verdict": verdict,
        "by_omission": by_omission,
        "comparison_results": comparisons,
        "interpretation_rule": (
            "An improvement after omitting a party is evidence of sensitivity "
            "to that training party, not a candidate model to select. No LOPO "
            "result may replace the frozen primary experiment."
        ),
    }


def render_findings(report: dict) -> str:
    """Render every omission/comparison and the pre-declared stability verdict."""

    lines = [
        "# Leave-one-party-out robustness of the production news experiment",
        "",
        "**This is a training-sensitivity audit, not model selection.** It uses "
        "2017 fitting data and 2021 validation only; the 2026 holdout file was "
        "not read. Positive MAE differences mean news beats that omission's "
        "training-only recalibration.",
        "",
        "## Design",
        "",
        f"- Omitted in turn: {', '.join(report['omitted_parties'])}.",
        "- Four party-level rows remain in each refit.",
        "- The two frozen features, ridge penalty 1.0 and all six confirmed "
        "windows are unchanged.",
        "- Cumulative periods are excluded because they are sensitivity analyses.",
        "- Conditional contest bootstraps are not repeated: the uncertainty "
        "being tested here is removal of one independent training party.",
        "",
        "## Summary by omitted party",
        "",
        "| omitted party | comparisons | overall improvements | coefficient "
        "sign flips | minimum MAE difference | maximum MAE difference |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for party, row in report["by_omission"].items():
        lines.append(
            f"| {party} | {row['comparisons']} | "
            f"{row['overall_improvements']} | {row['coefficient_sign_flips']} | "
            f"{row['minimum_news_vs_recalibrated_mae']:+.4f} | "
            f"{row['maximum_news_vs_recalibrated_mae']:+.4f} |"
        )

    # List the positive rows explicitly.  A summary count alone can hide that
    # every apparent improvement comes from the same omission, which is the
    # central stability finding and must remain visible in the written record.
    improvements = [
        row for row in report["comparison_results"]
        if row["creates_overall_improvement"]
    ]
    lines.extend([
        "",
        "## Apparent improvements after omission",
        "",
        "These rows are reported for completeness, not as candidate models. "
        "Positive values mean lower overall MAE than that omission's "
        "training-only recalibrated control.",
        "",
        "| omitted | analysis | period | full-model difference | omission "
        "difference | Reform difference | sign flips |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ])
    for row in improvements:
        flips = ", ".join(row["coefficient_sign_flips"]) or "none"
        lines.append(
            f"| {row['omitted_party']} | {row['analysis']} | {row['period']} | "
            f"{row['full_model_news_vs_recalibrated_mae']:+.4f} | "
            f"{row['lopo_news_vs_recalibrated_mae']:+.4f} | "
            f"{row['lopo_reform_news_vs_recalibrated_mae']:+.4f} | {flips} |"
        )

    lines.extend([
        "",
        "## All 90 robustness comparisons",
        "",
        "| omitted | analysis | period | full MAE difference | LOPO MAE "
        "difference | change from full | Reform MAE difference | sign flips |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ])
    for row in report["comparison_results"]:
        flips = ", ".join(row["coefficient_sign_flips"]) or "none"
        lines.append(
            f"| {row['omitted_party']} | {row['analysis']} | {row['period']} | "
            f"{row['full_model_news_vs_recalibrated_mae']:+.4f} | "
            f"{row['lopo_news_vs_recalibrated_mae']:+.4f} | "
            f"{row['change_from_full_model']:+.4f} | "
            f"{row['lopo_reform_news_vs_recalibrated_mae']:+.4f} | {flips} |"
        )

    lines.extend([
        "",
        "## Verdict",
        "",
        f"`{report['robustness_verdict']}`",
        "",
        f"Across {report['total_comparisons']} omission refits, "
        f"{report['overall_improvements_after_omission']} produce an overall "
        "improvement over their recalibrated control.",
        "",
        "If this count is non-zero, the primary 0/18 finding is sensitive to "
        "which single party is present in the four-row fit. Such rows are not "
        "alternative models and must not be selected. If it is zero, the "
        "direction of the primary confirmed-window conclusion survives every "
        "single-party omission, although the one-election/four-row refits still "
        "cannot establish a general news effect or a Reform-specific effect.",
        "",
        "The complete JSON also preserves clipping counts and parties outside "
        "the reduced training range for every comparison. Contest bootstraps "
        "are intentionally not repeated here: the primary experiment already "
        "records conditional 2021 contest-sampling intervals, while this audit "
        "isolates sensitivity to the independent training-party rows.",
        "",
    ])
    return "\n".join(lines)


def write_outputs(report: dict, output_dir: str | Path) -> None:
    """Write the complete audit in machine- and human-readable forms."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "lopo_results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (output / "lopo_findings.md").write_text(
        render_findings(report), encoding="utf-8"
    )
