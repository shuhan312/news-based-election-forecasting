"""Tests for the ward-resolution diagnostic.

Two risks, both of which would turn a gate into a liability.

The first is that the diagnostic quietly reads an outcome. Its whole value is
being runnable before deciding whether to spend reviewer time, and a gate that
costs a look at the 2026 answers is not a gate - it is an unsealing with extra
steps. So the outcome families are excluded by name and that exclusion is
asserted here rather than trusted.

The second is that it counts the cumulative snapshots alongside the six
disjoint windows. Those snapshots are supersets, so counting both would report
the same article twice under two names and inflate every rate - which would
make a closed route look open.
"""

import json
from pathlib import Path

import pytest

from src.news_features.ward_resolution_diagnostic import (CONFIRMATORY_WINDOWS,
                                                          GROUP_KEYS,
                                                          OUTCOME_PREFIXES,
                                                          WARD_KEY,
                                                          load_features,
                                                          news_columns)

RESULTS = Path("news_features/ward_resolution_v1/ward_resolution_results.json")

needs_results = pytest.mark.skipif(
    not RESULTS.exists(), reason="ward resolution results not built")


@pytest.fixture(scope="module")
def payload():
    return json.loads(RESULTS.read_text())


# ---- the diagnostic must not read an outcome -------------------------

# The ward-grain parquet is a local-by-design artefact (OneDrive copy; see
# the README's large-artefacts table), so a fresh clone skips these two.
_needs_ward_parquet = pytest.mark.skipif(
    not Path("news_features/ward_party_election_features_v1/"
             "ward_party_election_features.parquet").exists(),
    reason="requires the local ward-grain parquet (OneDrive; README large-artefacts table)",
)


@_needs_ward_parquet
def test_outcome_families_are_dropped_before_anything_is_counted():
    frame = load_features()
    offending = [column for column in frame.columns
                 if column.split("__")[0] in OUTCOME_PREFIXES]
    assert offending == [], (
        f"the diagnostic can see outcome columns {offending[:5]}; it is meant "
        "to be runnable without unsealing anything")


def test_the_outcome_prefixes_still_name_the_real_families():
    # If the feature builder renames `target__*`, the exclusion above would
    # silently pass while letting the outcome through.
    assert set(OUTCOME_PREFIXES) == {"target", "baseline"}


# ---- the counting rule is the disjoint one ---------------------------

@_needs_ward_parquet
def test_only_the_six_disjoint_windows_are_counted():
    frame = load_features()
    for _arm, window in news_columns(frame):
        assert window in CONFIRMATORY_WINDOWS, (
            f"{window} is a cumulative snapshot; counting it alongside the "
            "disjoint windows would double-count articles")


def test_the_grouping_axis_is_the_one_a_party_indicator_cannot_express():
    # A party indicator is constant within (election, party). The whole test
    # is whether news varies across wards *inside* such a group, so the ward
    # must not be part of the grouping key.
    assert WARD_KEY not in GROUP_KEYS


# ---- the decisive quantity is recorded -------------------------------

@needs_results
def test_the_ward_ceiling_is_reported(payload):
    ceiling = payload["ward_tier_ceiling"]
    for field in ("ward_tier_cells", "by_coverage_status", "unlockable_cells",
                  "max_wards_in_any_unlockable_group"):
        assert field in ceiling


@needs_results
def test_a_zero_rate_is_explained_rather_than_just_reported(payload):
    # A rate of zero is only interpretable next to the reason. If every
    # unlockable group carries one ward, the comparison is arithmetically
    # impossible and no review can change that; if it carries more, the rate
    # is a real measurement of the corpus. Either way the number must be
    # present, because the decision to spend reviewer time turns on it.
    ceiling = payload["ward_tier_ceiling"]
    local = payload["by_arm"].get("local", {})
    if local.get("ward_resolution_rate") == 0.0:
        assert ceiling["max_wards_in_any_unlockable_group"] is not None
