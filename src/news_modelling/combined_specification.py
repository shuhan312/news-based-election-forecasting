"""Does within-party tone survive party identity AND volume in one fit?

    PYTHONPATH=src .venv/bin/python -m news_modelling.combined_specification

## Why this run exists

The identity decomposition left one cell of its factorial unfitted: party
identity, news volume and the within-party tone centre in the SAME
specification. Whether the tone deviation still adds out-of-sample value
once both of the things it might be a proxy for are already in the model is
the question the within-party reading rests on, so it is fitted directly
rather than inferred from the pairwise cells.

`identity_placebos` built every pairwise cell of that factorial but not the
full one:

- ``placebo_party_dummies``          - identity alone
- ``party_dummies_plus_share``       - identity + volume
- ``party_dummies_plus_tone_within`` - identity + tone deviation
- ``tone_within_party``              - volume + tone deviation, no identity

This module adds the missing corner - all three at once - and reports the
marginal value of the tone deviation as a PAIRED comparison against the
nested arms, not just as another delta against the recalibrated control.
Two arms scored on the same 81 contests share their sampling noise, so the
honest interval on "what does tone add on top of identity and volume" comes
from resampling contests once and scoring both arms on each draw.

## Gates

1. The frozen specification must reproduce its committed confirmatory
   deltas (same gate as `placebo_specifications` and `identity_placebos`).
2. The four nested comparator arms, re-run here on the rebuilt derived
   index, must reproduce the deltas committed in
   ``identity_placebos_v1/identity_placebo_results.json``. If the derived
   columns are not byte-equivalent to the committed run, nothing the full
   arm does can be attributed to the specification rather than the drift.

EXPLORATORY, post-unblinding, downstream of section 16. Promotes nothing.
The derived columns obey the committed leakage discipline: tone centres are
estimated on the 45 fitting cells only (`build_derived_index` is imported
unchanged, not re-implemented).
"""

from __future__ import annotations

import json
from pathlib import Path

from news_modelling.blinded_2026_predictions import (
    predict_specification,
    sanitise_holdout_rows,
)
from news_modelling.blinded_2026_predictions_v2 import (
    _fit_specification,
    aggregate_v2_residuals,
)
from news_modelling.identity_placebos import (
    ARMS as IDENTITY_ARMS,
    DUMMY_COLUMNS,
    build_derived_index,
)
from news_modelling.news_estimator import bootstrap_improvement
from news_modelling.placebo_specifications import (
    FROZEN,
    WINDOWS,
    committed_deltas,
    run_arm,
)
from news_modelling.production_news_experiment import _feature_index, _read_csv
from news_modelling.stage1_bundle import load_stage1_bundle
from news_modelling.unblind_2026 import load_observed

FEATURES = Path("news_features/news_feature_table_v3party.csv")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
IDENTITY_RESULTS = Path(
    "news_features/identity_placebos_v1/identity_placebo_results.json")
OUT_DIR = Path("news_features/combined_specification_v1")

FULL_ARM = "party_dummies_plus_volume_and_tone_within"
FULL_COLUMNS = DUMMY_COLUMNS + ["party_article_share",
                                "net_portrayal_share_within"]

# The nested arms the full specification is measured against. Every one is
# a strict column-subset of FULL_COLUMNS, so each paired contrast isolates
# exactly the columns the comparator lacks.
COMPARATORS = (
    "placebo_party_dummies",
    "party_dummies_plus_share",
    "party_dummies_plus_tone_within",
    "tone_within_party",
)

STATUS = ("EXPLORATORY combined specification, post-unblinding. The final "
          "cell of the identity factorial: party identity, volume and "
          "within-party tone in one fit, on the 45 frozen fitting cells "
          "and the frozen prediction and scoring code. Promotes nothing.")


def supported_absolute_errors(columns, cells, feature_index, blinded,
                              observed, window):
    """Per-candidate absolute error of one arm, keyed for pairing.

    Uses the same fit and predict calls as `run_arm`, so an arm's error rows
    here and its delta there come from identical predictions. Restricted to
    the supported-party rows every reported metric uses.
    """
    model, _record = _fit_specification(
        cells, feature_index, period=window, feature_columns=columns)
    predictions, _clipped = predict_specification(
        blinded, feature_index, model, period=window, feature_columns=columns)
    errors = {}
    for row in predictions:
        if row["party_key"] is None:
            continue
        outcome = observed[row["candidate_contest_id"]]
        errors[row["candidate_contest_id"]] = {
            "election_id": outcome["election_id"],
            "area_id": outcome["division_id"],
            "absolute_error": abs(float(row["news_enhanced_prediction"])
                                  - outcome["observed_vote_share"]),
        }
    return errors


