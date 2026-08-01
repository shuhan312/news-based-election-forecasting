"""The one-time 2026 unblinding: score the frozen predictions against reality.

This module performs the project's terminal confirmatory step, and it is
built so that running it can only ever mean one thing:

1. **Integrity first.** Before a single observed value is read, every
   frozen prediction file is re-hashed and compared against the sha256
   manifest committed at its freeze, and the v2 protocol's embedded copy
   of the v1 hashes is checked too. If any byte has changed since the
   freeze, unblinding refuses to start - scoring tampered predictions
   would be worse than not scoring at all.
2. **One unblinding.** The output directory is refused if it exists.
   There is no flag to override this: a second "unblinding" would be a
   re-grading of a known answer.
3. **No selection.** Every archived specification is scored and written.
   The confirmatory verdicts are the two pre-declared families - the
   combined and national arms over the six confirmed windows, under the
   v1 primary variant and under the v2 enrichment variant - each
   compared against its recalibrated control on overall MAE, with
   contest-level bootstrap intervals. Everything else (local arm,
   cumulative periods, the 2017-only replication) is scored and labelled
   sensitivity. The renderer reports counts and lists; it never ranks,
   never picks a best row, and prints the interpretation rule beside
   every table.

Scoring conventions are inherited from the frozen pre-2026 experiment:
MAE over supported candidate rows (the six party families with news
coverage), Reform UK reported separately with its row count visible,
contest bootstrap with the baseline bundle's own seed, and seat-level
accuracy computed from the two-member allocations. The observed values
come from the Stage 1 holdout file - the same file whose predicted
columns fed the freezes; its observed columns are read here for the
first and only time in the news layer.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from news_modelling.news_estimator import bootstrap_improvement

V1_DIR = Path("news_features/blinded_2026_predictions_v1")
V2_DIR = Path("news_features/blinded_2026_predictions_v2")
HOLDOUT = Path(
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "holdout_predictions.csv"
)
OUTPUT_DIR = Path("news_features/unblinding_2026_v1")

# The two pre-declared confirmatory families, exactly as the frozen
# protocols state them. Everything not matched here is sensitivity.
CONFIRMATORY = {
    "v1": {"fit_variant": "pooled_2017_2021",
           "analyses": ("combined_exploratory", "national_exploratory"),
           "period_role": "confirmed_window"},
    "v2": {"fit_variant": "pooled_2017_2021_byelections",
           "analyses": ("combined_exploratory", "national_exploratory"),
           "period_role": "confirmed_window"},
}


class UnblindingRefused(RuntimeError):
    """The preconditions for a legitimate unblinding do not hold."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze_integrity() -> dict:
    """Prove the files being scored are the files that were frozen."""

    report = {}
    for name, directory in (("v1", V1_DIR), ("v2", V2_DIR)):
        manifest = json.loads((directory / "sha256_manifest.json").read_text())
        for filename in ("blinded_predictions.csv", "frozen_protocol.json"):
            actual = _sha256(directory / filename)
            if actual != manifest[filename]:
                raise UnblindingRefused(
                    f"{name}/{filename} does not match its frozen sha256; "
                    "refusing to score altered predictions"
                )
            report[f"{name}/{filename}"] = actual

    # The v2 protocol embedded the v1 hashes at its own freeze; a mismatch
    # would mean the two files were not frozen against each other.
    v2_protocol = json.loads((V2_DIR / "frozen_protocol.json").read_text())
    v1_manifest = json.loads((V1_DIR / "sha256_manifest.json").read_text())
    chain = v2_protocol["v1_freeze"]
    if (chain["predictions_sha256"] != v1_manifest["blinded_predictions.csv"]
            or chain["protocol_sha256"] != v1_manifest["frozen_protocol.json"]):
        raise UnblindingRefused(
            "v2 protocol's embedded v1 hashes disagree with the v1 manifest"
        )
    return report


def load_observed() -> dict[str, dict]:
    """The first sanctioned read of 2026 outcomes in the news layer."""

    observed = {}
    with HOLDOUT.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            observed[row["candidate_contest_id"]] = {
                "observed_vote_share": float(row["observed_vote_share"]),
                "observed_elected": row["observed_elected"],
                "baseline_predicted_share": float(row["predicted_vote_share"]),
                "baseline_predicted_elected": row["predicted_elected"],
                "election_id": row["election_id"],
                "division_id": row["division_id"],
                "is_reform_uk": row["is_reform_uk"],
            }
    return observed


def _metric_block(rows: list[dict], prediction_key: str) -> dict:
    """MAE/RMSE over rows, in the frozen experiment's shape."""

    if not rows:
        return {"rows": 0}
    errors = np.array([
        row[prediction_key] - row["observed_vote_share"] for row in rows
    ])
    return {
        "rows": len(rows),
        "contests": len({(row["election_id"], row["division_id"])
                         for row in rows}),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
    }


