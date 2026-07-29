"""Command-line entry point for the no-news baseline.

The brief asks for "a command-line training option". Three subcommands:

    train      build the model bundle
    config     print the resolved configuration and exit
    validate   check a configuration file and exit

``config`` and ``validate`` exist because the expensive failure mode is a
training run that takes minutes and then turns out to have used a setting the
operator did not intend. Both are instant, and ``config`` prints the resolved
values rather than the file's, so an override that did not take effect is
visible before anything is fitted.

Usage from the repository root::

    PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
        -m no_news_baseline.cli train

    # ship Architecture C regardless of the gates, with the UKIP block on
    PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
        -m no_news_baseline.cli train \
        --architecture C_partial_pooling --ukip-interactions \
        --output surrey-election-no-news-baseline/outputs/model_bundle_ukip

Command-line flags override the configuration file, and the file overrides
the code defaults. The resolved result is written into the bundle, so a
bundle always records what it was actually built with rather than what any
one of the three layers said.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from .configuration import (
    DEFAULT_CONFIG_PATH,
    BaselineConfig,
    ConfigurationError,
    load_config,
)
from .logging_setup import configure_logging, get_logger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="no_news_baseline",
        description="Train and export the Surrey no-news candidate baseline.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("train", "Build the model bundle."),
        ("config", "Print the resolved configuration and exit."),
        ("validate", "Validate a configuration file and exit."),
    ):
        sub = subcommands.add_parser(name, help=help_text)
        sub.add_argument(
            "--config",
            type=Path,
            default=DEFAULT_CONFIG_PATH,
            help=(
                "Configuration file. Defaults to %(default)s. "
                "Pass --no-config to use the code defaults instead."
            ),
        )
        sub.add_argument(
            "--no-config",
            action="store_true",
            help="Ignore any configuration file and use the code defaults.",
        )
        if name != "train":
            continue

        # Overrides. Every one of these is also a configuration key; they
        # exist so a one-off experimental run does not require editing, and
        # then remembering to revert, a file that is under version control.
        sub.add_argument(
            "--architecture",
            help=(
                "Ship this architecture regardless of the selection gates "
                "(the brief's manual mode). Omit for automatic selection."
            ),
        )
        sub.add_argument(
            "--output",
            type=Path,
            help="Bundle output directory, overriding the configured one.",
        )
        sub.add_argument(
            "--seed",
            type=int,
            help="Random seed for the gradient-boosted architecture.",
        )
        sub.add_argument(
            "--bootstrap-resamples",
            type=int,
            help="Contest-level bootstrap resamples.",
        )
        sub.add_argument(
            "--ukip-interactions",
            action="store_true",
            help=(
                "Enable the optional UKIP contextual interaction block. "
                "Reform UK and UKIP remain separate parties throughout; this "
                "adds UKIP's own columns and merges nothing."
            ),
        )
        sub.add_argument(
            "--no-reform-interactions",
            action="store_true",
            help="Disable the Reform UK interaction terms (ablation control arm).",
        )
        sub.add_argument(
            "--log-level",
            default="INFO",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        )
        sub.add_argument(
            "--log-file",
            type=Path,
            help=(
                "Also append the run log here. Defaults to training.log inside "
                "the bundle output directory."
            ),
        )
    return parser


def resolve(arguments: argparse.Namespace) -> BaselineConfig:
    """Configuration file plus command-line overrides, validated as a whole.

    Validation runs on the combined result rather than on the file alone,
    because an override can create a combination the file never contained -
    ``--architecture`` naming something outside ``selection.compared``, for
    instance.
    """

    config = load_config(None if arguments.no_config else arguments.config)

    selection_overrides = {}
    if getattr(arguments, "architecture", None):
        selection_overrides["mode"] = arguments.architecture
    if selection_overrides:
        config = replace(config, selection=replace(config.selection, **selection_overrides))

    feature_overrides = {}
    if getattr(arguments, "ukip_interactions", False):
        feature_overrides["ukip_interactions"] = True
    if getattr(arguments, "no_reform_interactions", False):
        feature_overrides["reform_interactions"] = False
    if feature_overrides:
        config = replace(config, features=replace(config.features, **feature_overrides))

    if getattr(arguments, "output", None):
        config = replace(
            config, paths=replace(config.paths, output_directory=arguments.output)
        )
    if getattr(arguments, "seed", None) is not None:
        config = replace(config, boosting_seed=arguments.seed)
    if getattr(arguments, "bootstrap_resamples", None) is not None:
        config = replace(
            config,
            evaluation=replace(
                config.evaluation, bootstrap_resamples=arguments.bootstrap_resamples
            ),
        )

    config.validate()
    return config


def main(argv: list[str] | None = None) -> int:
    """Return an exit status rather than raising, so the shell sees the failure."""

    arguments = build_parser().parse_args(argv)

    try:
        config = resolve(arguments)
    except ConfigurationError as error:
        # A configuration problem is the operator's to fix, so it is reported
        # as a message rather than a traceback with this module's internals
        # in it.
        print(f"configuration error: {error}", file=sys.stderr)
        return 2

    if arguments.command in {"config", "validate"}:
        if arguments.command == "validate":
            print(f"configuration is valid: {config.source_path or 'code defaults'}")
            return 0
        print(json.dumps(config.as_record(), indent=2))
        return 0

    log_file = arguments.log_file or (config.paths.output_directory / "training.log")
    logger = configure_logging(level=arguments.log_level, log_file=log_file)

    # Imported here rather than at module scope for two reasons. `config` and
    # `validate` must stay instant, and the build script pulls in numpy and
    # LightGBM. And `scripts` is a sibling top-level package, not a subpackage
    # of this one, so importing it at module scope would make the package
    # unimportable wherever the scripts directory is not on the path.
    from scripts.build_candidate_model_bundle import build_bundle

    try:
        build_bundle(config, logger=logger)
    except FileNotFoundError as error:
        logger.error("input missing: %s", error)
        logger.error(
            "The contract is produced by the extractor. Run "
            "surrey-election-extractor/scripts/generate_no_news_candidate_contests.py first."
        )
        return 1
    except Exception:
        # Logged with the traceback, because an unexpected failure here is a
        # bug in the modelling code and the traceback is the evidence.
        logger.exception("training run failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