def paired_contrast(comparator_errors, full_errors):
    """Contest-level paired bootstrap: comparator MAE minus full MAE.

    Positive means the full specification is better. Reuses the frozen
    bootstrap (same resampler, same seed): each draw picks contests once
    and scores both arms on that draw, so the interval is on the
    difference, not on two overlapping marginals.
    """
    rows = [
        {
            "election_id": entry["election_id"],
            "area_id": entry["area_id"],
            "baseline_absolute_error": entry["absolute_error"],
            "news_absolute_error": full_errors[key]["absolute_error"],
        }
        for key, entry in comparator_errors.items()
    ]
    point = (sum(e["baseline_absolute_error"] for e in rows)
             - sum(e["news_absolute_error"] for e in rows)) / len(rows)
    interval = bootstrap_improvement(rows)
    return {
        "rows": len(rows),
        "full_minus_comparator_mae_gain": point,
        "ci_lower": interval.get("improvement_ci_lower"),
        "ci_upper": interval.get("improvement_ci_upper"),
        "proportion_of_draws_favouring_full":
            interval.get("proportion_of_draws_favouring_news"),
    }


def committed_identity_deltas() -> dict[str, dict[str, float]]:
    """The comparator deltas this run must reproduce, per arm per window."""
    payload = json.loads(IDENTITY_RESULTS.read_text(encoding="utf-8"))
    return {
        name: {record["window"]: record["delta_vs_recalibrated"]
               for record in payload["arms"][name]}
        for name in COMPARATORS
    }