def _seat_accuracy(rows: list[dict], flag_key: str) -> dict:
    """Share of candidate rows whose elected/not-elected call was right."""

    if not rows:
        return {"rows": 0}
    correct = sum(
        1 for row in rows
        if str(row[flag_key]) == str(row["observed_elected"])
    )
    return {"rows": len(rows), "correct": correct,
            "accuracy": round(correct / len(rows), 4)}


def _bootstrap_rows(rows: list[dict], comparator_key: str) -> list[dict]:
    return [
        {
            "election_id": row["election_id"],
            "area_id": row["division_id"],
            "baseline_absolute_error":
                abs(row[comparator_key] - row["observed_vote_share"]),
            "news_absolute_error":
                abs(row["news_enhanced_prediction"]
                    - row["observed_vote_share"]),
        }
        for row in rows
    ]


def score_specification(spec_rows: list[dict], observed: dict,
                        *, with_bootstrap: bool) -> dict:
    """Score one (variant, analysis, period) block of prediction rows."""

    joined = []
    for row in spec_rows:
        outcome = observed[row["candidate_contest_id"]]
        joined.append({
            **outcome,
            "supported": row["included_in_reported_metrics"] == "True",
            "is_reform": row["is_reform_uk"] == "True",
            "baseline_prediction": float(row["baseline_prediction"]),
            "recalibrated_prediction": float(row["recalibrated_prediction"]),
            "news_enhanced_prediction":
                float(row["news_enhanced_prediction"]),
            "news_predicted_elected": row["news_predicted_elected"],
        })
    supported = [row for row in joined if row["supported"]]
    reform = [row for row in supported if row["is_reform"]]

    def scope(rows: list[dict]) -> dict:
        baseline = _metric_block(rows, "baseline_prediction")
        recalibrated = _metric_block(rows, "recalibrated_prediction")
        news = _metric_block(rows, "news_enhanced_prediction")
        return {
            "baseline": baseline,
            "recalibrated_without_news": recalibrated,
            "news_enhanced": news,
            "news_vs_raw_baseline_mae":
                baseline.get("mae", 0) - news.get("mae", 0),
            "news_vs_recalibrated_mae":
                recalibrated.get("mae", 0) - news.get("mae", 0),
        }

    result = {
        "all_supported_parties": scope(supported),
        "reform_uk": scope(reform),
        "seat_accuracy_news": _seat_accuracy(joined, "news_predicted_elected"),
    }
    if with_bootstrap:
        result["bootstrap_news_vs_recalibrated"] = bootstrap_improvement(
            _bootstrap_rows(supported, "recalibrated_prediction"))
        result["bootstrap_news_vs_raw_baseline"] = bootstrap_improvement(
            _bootstrap_rows(supported, "baseline_prediction"))
    return result


def _load_predictions(directory: Path) -> dict[tuple, list[dict]]:
    blocks: dict[tuple, list[dict]] = defaultdict(list)
    with (directory / "blinded_predictions.csv").open(
            encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["fit_variant"], row["analysis"], row["period"],
                   row["period_role"], row["analysis_role"])
            blocks[key].append(row)
    return blocks


def _is_confirmatory(version: str, key: tuple) -> bool:
    family = CONFIRMATORY[version]
    variant, analysis, _period, period_role, _role = key
    return (variant == family["fit_variant"]
            and analysis in family["analyses"]
            and period_role == family["period_role"])


def run_unblinding() -> dict:
    """Verify, read outcomes once, score everything, and report by family."""

    if OUTPUT_DIR.exists():
        raise UnblindingRefused(
            f"{OUTPUT_DIR} already exists. The unblinding happens once; "
            "these results are final."
        )
    integrity = verify_freeze_integrity()
    observed = load_observed()

    results = {"integrity": integrity, "files": {}}
    baseline_rows = [
        {**outcome,
         "baseline_prediction": outcome["baseline_predicted_share"]}
        for outcome in observed.values()
        # Score the baseline on the two principal 2026 elections only,
        # the same scope every frozen prediction file covers.
        if outcome["election_id"].startswith("surrey-county-council-2026")
    ]
    results["baseline_all_2026_rows"] = _metric_block(
        baseline_rows, "baseline_prediction")
    results["baseline_seat_accuracy"] = _seat_accuracy(
        baseline_rows, "baseline_predicted_elected")
    reform_baseline = [row for row in baseline_rows
                      if row["is_reform_uk"] == "True"]
    results["baseline_reform_rows"] = _metric_block(
        reform_baseline, "baseline_prediction")
    results["baseline_reform_seat_accuracy"] = _seat_accuracy(
        reform_baseline, "baseline_predicted_elected")

    for version, directory in (("v1", V1_DIR), ("v2", V2_DIR)):
        blocks = _load_predictions(directory)
        scored = []
        for key in sorted(blocks):
            confirmatory = _is_confirmatory(version, key)
            entry = {
                "fit_variant": key[0], "analysis": key[1], "period": key[2],
                "period_role": key[3], "analysis_role": key[4],
                "family": "confirmatory" if confirmatory else "sensitivity",
                "metrics": score_specification(
                    blocks[key], observed, with_bootstrap=confirmatory),
            }
            scored.append(entry)
        results["files"][version] = scored

    return results


