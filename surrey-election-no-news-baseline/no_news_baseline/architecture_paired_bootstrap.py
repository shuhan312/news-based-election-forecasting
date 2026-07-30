"""Is one architecture's advantage over another distinguishable from noise?

## Why this exists

The architecture comparison reports a mean absolute error per architecture per
fold, and the selection rule reads those point estimates. Nothing in the
project measured whether the *difference* between two architectures survives
resampling - so a 0.10-point gap and a 1.00-point gap were treated as the same
kind of evidence, differing only in whether they cleared a 5% threshold.

That gap in the evidence produced a real error. Architecture C's overall MAE is
0.10 lower than A's out of fold, and that was described in this project's own
working notes as C "beating A on every adequately-sampled metric". Bootstrapped,
the difference is **+0.103 with a 95% interval of [-0.385, +0.597]** - it
contains zero, and C is the better model in only 67% of resamples. The two are
not distinguishable, and the ranking of their point estimates said nothing.

## Method

Paired, and resampled by contest rather than by row. Paired because both
architectures predict the same rows, so their errors are correlated and the
difference has a much smaller variance than either error alone. By contest
because candidate shares within a contest sum to 100 - rows are not independent
observations, and row-level resampling reports an interval far narrower than
the data supports. This is the same resampling unit and seed the rest of the
project uses, so an interval from here is comparable to one from
`candidate_metrics`.

The input is two bundles' `out_of_fold_predictions.csv`, which carry the
project's own `absolute_error` column - recomputing it here would risk two
slightly different definitions of the thing being compared.

## What it cannot tell you

Whether a difference matters. An interval excluding zero says the difference is
real at this sample size, not that it is large enough to buy extra complexity;
that remains the materiality threshold's job. And an interval containing zero
is not evidence of equivalence - on 14 Reform rows the interval spans 1.6
points, wide enough to hide a difference that would matter a great deal.

Usage:
    PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \\
        -m no_news_baseline.architecture_paired_bootstrap \\
        outputs/model_bundle_paired_A outputs/model_bundle_paired_C
"""

from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# The project's resampling settings, repeated here rather than imported so a
# reader of this module can see what it did without following a reference.
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260728

# Only out-of-fold rows are compared. Holdout rows are excluded by construction:
# an architecture may not be chosen on the holdout, so measuring the difference
# there would produce a number nobody is allowed to act on.
COMPARED_SPLIT_ROLE = "rolling_origin_fold"


@dataclass(frozen=True)
class Row:
    """One prediction's absolute error, with the keys needed to pair and resample."""

    error: float
    contest: str
    is_reform: bool


def load_errors(bundle: Path, split_role: str = COMPARED_SPLIT_ROLE
                ) -> dict[tuple[str, str], Row]:
    """Absolute errors from one bundle, keyed by (split, candidate-contest).

    The key has to include the split: a candidate-contest appears in several
    rolling folds, and pairing on the contest alone would silently collapse
    them.
    """
    path = bundle / "out_of_fold_predictions.csv"
    out: dict[tuple[str, str], Row] = {}
    with path.open(newline="") as handle:
        for r in csv.DictReader(handle):
            if r["split_role"] != split_role or not r["absolute_error"]:
                continue
            out[(r["split_id"], r["candidate_contest_id"])] = Row(
                error=float(r["absolute_error"]),
                contest=f'{r["election_id"]}|{r["division_id"]}',
                is_reform=r["is_reform_uk"].strip().lower() in ("true", "1", "yes"),
            )
    if not out:
        raise SystemExit(
            f"{path} has no {split_role} rows with an absolute_error. A bundle "
            f"trained without rolling-origin folds cannot be compared this way.")
    return out


def _mae(rows: dict, keys) -> float:
    return sum(rows[k].error for k in keys) / len(keys)


def paired_interval(left: dict, right: dict, keys: list, *,
                    resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = BOOTSTRAP_SEED) -> dict:
    """Bootstrap the paired MAE difference (left minus right) over contests.

    A positive difference means `right` has the lower error. Contests are drawn
    with replacement to their original count, and every row of a drawn contest
    goes in together - that is what makes the interval respect the fact that a
    contest's rows are one observation, not several.
    """
    by_contest: dict[str, list] = defaultdict(list)
    for k in keys:
        by_contest[left[k].contest].append(k)
    contests = list(by_contest)
    rng = random.Random(seed)

    differences = []
    for _ in range(resamples):
        drawn = [rng.choice(contests) for _ in contests]
        sampled = [k for c in drawn for k in by_contest[c]]
        if sampled:
            differences.append(_mae(left, sampled) - _mae(right, sampled))
    differences.sort()
    lo = differences[int(0.025 * len(differences))]
    hi = differences[int(0.975 * len(differences))]
    point = _mae(left, keys) - _mae(right, keys)
    return {
        "rows": len(keys),
        "contests": len(contests),
        "left_mae": round(_mae(left, keys), 4),
        "right_mae": round(_mae(right, keys), 4),
        "difference": round(point, 4),
        "ci_lower": round(lo, 4),
        "ci_upper": round(hi, 4),
        # Whether the interval excludes zero. Named for what it is - a statement
        # about this sample size - rather than as "significant", which would
        # invite reading it as "important".
        "distinguishable_at_this_sample_size": bool(lo > 0 or hi < 0),
        "share_of_resamples_favouring_right": round(
            sum(1 for d in differences if d > 0) / len(differences), 4),
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    left_bundle, right_bundle = Path(sys.argv[1]), Path(sys.argv[2])
    left, right = load_errors(left_bundle), load_errors(right_bundle)

    shared = sorted(set(left) & set(right))
    if not shared:
        raise SystemExit(
            "The two bundles share no out-of-fold rows. They were probably "
            "trained on different splits, and a paired comparison is not "
            "defined across different splits.")
    dropped_left = len(left) - len(shared)
    dropped_right = len(right) - len(shared)

    reform = [k for k in shared if left[k].is_reform]
    report = {
        "left_bundle": str(left_bundle),
        "right_bundle": str(right_bundle),
        "split_role": COMPARED_SPLIT_ROLE,
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED,
        "paired_rows": len(shared),
        "unpaired_rows_dropped": {"left": dropped_left, "right": dropped_right},
        "all_candidates": paired_interval(left, right, shared),
        "reform_only": (paired_interval(left, right, reform)
                        if len(reform) >= 5 else
                        {"rows": len(reform),
                         "note": "fewer than 5 Reform rows; no interval computed"}),
        "reading": ("difference is left minus right, so positive means the "
                    "right-hand bundle has the lower error. An interval "
                    "containing zero means the two are not distinguishable at "
                    "this sample size - not that they are equivalent."),
    }

    out = Path("surrey-election-no-news-baseline/outputs/"
               f"architecture_paired_bootstrap_"
               f"{left_bundle.name}_vs_{right_bundle.name}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    for label, block in (("all candidates", report["all_candidates"]),
                         ("Reform only", report["reform_only"])):
        if "difference" not in block:
            print(f"  {label}: {block['note']}")
            continue
        verdict = ("distinguishable" if block["distinguishable_at_this_sample_size"]
                   else "NOT distinguishable")
        print(f"  {label}: {block['contests']} contests / {block['rows']} rows")
        print(f"    {block['left_mae']:.3f} vs {block['right_mae']:.3f}  "
              f"difference {block['difference']:+.3f}  "
              f"95% CI [{block['ci_lower']:+.3f}, {block['ci_upper']:+.3f}]  "
              f"{verdict}")
        print(f"    right-hand bundle better in "
              f"{block['share_of_resamples_favouring_right']:.1%} of resamples")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