def main() -> None:
    features = _read_csv(FEATURES)
    frozen_index = _feature_index(features)
    bundle = load_stage1_bundle(BUNDLE)
    cells = aggregate_v2_residuals([dict(r) for r in bundle.out_of_fold])
    blinded = sanitise_holdout_rows([dict(r) for r in bundle.holdout])
    observed = load_observed()

    # --- gate 1: the frozen specification ------------------------------
    frozen = [run_arm(FROZEN, cells, frozen_index, blinded, observed, w)
              for w in WINDOWS]
    reference = committed_deltas()
    mismatches = [
        (r["window"], round(r["delta_vs_recalibrated"], 3),
         reference[r["window"]])
        for r in frozen
        if abs(round(r["delta_vs_recalibrated"], 3)
               - reference[r["window"]]) > 1e-9
    ]
    if mismatches:
        raise RuntimeError(
            "the frozen specification did not reproduce its committed "
            f"deltas, so nothing else in this run is trustworthy: {mismatches}")

    derived_index, _tone_mean = build_derived_index(features, cells)

    # --- gate 2: the committed comparator arms -------------------------
    committed = committed_identity_deltas()
    arms = {"frozen": frozen}
    comparator_drift = 0.0
    for name in COMPARATORS:
        arms[name] = [run_arm(IDENTITY_ARMS[name], cells, derived_index,
                              blinded, observed, w) for w in WINDOWS]
        for record in arms[name]:
            drift = abs(record["delta_vs_recalibrated"]
                        - committed[name][record["window"]])
            comparator_drift = max(comparator_drift, drift)
    if comparator_drift > 1e-6:
        raise RuntimeError(
            "the rebuilt derived index does not reproduce the committed "
            f"identity-placebo deltas (max drift {comparator_drift}); the "
            "full arm would be fitted on different columns than the ones "
            "already reported")

    # --- the missing corner of the factorial ---------------------------
    arms[FULL_ARM] = [run_arm(FULL_COLUMNS, cells, derived_index, blinded,
                              observed, w) for w in WINDOWS]

    # --- paired marginals, per window ----------------------------------
    marginals: dict[str, dict[str, dict]] = {}
    for window in WINDOWS:
        full_errors = supported_absolute_errors(
            FULL_COLUMNS, cells, derived_index, blinded, observed, window)
        marginals[window] = {}
        for name in COMPARATORS:
            comparator_errors = supported_absolute_errors(
                IDENTITY_ARMS[name], cells, derived_index, blinded,
                observed, window)
            marginals[window][f"vs_{name}"] = paired_contrast(
                comparator_errors, full_errors)

    payload = {
        "status": STATUS,
        "feature_table": str(FEATURES),
        "fitting_cells": len(cells),
        "full_arm_columns": FULL_COLUMNS,
        "reproduction_check": {
            "frozen_max_absolute_difference": max(
                abs(round(r["delta_vs_recalibrated"], 3)
                    - reference[r["window"]]) for r in frozen),
            "comparator_max_absolute_drift": comparator_drift,
        },
        "arms": arms,
        "paired_marginals": marginals,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "combined_specification_results.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_findings(payload)
    print(f"-> {OUT_DIR}")


def write_findings(payload: dict) -> None:
    arms = payload["arms"]
    headline = "90_to_31_days"

    def entry(name, window):
        for record in arms[name]:
            if record["window"] == window:
                return record
        return None

    def cell(name, window):
        record = entry(name, window)
        if record is None:
            return "-"
        return f"{record['delta_vs_recalibrated']:+.4f}"

    lines = [
        "# Party identity, volume and within-party tone in one specification",
        "",
        f"**{payload['status']}**",
        "",
        "Delta is the change in election-wide MAE against the recalibrated "
        "control; positive is better. Every arm shares the "
        f"{payload['fitting_cells']} frozen fitting cells and the frozen "
        "prediction and scoring code; only `feature_columns` differs.",
        "",
        "## Reproduction gates",
        "",
        "The frozen specification reproduces its committed deltas to "
        f"**{payload['reproduction_check']['frozen_max_absolute_difference']:.4f}**; "
        "the four nested comparator arms reproduce their committed "
        "identity-placebo deltas to a maximum drift of "
        f"**{payload['reproduction_check']['comparator_max_absolute_drift']:.1e}**. "
        "The run aborts if either gate fails.",
        "",
        "## The factorial, every window",
        "",
        "| arm | " + " | ".join(w.replace("_", "-") for w in WINDOWS) + " |",
        "| --- | " + " | ".join("---:" for _ in WINDOWS) + " |",
    ]
    for name in ["frozen", *COMPARATORS, FULL_ARM]:
        lines.append(f"| {name} | "
                     + " | ".join(cell(name, w) for w in WINDOWS) + " |")

    full_headline = entry(FULL_ARM, headline)
    lines += [
        "",
        f"## The headline window, {headline}",
        "",
        f"The full specification scores "
        f"**{full_headline['delta_vs_recalibrated']:+.4f}** "
        f"[{full_headline['ci_lower']:+.4f}, {full_headline['ci_upper']:+.4f}] "
        "against the recalibrated control.",
        "",
        "## What each ingredient adds, paired per window",
        "",
        "Each contrast resamples the same 81 contests once per draw and "
        "scores both arms on that draw; positive means the full "
        "specification beats the nested one. `vs_party_dummies_plus_share` "
        "is the decisive contrast: what the tone deviation adds once "
        "identity and volume are both known.",
        "",
        "| window | vs identity alone | vs identity+volume (tone's marginal) "
        "| vs identity+tone (volume's marginal) | vs volume+tone "
        "(identity's marginal) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]

    def contrast_cell(window, name):
        record = payload["paired_marginals"][window][f"vs_{name}"]
        return (f"{record['full_minus_comparator_mae_gain']:+.4f} "
                f"[{record['ci_lower']:+.4f}, {record['ci_upper']:+.4f}]")

    for window in WINDOWS:
        lines.append(
            f"| {window.replace('_', '-')} | "
            + contrast_cell(window, "placebo_party_dummies") + " | "
            + contrast_cell(window, "party_dummies_plus_share") + " | "
            + contrast_cell(window, "party_dummies_plus_tone_within") + " | "
            + contrast_cell(window, "tone_within_party") + " |")

    lines += [
        "",
        "## Coefficients of the full arm",
        "",
        "| window | coefficients |",
        "| --- | --- |",
    ]
    for record in arms[FULL_ARM]:
        coefficients = ", ".join(
            f"{k} {v:+.3f}" for k, v in record["coefficients"].items())
        lines.append(f"| {record['window']} | {coefficients} |")

    lines.append("")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "combined_specification_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