def render_findings(results: dict) -> str:
    """Report both families in full. Counts and lists; no ranking."""

    def family_table(version: str) -> list[str]:
        rows = [e for e in results["files"][version]
                if e["family"] == "confirmatory"]
        lines = [
            "| analysis | window | baseline MAE | recalibrated MAE | "
            "news MAE | news vs recalibrated | 95% CI | Reform news MAE | "
            "Reform vs recalibrated |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
        ]
        for entry in rows:
            overall = entry["metrics"]["all_supported_parties"]
            reform = entry["metrics"]["reform_uk"]
            ci = entry["metrics"]["bootstrap_news_vs_recalibrated"]
            lines.append(
                f"| {entry['analysis']} | {entry['period']} | "
                f"{overall['baseline']['mae']:.4f} | "
                f"{overall['recalibrated_without_news']['mae']:.4f} | "
                f"{overall['news_enhanced']['mae']:.4f} | "
                f"{overall['news_vs_recalibrated_mae']:+.4f} | "
                f"[{ci.get('improvement_ci_lower', 0):+.4f}, "
                f"{ci.get('improvement_ci_upper', 0):+.4f}] | "
                f"{reform['news_enhanced']['mae']:.4f} | "
                f"{reform['news_vs_recalibrated_mae']:+.4f} |"
            )
        improved = sum(
            1 for entry in rows
            if entry["metrics"]["all_supported_parties"]
            ["news_vs_recalibrated_mae"] > 0)
        improved_raw = sum(
            1 for entry in rows
            if entry["metrics"]["all_supported_parties"]
            ["news_vs_raw_baseline_mae"] > 0)
        lines += [
            "",
            f"- **{improved} of {len(rows)}** confirmatory comparisons "
            "improve overall MAE over the recalibrated control; "
            f"**{improved_raw} of {len(rows)}** over the untouched baseline.",
        ]
        return lines

    def sensitivity_counts(version: str) -> str:
        rows = [e for e in results["files"][version]
                if e["family"] == "sensitivity"]
        improved = sum(
            1 for entry in rows
            if entry["metrics"]["all_supported_parties"]
            ["news_vs_recalibrated_mae"] > 0)
        return (f"{improved} of {len(rows)} sensitivity comparisons improve "
                "on their recalibrated control (full detail in "
                "unblinding_results.json; sensitivity results cannot be "
                "promoted).")

    baseline = results["baseline_all_2026_rows"]
    reform_baseline = results["baseline_reform_rows"]
    seats = results["baseline_seat_accuracy"]
    reform_seats = results["baseline_reform_seat_accuracy"]
    return "\n".join([
        "# The 2026 unblinding",
        "",
        "**One-time confirmatory comparison, performed on the frozen,",
        "hash-verified prediction files. Every specification is reported;",
        "nothing was selected after outcomes were seen.**",
        "",
        "## The untouched baseline on 2026",
        "",
        f"- Overall MAE {baseline['mae']:.4f} across {baseline['rows']} "
        f"candidate rows in {baseline['contests']} two-member wards; "
        f"seat-call accuracy {seats['accuracy']:.4f}.",
        f"- Reform UK: MAE {reform_baseline['mae']:.4f} over "
        f"{reform_baseline['rows']} rows; seat-call accuracy "
        f"{reform_seats['accuracy']:.4f}.",
        "",
        "## Confirmatory family - v1 primary (pooled 2017+2021)",
        "",
        *family_table("v1"),
        "",
        "## Confirmatory family - v2 enrichment (2017+2021+by-elections)",
        "",
        *family_table("v2"),
        "",
        "## Sensitivity families",
        "",
        f"- v1: {sensitivity_counts('v1')}",
        f"- v2: {sensitivity_counts('v2')}",
        "",
        "## Interpretation rule (pre-declared, reproduced verbatim in the",
        "frozen protocols)",
        "",
        "No specification, window, arm or variant may be selected or",
        "promoted because of these numbers. The confirmatory counts above,",
        "with their bootstrap intervals, are the project's answer to the",
        "supervisor's central question.",
        "",
    ])


def main() -> None:
    results = run_unblinding()
    OUTPUT_DIR.mkdir(parents=True)
    (OUTPUT_DIR / "unblinding_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")
    findings = render_findings(results)
    (OUTPUT_DIR / "unblinding_findings.md").write_text(
        findings, encoding="utf-8")
    print(findings)
    print(f"-> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
