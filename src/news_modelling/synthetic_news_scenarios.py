"""Synthetic what-if news scenarios against the frozen v2 model.

    PYTHONPATH=src .venv/bin/python -m news_modelling.synthetic_news_scenarios

The final stage of the research design: clearly-labelled hypothetical
news stories are injected into the 2026 feature cells and the frozen
enrichment model re-predicts the election, so the sensitivity of the
predictions to tone, timing, target party and collection arm can be
read off. **Every output of this module is a simulation of the fitted
model's behaviour and never a real-world claim** - the design says so
in terms, and the disclaimer is stamped into both output files.

What a scenario is, mechanically
--------------------------------
"Inject n articles about party P with tone T into window W through arm
A" changes exactly the numbers those articles would have changed had
they been collected: the window's article total rises by n, P's article
count rises by n, and P's favourable or unfavourable count rises by n
when the tone says so. Every party's share features are then recomputed
under the enlarged denominator - an injected story about Reform dilutes
everyone else's share of coverage, which is how shares work, not a
modelling choice. The frozen ridge specification for (A, W) turns the
perturbed features into per-candidate adjustments, contests are
renormalised exactly as in the freeze, and the report shows what moved:
mean share deltas per party and any seats that flip relative to the
unperturbed prediction.

Why the model is provably the frozen one
----------------------------------------
The specification is refitted here from the same inputs the v2 freeze
used - the fit is deterministic - and every standardised coefficient is
asserted equal to the value recorded in the frozen protocol before any
scenario runs. A drifted input or edited feature table fails loudly
rather than producing quietly different what-ifs.

What cannot be simulated, and why it is stated
----------------------------------------------
The design's issue axis ("a new story focused on crime") cannot flow
through this model: the frozen specifications carry volume and
portrayal only, because the issue-level features never cleared the
ten-cell reporting threshold. That boundary is recorded in the output
rather than approximated around.
"""

from __future__ import annotations

import json
from pathlib import Path

from news_modelling.blinded_2026_predictions import sanitise_holdout_rows
from news_modelling.blinded_2026_predictions_v2 import (
    aggregate_v2_residuals,
)
from news_modelling.production_news_experiment import (
    ProductionExperimentError,
    _feature_index,
    _read_csv,
)
from news_modelling.blinded_2026_predictions import (
    HOLDOUT_NEWS_ELECTION,
    predict_specification,
)
from news_modelling.blinded_2026_predictions_v2 import _fit_specification
from news_modelling.stage1_bundle import load_stage1_bundle

FEATURES = Path("news_features/news_feature_table_v2.csv")
V2_PROTOCOL = Path("news_features/blinded_2026_predictions_v2/frozen_protocol.json")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUTPUT_DIR = Path("news_features/synthetic_scenarios_v1")

DISCLAIMER = (
    "SYNTHETIC SIMULATION. These figures describe how the frozen model's "
    "predictions move when hypothetical, clearly-labelled news is injected "
    "into its inputs. They are simulations, not real-world claims, and no "
    "coefficient in the model is causal."
)

# Column names per arm: which feature pair a specification reads, and which
# count columns the injection must recompute.
ARM_COLUMNS = {
    "combined": {"share": "party_article_share",
                 "net": "net_portrayal_share",
                 "party_count": "party_article_count",
                 "favourable": "favourable_count",
                 "unfavourable": "unfavourable_count",
                 "total": "article_count",
                 "analysis": "combined_exploratory"},
    "national": {"share": "national_party_article_share",
                 "net": "national_net_portrayal_share",
                 "party_count": "national_party_article_count",
                 "favourable": "national_favourable_count",
                 "unfavourable": "national_unfavourable_count",
                 "total": "national_article_count",
                 "analysis": "national_exploratory"},
    "local": {"share": "local_party_article_share",
              "net": "local_net_portrayal_share",
              "party_count": "local_party_article_count",
              "favourable": "local_favourable_count",
              "unfavourable": "local_unfavourable_count",
              "total": "local_article_count",
              "analysis": "local_sensitivity"},
}

PARTIES = ("conservative", "labour", "liberal_democrat", "green",
           "ukip", "reform_uk")


