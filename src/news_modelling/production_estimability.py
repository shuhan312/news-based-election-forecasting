"""Audit whether the production news table can support the planned models.

This module deliberately fits nothing.  The production feature table has only
two pre-2026 principal elections with Stage 1 out-of-fold predictions (2017
and 2021), and Reform UK appears in only the latter.  A modelling command that
ignores that fact can still return coefficients and an error score; those
numbers would look precise without providing a reproducible Reform-specific
estimate.

The audit therefore freezes the smallest defensible next-stage design:

* the 1,632-article canonical release and the supervisor-confirmed six windows;
* combined and national features as exploratory pre-2026 comparisons;
* local features as a sensitivity analysis, because their training variation
  is below the repository's reporting threshold;
* 2026 as an unreachable holdout for feature or model selection; and
* no claim of a Reform-specific learned news effect, because there are zero
  Reform observations in the 2017 fitting election.

The result is a machine-readable report that a later training command must
consume rather than re-deciding these rules after seeing validation results.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


WINDOWS = (
    "180_to_91_days",
    "90_to_31_days",
    "30_to_15_days",
    "14_to_8_days",
    "7_to_4_days",
    "final_72_hours",
)

# Keep the feature budget at two per arm.  With one fitting election, trying
# many topics, frames and transformations would be outcome-guided screening,
# not model development.  Shares reduce sensitivity to unequal search depth;
# a structurally undefined share is handled explicitly below, never by a
# general-purpose imputer.
FEATURE_SETS = {
    "combined_exploratory": (
        "party_article_share",
        "net_portrayal_share",
    ),
    "national_exploratory": (
        "national_party_article_share",
        "national_net_portrayal_share",
    ),
    "local_sensitivity": (
        "local_party_article_share",
        "local_net_portrayal_share",
    ),
}

# Each share has a denominator already present in the table.  A blank is only
# a structural zero when that denominator is zero.  Any other blank is a real
# missing value and must stop the model rather than being silently filled.
SHARE_DENOMINATORS = {
    "party_article_share": "article_count",
    "net_portrayal_share": "party_article_count",
    "national_party_article_share": "national_article_count",
    "national_net_portrayal_share": "national_party_article_count",
    "local_party_article_share": "local_article_count",
    "local_net_portrayal_share": "local_party_article_count",
}

NEWS_TO_BASELINE_ELECTION = {
    "SCC-2017-05": "surrey-county-council-2017",
    "SCC-2021-05": "surrey-county-council-2021",
}


class ProductionAuditError(RuntimeError):
    """The frozen news inputs are internally inconsistent or unsafe to use."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _validate_structural_missingness(rows: list[dict[str, str]]) -> dict:
    """Prove every blank selected share is caused by a zero denominator.

    The later estimator may map these specific blanks to zero: no coverage
    means no volume or portrayal signal.  It may not apply blanket imputation,
    because that would make extraction failures indistinguishable from no
    news.  Returning counts makes the policy visible in the report.
    """

    result = {}
    # Preserve the declared feature-set order.  Iterating a set here made the
    # JSON key order depend on Python's per-process hash seed, even though the
    # audited values were identical.
    for feature in (item for values in FEATURE_SETS.values() for item in values):
        denominator = SHARE_DENOMINATORS[feature]
        structural = 0
        invalid = []
        for row in rows:
            if row[feature] != "":
                continue
            if float(row[denominator]) == 0:
                structural += 1
            else:
                invalid.append(
                    f"{row['election_id']}|{row['standard_party_key']}|"
                    f"{row['period']}"
                )
        if invalid:
            raise ProductionAuditError(
                f"{feature} has {len(invalid)} blank value(s) with a non-zero "
                f"{denominator}; first keys: {invalid[:5]}"
            )
        result[feature] = {
            "blank_values": structural,
            "allowed_only_when": f"{denominator} == 0",
            "model_value_for_structural_blank": 0.0,
        }
    return result


