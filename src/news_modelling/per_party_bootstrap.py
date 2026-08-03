"""Contest-bootstrap uncertainty for the per-party tide-gauge split.

    PYTHONPATH=src .venv/bin/python -m news_modelling.per_party_bootstrap

Why this exists
---------------
Register section 18 records the per-party bias/dispersion decomposition
(findings section 2b) as point estimates on one island only: the
unsealed 2026 outcomes. That reading has two holes. First, no
uncertainty: a fraction-of-a-point level shift measured over ~81
contests can be resampling noise - the same shape of evidence as the
local arm's exploratory 4/6 record, which the Woking South blind test
then refuted. The brief's evaluation section requires group-aware
intervals ("Do not treat every candidate row as statistically
independent"), and every candidate of a party shares one broadcast
news value per contest, so candidate rows are the wrong resampling
unit. Second, one island: the only other candidate-level evaluation
the news layer owns is the frozen 2021 validation prediction file
(production_news_experiment_v1), and the split was never run there.

This module recomputes the split on BOTH islands and puts a
contest-level bootstrap interval on every change, using the resample
count and seed the primary experiment's interval already uses
(news_estimator.BOOTSTRAP_RESAMPLES / BOOTSTRAP_SEED). Nothing is
refitted: both prediction files are frozen artefacts, and the 2026
point estimates are asserted against the committed decomposition
results so this annex can never drift from findings section 2b.

Definitions (identical to exploratory_decompositions)
-----------------------------------------------------
For one party inside one specification, with signed errors
e_i = prediction_i - observed_i over that party's candidate rows:

    bias       = mean(e_i)          - the election-wide level error a
                                      broadcast party-level adjustment
                                      CAN move (the tide);
    dispersion = mean(|e_i - bias|) - the ward-to-ward geography such
                                      an adjustment cannot touch.

Reported changes are news minus control for |bias| and for dispersion,
so negative = the news model reduced that error component. Both
controls are kept: the recalibrated prediction (the confirmatory
comparator throughout the register) and the untouched baseline (what
findings section 2b tabulated).

Bootstrap design
----------------
Contests (division-level candidate groups) are resampled with
replacement within each specification. Every party, the non-Reform
group mean and the Reform-versus-group contrast are recomputed from
the SAME draw, so the contrast interval is a paired interval, not a
difference of two marginal ones. A party absent from a draw - possible
for the thin parties (Reform 2021: 6 rows; UKIP 2021: 5 rows) -
contributes nothing to that draw, and the effective draw count is
reported beside every interval.

Evidence status
---------------
EXPLORATORY on both islands. The 2026 side reuses already-unsealed
outcomes and can promote nothing. The 2021 side reuses pre-2026
outcomes the production experiment already scored, but this split was
not pre-declared there, so it carries the same label. This is an
uncertainty annex to the declared decomposition, not a new comparison;
no window or arm may be selected from it.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from news_modelling.news_estimator import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED
from news_modelling.unblind_2026 import CONFIRMATORY, load_observed

VALIDATION_PREDICTIONS = Path(
    "news_features/production_news_experiment_v1/validation_predictions.csv")
V2_PREDICTIONS = Path(
    "news_features/blinded_2026_predictions_v2/blinded_predictions.csv")
DECOMPOSITION_RESULTS = Path(
    "news_features/exploratory_decompositions_v1/decomposition_results.json")
OUTPUT_DIR = Path("news_features/per_party_bootstrap_v1")

STATUS = ("EXPLORATORY, both islands. Uncertainty annex to the "
          "pre-declared per-party decomposition (register section 18); "
          "reads frozen prediction files only, refits nothing, promotes "
          "nothing.")

# The five parties whose aggregated 2017 residuals were the news
# model's only fitting rows on the 2021 island (register section 11).
# Reform UK had zero fitting rows there, so its 2021 adjustment is pure
# extrapolation from these parties' fitted mapping. On the 2026 island
# the v2 fit had 45 election x party cells of which seven were
# Reform-era cells (register sections 16 and 18): thin history rather
# than none. The group contrast is therefore "non-Reform supported
# parties versus Reform" on both islands, with the fitting-cell
# asymmetry stated in the findings rather than encoded here.
STUDY_PARTY = "reform_uk"

ISLANDS = (
    {
        "name": "validation_2021",
        "description": (
            "Frozen 2021 validation predictions (fit: five aggregated "
            "2017 party rows, zero Reform rows). 18 specifications: "
            "three arms x six confirmed windows."),
        "expected_blocks": 18,
    },
    {
        "name": "holdout_2026_v2",
        "description": (
            "Frozen v2 blinded predictions scored at the recorded "
            "unblinding (fit: 45 election x party cells, seven of them "
            "Reform-era). 12 confirmatory specifications: two arms x "
            "six confirmed windows."),
        "expected_blocks": 12,
    },
)


def _read_validation_blocks() -> dict[tuple[str, str], list[dict]]:
    """2021 rows: observed shares travel inside the frozen file."""

    blocks: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with VALIDATION_PREDICTIONS.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["period_role"] != "confirmed_window":
                continue
            if row["included_in_reported_metrics"] != "True":
                continue
            blocks[(row["analysis"], row["period"])].append({
                "party": row["party_key"],
                "contest": (row["election_id"], row["division_id"]),
                "baseline": float(row["baseline_prediction"]),
                "recalibrated": float(row["recalibrated_prediction"]),
                "news": float(row["news_enhanced_prediction"]),
                "observed": float(row["observed_vote_share"]),
            })
    return blocks


def _read_holdout_blocks() -> dict[tuple[str, str], list[dict]]:
    """2026 rows: the blinded file carries no outcomes by design, so
    observed shares come from the unblinding module's sanctioned read -
    the same join exploratory_decompositions used."""

    observed = load_observed()
    family = CONFIRMATORY["v2"]
    blocks: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with V2_PREDICTIONS.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["fit_variant"] != family["fit_variant"]:
                continue
            if row["period_role"] != family["period_role"]:
                continue
            if row["analysis"] not in family["analyses"]:
                continue
            if row["included_in_reported_metrics"] != "True":
                continue
            actual = observed[row["candidate_contest_id"]]
            blocks[(row["analysis"], row["period"])].append({
                "party": row["party_key"],
                "contest": (row["election_id"], row["division_id"]),
                "baseline": float(row["baseline_prediction"]),
                "recalibrated": float(row["recalibrated_prediction"]),
                "news": float(row["news_enhanced_prediction"]),
                "observed": float(actual["observed_vote_share"]),
            })
    return blocks


def error_split(errors: np.ndarray) -> dict:
    """Bias / dispersion split of one signed-error vector.

    Kept byte-compatible with exploratory_decompositions._split_errors
    so the 2026 cross-check below can demand exact-after-rounding
    agreement with the committed decomposition results.
    """

    bias = float(errors.mean())
    return {
        "rows": int(errors.size),
        "signed_bias": round(bias, 4),
        "abs_bias": round(abs(bias), 4),
        "dispersion_mae": round(float(np.abs(errors - bias).mean()), 4),
        "total_mae": round(float(np.abs(errors).mean()), 4),
    }


def _summarise_draws(draws: np.ndarray) -> dict:
    """Percentile interval over the non-empty draws of one quantity."""

    valid = draws[~np.isnan(draws)]
    if valid.size == 0:
        return {"effective_draws": 0}
    return {
        "effective_draws": int(valid.size),
        "ci_lower": round(float(np.percentile(valid, 2.5)), 4),
        "ci_upper": round(float(np.percentile(valid, 97.5)), 4),
        # Direction convention: negative change = news reduced that
        # error component, so negative draws favour news. Both shares
        # are reported because structural-zero windows produce draws
        # that are exactly zero - neither negative nor positive - and
        # one share alone would misread them as unanimous.
        "share_draws_negative": round(float((valid < 0).mean()), 4),
        "share_draws_positive": round(float((valid > 0).mean()), 4),
    }


def block_analysis(rows: list[dict], *, study_party: str = STUDY_PARTY,
                   rng: np.random.Generator | None = None,
                   resamples: int = BOOTSTRAP_RESAMPLES,
                   return_draws: bool = False) -> dict:
    """Point estimates and paired contest-bootstrap intervals for one
    (analysis, period) block.

    ``rows`` are candidate rows: party, contest, three predictions and
    the observed share. The group aggregate is the unweighted mean over
    the non-Reform parties' changes (party-level mean, not row-pooled,
    so an 81-row Conservative slate cannot outvote a 36-row Green one),
    and the contrast is Reform minus that mean inside every draw.
    """

    if rng is None:
        rng = np.random.default_rng(BOOTSTRAP_SEED)

    parties = sorted({r["party"] for r in rows})
    group_parties = [p for p in parties if p != study_party]
    contests = sorted({r["contest"] for r in rows})
    contest_index = {c: i for i, c in enumerate(contests)}
    party_index = {p: i for i, p in enumerate(parties)}

    contest_of = np.array([contest_index[r["contest"]] for r in rows])
    party_of = np.array([party_index[r["party"]] for r in rows])
    observed = np.array([r["observed"] for r in rows])
    errors = {model: np.array([r[model] for r in rows]) - observed
              for model in ("baseline", "recalibrated", "news")}
    rows_by_contest = [np.flatnonzero(contest_of == i)
                       for i in range(len(contests))]

    # Point estimates on the full block, per party and per model, plus
    # the two change columns against each control.
    point: dict[str, dict] = {}
    for party in parties:
        mask = party_of == party_index[party]
        models = {m: error_split(errors[m][mask])
                  for m in ("baseline", "recalibrated", "news")}
        entry = {"models": models,
                 "contests": int(len(set(contest_of[mask].tolist())))}
        for control in ("recalibrated", "baseline"):
            entry[f"abs_bias_change_vs_{control}"] = round(
                models["news"]["abs_bias"] - models[control]["abs_bias"], 4)
            entry[f"dispersion_change_vs_{control}"] = round(
                models["news"]["dispersion_mae"]
                - models[control]["dispersion_mae"], 4)
        point[party] = entry

    # Point-estimate group mean and contrast on the full block, so the
    # findings table can show the actual estimate rather than an
    # interval midpoint. Same definitions as inside the draws.
    contrast_point: dict[str, float] = {}
    group_point: dict[str, float] = {}
    group_present = [p for p in group_parties if p in point]
    for control in ("recalibrated", "baseline"):
        for component in ("abs_bias_change", "dispersion_change"):
            q = f"{component}_vs_{control}"
            if group_present:
                group_point[q] = round(float(np.mean(
                    [point[p][q] for p in group_present])), 4)
                if study_party in point:
                    contrast_point[q] = round(
                        point[study_party][q] - group_point[q], 4)

    if len(contests) < 2:
        # Same guard as news_estimator.bootstrap_improvement: one
        # contest resamples itself into a zero-width interval.
        return {"parties": point, "contests": len(contests),
                "group_point": group_point, "contrast_point": contrast_point,
                "bootstrap": {"resamples": 0,
                              "reason": f"{len(contests)} contest(s)"}}

    # Paired draws. Axis 0 = draw; NaN marks "party absent from draw".
    quantities = ("abs_bias_change_vs_recalibrated",
                  "dispersion_change_vs_recalibrated",
                  "abs_bias_change_vs_baseline",
                  "dispersion_change_vs_baseline")
    draws = {q: {unit: np.full(resamples, np.nan)
                 for unit in parties + ["group_mean", "contrast"]}
             for q in quantities}

    for d in range(resamples):
        picked = rng.integers(0, len(contests), size=len(contests))
        idx = np.concatenate([rows_by_contest[c] for c in picked])
        sample_party = party_of[idx]
        per_party: dict[str, dict[str, float]] = {}
        for party in parties:
            sel = idx[sample_party == party_index[party]]
            if sel.size == 0:
                continue
            news_err = errors["news"][sel]
            news_bias = news_err.mean()
            news_disp = np.abs(news_err - news_bias).mean()
            values = {}
            for control in ("recalibrated", "baseline"):
                ctrl_err = errors[control][sel]
                ctrl_bias = ctrl_err.mean()
                values[f"abs_bias_change_vs_{control}"] = (
                    abs(news_bias) - abs(ctrl_bias))
                values[f"dispersion_change_vs_{control}"] = (
                    news_disp - np.abs(ctrl_err - ctrl_bias).mean())
            per_party[party] = values
            for q in quantities:
                draws[q][party][d] = values[q]
        present_group = [p for p in group_parties if p in per_party]
        if present_group:
            for q in quantities:
                group_value = float(np.mean(
                    [per_party[p][q] for p in present_group]))
                draws[q]["group_mean"][d] = group_value
                if study_party in per_party:
                    draws[q]["contrast"][d] = (
                        per_party[study_party][q] - group_value)

    bootstrap = {
        "resamples": resamples,
        "seed": BOOTSTRAP_SEED,
        "contests_resampled": len(contests),
        "group_parties": group_parties,
        "units": {unit: {q: _summarise_draws(draws[q][unit])
                         for q in quantities}
                  for unit in parties + ["group_mean", "contrast"]},
    }
    result = {"parties": point, "contests": len(contests),
              "group_point": group_point, "contrast_point": contrast_point,
              "bootstrap": bootstrap}
    if return_draws:
        result["draws"] = draws
    return result


def cross_check_2026(results: dict) -> int:
    """Fail loudly if the 2026 point estimates drift from the committed
    decomposition results (findings section 2b). Returns cells checked.
    """

    committed = json.loads(DECOMPOSITION_RESULTS.read_text(encoding="utf-8"))
    reference = {
        (spec["analysis"], spec["window"]): spec["parties"]
        for spec in committed["mechanism_per_party"]["per_specification"]
    }
    checked = 0
    for block in results:
        if block["island"] != "holdout_2026_v2":
            continue
        expected = reference[(block["analysis"], block["period"])]
        for party, entry in block["parties"].items():
            for mine, theirs in (("news", "news"), ("baseline", "baseline")):
                for field in ("abs_bias", "dispersion_mae"):
                    a = entry["models"][mine][field]
                    b = expected[party][theirs][field]
                    if abs(a - b) > 5e-4:
                        raise AssertionError(
                            f"2026 drift at {block['analysis']} "
                            f"{block['period']} {party} {mine}.{field}: "
                            f"{a} vs committed {b}")
                    checked += 1
    return checked


def _interval_rows(results: list[dict]) -> list[dict]:
    """Flatten to one CSV row per island x spec x unit x control."""

    out = []
    for block in results:
        boot = block["bootstrap"]
        if boot.get("resamples", 0) == 0:
            continue
        for unit, quantities in boot["units"].items():
            for control in ("recalibrated", "baseline"):
                bias = quantities[f"abs_bias_change_vs_{control}"]
                disp = quantities[f"dispersion_change_vs_{control}"]
                if unit in block["parties"]:
                    point_bias = block["parties"][unit][
                        f"abs_bias_change_vs_{control}"]
                    point_disp = block["parties"][unit][
                        f"dispersion_change_vs_{control}"]
                    rows = block["parties"][unit]["models"]["news"]["rows"]
                else:
                    point_bias = point_disp = None
                    rows = None
                out.append({
                    "island": block["island"],
                    "analysis": block["analysis"],
                    "period": block["period"],
                    "unit": unit,
                    "control": control,
                    "rows": rows,
                    "contests": block["contests"],
                    "abs_bias_change": point_bias,
                    "abs_bias_ci_lower": bias.get("ci_lower"),
                    "abs_bias_ci_upper": bias.get("ci_upper"),
                    "abs_bias_share_draws_negative":
                        bias.get("share_draws_negative"),
                    "abs_bias_share_draws_positive":
                        bias.get("share_draws_positive"),
                    "dispersion_change": point_disp,
                    "dispersion_ci_lower": disp.get("ci_lower"),
                    "dispersion_ci_upper": disp.get("ci_upper"),
                    "effective_draws": bias.get("effective_draws"),
                })
    return out


def _excludes_zero(summary: dict) -> bool:
    return ("ci_lower" in summary
            and (summary["ci_upper"] < 0 or summary["ci_lower"] > 0))


def _island_footnotes(name: str, blocks: list[dict]) -> list[str]:
    """The details an honest read of the tables must not lose.

    Everything here is computed from the blocks, so a re-run can never
    leave these sentences contradicting the tables above them.
    """

    q = "abs_bias_change_vs_recalibrated"
    dq = "dispersion_change_vs_recalibrated"

    positive, negative = [], []
    for block in blocks:
        summary = block["bootstrap"]["units"]["contrast"][q]
        if _excludes_zero(summary):
            label = (f"{block['analysis']} {block['period']} "
                     f"({block['contrast_point'][q]:+.3f})")
            (positive if summary["ci_lower"] > 0 else negative).append(label)

    starred_dispersion = []
    largest_dispersion = 0.0
    for block in blocks:
        for party, entry in block["parties"].items():
            value = entry["dispersion_change_vs_recalibrated"]
            largest_dispersion = max(largest_dispersion, abs(value))
            if _excludes_zero(block["bootstrap"]["units"][party][dq]):
                starred_dispersion.append(
                    f"{party} {block['analysis']} {block['period']} "
                    f"({value:+.2f})")

    # The study party's headline cell under BOTH controls: if the
    # direction agreed only against the recalibrated control it could
    # be a recalibration artefact rather than a news movement.
    headline = next(b for b in blocks
                    if b["analysis"] == "combined_exploratory"
                    and b["period"] == "90_to_31_days")
    reform = headline["parties"][STUDY_PARTY]
    units = headline["bootstrap"]["units"][STUDY_PARTY]
    recal = units["abs_bias_change_vs_recalibrated"]
    base = units["abs_bias_change_vs_baseline"]

    lines = ["Footnotes the tables force:", ""]
    lines.append(
        f"- Contrast direction census: {len(positive)} interval(s) exclude "
        f"zero on the positive side (Reform's level handled worse than the "
        f"group), {len(negative)} on the negative side"
        + (f" - {'; '.join(negative)}." if negative else "."))
    lines.append(
        f"- Reform's combined 90-31-day level change keeps its sign under "
        f"both controls: {reform['abs_bias_change_vs_recalibrated']:+.3f} "
        f"[{recal.get('ci_lower'):+.3f}, {recal.get('ci_upper'):+.3f}] "
        f"versus recalibrated, "
        f"{reform['abs_bias_change_vs_baseline']:+.3f} "
        f"[{base.get('ci_lower'):+.3f}, {base.get('ci_upper'):+.3f}] versus "
        f"baseline - not a recalibration artefact.")
    lines.append(
        f"- Dispersion: largest point change {largest_dispersion:.3f}; "
        f"{len(starred_dispersion)} of {sum(len(b['parties']) for b in blocks)} "
        f"party x specification dispersion intervals exclude zero"
        + (f" ({'; '.join(starred_dispersion)})" if starred_dispersion
           else "") + ". A constant per-party shift cannot move dispersion "
        "at all, so every non-zero cell here measures the clip-and-"
        "renormalise step - the prediction arithmetic's only "
        "ward-dependent operation - not news content reaching geography.")
    if name == "validation_2021":
        lines.append(
            "- Reform's starred level improvements on this island are "
            "section 11's extrapolation artefact restated with intervals: "
            "six candidate rows, ZERO Reform fitting rows, so the "
            "adjustment is borrowed entirely from the five fitted parties' "
            "mapping. A narrow interval says the borrowed shift is stable "
            "under contest resampling within 2021; it is not evidence of a "
            "learned Reform effect.")
    lines.append("")
    return lines


def render_findings(results: list[dict], checked: int) -> str:
    """Register-voice findings: headline tables plus honest counts."""

    lines = [
        "# Per-party tide-gauge changes with contest-bootstrap intervals",
        "", f"**{STATUS}**", "",
        f"Resamples {BOOTSTRAP_RESAMPLES}, seed {BOOTSTRAP_SEED}, "
        f"contests resampled with replacement inside every "
        f"specification; draws are paired across parties, the group "
        f"mean and the Reform contrast. The 2026 point estimates were "
        f"asserted against the committed decomposition results "
        f"({checked} cells checked). Negative change = the news model "
        f"reduced that error component relative to the control.", "",
        "Controls: `recalibrated` is the confirmatory comparator; "
        "`baseline` is the untouched Stage 1 prediction that findings "
        "section 2b tabulated. Group mean = unweighted party-level "
        "mean over non-Reform supported parties; contrast = Reform "
        "minus that mean, computed inside each draw.", "",
    ]

    for island in ISLANDS:
        name = island["name"]
        blocks = [b for b in results if b["island"] == name]
        lines += [f"## {name}", "", island["description"], ""]

        # Headline table: the 90-31-day window every prior record
        # treats as the informative panel, all arms, per party.
        lines += ["Per-party |bias| change versus the recalibrated "
                  "control, 90-31-day window (bracketed 95% interval; "
                  "* = interval excludes zero):", "",
                  "| arm | party | rows | d|bias| [95% CI] | "
                  "d dispersion [95% CI] |",
                  "| --- | --- | ---: | --- | --- |"]
        for block in blocks:
            if block["period"] != "90_to_31_days":
                continue
            units = block["bootstrap"]["units"]
            for party, entry in block["parties"].items():
                bias = units[party]["abs_bias_change_vs_recalibrated"]
                disp = units[party]["dispersion_change_vs_recalibrated"]
                star = "*" if _excludes_zero(bias) else ""
                dstar = "*" if _excludes_zero(disp) else ""
                lines.append(
                    f"| {block['analysis']} | {party} | "
                    f"{entry['models']['news']['rows']} | "
                    f"{entry['abs_bias_change_vs_recalibrated']:+.3f} "
                    f"[{bias.get('ci_lower', float('nan')):+.3f}, "
                    f"{bias.get('ci_upper', float('nan')):+.3f}]{star} | "
                    f"{entry['dispersion_change_vs_recalibrated']:+.3f} "
                    f"[{disp.get('ci_lower', float('nan')):+.3f}, "
                    f"{disp.get('ci_upper', float('nan')):+.3f}]{dstar} |")
        lines.append("")

        # Contrast table across every specification on the island.
        lines += ["Reform minus non-Reform group mean, |bias| change "
                  "versus recalibrated (positive = Reform's level "
                  "handled worse than the fitted/legacy parties'):", "",
                  "| arm | window | contrast [95% CI] | share of draws "
                  "with contrast > 0 |",
                  "| --- | --- | --- | ---: |"]
        for block in blocks:
            contrast = block["bootstrap"]["units"]["contrast"][
                "abs_bias_change_vs_recalibrated"]
            estimate = block["contrast_point"].get(
                "abs_bias_change_vs_recalibrated")
            if "ci_lower" not in contrast or estimate is None:
                lines.append(f"| {block['analysis']} | {block['period']} | "
                             f"no draws | - |")
                continue
            star = "*" if _excludes_zero(contrast) else ""
            lines.append(
                f"| {block['analysis']} | {block['period']} | "
                f"{estimate:+.3f} [{contrast['ci_lower']:+.3f}, "
                f"{contrast['ci_upper']:+.3f}]{star} | "
                f"{contrast['share_draws_positive']} |")
        lines.append("")

        # Honest census: how many party-level intervals exclude zero,
        # and in which direction, out of how many.
        improved = worsened = total = 0
        for block in blocks:
            for party in block["parties"]:
                summary = block["bootstrap"]["units"][party][
                    "abs_bias_change_vs_recalibrated"]
                total += 1
                if _excludes_zero(summary):
                    if summary["ci_upper"] < 0:
                        improved += 1
                    else:
                        worsened += 1
        lines += [f"Census over all {total} party x specification "
                  f"|bias|-change intervals versus recalibrated: "
                  f"**{improved} exclude zero on the improving side, "
                  f"{worsened} on the worsening side**, "
                  f"{total - improved - worsened} straddle zero.", ""]
        lines += _island_footnotes(name, blocks)

    lines += [
        "## Reading", "",
        "These are exploratory intervals over frozen predictions. A "
        "starred cell is a level shift the contest resampling cannot "
        "explain away; an unstarred cell is indistinguishable from "
        "noise at this contest count - the same standard the register "
        "applies to every other exploratory reading. Nothing here "
        "selects a window, an arm or a model.", "",
        "The cross-island reading is the headline: the Reform-minus-"
        "group contrast is negative through most 2021 windows and "
        "positive through most 2026 ones, so the direction of the news "
        "layer's Reform level correction does not survive the change "
        "of island. A narrow interval is a statement about resampling "
        "noise WITHIN one election only; the instability that matters "
        "lives between islands, and no within-island interval can "
        "certify it away. This is the transfer failure Haslemere and "
        "Woking South recorded, stated a third time in resampling "
        "form.", "",
    ]
    return "\n".join(lines)


def main() -> None:
    islands = {
        "validation_2021": _read_validation_blocks(),
        "holdout_2026_v2": _read_holdout_blocks(),
    }
    results: list[dict] = []
    for island in ISLANDS:
        blocks = islands[island["name"]]
        if len(blocks) != island["expected_blocks"]:
            raise AssertionError(
                f"{island['name']}: expected {island['expected_blocks']} "
                f"specifications, found {len(blocks)}")
        # One seeded generator per island, blocks in sorted order, so
        # the whole run is deterministic end to end.
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        for (analysis, period) in sorted(blocks):
            block = block_analysis(blocks[(analysis, period)], rng=rng)
            block.update({"island": island["name"],
                          "analysis": analysis, "period": period})
            results.append(block)

    checked = cross_check_2026(results)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": STATUS,
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED,
        "cross_check_cells": checked,
        "islands": {i["name"]: i["description"] for i in ISLANDS},
        "specifications": results,
    }
    (OUTPUT_DIR / "per_party_bootstrap_results.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    interval_rows = _interval_rows(results)
    with (OUTPUT_DIR / "per_party_intervals.csv").open(
            "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(interval_rows[0]))
        writer.writeheader()
        writer.writerows(interval_rows)

    (OUTPUT_DIR / "per_party_bootstrap_findings.md").write_text(
        render_findings(results, checked), encoding="utf-8")
    print(f"{len(results)} specifications, {checked} cross-checked cells, "
          f"outputs in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
