"""Predict the Haslemere by-election with the frozen v2 specifications.

    PYTHONPATH=src .venv/bin/python -m news_modelling.haslemere_probe_prediction

The probe's final stage, and the only new arithmetic in it is scoring.
Everything that decides a number is frozen code reused whole:

- each of the twelve confirmatory specifications is refitted with
  ``fit_frozen_specification``, which re-asserts every coefficient
  against the frozen v2 protocol before anything is predicted - the
  same guard the scenario tool and the app use, so a drifted model
  cannot serve silently;
- the per-candidate application - supported parties adjusted, contest
  clipping and renormalisation - is ``predict_specification`` itself,
  pointed at the probe election by rebinding the module's
  ``HOLDOUT_NEWS_ELECTION`` inside a try/finally;
- the baseline rows are the Stage 1 bundle's own
  ``secondary_holdout_haslemere_before_may`` predictions (no 7 May
  information, the same information regime the news models were frozen
  under), passed through ``sanitise_holdout_rows`` so the prediction
  path never sees an outcome column. Observed shares are joined only
  afterwards, for scoring.

Reference points, from the committed bundle metrics: before-May
baseline contest MAE 4.4738 with Reform over-predicted +8.95;
after-May retraining 7.3169 with Reform +14.63; both call the Liberal
Democrat winner. The probe asks where the news adjustments move the
before-May baseline - toward the observed result (ward-level signal
exists in the 20-article corpus) or away from it.

EXPLORATORY, post-unblinding, single contest, four candidates. Nothing
here joins the confirmatory verdict; the output says so.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from news_modelling import blinded_2026_predictions as frozen_predict
from news_modelling.exploratory_decompositions import confirmatory_windows
from news_modelling.production_news_experiment import (
    _feature_index,
    _read_csv,
)
from news_modelling.synthetic_news_scenarios import fit_frozen_specification

HASLEMERE = "surrey-county-council-by-election-haslemere-2026-07-07"
V2_FEATURES = Path("news_features/news_feature_table_v2.csv")
PROBE_FEATURES = Path(
    "news_features/haslemere_probe/news_feature_table_haslemere.csv")
AUDIT = Path("news_features/production_estimability_v1/estimability_report.json")
HOLDOUT = Path(
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "holdout_predictions.csv")
OUT_DIR = Path("news_features/haslemere_probe")

STATUS = ("EXPLORATORY, post-unblinding, pre-declared Haslemere case study: "
          "one contest, four candidates. Nothing here joins the "
          "confirmatory verdict.")

ARM_OF = {"combined_exploratory": "combined", "national_exploratory": "national"}


def load_haslemere_baseline() -> tuple[list[dict], dict[str, dict]]:
    """The before-May baseline rows, and the observed outcomes kept apart.

    ``sanitise_holdout_rows`` strips every outcome column from what the
    prediction path sees; the observed map is returned separately and
    only ever touched by the scorer.
    """

    with HOLDOUT.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle)
                if row["split_id"] == "secondary_holdout_haslemere_before_may"]
    assert len(rows) == 4, f"expected 4 Haslemere rows, got {len(rows)}"
    assert all(row["election_id"] == HASLEMERE for row in rows)
    observed = {
        row["candidate_contest_id"]: {
            "party": row["standard_party_name"],
            "observed_share": float(row["observed_vote_share"]),
            "observed_elected": row["observed_elected"] == "True",
        }
        for row in rows
    }
    # ``sanitise_holdout_rows`` is scoped to the 2026 principal election
    # by design; its blinding step is the reusable part. The probe applies
    # the same frozen strip list with its own row assertions above.
    return frozen_predict.strip_outcome_columns(
        [dict(r) for r in rows]), observed


def score(predictions: list[dict], observed: dict) -> dict:
    """Contest MAE, per-party signed error and the winner call, per column."""

    def one(column: str) -> dict:
        errors, per_party = [], {}
        top_prediction, top_party = -1.0, None
        for row in predictions:
            actual = observed[row["candidate_contest_id"]]
            error = row[column] - actual["observed_share"]
            errors.append(abs(error))
            per_party[row["party_key"]] = round(error, 3)
            if row[column] > top_prediction:
                top_prediction, top_party = row[column], actual["party"]
        winner_observed = next(v["party"] for v in observed.values()
                               if v["observed_elected"])
        return {
            "contest_mae": round(sum(errors) / len(errors), 4),
            "signed_error_by_party": per_party,
            "predicted_winner": top_party,
            "winner_correct": top_party == winner_observed,
        }

    return {"news": one("news_enhanced_prediction"),
            "recalibrated": one("recalibrated_prediction"),
            "baseline": one("baseline_prediction")}


def main() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    fitting_features = _read_csv(V2_FEATURES)
    probe_index = _feature_index(_read_csv(PROBE_FEATURES))
    blinded, observed = load_haslemere_baseline()

    results = []
    saved_election = frozen_predict.HOLDOUT_NEWS_ELECTION
    try:
        # The frozen applier looks features up under this module global;
        # for the probe the "holdout election" is the Haslemere contest.
        frozen_predict.HOLDOUT_NEWS_ELECTION = HASLEMERE
        for analysis, window, columns in confirmatory_windows(audit):
            model, fit_columns, _bundle = fit_frozen_specification(
                fitting_features, arm=ARM_OF[analysis], window=window)
            assert fit_columns == columns, (analysis, window)
            predictions, clipped = frozen_predict.predict_specification(
                blinded, probe_index, model,
                period=window, feature_columns=columns)
            entry = {
                "analysis": analysis, "window": window,
                **score(predictions, observed),
                "clipped_rows": clipped,
                "news_adjustment_by_party": {
                    row["party_key"]: round(row["news_adjustment"], 3)
                    for row in predictions
                },
            }
            results.append(entry)
    finally:
        frozen_predict.HOLDOUT_NEWS_ELECTION = saved_election

    payload = {
        "status": STATUS,
        "election": HASLEMERE,
        "reference": {
            "before_may_baseline_mae": 4.4738,
            "after_may_baseline_mae": 7.3169,
            "reform_before_may_signed_error": 8.948,
            "reform_after_may_signed_error": 14.634,
        },
        "corpus": {"articles": 20, "all_local_arm": True,
                   "articles_naming_a_study_party": 3},
        "specifications": results,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "probe_result.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# The Haslemere probe: frozen v2 predictions on the 7 July contest",
        "", f"**{STATUS}**", "",
        "Reference: before-May baseline contest MAE 4.4738 (Reform signed "
        "error +8.95), after-May 7.3169 (Reform +14.63); both call the "
        "Liberal Democrat winner. Corpus: 20 articles, all local-arm, 3 "
        "naming any study party.", "",
        "| analysis | window | news MAE | recal MAE | baseline MAE | "
        "news Reform error | news winner ok |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for entry in results:
        news, recal, base = (entry["news"], entry["recalibrated"],
                             entry["baseline"])
        lines.append(
            f"| {entry['analysis']} | {entry['window']} | "
            f"{news['contest_mae']:.3f} | {recal['contest_mae']:.3f} | "
            f"{base['contest_mae']:.3f} | "
            f"{news['signed_error_by_party'].get('reform_uk', 0):+.2f} | "
            f"{'yes' if news['winner_correct'] else 'NO'} |")
    improved = sum(
        1 for entry in results
        if entry["news"]["contest_mae"] < entry["recalibrated"]["contest_mae"])
    reform_better = sum(
        1 for entry in results
        if abs(entry["news"]["signed_error_by_party"].get("reform_uk", 99.0))
        < 8.948)
    lines += [
        "",
        f"News beat its recalibrated control in **{improved} of "
        f"{len(results)}** specifications; the news Reform error was "
        f"smaller than the baseline's +8.95 in **{reform_better} of "
        f"{len(results)}**.", "",
    ]
    (OUT_DIR / "probe_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"-> {OUT_DIR}")


if __name__ == "__main__":
    main()