def perturb_features(features: list[dict], *, party: str, window: str,
                     arm: str, articles: int, tone: str) -> list[dict]:
    """Return a copied feature table with the synthetic articles injected.

    Only the 2026 election's cells for the chosen window change. Counts
    move by exactly ``articles``; every party's share in that window is
    recomputed under the enlarged total, and the target party's net
    portrayal moves only when the tone is favourable or unfavourable -
    a neutral story adds volume without moving tone, which is the
    design's "same story, different tone" contrast in feature terms.
    """

    if tone not in ("favourable", "unfavourable", "neither"):
        raise ProductionExperimentError(f"unknown tone {tone!r}")
    columns = ARM_COLUMNS[arm]
    perturbed = [dict(row) for row in features]
    cells = {
        row["standard_party_key"]: row for row in perturbed
        if row["election_id"] == HOLDOUT_NEWS_ELECTION
        and row["period"] == window
    }
    if party not in cells:
        raise ProductionExperimentError(
            f"no 2026 cell for {party} in window {window}")

    old_total = int(cells[party][columns["total"]] or 0)
    new_total = old_total + articles

    target = cells[party]
    party_count = int(target[columns["party_count"]] or 0) + articles
    favourable = int(target[columns["favourable"]] or 0)
    unfavourable = int(target[columns["unfavourable"]] or 0)
    if tone == "favourable":
        favourable += articles
    elif tone == "unfavourable":
        unfavourable += articles
    target[columns["party_count"]] = str(party_count)
    target[columns["favourable"]] = str(favourable)
    target[columns["unfavourable"]] = str(unfavourable)
    target[columns["net"]] = (
        f"{(favourable - unfavourable) / party_count:.6f}"
        if party_count else "")

    # The denominator grew for everyone: recompute every party's share and
    # the stored total, leaving each non-target party's tone untouched.
    for cell in cells.values():
        cell[columns["total"]] = str(new_total)
        count = int(cell[columns["party_count"]] or 0)
        cell[columns["share"]] = (
            f"{count / new_total:.6f}" if new_total else "")
    return perturbed


def fit_frozen_specification(features: list[dict], *, arm: str, window: str):
    """Refit one (arm, window) specification and prove it is the frozen one."""

    protocol = json.loads(V2_PROTOCOL.read_text(encoding="utf-8"))
    columns = ARM_COLUMNS[arm]
    frozen_record = next(
        spec for spec in protocol["specifications"]
        if spec["analysis"] == columns["analysis"]
        and spec["period"] == window
    )
    bundle = load_stage1_bundle(BUNDLE)
    fitting_rows = aggregate_v2_residuals(
        [dict(row) for row in bundle.out_of_fold])
    model, fit_record = _fit_specification(
        fitting_rows, _feature_index(features),
        period=window,
        feature_columns=list(frozen_record["feature_columns"]),
    )
    for name, frozen_value in frozen_record["standardised_coefficients"].items():
        refit_value = fit_record["standardised_coefficients"][name]
        if abs(refit_value - frozen_value) > 1e-9:
            raise ProductionExperimentError(
                f"refit coefficient {name} = {refit_value} differs from the "
                f"frozen protocol's {frozen_value}; inputs have drifted and "
                "no scenario may run against an unfrozen model")
    return model, list(frozen_record["feature_columns"]), bundle


def run_scenario(features: list[dict], blinded: list[dict], model,
                 feature_columns: list[str], *, window: str,
                 scenario: dict) -> dict:
    """Predict unperturbed and perturbed, and report what moved."""

    reference, _ = predict_specification(
        blinded, _feature_index(features), model,
        period=window, feature_columns=feature_columns)
    perturbed_features = perturb_features(features, window=window, **scenario)
    perturbed, _ = predict_specification(
        blinded, _feature_index(perturbed_features), model,
        period=window, feature_columns=feature_columns)

    # The injection's size only means something relative to what the cell
    # already held: ten articles are a ripple on 300 and a flood on 10.
    # Recorded per scenario so no delta is read without its denominator.
    columns = ARM_COLUMNS[scenario["arm"]]
    cell = next(
        row for row in features
        if row["election_id"] == HOLDOUT_NEWS_ELECTION
        and row["period"] == window
        and row["standard_party_key"] == scenario["party"]
    )
    context = {
        "window_articles_before_injection": int(cell[columns["total"]] or 0),
        "party_articles_before_injection":
            int(cell[columns["party_count"]] or 0),
    }

    by_id = {row["candidate_contest_id"]: row for row in reference}
    deltas: dict[str, list[float]] = {}
    flips = []
    for row in perturbed:
        before = by_id[row["candidate_contest_id"]]
        party = row["party_key"] or "unsupported"
        deltas.setdefault(party, []).append(
            row["news_enhanced_prediction"]
            - before["news_enhanced_prediction"])
        if row["news_predicted_elected"] != before["news_predicted_elected"]:
            flips.append({
                "division_id": row["division_id"],
                "party": row["standard_party_name"],
                "now_elected": row["news_predicted_elected"],
            })
    return {
        "scenario": scenario, "window": window,
        "injection_context": context,
        "mean_share_delta_by_party": {
            party: round(sum(values) / len(values), 4)
            for party, values in sorted(deltas.items())
        },
        "seat_flips": flips,
        "seat_flip_count": len(flips),
    }


