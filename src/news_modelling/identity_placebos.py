"""Is the news layer anything more than the party's name?

    PYTHONPATH=src .venv/bin/python -m news_modelling.identity_placebos

## The question this asks, and why it is not the one `placebo_specifications` asked

`placebo_specifications` asked whether the LLM's *content* layers beat
counting articles.  They did not, clearly enough.  That left the two
features which actually are in the frozen specification - volume and tone -
still credited with the certified +0.2404 at 90-31 days.

This module asks whether those two features carry any information beyond
**which party the row is about**.  The reason to suspect they do not is
measurable in the fitting cells themselves: decomposing the variance of
``net_portrayal_share`` across the 19 covered cells splits it 64.3 per cent
between parties against 35.7 per cent within a party across elections at
90-31 days, and 86.3 / 13.7 at 180-91 days.  Conservative's tone over three
elections is -0.714, -0.800, -0.818; Reform's is -0.600, -0.680, -0.900.
A number that barely moves for a given party is a party label, not a
measurement of an election.

The fitted model has no party term, so nothing stops the tone coefficient
from absorbing that label.  If it does, the layer's whole observable
behaviour - push Reform down on both islands, which rescues a 2021 baseline
that over-predicts Reform by 12.21 points and damages a 2026 baseline that
under-predicts it by 1.33 - follows from party identity alone and needs no
news at all.

## The arms

Identity arms, none of which reads a single article:

- ``placebo_party_dummies`` - six party indicators, nothing else.
- ``placebo_reform_dummy`` - one indicator, Reform or not.
- ``placebo_prior_vote_share`` - the party's mean vote share at the
  immediately preceding county-wide election.  This is the supervisor's
  named test.  Every value is strictly prior to the election it is used
  for, so no arm reads its own outcome.

Decomposition arms, which keep the news features but remove what identity
can explain:

- ``tone_within_party`` - ``party_article_share`` plus tone measured as a
  deviation from that party's own mean, so only the 14-36 per cent that
  moves between elections survives.
- ``tone_within_party_only`` - that deviation alone.
- ``frozen_plus_party_dummies`` - the frozen pair *and* the six indicators.
  Its delta against ``placebo_party_dummies`` is what the news features add
  once identity is already in the model, which is the marginal quantity the
  research question actually asks about.

## Leakage discipline

Every parameter that turns a raw column into a derived one - the per-party
tone mean, the prior-election shares - is computed from the 45 fitting
cells only and then applied unchanged to the 2026 rows.  The holdout
contributes nothing to any feature's definition.  ``ESWS-2026-05``'s prior
shares come from 2021, which is a fitting election, not from 2026.

EXPLORATORY, post-unblinding, like everything downstream of section 16.
This module cannot promote or revise a confirmatory verdict.  What it can
do is say whether the certified number survives being told the party's
name.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from news_modelling.blinded_2026_predictions import (
    HOLDOUT_NEWS_ELECTION,
    sanitise_holdout_rows,
)
from news_modelling.blinded_2026_predictions_v2 import aggregate_v2_residuals
from news_modelling.placebo_specifications import (
    FROZEN,
    WINDOWS,
    committed_deltas,
    run_arm,
)
from news_modelling.production_news_experiment import (
    _feature_index,
    _read_csv,
    party_key,
)
from news_modelling.stage1_bundle import load_stage1_bundle
from news_modelling.unblind_2026 import load_observed

FEATURES = Path("news_features/news_feature_table_v3party.csv")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
RESULTS_2013 = Path("data/elections/2013_scc_results.csv")
OUT_DIR = Path("news_features/identity_placebos_v1")

PARTIES = ("conservative", "green", "labour", "liberal_democrat",
           "reform_uk", "ukip")

# Which election supplies each fitting cell's prior vote share.  Every value
# is strictly earlier than the election it feeds, including the holdout's,
# whose prior is 2021 rather than anything from 2026.
PRIOR_ELECTION = {
    "SCC-2017-05": "SCC-2013-05",
    "SCC-2021-05": "surrey-county-council-2017",
    "surrey-county-council-by-election-weybridge-2015-05-07": "SCC-2013-05",
    "surrey-county-council-by-election-warlingham-2019-01-31":
        "surrey-county-council-2017",
    "surrey-county-council-by-election-addlestone-2025-08-21":
        "surrey-county-council-2021",
    "surrey-county-council-by-election-camberley-west-2025-10-16":
        "surrey-county-council-2021",
    "surrey-county-council-by-election-caterham-valley-2025-10-16":
        "surrey-county-council-2021",
    "surrey-county-council-by-election-guildford-south-east-2025-10-16":
        "surrey-county-council-2021",
    "surrey-county-council-by-election-hinchley-wood-claygate-oxshott-2025-08-21":
        "surrey-county-council-2021",
    "surrey-county-council-by-election-nork-tattenhams-2025-05-01":
        "surrey-county-council-2021",
    HOLDOUT_NEWS_ELECTION: "surrey-county-council-2021",
}

DUMMY_COLUMNS = [f"party_is_{name}" for name in PARTIES]

ARMS = {
    "placebo_party_dummies": DUMMY_COLUMNS,
    "placebo_reform_dummy": ["party_is_reform_uk"],
    "placebo_prior_vote_share": ["prior_party_vote_share"],
    "tone_within_party": ["party_article_share",
                          "net_portrayal_share_within"],
    "tone_within_party_only": ["net_portrayal_share_within"],
    "frozen_plus_party_dummies": FROZEN + DUMMY_COLUMNS,
    # The two marginal cells. `frozen_plus_party_dummies` minus
    # `placebo_party_dummies` says what the frozen pair adds once identity
    # is already known; these two say the same thing for each half of the
    # news layer separately, so a null in the pair cannot hide one half
    # helping while the other hurts.
    "party_dummies_plus_share": DUMMY_COLUMNS + ["party_article_share"],
    "party_dummies_plus_tone_within": DUMMY_COLUMNS
    + ["net_portrayal_share_within"],
    # The two content features whose raw association with the target
    # survives the 19 covered cells (r = +0.557 and +0.346 against a noise
    # scale of 0.250). Both were already reported by
    # `placebo_specifications`; what is new here is asking whether either
    # says anything a party indicator does not already say. A content
    # feature that fails this is a third identity proxy, however good its
    # correlation looked.
    "party_dummies_plus_incumbent_judgement": DUMMY_COLUMNS
    + ["party_frame_incumbent_judgement_share"],
    "party_dummies_plus_immigration": DUMMY_COLUMNS
    + ["party_issue_immigration_share"],
    # The trajectory arms. Every feature above is a LEVEL - one number
    # describing a party's coverage in a window - and a level is what a party
    # indicator reproduces best. `tone_trajectory` is instead the slope of a
    # party's tone across the six windows of one election: whether coverage
    # hardened or softened as polling day approached. A party indicator gives
    # a party one number for all time, so it cannot express that Conservative
    # coverage softened through 2017 (-0.70 to -0.33) and hardened through
    # 2021 (-0.80 to -0.88). Measured on the fitting cells the slope is 51.6
    # per cent within-party across elections against 35.7 per cent for the
    # tone level, so it is the most identity-orthogonal quantity in the
    # project - which is the necessary condition, not the sufficient one.
    "tone_trajectory_only": ["tone_trajectory"],
    "party_dummies_plus_trajectory": DUMMY_COLUMNS + ["tone_trajectory"],
    "party_dummies_plus_trajectory_and_level": DUMMY_COLUMNS
    + ["tone_trajectory", "net_portrayal_share"],
}

# Window midpoints in days before polling day. Used only to place the six
# windows on a time axis so a slope means "tone change per 100 days closer to
# the vote"; nothing about an outcome enters.
WINDOW_MIDPOINTS = {
    "180_to_91_days": 135.5, "90_to_31_days": 60.5, "30_to_15_days": 22.5,
    "14_to_8_days": 11.0, "7_to_4_days": 5.5, "final_72_hours": 1.5,
}

STATUS = ("EXPLORATORY identity placebo, post-unblinding. Every arm shares "
          "the 45 frozen fitting cells and the frozen prediction and scoring "
          "code; only `feature_columns` differs. Promotes nothing.")


def prior_vote_shares(oof_rows: list[dict]) -> dict[tuple[str, str], float]:
    """Mean observed vote share per (source election, party).

    Reads 2017 and 2021 from the Stage 1 out-of-fold file and 2013 from the
    committed results table, because 2013 predates the baseline's own
    training window and so has no out-of-fold row.  A party that did not
    stand in the source election gets 0.0 rather than a blank: it is the
    honest encoding of "took no votes there", and every arm here is a
    placebo whose whole point is to be dumb.
    """

    shares: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in oof_rows:
        key = party_key(row.get("standard_party_name"))
        if key is None:
            continue
        shares[(row["election_id"], key)].append(
            float(row["observed_vote_share"]))

    for row in _read_csv(RESULTS_2013):
        key = party_key(row.get("party_canonical"))
        value = str(row.get("candidate_vote_share", "")).strip()
        if key is None or value == "":
            continue
        shares[("SCC-2013-05", key)].append(float(value))

    return {key: sum(values) / len(values)
            for key, values in shares.items()}


def build_derived_index(features: list[dict], cells: list[dict]) -> dict:
    """Add the identity columns to a copy of the frozen feature index.

    The frozen columns are untouched, so the reproduction gate still runs
    against exactly the table the committed result used.  Both derived
    quantities that need an estimate - the per-party tone mean - take it
    from the fitting cells alone.
    """

    index = {key: dict(row) for key, row in _feature_index(features).items()}
    priors = prior_vote_shares(
        [dict(r) for r in load_stage1_bundle(BUNDLE).out_of_fold])

    # Per-party mean tone, per window, over fitting cells that actually
    # carry coverage.  Cells with no articles are excluded from the mean:
    # a structural zero is "no evidence", not "perfectly neutral coverage",
    # and averaging it in would drag every party's centre towards zero in
    # proportion to how badly covered it is.
    fitting_keys = {(cell["news_election_id"], cell["party_key"])
                    for cell in cells}
    tone_mean: dict[tuple[str, str], float] = {}
    for window in WINDOWS:
        by_party: dict[str, list[float]] = defaultdict(list)
        for election, party in fitting_keys:
            row = index.get((election, party, window))
            if row is None:
                continue
            count = str(row.get("party_article_count", "")).strip()
            if count == "" or float(count) == 0:
                continue
            tone = str(row.get("net_portrayal_share", "")).strip()
            if tone == "":
                continue
            by_party[party].append(float(tone))
        for party, values in by_party.items():
            tone_mean[(party, window)] = sum(values) / len(values)

    for (election, party, window), row in index.items():
        for name in PARTIES:
            row[f"party_is_{name}"] = "1" if party == name else "0"

        count = str(row.get("party_article_count", "")).strip()
        tone = str(row.get("net_portrayal_share", "")).strip()
        if count in ("", "0") or float(count) == 0 or tone == "":
            # No coverage means no evidence of deviation, so the centred
            # feature is zero rather than minus the party's mean - which
            # would otherwise turn "we know nothing" into a confident
            # statement that this election was unusually favourable.
            row["net_portrayal_share_within"] = "0"
        else:
            centre = tone_mean.get((party, window), 0.0)
            row["net_portrayal_share_within"] = repr(float(tone) - centre)

        source = PRIOR_ELECTION.get(election)
        row["prior_party_vote_share"] = (
            repr(priors.get((source, party), 0.0)) if source else "0")

    # The trajectory is one number per (election, party), identical in every
    # window, because it describes the shape of the whole campaign rather than
    # a moment in it. Computed after the loop above so it can read across the
    # window rows it needs.
    trajectories = tone_trajectories(index)
    for (election, party, _window), row in index.items():
        row["tone_trajectory"] = repr(trajectories.get((election, party), 0.0))

    return index, tone_mean


def tone_trajectories(index: dict) -> dict[tuple[str, str], float]:
    """Slope of tone against time-to-poll, per (election, party).

    Positive means coverage softened as polling day approached; negative
    means it hardened. Windows with no coverage are skipped rather than read
    as neutral - a zero there is "no articles", and treating it as a tone of
    zero would manufacture a swing towards neutrality in exactly the cells
    where the corpus is thinnest.

    A cell with fewer than two covered windows has no slope and gets 0.0.
    That is the same structural-zero convention the frozen features use, and
    it means the feature says nothing rather than something invented.
    """

    points: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for (election, party, window), row in index.items():
        if window not in WINDOW_MIDPOINTS:
            continue
        count = str(row.get("party_article_count", "")).strip()
        tone = str(row.get("net_portrayal_share", "")).strip()
        if count in ("", "0") or float(count) == 0 or tone == "":
            continue
        # Negated so the axis increases towards polling day: a positive slope
        # then reads as "tone improved as the vote approached".
        points[(election, party)].append(
            (-WINDOW_MIDPOINTS[window], float(tone)))

    slopes: dict[tuple[str, str], float] = {}
    for key, observed in points.items():
        if len(observed) < 2:
            continue
        days = [p[0] for p in observed]
        tones = [p[1] for p in observed]
        mean_days = sum(days) / len(days)
        mean_tone = sum(tones) / len(tones)
        spread = sum((d - mean_days) ** 2 for d in days)
        if spread == 0:
            continue
        covariance = sum((d - mean_days) * (t - mean_tone)
                         for d, t in zip(days, tones))
        # Scaled to tone change per 100 days so the coefficient is readable
        # next to features that live on [-1, 1].
        slopes[key] = covariance / spread * 100
    return slopes


def variance_split(index: dict, cells: list[dict]) -> dict:
    """Between-party against within-party variance, the reason for this run."""

    fitting_keys = {(cell["news_election_id"], cell["party_key"])
                    for cell in cells}
    report = {}
    for window in WINDOWS:
        for column in ("net_portrayal_share", "party_article_share"):
            by_party: dict[str, list[float]] = defaultdict(list)
            for election, party in fitting_keys:
                row = index.get((election, party, window))
                if row is None:
                    continue
                count = str(row.get("party_article_count", "")).strip()
                value = str(row.get(column, "")).strip()
                if count in ("", "0") or value == "":
                    continue
                by_party[party].append(float(value))
            values = [v for group in by_party.values() for v in group]
            if len(values) < 3:
                continue
            grand = sum(values) / len(values)
            between = sum(len(g) * (sum(g) / len(g) - grand) ** 2
                          for g in by_party.values())
            within = sum(sum((v - sum(g) / len(g)) ** 2 for v in g)
                         for g in by_party.values())
            total = between + within
            report[f"{window}/{column}"] = {
                "covered_cells": len(values),
                "between_party_share": round(between / total, 4) if total else None,
                "within_party_share": round(within / total, 4) if total else None,
                "party_means": {p: round(sum(g) / len(g), 4)
                                for p, g in sorted(by_party.items())},
            }
    return report


def main() -> None:
    features = _read_csv(FEATURES)
    frozen_index = _feature_index(features)
    bundle = load_stage1_bundle(BUNDLE)
    cells = aggregate_v2_residuals([dict(r) for r in bundle.out_of_fold])
    blinded = sanitise_holdout_rows([dict(r) for r in bundle.holdout])
    observed = load_observed()

    # --- the reproduction gate, on the untouched frozen index ------------
    frozen = [run_arm(FROZEN, cells, frozen_index, blinded, observed, w)
              for w in WINDOWS]
    reference = committed_deltas()
    mismatches = [
        (r["window"], round(r["delta_vs_recalibrated"], 3), reference[r["window"]])
        for r in frozen
        if abs(round(r["delta_vs_recalibrated"], 3)
               - reference[r["window"]]) > 1e-9
    ]
    if mismatches:
        raise RuntimeError(
            "the frozen specification did not reproduce its committed "
            f"deltas, so nothing else in this run is trustworthy: {mismatches}")

    derived_index, tone_mean = build_derived_index(features, cells)
    arms = {"frozen": frozen}
    for name, columns in ARMS.items():
        arms[name] = [run_arm(columns, cells, derived_index, blinded,
                              observed, w) for w in WINDOWS]

    payload = {
        "status": STATUS,
        "feature_table": str(FEATURES),
        "fitting_cells": len(cells),
        "reproduction_check": {
            "committed_combined_deltas": reference,
            "reproduced": {r["window"]: round(r["delta_vs_recalibrated"], 4)
                           for r in frozen},
            "max_absolute_difference": max(
                abs(round(r["delta_vs_recalibrated"], 3) - reference[r["window"]])
                for r in frozen),
        },
        "tone_centres_from_fitting_cells": {
            f"{party}/{window}": round(value, 4)
            for (party, window), value in sorted(tone_mean.items())},
        "variance_split": variance_split(derived_index, cells),
        "arms": arms,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "identity_placebo_results.json").write_text(
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
        if record is None or "delta_vs_recalibrated" not in record:
            return "-"
        return f"{record['delta_vs_recalibrated']:+.4f}"

    lines = [
        "# Is the news layer anything more than the party's name?",
        "",
        f"**{payload['status']}**",
        "",
        "Delta is the change in election-wide MAE against the recalibrated "
        "control; positive is better. Every arm shares the "
        f"{payload['fitting_cells']} frozen fitting cells and the frozen "
        "prediction and scoring code, so the only thing that differs between "
        "rows is which columns the model was given.",
        "",
        "## Reproduction gate",
        "",
        "The frozen specification reproduces its committed deltas to a "
        "maximum absolute difference of "
        f"**{payload['reproduction_check']['max_absolute_difference']:.4f}**. "
        "The run aborts if it does not.",
        "",
        "## Why this run exists",
        "",
        "Variance of the two frozen features across the covered fitting "
        "cells, split into the part that separates parties from the part "
        "that separates elections within a party:",
        "",
        "| window / column | covered cells | between parties | within a party |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key, record in payload["variance_split"].items():
        if not key.startswith(("180_to_91_days", "90_to_31_days")):
            continue
        lines.append(
            f"| {key} | {record['covered_cells']} | "
            f"{record['between_party_share'] * 100:.1f}% | "
            f"{record['within_party_share'] * 100:.1f}% |")

    lines += [
        "",
        "## Every arm, every window",
        "",
        "| arm | " + " | ".join(w.replace("_", "-") for w in WINDOWS) + " |",
        "| --- | " + " | ".join("---:" for _ in WINDOWS) + " |",
    ]
    for name in ["frozen", *ARMS]:
        lines.append(f"| {name} | "
                     + " | ".join(cell(name, w) for w in WINDOWS) + " |")

    frozen_headline = entry("frozen", headline)["delta_vs_recalibrated"]
    lines += [
        "",
        f"## The headline window, {headline}",
        "",
        f"The frozen specification scores **{frozen_headline:+.4f}** here. "
        "The question is how much of that survives an arm that never reads "
        "an article.",
        "",
        "| arm | delta | 95% CI | share of the frozen result |",
        "| --- | ---: | --- | ---: |",
    ]
    for name in ["frozen", *ARMS]:
        record = entry(name, headline)
        if record is None or "delta_vs_recalibrated" not in record:
            continue
        delta = record["delta_vs_recalibrated"]
        low, high = record.get("ci_lower"), record.get("ci_upper")
        interval = (f"[{low:+.4f}, {high:+.4f}]"
                    if low is not None and high is not None else "-")
        share = (f"{delta / frozen_headline * 100:.0f}%"
                 if frozen_headline else "-")
        lines.append(f"| {name} | {delta:+.4f} | {interval} | {share} |")

    lines += [
        "",
        "## Coefficients at the headline window",
        "",
        "| arm | coefficients |",
        "| --- | --- |",
    ]
    for name in ["frozen", *ARMS]:
        record = entry(name, headline)
        if record is None or "coefficients" not in record:
            continue
        coefficients = ", ".join(
            f"{k} {v:+.3f}" for k, v in record["coefficients"].items())
        lines.append(f"| {name} | {coefficients} |")

    lines.append("")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "identity_placebo_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
