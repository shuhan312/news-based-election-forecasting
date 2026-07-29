"""Tests for the configuration layer, the CLI and logging.

The tests that matter most here are not about happy paths. A configuration
system earns its place by refusing bad input loudly, so most of what follows
asserts that something *fails*: an unknown key, a manual architecture that was
never scored, a UKIP block without its Reform base, a named file that does not
exist. Each of those, if it passed silently, would produce a run that reported
success while doing something other than what was asked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from no_news_baseline import cli
from no_news_baseline.candidate_architecture_selection import (
    COMPLEXITY_ORDER,
    MATERIAL_IMPROVEMENT,
    MAX_ADVERSE_FOLDS,
    MIN_DEVELOPMENT_FOLDS,
    PRIMARY_CRITERION,
)
from no_news_baseline.candidate_boosted_model import BOOSTING_PARAMS, boosting_params
from no_news_baseline.candidate_historical_strength import (
    MIN_CONTESTS_FOR_COUNTY_STRENGTH,
    POOLING_WINDOW_YEARS,
)
from no_news_baseline.candidate_interactions import attach_interactions
from no_news_baseline.candidate_metrics import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED
from no_news_baseline.configuration import (
    DEFAULT_CONFIG_PATH,
    BaselineConfig,
    ConfigurationError,
    load_config,
)
from no_news_baseline.logging_setup import configure_logging, get_logger

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_CONFIG = REPOSITORY_ROOT / DEFAULT_CONFIG_PATH


def write_config(directory: Path, document: dict) -> Path:
    path = directory / "config.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The shipped file and the code defaults must agree
# ---------------------------------------------------------------------------


def test_shipped_configuration_file_exists_and_parses():
    assert SHIPPED_CONFIG.exists(), f"{SHIPPED_CONFIG} is referenced by the CLI default"
    assert load_config(SHIPPED_CONFIG).source_path == SHIPPED_CONFIG


def test_shipped_configuration_states_exactly_the_code_defaults():
    """The file restates every default, so the restatement is checked.

    The file exists to be read by a person, which means it has to be complete
    rather than a list of overrides. Completeness creates a second copy of
    every number; this test is what stops the two copies drifting apart.
    """

    shipped = load_config(SHIPPED_CONFIG)
    defaults = BaselineConfig.defaults()

    assert shipped.bundle_version == defaults.bundle_version
    assert shipped.boosting_seed == defaults.boosting_seed == BOOSTING_PARAMS["seed"]
    assert shipped.selection.compared == tuple(COMPLEXITY_ORDER)
    assert shipped.selection.primary_criterion == PRIMARY_CRITERION
    assert shipped.selection.material_improvement == MATERIAL_IMPROVEMENT
    assert shipped.selection.max_adverse_folds == MAX_ADVERSE_FOLDS
    assert shipped.selection.min_development_folds == MIN_DEVELOPMENT_FOLDS
    assert shipped.selection.decision_split_id is None
    assert (
        shipped.features.county_strength_minimum_contests
        == MIN_CONTESTS_FOR_COUNTY_STRENGTH
    )
    assert (
        shipped.features.county_strength_pooling_window_years == POOLING_WINDOW_YEARS
    )
    assert shipped.evaluation.bootstrap_resamples == BOOTSTRAP_RESAMPLES
    assert shipped.evaluation.bootstrap_seed == BOOTSTRAP_SEED


def test_shipped_configuration_keeps_ukip_off_and_reform_on():
    """The brief's default position, asserted rather than assumed.

    UKIP's block is the optional labelled sensitivity feature. If it were ever
    on by default, every published figure would silently include it and the
    "clearly labelled" requirement would be unmet.
    """

    shipped = load_config(SHIPPED_CONFIG)
    assert shipped.features.reform_interactions is True
    assert shipped.features.ukip_interactions is False


def test_defaults_are_used_when_no_file_is_given():
    config = load_config(None)
    assert config.source_path is None
    assert config.as_record()["config_source"] == "module_defaults"


# ---------------------------------------------------------------------------
# Bad input must fail, not be ignored
# ---------------------------------------------------------------------------


def test_unknown_top_level_key_is_refused(tmp_path):
    path = write_config(tmp_path, {"bundle_verison": "typo"})
    with pytest.raises(ConfigurationError, match="unknown key"):
        load_config(path)


def test_unknown_nested_key_is_refused(tmp_path):
    path = write_config(tmp_path, {"selection": {"materal_improvement": 0.1}})
    with pytest.raises(ConfigurationError, match="unknown key"):
        load_config(path)


def test_missing_named_file_is_an_error_not_a_silent_default(tmp_path):
    """An operator who typed --config meant it."""

    with pytest.raises(ConfigurationError, match="not found"):
        load_config(tmp_path / "absent.yaml")


def test_malformed_yaml_is_reported_as_a_configuration_error(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("selection: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="not valid YAML"):
        load_config(path)


def test_manual_architecture_outside_compared_is_refused(tmp_path):
    """A shipped architecture with no fold results is not a shipped model."""

    path = write_config(tmp_path, {
        "selection": {
            "mode": "B_gradient_boosted_trees",
            "compared": ["A_regularised_linear"],
        }
    })
    with pytest.raises(ConfigurationError, match="not among selection.compared"):
        load_config(path)


def test_unknown_architecture_name_is_refused(tmp_path):
    path = write_config(tmp_path, {"selection": {"compared": ["D_random_forest"]}})
    with pytest.raises(ConfigurationError, match="unknown architecture"):
        load_config(path)


def test_ukip_interactions_require_the_reform_terms(tmp_path):
    """The UKIP block extends the Reform terms; it never replaces them."""

    path = write_config(tmp_path, {
        "features": {"reform_interactions": False, "ukip_interactions": True}
    })
    with pytest.raises(ConfigurationError, match="requires features.reform_interactions"):
        load_config(path)


@pytest.mark.parametrize("document, message", [
    ({"selection": {"material_improvement": 1.5}}, "0 <= x < 1"),
    ({"selection": {"min_development_folds": 0}}, "at least 1"),
    ({"selection": {"max_adverse_folds": -1}}, "must not be negative"),
    ({"features": {"county_strength_minimum_contests": 0}}, "at least 1"),
    ({"features": {"county_strength_pooling_window_years": 0}}, "must be positive"),
    ({"evaluation": {"bootstrap_resamples": 0}}, "at least 1"),
])
def test_out_of_range_values_are_refused(tmp_path, document, message):
    with pytest.raises(ConfigurationError, match=message):
        load_config(write_config(tmp_path, document))


# ---------------------------------------------------------------------------
# Overlay behaviour
# ---------------------------------------------------------------------------


def test_a_partial_file_overrides_only_what_it_names(tmp_path):
    path = write_config(tmp_path, {"selection": {"material_improvement": 0.2}})
    config = load_config(path)
    defaults = BaselineConfig.defaults()

    assert config.selection.material_improvement == 0.2
    assert config.selection.max_adverse_folds == defaults.selection.max_adverse_folds
    assert config.evaluation.bootstrap_seed == defaults.evaluation.bootstrap_seed


def test_an_empty_file_is_the_defaults_with_provenance(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("# nothing set\n", encoding="utf-8")
    config = load_config(path)
    assert config.selection.material_improvement == MATERIAL_IMPROVEMENT
    assert config.as_record()["config_source"] == "file"


def test_as_record_is_json_serialisable():
    """It is written into training_config.yaml, so it must survive json.dumps."""

    json.dumps(load_config(SHIPPED_CONFIG).as_record())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_flags_override_the_file(tmp_path):
    path = write_config(tmp_path, {"selection": {"mode": "auto"}})
    arguments = cli.build_parser().parse_args([
        "train", "--config", str(path),
        "--architecture", "C_partial_pooling",
        "--seed", "7",
        "--bootstrap-resamples", "50",
        "--output", str(tmp_path / "bundle"),
        "--ukip-interactions",
    ])
    config = cli.resolve(arguments)

    assert config.selection.mode == "C_partial_pooling"
    assert config.selection.is_automatic is False
    assert config.boosting_seed == 7
    assert config.evaluation.bootstrap_resamples == 50
    assert config.paths.output_directory == tmp_path / "bundle"
    assert config.features.ukip_interactions is True


def test_cli_validates_the_combination_not_only_the_file(tmp_path):
    """An override can create a state the file never contained."""

    path = write_config(tmp_path, {
        "selection": {"compared": ["A_regularised_linear", "C_partial_pooling"]}
    })
    arguments = cli.build_parser().parse_args([
        "train", "--config", str(path), "--architecture", "B_gradient_boosted_trees",
    ])
    with pytest.raises(ConfigurationError, match="not among selection.compared"):
        cli.resolve(arguments)


def test_cli_no_config_ignores_the_file(tmp_path):
    path = write_config(tmp_path, {"selection": {"material_improvement": 0.42}})
    arguments = cli.build_parser().parse_args(
        ["config", "--config", str(path), "--no-config"]
    )
    assert cli.resolve(arguments).selection.material_improvement == MATERIAL_IMPROVEMENT


def test_cli_validate_command_returns_zero_on_a_good_file(tmp_path, capsys):
    path = write_config(tmp_path, {"selection": {"material_improvement": 0.1}})
    assert cli.main(["validate", "--config", str(path)]) == 0
    assert "valid" in capsys.readouterr().out


def test_cli_reports_a_bad_configuration_without_a_traceback(tmp_path, capsys):
    path = write_config(tmp_path, {"nonsense": 1})
    assert cli.main(["validate", "--config", str(path)]) == 2
    assert "configuration error" in capsys.readouterr().err


def test_cli_config_command_prints_the_resolved_values(tmp_path, capsys):
    path = write_config(tmp_path, {"selection": {"material_improvement": 0.11}})
    assert cli.main(["config", "--config", str(path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["selection"]["material_improvement"] == 0.11
    assert printed["config_file"] == str(path)


# ---------------------------------------------------------------------------
# The knobs actually reach the code they configure
# ---------------------------------------------------------------------------


def test_boosting_params_replaces_only_the_seed():
    params = boosting_params(123)
    assert params["seed"] == 123
    assert {k: v for k, v in params.items() if k != "seed"} == {
        k: v for k, v in BOOSTING_PARAMS.items() if k != "seed"
    }


def test_boosting_params_returns_a_fresh_copy():
    """LightGBM mutates the dictionary it is given."""

    first = boosting_params()
    first["num_leaves"] = 999
    assert boosting_params()["num_leaves"] == BOOSTING_PARAMS["num_leaves"]


def test_reform_interactions_can_be_switched_off():
    rows = [{"is_reform_uk": True, "is_ukip": False, "previous_party_vote_share": 12.0}]
    without = attach_interactions(rows, include_reform=False)[0]
    assert not any(name.startswith("reform_x_") for name in without)

    with_terms = attach_interactions(rows)[0]
    assert with_terms["reform_x_previous_party_vote_share"] == 12.0


def test_ukip_block_alone_is_refused_at_the_function_too():
    """Defended in the function as well as the configuration.

    The configuration is not the only caller, and a rule enforced in one place
    is a rule that holds only for callers who go through that place.
    """

    with pytest.raises(ValueError, match="include_ukip requires include_reform"):
        attach_interactions([{"is_reform_uk": True, "is_ukip": False}],
                            include_reform=False, include_ukip=True)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def test_configure_logging_writes_to_the_named_file(tmp_path):
    log_file = tmp_path / "nested" / "training.log"
    configure_logging(level="INFO", log_file=log_file)
    get_logger("test").info("a recorded message")
    assert "a recorded message" in log_file.read_text(encoding="utf-8")


def test_configure_logging_twice_does_not_double_records(tmp_path):
    log_file = tmp_path / "training.log"
    configure_logging(log_file=log_file)
    configure_logging(log_file=log_file)
    get_logger("test").info("once")
    assert log_file.read_text(encoding="utf-8").count("once") == 1
