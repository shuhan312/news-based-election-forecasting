"""One file where every tunable assumption in the baseline is written down.

Why this module exists
----------------------
The brief asks for "configuration files rather than hardcoded assumptions",
a "command-line training option", a configurable random seed, and a *manual*
architecture-selection mode beside the automatic one. Until now each of those
values lived as a constant inside whichever module happened to use it:
``MATERIAL_IMPROVEMENT`` in the selection module, ``BOOTSTRAP_SEED`` in the
metrics module, ``MIN_CONTESTS_FOR_COUNTY_STRENGTH`` in the strength module.
Individually each was documented; collectively there was no single place a
reader could look to see what the run assumed, and no way to change one
without editing source.

The defaults are not duplicated here
------------------------------------
A configuration layer that restates its own defaults acquires a second copy
of every number, and the two copies drift. So the module constants remain the
single source of each default, :meth:`BaselineConfig.defaults` reads them, and
a configuration file overrides only the keys it names. The shipped
``config/baseline_model.yaml`` does state every value explicitly, because a
file a supervisor reads should be complete rather than half-empty - and
``tests/test_configuration.py`` asserts that what it states still equals the
module defaults, so the redundancy is checked rather than trusted.

Unknown keys are an error
-------------------------
A misspelled key that is silently ignored is the worst failure mode a
configuration file has: the run reports success, the setting never applied,
and nothing anywhere records the difference. Every mapping is validated
against its known keys and an unknown one stops the run.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

import yaml

from .candidate_architecture_selection import (
    COMPLEXITY_ORDER,
    MATERIAL_IMPROVEMENT,
    MAX_ADVERSE_FOLDS,
    MIN_DEVELOPMENT_FOLDS,
    PRIMARY_CRITERION,
)
from .candidate_boosted_model import BOOSTING_PARAMS
from .candidate_historical_strength import (
    MIN_CONTESTS_FOR_COUNTY_STRENGTH,
    POOLING_WINDOW_YEARS,
)
from .candidate_metrics import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED

# The default configuration file, anchored to this package rather than to the
# working directory. The previous value was relative to the repository root,
# so it resolved only for a process launched from there - running the app or
# the test suite from inside this project raised "Configuration file not
# found" for a file that was present the whole time.
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config/baseline_model.yaml"
)

# "auto" runs the two selection gates. Any other value names the architecture
# to ship regardless, which is the brief's manual mode.
AUTO = "auto"


class ConfigurationError(ValueError):
    """A configuration file is malformed, or names something that cannot work.

    A distinct type so a caller can tell a bad configuration from a bad model:
    the first is fixed by editing a file, the second is not.
    """


def _require_mapping(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{where} must be a mapping, found {type(value).__name__}")
    return dict(value)


def _reject_unknown(given: Mapping[str, Any], known: tuple[str, ...], where: str) -> None:
    """Stop on any key that is not recognised.

    Silently ignoring a typo is how a configuration file comes to describe a
    run that never happened.
    """

    unknown = sorted(set(given) - set(known))
    if unknown:
        raise ConfigurationError(
            f"{where}: unknown key(s) {unknown}. Known keys are {list(known)}."
        )


@dataclass(frozen=True)
class PathsConfig:
    """Where the run reads from and writes to.

    Paths are interpreted relative to the working directory, which for every
    documented invocation is the repository root. They are stored as written
    so the bundle records the same strings the operator typed.
    """

    contract_directory: Path
    split_leakage_directory: Path
    output_directory: Path

    KEYS = ("contract_directory", "split_leakage_directory", "output_directory")


@dataclass(frozen=True)
class SelectionConfig:
    """How the shipped architecture is decided.

    ``mode`` is the brief's two-mode requirement in one field: ``auto`` runs
    the gates, anything else names the architecture to ship. A manual choice
    does not suppress the comparison - every architecture is still scored and
    the table still written, so a manual override remains visibly an override
    rather than a rewriting of the evidence.
    """

    mode: str
    compared: tuple[str, ...]
    primary_criterion: str
    material_improvement: float
    max_adverse_folds: int
    min_development_folds: int
    decision_split_id: str | None

    KEYS = (
        "mode", "compared", "primary_criterion", "material_improvement",
        "max_adverse_folds", "min_development_folds", "decision_split_id",
    )

    @property
    def is_automatic(self) -> bool:
        return self.mode == AUTO

    def validate(self) -> None:
        if not self.compared:
            raise ConfigurationError("selection.compared must list at least one architecture")
        unknown = [name for name in self.compared if name not in COMPLEXITY_ORDER]
        if unknown:
            raise ConfigurationError(
                f"selection.compared names unknown architecture(s) {unknown}. "
                f"Known architectures are {list(COMPLEXITY_ORDER)}."
            )
        if not self.is_automatic and self.mode not in self.compared:
            raise ConfigurationError(
                f"selection.mode={self.mode!r} is not among selection.compared "
                f"{list(self.compared)}. A manual choice must still be scored, "
                "otherwise the bundle would ship a model with no fold results."
            )
        if not 0.0 <= self.material_improvement < 1.0:
            raise ConfigurationError(
                "selection.material_improvement is a fraction and must satisfy "
                f"0 <= x < 1, found {self.material_improvement}"
            )
        if self.max_adverse_folds < 0:
            raise ConfigurationError("selection.max_adverse_folds must not be negative")
        if self.min_development_folds < 1:
            raise ConfigurationError(
                "selection.min_development_folds must be at least 1: a stability "
                "gate with nothing to check is not a gate."
            )


@dataclass(frozen=True)
class FeatureConfig:
    """The derived features and the two judgement calls inside them.

    ``county_strength_minimum_contests`` and the pooling window are the rule
    that decides when a party has enough earlier record to be given a county
    strength at all. Three and five years are defensible, not obvious, so they
    belong in a file rather than in a function default.
    """

    county_strength_minimum_contests: int
    county_strength_pooling_window_years: float
    reform_interactions: bool
    ukip_interactions: bool

    KEYS = (
        "county_strength_minimum_contests", "county_strength_pooling_window_years",
        "reform_interactions", "ukip_interactions",
    )

    def validate(self) -> None:
        if self.county_strength_minimum_contests < 1:
            raise ConfigurationError(
                "features.county_strength_minimum_contests must be at least 1"
            )
        if self.county_strength_pooling_window_years <= 0:
            raise ConfigurationError(
                "features.county_strength_pooling_window_years must be positive"
            )
        if self.ukip_interactions and not self.reform_interactions:
            raise ConfigurationError(
                "features.ukip_interactions requires features.reform_interactions. "
                "The UKIP block is the brief's labelled sensitivity extension of "
                "the Reform terms, never a substitute for them."
            )


@dataclass(frozen=True)
class EvaluationConfig:
    """Bootstrap settings. Both affect published intervals, so both are recorded."""

    bootstrap_resamples: int
    bootstrap_seed: int

    KEYS = ("bootstrap_resamples", "bootstrap_seed")

    def validate(self) -> None:
        if self.bootstrap_resamples < 1:
            raise ConfigurationError("evaluation.bootstrap_resamples must be at least 1")


@dataclass(frozen=True)
class BaselineConfig:
    """A whole run's assumptions, resolved and validated."""

    bundle_version: str
    boosting_seed: int
    paths: PathsConfig
    selection: SelectionConfig
    features: FeatureConfig
    evaluation: EvaluationConfig
    source_path: Path | None = None

    KEYS = (
        "bundle_version", "boosting_seed", "paths", "selection", "features",
        "evaluation",
    )

    # -- construction -----------------------------------------------------

    @classmethod
    def defaults(cls) -> "BaselineConfig":
        """The configuration the code uses when no file is supplied.

        Every value is read from the module that owns it, so this can never
        disagree with the constants; it is a view of them, not a copy.
        """

        return cls(
            bundle_version="candidate_model_bundle_v1",
            boosting_seed=int(BOOSTING_PARAMS["seed"]),
            paths=PathsConfig(
                contract_directory=Path(
                    "surrey-election-extractor/outputs/no_news_candidate_contests"
                ),
                split_leakage_directory=Path(
                    "surrey-election-no-news-baseline/outputs/candidate_split_leakage"
                ),
                output_directory=Path(
                    "surrey-election-no-news-baseline/outputs/model_bundle_v1"
                ),
            ),
            selection=SelectionConfig(
                mode=AUTO,
                compared=tuple(COMPLEXITY_ORDER),
                primary_criterion=PRIMARY_CRITERION,
                material_improvement=MATERIAL_IMPROVEMENT,
                max_adverse_folds=MAX_ADVERSE_FOLDS,
                min_development_folds=MIN_DEVELOPMENT_FOLDS,
                # None pools every development fold. Naming one split reads a
                # single fold, which is how an earlier version came to decide
                # on three Reform rows.
                decision_split_id=None,
            ),
            features=FeatureConfig(
                county_strength_minimum_contests=MIN_CONTESTS_FOR_COUNTY_STRENGTH,
                county_strength_pooling_window_years=POOLING_WINDOW_YEARS,
                reform_interactions=True,
                ukip_interactions=False,
            ),
            evaluation=EvaluationConfig(
                bootstrap_resamples=BOOTSTRAP_RESAMPLES,
                bootstrap_seed=BOOTSTRAP_SEED,
            ),
        )

    @classmethod
    def from_mapping(
        cls, document: Mapping[str, Any], *, source_path: Path | None = None
    ) -> "BaselineConfig":
        """Overlay a parsed document on the defaults and validate the result."""

        given = _require_mapping(document, "configuration root")
        _reject_unknown(given, cls.KEYS, "configuration root")
        base = cls.defaults()

        paths_given = _require_mapping(given.get("paths"), "paths")
        _reject_unknown(paths_given, PathsConfig.KEYS, "paths")
        paths = replace(base.paths, **{
            key: Path(str(paths_given[key]))
            for key in PathsConfig.KEYS
            if key in paths_given
        })

        selection_given = _require_mapping(given.get("selection"), "selection")
        _reject_unknown(selection_given, SelectionConfig.KEYS, "selection")
        selection_overrides: dict[str, Any] = {}
        for key in SelectionConfig.KEYS:
            if key not in selection_given:
                continue
            value = selection_given[key]
            if key == "compared":
                if not isinstance(value, (list, tuple)):
                    raise ConfigurationError("selection.compared must be a list")
                value = tuple(str(item) for item in value)
            elif key == "decision_split_id":
                value = None if value is None else str(value)
            elif key in {"mode", "primary_criterion"}:
                value = str(value)
            elif key == "material_improvement":
                value = float(value)
            else:
                value = int(value)
            selection_overrides[key] = value
        selection = replace(base.selection, **selection_overrides)

        features_given = _require_mapping(given.get("features"), "features")
        _reject_unknown(features_given, FeatureConfig.KEYS, "features")
        features = replace(base.features, **{
            key: (
                bool(features_given[key])
                if key.endswith("interactions")
                else (
                    float(features_given[key])
                    if key.endswith("years")
                    else int(features_given[key])
                )
            )
            for key in FeatureConfig.KEYS
            if key in features_given
        })

        evaluation_given = _require_mapping(given.get("evaluation"), "evaluation")
        _reject_unknown(evaluation_given, EvaluationConfig.KEYS, "evaluation")
        evaluation = replace(base.evaluation, **{
            key: int(evaluation_given[key])
            for key in EvaluationConfig.KEYS
            if key in evaluation_given
        })

        resolved = cls(
            bundle_version=str(given.get("bundle_version", base.bundle_version)),
            boosting_seed=int(given.get("boosting_seed", base.boosting_seed)),
            paths=paths,
            selection=selection,
            features=features,
            evaluation=evaluation,
            source_path=source_path,
        )
        resolved.validate()
        return resolved

    def validate(self) -> None:
        if not self.bundle_version:
            raise ConfigurationError("bundle_version must not be empty")
        self.selection.validate()
        self.features.validate()
        self.evaluation.validate()

    # -- provenance -------------------------------------------------------

    def as_record(self) -> dict[str, Any]:
        """The configuration as it will be written into the bundle.

        Written for every run, including runs that supplied no file, because
        "the defaults were used" is itself a fact a later reader needs and
        cannot recover from an absent key.
        """

        return {
            "bundle_version": self.bundle_version,
            "boosting_seed": self.boosting_seed,
            "config_file": str(self.source_path) if self.source_path else None,
            "config_source": "file" if self.source_path else "module_defaults",
            "paths": {
                "contract_directory": str(self.paths.contract_directory),
                "split_leakage_directory": str(self.paths.split_leakage_directory),
                "output_directory": str(self.paths.output_directory),
            },
            "selection": {
                "mode": self.selection.mode,
                "is_automatic": self.selection.is_automatic,
                "compared": list(self.selection.compared),
                "primary_criterion": self.selection.primary_criterion,
                "material_improvement": self.selection.material_improvement,
                "max_adverse_folds": self.selection.max_adverse_folds,
                "min_development_folds": self.selection.min_development_folds,
                "decision_split_id": self.selection.decision_split_id,
            },
            "features": {
                "county_strength_minimum_contests":
                    self.features.county_strength_minimum_contests,
                "county_strength_pooling_window_years":
                    self.features.county_strength_pooling_window_years,
                "reform_interactions": self.features.reform_interactions,
                "ukip_interactions": self.features.ukip_interactions,
            },
            "evaluation": {
                "bootstrap_resamples": self.evaluation.bootstrap_resamples,
                "bootstrap_seed": self.evaluation.bootstrap_seed,
            },
        }


def load_config(path: str | Path | None = None) -> BaselineConfig:
    """Read a configuration file, or return the defaults when none is given.

    An explicitly named file that does not exist is an error rather than a
    silent fall back to defaults: an operator who typed ``--config`` meant it,
    and a run that quietly ignored the argument would report figures that
    belong to a different configuration.
    """

    if path is None:
        return BaselineConfig.defaults()

    resolved = Path(path)
    if not resolved.exists():
        raise ConfigurationError(f"Configuration file not found: {resolved}")
    try:
        document = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigurationError(f"{resolved} is not valid YAML: {error}") from error
    return BaselineConfig.from_mapping(document or {}, source_path=resolved)