# The design's scenario axes, expressed as preset contrasts. Each preset
# is a list of scenarios whose results are meant to be read side by side.
PRESETS = {
    "tone: same Reform story, favourable vs unfavourable (30-15d, combined)": [
        {"party": "reform_uk", "arm": "combined", "articles": 10,
         "tone": "favourable", "window": "30_to_15_days"},
        {"party": "reform_uk", "arm": "combined", "articles": 10,
         "tone": "unfavourable", "window": "30_to_15_days"},
    ],
    "timing: unfavourable Reform story, a month out vs the final 72 hours": [
        {"party": "reform_uk", "arm": "combined", "articles": 10,
         "tone": "unfavourable", "window": "30_to_15_days"},
        {"party": "reform_uk", "arm": "combined", "articles": 10,
         "tone": "unfavourable", "window": "final_72_hours"},
    ],
    "target: the same unfavourable story about Reform vs the Conservatives": [
        {"party": "reform_uk", "arm": "combined", "articles": 10,
         "tone": "unfavourable", "window": "90_to_31_days"},
        {"party": "conservative", "arm": "combined", "articles": 10,
         "tone": "unfavourable", "window": "90_to_31_days"},
    ],
    "arm: one favourable Reform story via national vs local collection": [
        {"party": "reform_uk", "arm": "national", "articles": 10,
         "tone": "favourable", "window": "90_to_31_days"},
        {"party": "reform_uk", "arm": "local", "articles": 10,
         "tone": "favourable", "window": "90_to_31_days"},
    ],
}


def main() -> None:
    features = _read_csv(FEATURES)
    results = {"disclaimer": DISCLAIMER, "presets": {}}
    blinded_cache: dict = {}

    for label, scenarios in PRESETS.items():
        entries = []
        for scenario in scenarios:
            window = scenario.pop("window")
            arm = scenario["arm"]
            model, columns, bundle = fit_frozen_specification(
                features, arm=arm, window=window)
            if "rows" not in blinded_cache:
                blinded_cache["rows"] = sanitise_holdout_rows(
                    [dict(row) for row in bundle.holdout])
            entries.append(run_scenario(
                features, blinded_cache["rows"], model, columns,
                window=window, scenario=scenario))
        results["presets"][label] = entries

    results["not_simulatable"] = (
        "The issue axis (e.g. a crime-focused story) cannot flow through "
        "the frozen specifications: they carry volume and portrayal "
        "features only, because issue-level features never cleared the "
        "ten-cell reporting threshold. Recorded as a boundary, not "
        "approximated around."
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "scenario_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Synthetic news scenarios (frozen v2 model)", "",
        f"**{DISCLAIMER}**", "",
    ]
    for label, entries in results["presets"].items():
        lines += [f"## {label}", ""]
        for entry in entries:
            scenario = entry["scenario"]
            reform = entry["mean_share_delta_by_party"].get("reform_uk", 0.0)
            context = entry["injection_context"]
            lines += [
                f"- {scenario['articles']} {scenario['tone']} articles about "
                f"`{scenario['party']}` via the {scenario['arm']} arm, "
                f"window `{entry['window']}` (cell held "
                f"{context['window_articles_before_injection']} articles, "
                f"{context['party_articles_before_injection']} naming the "
                f"party, before injection): Reform mean share moves "
                f"{reform:+.3f} points, {entry['seat_flip_count']} seat "
                f"call(s) change. Full per-party deltas in the JSON.",
            ]
        lines.append("")
    lines += [
        "## Reading the magnitudes", "",
        "A delta is only meaningful against the cell size printed beside "
        "it: the same ten articles are a small perturbation of a "
        "well-covered window and a doubling of a thin one. The local-arm "
        "scenario in particular injects into a near-empty cell under a "
        "sensitivity-only specification, so its large response measures "
        "the fragility of thin local coverage, not the power of one "
        "story.", "",
    ]
    lines += ["## Boundary", "", results["not_simulatable"], ""]
    (OUTPUT_DIR / "scenario_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"-> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
