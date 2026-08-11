"""Tests for the design-sensitivity (MDE) annex arithmetic.

Synthetic intervals only - the real-data invariants (row counts per
island, source files) are asserted inside the module's main().
"""

import pytest

from src.news_modelling.minimal_detectable_effect import (
    MDE80_FACTOR,
    _asymmetric,
    mde_from_interval,
    summarise,
)


def test_mde_arithmetic_by_hand():
    result = mde_from_interval(-1.0, 1.0)
    assert result["status"] == "ok"
    assert result["half_width"] == 1.0
    # SE = 1 / 1.96; MDE80 = (1.96 + 0.8416) * SE = 1.4294 * half.
    assert result["se_normal_approx"] == pytest.approx(0.5102, abs=1e-4)
    assert result["mde_50_power"] == 1.0
    assert result["mde_80_power"] == pytest.approx(1.429, abs=1e-3)
    assert MDE80_FACTOR == pytest.approx(1.4294, abs=1e-4)


def test_structural_zero_and_degenerate_intervals_refused():
    assert mde_from_interval(0.0, 0.0)["status"] == "structural_zero"
    # A zero-width interval away from zero is equally undefined: the
    # width, not the location, carries the noise scale.
    assert mde_from_interval(2.0, 2.0)["status"] == "structural_zero"


def test_asymmetry_flag_thresholds():
    # Centre 0, half-width 1: means within 0.1 pass, beyond flag.
    assert not _asymmetric(-1.0, 1.0, 0.05)
    assert _asymmetric(-1.0, 1.0, 0.25)
    # Structural-zero intervals are never flagged.
    assert not _asymmetric(0.0, 0.0, 0.0)


def test_summarise_excludes_structural_zeros_from_median():
    rows = [
        {"island": "i", "scope": "s", "status": "ok", "mde_80_power": 1.0},
        {"island": "i", "scope": "s", "status": "ok", "mde_80_power": 3.0},
        {"island": "i", "scope": "s", "status": "structural_zero"},
    ]
    (entry,) = summarise(rows)
    assert entry["comparisons"] == 3
    assert entry["estimable"] == 2
    assert entry["structural_zero"] == 1
    assert entry["median_mde_80"] == 2.0
    assert entry["min_mde_80"] == 1.0
    assert entry["max_mde_80"] == 3.0
    # Rows without a party key group under the empty party.
    assert entry["party"] == ""


def test_summarise_keeps_parties_apart():
    """Per-party resolutions differ by an order of magnitude, so pooling
    them would produce a median that is wrong for every party in it."""

    rows = [
        {"island": "i", "scope": "party_level", "party": "a",
         "status": "ok", "mde_80_power": 0.05},
        {"island": "i", "scope": "party_level", "party": "b",
         "status": "ok", "mde_80_power": 2.0},
    ]
    summary = summarise(rows)
    assert [e["party"] for e in summary] == ["a", "b"]
    assert [e["median_mde_80"] for e in summary] == [0.05, 2.0]


def test_duplicate_vectors_are_not_counted_twice():
    """Two specifications that predicted the same thing are one look at the
    data, not two. Counting both would inflate the number of independent
    comparisons a resolution figure claims to summarise."""

    rows = [
        {"island": "i", "scope": "overall_mae", "party": "",
         "status": "ok", "mde_80_power": 1.0,
         "vector_owner": "combined/7_to_4_days"},
        {"island": "i", "scope": "overall_mae", "party": "",
         "status": "ok", "mde_80_power": 1.0,
         "vector_owner": "combined/7_to_4_days"},
        {"island": "i", "scope": "overall_mae", "party": "",
         "status": "ok", "mde_80_power": 3.0,
         "vector_owner": "local/90_to_31_days"},
    ]
    entry = summarise(rows)[0]
    assert entry["estimable"] == 3
    assert entry["distinct_estimable"] == 2
    assert entry["duplicate_vectors"] == 1
    # The median is over every estimable interval, duplicates included:
    # identical vectors give identical intervals, so dropping one would not
    # change the resolution, only the count of independent looks.
    assert entry["median_mde_80"] == 1.0


def test_rows_without_a_recorded_owner_stay_distinct():
    """The annex rows predate the duplicate check. Absent an owner they must
    count as separate comparisons rather than collapsing into one."""

    rows = [
        {"island": "i", "scope": "overall_mae", "party": "",
         "status": "ok", "mde_80_power": 1.0},
        {"island": "i", "scope": "overall_mae", "party": "",
         "status": "ok", "mde_80_power": 2.0},
    ]
    entry = summarise(rows)[0]
    assert entry["distinct_estimable"] == 2
    assert entry["duplicate_vectors"] == 0
