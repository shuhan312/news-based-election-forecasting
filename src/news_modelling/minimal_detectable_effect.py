"""Minimal detectable effects of the archived design, from interval widths.

    PYTHONPATH=src .venv/bin/python -m news_modelling.minimal_detectable_effect

The question this answers
-------------------------
The confirmatory record says news produced no reliable improvement
(0 of 18 pre-2026; a handful of small starred cells at the unblinding).
The examiner's follow-up is: how small an improvement COULD this design
have seen? Without that number, "no improvement" over-reads as "no
effect"; with it, the verdict states its own resolution - any true
effect, if present, is smaller than the minimal detectable effect.

Method: assembly, not modelling
-------------------------------
Every number here is derived from the WIDTH of an already-committed
contest-bootstrap interval; nothing is refitted and no data is read
beyond the archived result files. For one comparison with a 95%
percentile interval [l, u]:

    half  = (u - l) / 2          the sampling-noise scale of the design
    se    = half / 1.96          normal-approximation standard error
    MDE50 = half                 a true effect this size straddles the
                                 exclusion boundary - detected in about
                                 half of repeated samples
    MDE80 = (1.96 + 0.8416) * se an effect detected in about 80% of
                                 repeated samples - the conventional
                                 design-sensitivity figure

Because the interval width measures sampling noise and not the observed
point estimate, this is the legitimate design-sensitivity calculation,
distinct from the criticised habit of computing "post-hoc power" from
the observed effect itself. The observed delta is reported alongside
for context only; it never enters the MDE arithmetic.

Two guards. Structural-zero windows (no in-window signal, so the news
prediction equals the recalibrated control identically) produce [0, 0]
intervals: their MDE is undefined and they are marked, not averaged in.
Percentile intervals can sit asymmetrically around the bootstrap mean
where clipping binds; the symmetric half-width is used regardless and
the asymmetric cases are counted in the results file.

What is covered
---------------
1. Overall news-versus-recalibrated MAE deltas: the 18 confirmed 2021
   comparisons and the 24 confirmatory 2026 cells (v1 and v2).
2. Reform-specific MAE deltas on 2021 (six Reform contests) - the
   design's resolution on the study party where it had zero fitting
   rows.
3. Per-party level-error changes and the Reform-minus-group contrast
   from the per-party bootstrap annex, both islands - the resolution
   of the tide-gauge reading itself, party by party. Resolutions
   differ by more than an order of magnitude between parties inside a
   single specification, so each party's verdict has to be read
   against its own threshold, never a shared one.

Haslemere and Woking South carry no rows here: single-contest case
studies admit no resampling interval, which is exactly why the register
records them as illustrative.

Evidence status
---------------
EXPLORATORY summary of archived confirmatory and exploratory intervals;
computes design resolution only, promotes nothing, selects nothing.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from statistics import median

EXPERIMENT = Path(
    "news_features/production_news_experiment_v1/experiment_results.json")
UNBLINDING = Path("news_features/unblinding_2026_v1/unblinding_results.json")
ANNEX = Path(
    "news_features/per_party_bootstrap_v1/per_party_bootstrap_results.json")
OUTPUT_DIR = Path("news_features/minimal_detectable_effect_v1")

# The prediction files themselves, read only to count how many of the
# specifications are actually distinct.  A specification whose prediction
# vector is byte-identical to another's is the same comparison wearing a
# second name: it carries its own interval and would otherwise be counted
# twice in a resolution figure that is supposed to say how many independent
# looks the design took.
VALIDATION_PREDICTIONS = Path(
    "news_features/production_news_experiment_v1/validation_predictions.csv")
HOLDOUT_PREDICTIONS = {
    "holdout_2026_v1": Path(
        "news_features/blinded_2026_predictions_v1/blinded_predictions.csv"),
    "holdout_2026_v2": Path(
        "news_features/blinded_2026_predictions_v2/blinded_predictions.csv"),
}

STATUS = ("EXPLORATORY design-sensitivity annex. Every number derives "
          "from the width of a committed bootstrap interval; nothing is "
          "refitted, promoted or selected.")

Z95 = 1.959964
Z80 = 0.841621
MDE80_FACTOR = (Z95 + Z80) / Z95  # 1.4294...: MDE80 = half-width * this


def mde_from_interval(lower: float, upper: float) -> dict:
    """The three derived quantities for one interval; None if degenerate."""

    half = (upper - lower) / 2
    if half <= 0:
        return {"status": "structural_zero", "half_width": 0.0}
    return {
        "status": "ok",
        "half_width": round(half, 4),
        "se_normal_approx": round(half / Z95, 4),
        "mde_50_power": round(half, 3),
        "mde_80_power": round(half * MDE80_FACTOR, 3),
    }


def _asymmetric(lower: float, upper: float, mean: float) -> bool:
    """Flag intervals whose bootstrap mean sits well off-centre."""

    half = (upper - lower) / 2
    return half > 0 and abs((upper + lower) / 2 - mean) > 0.1 * half


def distinct_prediction_vectors(path: Path) -> dict[tuple[str, str], str]:
    """Map each (arm, window) to the first specification sharing its vector.

    A specification is only an independent look at the data if it predicts
    something no other specification already predicted.  Two ways that fails
    here.  A window that admitted no articles leaves the news prediction
    equal to the recalibrated control, so several such specifications are
    identical to each other and to doing nothing; those are already caught
    as structural zeros.  The second way is subtler and was not caught: two
    genuinely fitted arms can land on the same vector because the arms are
    not independent - `combined = local + national`, so where one component
    is empty the other two coincide exactly.

    Returns a key -> canonical-key map.  A key mapping to itself is the
    first occurrence of its vector and counts; a key mapping to something
    else is a duplicate and must not be counted again.
    """

    if not path.exists():
        return {}
    by_spec: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("period_role") != "confirmed_window":
                continue
            by_spec[(row["analysis"], row["period"])].append(
                (row["candidate_contest_id"], row["party_key"],
                 row["news_enhanced_prediction"]))

    first_seen: dict[str, tuple[str, str]] = {}
    canonical: dict[tuple[str, str], str] = {}
    for key in sorted(by_spec):
        digest = sha256(
            "|".join(f"{c}:{p}:{v}" for c, p, v in sorted(by_spec[key]))
            .encode("utf-8")).hexdigest()
        owner = first_seen.setdefault(digest, key)
        canonical[key] = f"{owner[0]}/{owner[1]}"
    return canonical


def comparisons_2021(experiment: dict) -> list[dict]:
    """Overall and Reform-specific rows for the 18 confirmed windows."""

    canonical = distinct_prediction_vectors(VALIDATION_PREDICTIONS)
    rows = []
    for spec in experiment["specification_results"]:
        if spec["period_role"] != "confirmed_window":
            continue
        key = (spec["analysis"], spec["period"])
        owner = canonical.get(key, f"{key[0]}/{key[1]}")
        for scope, key in (("overall_mae", "bootstrap_news_vs_recalibrated"),
                           ("reform_mae",
                            "reform_bootstrap_news_vs_recalibrated")):
            interval = spec[key]
            observed = spec["metrics"][
                "all_supported_parties" if scope == "overall_mae"
                else "reform_uk"]["news_vs_recalibrated_mae"]
            rows.append({
                "island": "validation_2021",
                "scope": scope,
                "party": "reform_uk" if scope == "reform_mae" else "",
                "arm": spec["analysis"],
                "window": spec["period"],
                # The specification whose prediction vector this one shares.
                # Equal to its own key when it is the first occurrence.
                "vector_owner": owner,
                "duplicate_vector": owner != f"{key[0]}/{key[1]}",
                "observed_delta": round(observed, 3),
                "ci_lower": interval["improvement_ci_lower"],
                "ci_upper": interval["improvement_ci_upper"],
                "contests": interval["contests_resampled"],
                "asymmetric": _asymmetric(interval["improvement_ci_lower"],
                                          interval["improvement_ci_upper"],
                                          interval["improvement_mean"]),
                **mde_from_interval(interval["improvement_ci_lower"],
                                    interval["improvement_ci_upper"]),
            })
    return rows


def comparisons_2026(unblinding: dict) -> list[dict]:
    """Overall rows for the 24 confirmatory unblinding cells."""

    rows = []
    for version in ("v1", "v2"):
        island = f"holdout_2026_{version}"
        canonical = distinct_prediction_vectors(HOLDOUT_PREDICTIONS[island])
        for entry in unblinding["files"][version]:
            if entry["family"] != "confirmatory":
                continue
            interval = entry["metrics"]["bootstrap_news_vs_recalibrated"]
            key = (entry["analysis"], entry["period"])
            owner = canonical.get(key, f"{key[0]}/{key[1]}")
            rows.append({
                "island": island,
                "scope": "overall_mae",
                "party": "",
                "arm": entry["analysis"],
                "window": entry["period"],
                "vector_owner": owner,
                "duplicate_vector": owner != f"{key[0]}/{key[1]}",
                "observed_delta": round(
                    entry["metrics"]["all_supported_parties"]
                    ["news_vs_recalibrated_mae"], 3),
                "ci_lower": interval["improvement_ci_lower"],
                "ci_upper": interval["improvement_ci_upper"],
                "contests": interval["contests_resampled"],
                "asymmetric": _asymmetric(interval["improvement_ci_lower"],
                                          interval["improvement_ci_upper"],
                                          interval["improvement_mean"]),
                **mde_from_interval(interval["improvement_ci_lower"],
                                    interval["improvement_ci_upper"]),
            })
    return rows


def comparisons_annex(annex: dict) -> list[dict]:
    """Per-party level-change and contrast rows from the bootstrap annex.

    These intervals are on |bias| changes (level errors), not MAE
    deltas, so they state the resolution of the tide-gauge reading:
    how small a level shift, for EACH party, the islands could certify.

    Every supported party is covered, not just the study party. The
    per-party resolutions differ by more than an order of magnitude
    within one specification - a party's interval width depends on how
    many contests it stood in and how stable its errors are across
    them - so a shared threshold would misread most cells. The
    Reform-versus-group contrast keeps its own row: it is a difference
    of two quantities with its own paired interval, not any party's.
    """

    quantity = "abs_bias_change_vs_recalibrated"
    # Same duplicate-vector rule as the MAE rows. These are the same
    # specifications scored on a different quantity, so a pair that shares a
    # prediction vector shares it here too - a per-party level change is a
    # function of the predictions, and identical predictions cannot give two
    # independent readings of it.
    canonical = {
        "validation_2021": distinct_prediction_vectors(VALIDATION_PREDICTIONS),
        **{island: distinct_prediction_vectors(path)
           for island, path in HOLDOUT_PREDICTIONS.items()},
    }
    rows = []
    for spec in annex["specifications"]:
        key = (spec["analysis"], spec["period"])
        owner = canonical.get(spec["island"], {}).get(
            key, f"{key[0]}/{key[1]}")
        units = [("party_level", party) for party in sorted(spec["parties"])]
        units.append(("reform_vs_group_contrast", "contrast"))
        for scope, unit in units:
            interval = spec["bootstrap"]["units"][unit][quantity]
            if "ci_lower" not in interval:
                continue
            observed = (spec["parties"][unit][quantity]
                        if scope == "party_level"
                        else spec["contrast_point"][quantity])
            rows.append({
                "island": spec["island"],
                "scope": scope,
                "party": unit if scope == "party_level" else "",
                "arm": spec["analysis"],
                "window": spec["period"],
                "vector_owner": owner,
                "duplicate_vector": owner != f"{key[0]}/{key[1]}",
                "observed_delta": round(observed, 3),
                "ci_lower": interval["ci_lower"],
                "ci_upper": interval["ci_upper"],
                "contests": spec["bootstrap"]["contests_resampled"],
                "asymmetric": False,  # annex stores no draw mean; not judged
                **mde_from_interval(interval["ci_lower"],
                                    interval["ci_upper"]),
            })
    return rows


def summarise(rows: list[dict]) -> list[dict]:
    """Median and range of MDE80 per island x scope x party.

    Party is part of the key, not pooled away: within one island the
    per-party resolutions span more than an order of magnitude, so a
    pooled median would be quotable but wrong for every party in it.
    Non-party scopes carry an empty party and group as before.
    """

    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["island"], row["scope"], row.get("party", ""))].append(row)
    out = []
    for (island, scope, party), members in sorted(grouped.items()):
        ok = [m for m in members if m["status"] == "ok"]
        estimable = [m["mde_80_power"] for m in ok]
        # An estimable comparison that shares its prediction vector with an
        # earlier one is the same look at the data counted twice. The median
        # and range below are unaffected - identical vectors give identical
        # intervals - but the count of independent comparisons is not, and
        # that count is what a resolution figure is claiming.
        # A row without a recorded owner has no vector to compare, so it
        # counts as its own: the index keeps it distinct rather than
        # silently collapsing rows that were never checked.
        distinct = len({m.get("vector_owner") or f"row-{i}"
                        for i, m in enumerate(ok)})
        entry = {"island": island, "scope": scope, "party": party,
                 "comparisons": len(members),
                 "estimable": len(estimable),
                 "distinct_estimable": distinct,
                 "duplicate_vectors": len(estimable) - distinct,
                 "structural_zero": len(members) - len(estimable)}
        if estimable:
            entry.update({
                "median_mde_80": round(median(estimable), 3),
                "min_mde_80": round(min(estimable), 3),
                "max_mde_80": round(max(estimable), 3),
            })
        out.append(entry)
    return out


def render_findings(rows: list[dict], summary: list[dict]) -> str:
    lines = [
        "# Minimal detectable effects of the archived design",
        "", f"**{STATUS}**", "",
        f"MDE50 = interval half-width (a true effect that size is "
        f"detected in ~half of repeated samples); MDE80 = half-width x "
        f"{MDE80_FACTOR:.3f} (detected in ~80%). Derived from interval "
        f"WIDTH only - the observed delta never enters the arithmetic, "
        f"which is what separates design sensitivity from the "
        f"discredited observed-effect post-hoc power. Share-point "
        f"units throughout.", "",
        "## Summary: the design's resolution", "",
        "| island | scope | party | distinct estimable | median MDE80 | range |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for entry in summary:
        if entry.get("median_mde_80") is None:
            lines.append(f"| {entry['island']} | {entry['scope']} | "
                         f"{entry['party'] or '-'} | {entry['comparisons']} | "
                         f"- | all structural zero |")
            continue
        notes = []
        if entry["structural_zero"]:
            notes.append(f"{entry['structural_zero']} structural-zero")
        if entry.get("duplicate_vectors"):
            notes.append(f"{entry['duplicate_vectors']} duplicate-vector")
        note = f" ({', '.join(notes)} excluded)" if notes else ""
        lines.append(
            f"| {entry['island']} | {entry['scope']} | "
            f"{entry['party'] or '-'} | "
            f"{entry.get('distinct_estimable', entry['estimable'])}{note} | "
            f"{entry['median_mde_80']} | "
            f"[{entry['min_mde_80']}, {entry['max_mde_80']}] |")

    # The headline window every prior record treats as informative,
    # party by party: the threshold beside the effect actually seen,
    # so a cell's verdict can be read as "cleared it" or "did not".
    lines += ["", "## Headline window, party by party (combined arm, "
              "90-31 days)", "",
              "| island | party | observed d\\|bias\\| | MDE80 | detectable |",
              "| --- | --- | ---: | ---: | --- |"]
    headline = [r for r in rows if r["scope"] == "party_level"
                and r["window"] == "90_to_31_days"
                and r["arm"] == "combined_exploratory"]
    for row in sorted(headline, key=lambda r: (r["island"], r["party"])):
        if row["status"] != "ok":
            lines.append(f"| {row['island']} | {row['party']} | "
                         f"{row['observed_delta']:+.3f} | - | structural zero |")
            continue
        clears = abs(row["observed_delta"]) >= row["mde_80_power"]
        lines.append(
            f"| {row['island']} | {row['party']} | "
            f"{row['observed_delta']:+.3f} | {row['mde_80_power']:.3f} | "
            f"{'yes' if clears else 'NO - inside the blind zone'} |")

    by_key = {(e["island"], e["scope"], e["party"]): e for e in summary}
    overall_2021 = by_key[("validation_2021", "overall_mae", "")]
    reform_2021 = by_key[("validation_2021", "reform_mae", "reform_uk")]
    overall_v2 = by_key[("holdout_2026_v2", "overall_mae", "")]
    lines += [
        "", "## Reading", "",
        f"The pre-2026 verdict now states its own resolution. The eighteen "
        f"confirmed 2021 specifications are fewer looks at the data than "
        f"they appear: four windows admitted no articles, leaving the news "
        f"prediction identical to the control, and one further pair is "
        f"byte-identical because `combined = local + national` collapses "
        f"where one component is empty. That leaves "
        f"{overall_2021['distinct_estimable']} distinct estimable "
        f"comparisons, not eighteen. Across them the 0-of-18 "
        f"result bounds any true overall improvement below roughly "
        f"{overall_2021['median_mde_80']} share points of MAE (median "
        f"MDE80 across the confirmed windows), and any Reform-specific "
        f"improvement below roughly {reform_2021['median_mde_80']} points "
        f"- an order the six 2021 Reform contests could never certify. "
        f"\"No Reform evidence\" is therefore a statement about the "
        f"design's resolution as much as about news. The 2026 island is "
        f"the sharp one: with 81 contests the v2 overall comparisons "
        f"resolve effects down to a median {overall_v2['median_mde_80']} "
        f"points, which is why the small legacy-party level corrections "
        f"could be certified there at all.", "",
        "Haslemere and Woking South admit no interval (single contests): "
        "their MDE is unbounded, which is the arithmetic form of the "
        "register's insistence that they are illustrative case studies.",
        "",
        "Per-party resolutions are NOT interchangeable. Inside the 2026 "
        "headline window they span 0.031 (Labour) to 1.072 (Green), a "
        "thirty-fold range, and party size does not explain it: Green "
        "stood 146 candidates against Labour's 126. The driver is the "
        "absolute value in |bias| itself, which has a corner at zero. A "
        "party whose level error already sits near zero - Green's "
        "baseline bias is +0.25 - has resampled biases that fall on "
        "both sides of that corner and get folded together, widening "
        "and skewing its interval. So a well-calibrated party is "
        "intrinsically the hardest place to certify a level change, "
        "and Green's undetectable cell should be read as that, not as "
        "a weaker measurement of the same kind. The same mechanism "
        "explains 2021 Labour (bias +3.74 but volatile across "
        "contests; threshold 3.99, observed 1.05, inside the blind "
        "zone).", "",
    ]
    flagged = [r for r in rows if r.get("asymmetric")]
    groups = sorted({f"{r['island']}/{r['scope']}" for r in flagged})
    where = (f", all of them in {groups[0]}" if len(groups) == 1
             else f", in {', '.join(groups)}" if groups else "")
    lines += [
        f"Caveats: normal-approximation SE from percentile-interval "
        f"width; asymmetric intervals (bootstrap mean off-centre by more "
        f"than a tenth of the half-width) are flagged per row and the "
        f"symmetric half-width is used regardless - {len(flagged)} of "
        f"{len(rows)} comparisons are flagged{where}, which is the "
        f"six-contest corner where the normal approximation is weakest, "
        f"so its resolution figure is an approximation, not a sharp "
        f"threshold; every MDE is conditional on this frozen design - "
        f"features, fitting cells and contest counts - not a claim "
        f"about news effects in general.", "",
    ]
    return "\n".join(lines)


def main() -> None:
    experiment = json.loads(EXPERIMENT.read_text(encoding="utf-8"))
    unblinding = json.loads(UNBLINDING.read_text(encoding="utf-8"))
    annex = json.loads(ANNEX.read_text(encoding="utf-8"))

    rows = (comparisons_2021(experiment) + comparisons_2026(unblinding)
            + comparisons_annex(annex))
    # 18 confirmed 2021 windows x {overall, Reform} + 24 confirmatory 2026
    # cells + the annex: 18 specs x (6 parties + contrast) on 2021 and
    # 12 x (5 parties + contrast) on 2026 - UKIP stood in 2021 only.
    expected = 18 * 2 + 24 + 18 * 7 + 12 * 6
    if len(rows) != expected:
        raise AssertionError(f"expected {expected} rows, built {len(rows)}")
    summary = summarise(rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "mde_results.json").write_text(
        json.dumps({"status": STATUS, "z_95": Z95, "z_80": Z80,
                    "mde80_factor": round(MDE80_FACTOR, 6),
                    "summary": summary, "comparisons": rows},
                   indent=2) + "\n", encoding="utf-8")

    columns = ["island", "scope", "party", "arm", "window", "observed_delta",
               "ci_lower", "ci_upper", "contests", "status", "half_width",
               "se_normal_approx", "mde_50_power", "mde_80_power",
               "asymmetric"]
    with (OUTPUT_DIR / "mde_table.csv").open("w", newline="",
                                             encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns,
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})

    (OUTPUT_DIR / "mde_findings.md").write_text(
        render_findings(rows, summary), encoding="utf-8")
    print(f"{len(rows)} comparisons, {len(summary)} summary groups "
          f"-> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
