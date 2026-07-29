"""Load and validate the frozen Stage 1 model bundle.

Prompt 2's first requirement: "Load and validate the model bundle produced by
Stage 1... The application must fail safely if the selected Stage 1 model
bundle is incomplete or incompatible", and "Do not alter or overwrite the
Stage 1 model bundle."

This module is the only route by which the news layer touches Stage 1, and it
opens everything read-only. That is not politeness. Stage 1's out-of-fold
predictions are the thing the residual model is measured against; if the news
layer could write to the bundle, a disappointing news result and a quietly
regenerated baseline would be indistinguishable afterwards.

What "compatible" means here
----------------------------
Not merely "the files exist". The checks below are the ones whose failure
would produce a news model that trains on the wrong thing while reporting
success:

- **the manifest hashes still match**, so the metrics describing the bundle
  describe the files actually being read;
- **out-of-fold predictions exist and are unique per row**, because the
  residual is defined per candidate and two predictions for one candidate
  would silently pick whichever was read last;
- **out-of-fold predictions are not in-sample fits** — Prompt 2 is explicit
  that the news layer must train on out-of-fold predictions, and the split
  role recorded on each row is what proves they are;
- **Reform UK and UKIP labels are present and never both set**, which is the
  separation requirement restated as a property of the data.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

# The files Prompt 1 requires a bundle to contain. A bundle missing any of
# them is incomplete, whatever else it holds.
REQUIRED_FILES: tuple[str, ...] = (
    "model.pkl", "preprocessor.pkl", "architecture.json", "feature_schema.json",
    "feature_dictionary.csv", "leakage_audit.csv", "split_manifest.csv",
    "training_rows.csv", "out_of_fold_predictions.csv", "holdout_predictions.csv",
    "metrics.json", "reform_metrics.json", "data_quality_report.json",
    "model_card.md", "requirements-lock.txt", "training_config.yaml",
)

# Out-of-fold predictions must come from rolling-origin folds. A row carrying
# any other split role is a holdout or development prediction and must not be
# used as a baseline for residual training.
OUT_OF_FOLD_ROLE = "rolling_origin_fold"


class BundleIncompatible(RuntimeError):
    """The Stage 1 bundle cannot be used as a baseline.

    A distinct type so a caller can tell "this bundle is unusable" from "this
    model failed to fit". The first is fixed by rebuilding Stage 1; the second
    is not.
    """


@dataclass(frozen=True)
class Stage1Bundle:
    """A validated, read-only view of the Stage 1 bundle."""

    directory: Path
    architecture: dict
    metrics: dict
    reform_metrics: dict
    manifest: dict
    out_of_fold: tuple[dict, ...]
    holdout: tuple[dict, ...]
    split_manifest: tuple[dict, ...]
    warnings: tuple[str, ...] = field(default=())

    # -- the facts the news layer needs to display -------------------------

    @property
    def bundle_version(self) -> str:
        return str(self.architecture.get("bundle_version", "unknown"))

    @property
    def selected_architecture(self) -> str:
        return str(self.architecture.get("selected_model_type", "unknown"))

    @property
    def training_date(self) -> str:
        return str(self.architecture.get("training_date", "unknown"))

    @property
    def reform_rows_out_of_fold(self) -> int:
        return sum(1 for row in self.out_of_fold if _truthy(row.get("is_reform_uk")))

    def summary(self) -> dict:
        """What Prompt 2 asks the application to display after loading."""

        overall = self.metrics.get("out_of_fold", {}).get("overall", {})
        holdout = self.metrics.get("primary_holdout", {}).get("overall", {})
        reform = self.reform_metrics.get("out_of_fold", {}).get("reform_uk", {})
        selection = self.architecture.get("selection", {})
        return {
            "bundle_version": self.bundle_version,
            "selected_architecture": self.selected_architecture,
            "selected_automatically": selection.get("selected_automatically"),
            "training_date": self.training_date,
            "packages": self.architecture.get("packages", {}),
            "random_seed": self.architecture.get("random_seed"),
            "baseline_out_of_fold_rows": len(self.out_of_fold),
            "baseline_out_of_fold_mae": overall.get("mae"),
            "baseline_holdout_mae": holdout.get("mae"),
            "reform_out_of_fold_rows": self.reform_rows_out_of_fold,
            "reform_out_of_fold_mae": reform.get("mae"),
            "reform_small_sample_warning": self.reform_metrics.get(
                "out_of_fold", {}).get("small_sample_warning"),
            "split_method": self.architecture.get("split_method"),
            "holdout_elections": sorted({
                str(row["election_id"]) for row in self.holdout
            }),
            # Carried forward rather than summarised, because a news result
            # reported without the baseline's own limitations reads as though
            # the baseline had none.
            "known_limitations_reference": "docs/candidate_model_card.md",
            "warnings": list(self.warnings),
        }


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> tuple[dict, ...]:
    with path.open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle))


def load_stage1_bundle(
    directory: str | Path,
    *,
    verify_hashes: bool = True,
) -> Stage1Bundle:
    """Read the bundle, check it, and return it. Never writes.

    ``verify_hashes`` compares every file against ``bundle_manifest.json``.
    Left on by default: the manifest exists precisely so a later stage can
    prove it loaded the bundle a set of metrics describes, and a verification
    that is off by default is one nobody runs.
    """

    path = Path(directory)
    if not path.is_dir():
        raise BundleIncompatible(f"Stage 1 bundle directory not found: {path}")

    missing = [name for name in REQUIRED_FILES if not (path / name).exists()]
    if missing:
        raise BundleIncompatible(
            f"Stage 1 bundle at {path} is incomplete. Missing: {missing}. "
            "Rebuild it with `python -m no_news_baseline.cli train`."
        )

    warnings: list[str] = []

    manifest_path = path / "bundle_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    if verify_hashes and manifest.get("files"):
        mismatched = []
        for name, expected in manifest["files"].items():
            candidate = path / name
            if not candidate.exists():
                mismatched.append(f"{name} (missing)")
                continue
            actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual != expected:
                mismatched.append(f"{name} (hash differs)")
        if mismatched:
            raise BundleIncompatible(
                f"Stage 1 bundle at {path} does not match its own manifest: "
                f"{mismatched}. The metrics in this bundle describe different "
                "files from the ones on disk; rebuild rather than proceed."
            )
    elif verify_hashes:
        warnings.append(
            "bundle_manifest.json is absent or empty, so file integrity was "
            "not verified."
        )

    architecture = _read_json(path / "architecture.json")
    out_of_fold = _read_csv(path / "out_of_fold_predictions.csv")
    holdout = _read_csv(path / "holdout_predictions.csv")
    split_manifest = _read_csv(path / "split_manifest.csv")

    _validate_predictions(out_of_fold, warnings)

    bundle = Stage1Bundle(
        directory=path,
        architecture=architecture,
        metrics=_read_json(path / "metrics.json"),
        reform_metrics=_read_json(path / "reform_metrics.json"),
        manifest=manifest,
        out_of_fold=out_of_fold,
        holdout=holdout,
        split_manifest=split_manifest,
        warnings=tuple(warnings),
    )
    return bundle


def _validate_predictions(rows: tuple[dict, ...], warnings: list[str]) -> None:
    """Check the out-of-fold table is what the residual model requires."""

    if not rows:
        raise BundleIncompatible(
            "out_of_fold_predictions.csv is empty. The residual model has "
            "nothing to compute a residual against."
        )

    required = {
        "candidate_contest_id", "election_id", "division_id", "split_role",
        "standard_party_name", "is_reform_uk", "is_ukip",
        "predicted_vote_share", "observed_vote_share",
    }
    absent = sorted(required - set(rows[0]))
    if absent:
        raise BundleIncompatible(
            f"out_of_fold_predictions.csv lacks required columns: {absent}"
        )

    identifiers = [str(row["candidate_contest_id"]) for row in rows]
    if len(identifiers) != len(set(identifiers)):
        duplicated = len(identifiers) - len(set(identifiers))
        raise BundleIncompatible(
            f"{duplicated} candidate row(s) carry more than one out-of-fold "
            "prediction. A residual is defined per candidate, so which "
            "prediction is used would depend on read order."
        )

    # Prompt 2: "Training uses Stage 1 out-of-fold predictions." A row from
    # any other split role is an in-sample or holdout figure and would make
    # the residual an artefact of the baseline having seen the row.
    wrong_role = {
        str(row.get("split_role")) for row in rows
        if str(row.get("split_role")) != OUT_OF_FOLD_ROLE
    }
    if wrong_role:
        raise BundleIncompatible(
            f"out_of_fold_predictions.csv contains rows with split roles "
            f"{sorted(wrong_role)}. Only {OUT_OF_FOLD_ROLE!r} rows are "
            "genuinely out of fold."
        )

    both = [
        str(row["candidate_contest_id"]) for row in rows
        if _truthy(row.get("is_reform_uk")) and _truthy(row.get("is_ukip"))
    ]
    if both:
        raise BundleIncompatible(
            f"{len(both)} row(s) are labelled both Reform UK and UKIP. The two "
            "parties must remain separate throughout."
        )

    unscored = sum(
        1 for row in rows
        if str(row.get("observed_vote_share", "")).strip() in {"", "None"}
    )
    if unscored:
        warnings.append(
            f"{unscored} out-of-fold row(s) have no observed vote share and "
            "cannot contribute a residual."
        )
