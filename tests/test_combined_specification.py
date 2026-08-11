"""Tests for the combined specification.

The risk is not a crash. It is a contrast that silently compares
non-nested models - a "marginal value of tone" computed against an arm
that is not actually inside the full one - or a rebuilt derived index
that drifted from the committed identity-placebo run. Either would let
the headline claim ("tone survives identity and volume") rest on a
comparison it never made.
"""

import json
from pathlib import Path

import pytest

from src.news_modelling.combined_specification import (COMPARATORS,
                                                       FULL_ARM,
                                                       FULL_COLUMNS)
from src.news_modelling.identity_placebos import ARMS as IDENTITY_ARMS
from src.news_modelling.identity_placebos import DUMMY_COLUMNS

RESULTS = Path("news_features/combined_specification_v1/"
               "combined_specification_results.json")

needs_results = pytest.mark.skipif(
    not RESULTS.exists(), reason="combined specification results not built")


@pytest.fixture(scope="module")
def payload():
    return json.loads(RESULTS.read_text())


# ---- the contrasts must be nested ------------------------------------

def test_full_arm_is_exactly_identity_plus_volume_plus_tone_within():
    assert FULL_COLUMNS == DUMMY_COLUMNS + ["party_article_share",
                                            "net_portrayal_share_within"]


def test_every_comparator_is_a_strict_subset_of_the_full_arm():
    # A comparator with a column the full arm lacks would make the paired
    # contrast a comparison of siblings, not of nested models, and the
    # "marginal value" reading would be wrong.
    for name in COMPARATORS:
        columns = IDENTITY_ARMS[name]
        assert set(columns) < set(FULL_COLUMNS), name


def test_the_decisive_contrast_isolates_only_the_tone_column():
    missing = set(FULL_COLUMNS) - set(IDENTITY_ARMS["party_dummies_plus_share"])
    assert missing == {"net_portrayal_share_within"}


# ---- the built results must be internally consistent ------------------

@needs_results
def test_both_reproduction_gates_recorded_a_pass(payload):
    check = payload["reproduction_check"]
    assert check["frozen_max_absolute_difference"] == 0.0
    assert check["comparator_max_absolute_drift"] <= 1e-6


@needs_results
def test_full_arm_covers_all_six_windows(payload):
    windows = [record["window"] for record in payload["arms"][FULL_ARM]]
    assert len(windows) == 6 and len(set(windows)) == 6


@needs_results
def test_paired_point_gain_equals_the_delta_difference(payload):
    # The paired bootstrap's point estimate and the two arms' deltas are
    # computed from the same 753 rows, so comparator_mae - full_mae must
    # equal delta_full - delta_comparator exactly; a gap means the pairing
    # scored different predictions than the arms reported.
    deltas = {
        name: {record["window"]: record["delta_vs_recalibrated"]
               for record in payload["arms"][name]}
        for name in (FULL_ARM, *COMPARATORS)
    }
    for window, contrasts in payload["paired_marginals"].items():
        for name in COMPARATORS:
            record = contrasts[f"vs_{name}"]
            expected = deltas[FULL_ARM][window] - deltas[name][window]
            assert abs(record["full_minus_comparator_mae_gain"]
                       - expected) < 1e-9, (window, name)


@needs_results
def test_pairing_covers_the_supported_rows_with_the_frozen_resampler(payload):
    for contrasts in payload["paired_marginals"].values():
        for record in contrasts.values():
            assert record["rows"] == 753
            assert record["ci_lower"] <= record["ci_upper"]
