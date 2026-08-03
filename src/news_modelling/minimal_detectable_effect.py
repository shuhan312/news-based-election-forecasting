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
3. Reform level-error changes and the Reform-minus-group contrast from
   the per-party bootstrap annex, both islands - the resolution of the
   tide-gauge reading itself.

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
from pathlib import Path
from statistics import median

EXPERIMENT = Path(
    "news_features/production_news_experiment_v1/experiment_results.json")
UNBLINDING = Path("news_features/unblinding_2026_v1/unblinding_results.json")
ANNEX = Path(
    "news_features/per_party_bootstrap_v1/per_party_bootstrap_results.json")
OUTPUT_DIR = Path("news_features/minimal_detectable_effect_v1")

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


def comparisons_2021(experiment: dict) -> list[dict]:
    """Overall and Reform-specific rows for the 18 confirmed windows."""

    rows = []
    for spec in experiment["specification_results"]:
        if spec["period_role"] != "confirmed_window":
            continue
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
                "arm": spec["analysis"],
                "window": spec["period"],
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
        for entry in unblinding["files"][version]:
            if entry["family"] != "confirmatory":
                continue
            interval = entry["metrics"]["bootstrap_news_vs_recalibrated"]
            rows.append({
                "island": f"holdout_2026_{version}",
                "scope": "overall_mae",
                "arm": entry["analysis"],
                "window": entry["period"],
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
    """Reform level-change and contrast rows from the bootstrap annex.

    These intervals are on |bias| changes (level errors), not MAE
    deltas, so they state the resolution of the tide-gauge reading:
    how small a Reform level shift, or a Reform-versus-group gap, the
    islands could certify.
    """

    quantity = "abs_bias_change_vs_recalibrated"
    rows = []
    for spec in annex["specifications"]:
        for scope, unit in (("reform_level", "reform_uk"),
                            ("reform_vs_group_contrast", "contrast")):
            interval = spec["bootstrap"]["units"][unit][quantity]
            if "ci_lower" not in interval:
                continue
            observed = (spec["parties"]["reform_uk"][quantity]
                        if unit == "reform_uk"
                        else spec["contrast_point"][quantity])
            rows.append({
                "island": spec["island"],
                "scope": scope,
                "arm": spec["analysis"],
                "window": spec["period"],
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
    """Median and range of MDE80 per island x scope - the quotable form."""

    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["island"], row["scope"])].append(row)
    out = []
    for (island, scope), members in sorted(grouped.items()):
        estimable = [m["mde_80_power"] for m in members
                     if m["status"] == "ok"]
        entry = {"island": island, "scope": scope,
                 "comparisons": len(members),
                 "estimable": len(estimable),
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
        "| island | scope | comparisons | median MDE80 | range |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for entry in summary:
        if entry.get("median_mde_80") is None:
            lines.append(f"| {entry['island']} | {entry['scope']} | "
                         f"{entry['comparisons']} | - | all structural zero |")
            continue
        note = (f" ({entry['structural_zero']} structural-zero excluded)"
                if entry["structural_zero"] else "")
        lines.append(
            f"| {entry['island']} | {entry['scope']} | "
            f"{entry['comparisons']}{note} | {entry['median_mde_80']} | "
            f"[{entry['min_mde_80']}, {entry['max_mde_80']}] |")

    by_key = {(e["island"], e["scope"]): e for e in summary}
    overall_2021 = by_key[("validation_2021", "overall_mae")]
    reform_2021 = by_key[("validation_2021", "reform_mae")]
    overall_v2 = by_key[("holdout_2026_v2", "overall_mae")]
    lines += [
        "", "## Reading", "",
        f"The pre-2026 verdict now states its own resolution: the 0-of-18 "
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
    expected = 18 * 2 + 24 + 30 * 2
    if len(rows) != expected:
        raise AssertionError(f"expected {expected} rows, built {len(rows)}")
    summary = summarise(rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "mde_results.json").write_text(
        json.dumps({"status": STATUS, "z_95": Z95, "z_80": Z80,
                    "mde80_factor": round(MDE80_FACTOR, 6),
                    "summary": summary, "comparisons": rows},
                   indent=2) + "\n", encoding="utf-8")

    columns = ["island", "scope", "arm", "window", "observed_delta",
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