def build_estimability_report(
    feature_table: str | Path,
    metadata_path: str | Path,
    out_of_fold_path: str | Path,
) -> dict:
    """Validate the frozen inputs and return the permitted analysis design."""

    feature_rows = _read_csv(Path(feature_table))
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    out_of_fold = _read_csv(Path(out_of_fold_path))

    keys = {
        (r["election_id"], r["standard_party_key"], r["period"])
        for r in feature_rows
    }
    expected_rows = (
        len(metadata["elections"])
        * len(metadata["parties"])
        * len(metadata["periods"])
    )
    if len(feature_rows) != len(keys) or len(feature_rows) != expected_rows:
        raise ProductionAuditError(
            "Feature table is not a complete unique election x party x period "
            f"grid: rows={len(feature_rows)}, unique_keys={len(keys)}, "
            f"expected={expected_rows}."
        )
    if metadata["rows"] != expected_rows or metadata["expected_rows"] != expected_rows:
        raise ProductionAuditError("Feature metadata does not match the table grid.")

    actual_windows = tuple(
        p for p in metadata["periods"] if p in WINDOWS
    )
    if actual_windows != WINDOWS:
        raise ProductionAuditError(
            f"Confirmed six-window scheme changed: {actual_windows!r}."
        )
    if metadata["unique_articles"] != metadata["corpus_size"]:
        raise ProductionAuditError(
            "Feature extraction does not cover the full canonical corpus."
        )

    # The selection path may read only OOF development rows.  Seeing a 2026
    # row here is a hard failure, even if a caller promises not to use it.
    leaked_oof = [r for r in out_of_fold if "2026" in r.get("election_id", "")]
    if leaked_oof:
        raise ProductionAuditError(
            f"2026 appears in {len(leaked_oof)} out-of-fold row(s)."
        )
    both_parties = [
        r["candidate_contest_id"] for r in out_of_fold
        if _truthy(r.get("is_reform_uk")) and _truthy(r.get("is_ukip"))
    ]
    if both_parties:
        raise ProductionAuditError(
            f"{len(both_parties)} row(s) merge Reform UK and UKIP labels."
        )

    shared = {}
    for news_id, baseline_id in NEWS_TO_BASELINE_ELECTION.items():
        rows = [r for r in out_of_fold if r["election_id"] == baseline_id]
        shared[news_id] = {
            "baseline_election_id": baseline_id,
            "out_of_fold_candidate_rows": len(rows),
            "reform_uk_rows": sum(_truthy(r.get("is_reform_uk")) for r in rows),
            "ukip_rows": sum(_truthy(r.get("is_ukip")) for r in rows),
        }

    if shared["SCC-2017-05"]["out_of_fold_candidate_rows"] == 0:
        raise ProductionAuditError("2017 has no Stage 1 out-of-fold baseline.")
    if shared["SCC-2021-05"]["out_of_fold_candidate_rows"] == 0:
        raise ProductionAuditError("2021 has no Stage 1 out-of-fold baseline.")

    feature_status = {}
    for name, columns in FEATURE_SETS.items():
        verdicts = {
            column: metadata["training_variation"][column]["verdict"]
            for column in columns
        }
        feature_status[name] = {
            "columns": list(columns),
            "column_verdicts": verdicts,
            "analysis_role": (
                "sensitivity_only" if name == "local_sensitivity"
                else "exploratory_primary_comparison"
            ),
        }

    roles = Counter(r["split_role"] for r in feature_rows)
    # Derive the reserved election names from the feature split only.  This
    # selection gate intentionally has no argument or code path for opening
    # Stage 1's holdout predictions: "read but do not use" is weaker protection
    # than making the outcomes unreachable.
    holdout_elections = sorted({
        r["election_id"] for r in feature_rows if r["split_role"] == "test"
    })
    return {
        "status": "exploratory_news_modelling_permitted_with_limits",
        "canonical_release": {
            "release_id": metadata["canonical_corpus_release_id"],
            "articles": metadata["corpus_size"],
            "local_articles": metadata["canonical_corpus_by_arm"]["local"],
            "national_articles": metadata["canonical_corpus_by_arm"]["national"],
        },
        "feature_table": {
            "grain": metadata["grain"],
            "rows": len(feature_rows),
            "expected_rows": expected_rows,
            "split_role_rows": dict(roles),
            "windows": list(WINDOWS),
            "cumulative_periods": [
                p for p in metadata["periods"] if p not in WINDOWS
            ],
            "zero_article_cells": len(metadata["zero_article_cells"]),
            "structural_missingness": _validate_structural_missingness(feature_rows),
        },
        "frozen_feature_sets": feature_status,
        "baseline_overlap": shared,
        "holdout_protection": {
            "out_of_fold_2026_rows": 0,
            "holdout_elections": holdout_elections,
            "stage1_holdout_file_read": False,
            "rule": (
                "Do not read 2026 outcomes, metrics or residuals during feature, "
                "window, hyperparameter or architecture selection."
            ),
        },
        "estimability": {
            "reform_specific_news_coefficient": "not_estimable",
            "reason": (
                "The only principal fitting election with a Stage 1 OOF "
                "baseline is 2017, which has zero Reform UK candidate rows. "
                "Reform appears only in the 2021 validation election."
            ),
            "party_generic_news_adjustment": "exploratory_only",
            "permitted_design": (
                "Fit the pre-specified two-feature adjustment on 2017 parties "
                "and evaluate once on 2021; report Reform's six candidate rows "
                "separately, without interpreting a coefficient as Reform-specific."
            ),
            "local_news_effect": "sensitivity_only_not_confirmatory",
            "local_reason": (
                "Local feature variation is below the repository's ten-cell "
                "reporting threshold and the feature grain cannot explain "
                "differences between Surrey divisions."
            ),
        },
        "next_model_step": {
            "primary_comparisons": [
                "baseline versus combined_exploratory",
                "baseline versus national_exploratory",
            ],
            "sensitivity_comparison": "baseline versus local_sensitivity",
            "period_policy": (
                "Fit each of the six confirmed windows separately; treat "
                "cumulative periods as sensitivity analyses and do not select "
                "the best-looking window on 2021."
            ),
            "minimum_reporting": [
                "baseline and news-enhanced MAE on identical 2021 rows",
                "Reform-only 2021 errors with n=6 stated prominently",
                "all-party results separated from Reform results",
                "no causal wording",
                "local result labelled sensitivity-only",
            ],
        },
    }


def write_report(report: dict, output: str | Path) -> None:
    """Write the audit deterministically so it can be versioned and reviewed."""

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
