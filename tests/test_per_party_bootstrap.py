"""Tests for the per-party contest-bootstrap annex.

Only the new arithmetic surface is tested on synthetic rows - the
bias/dispersion split, the paired draws, the absent-party handling and
the single-contest guard. The real-data invariants (block counts, the
240-cell agreement with the committed decomposition) are asserted
inside the module itself every time it runs.
"""

import numpy as np
import pytest

from src.news_modelling.per_party_bootstrap import (
    block_analysis,
    error_split,
)


def _row(party, contest, baseline, recalibrated, news, observed):
    return {"party": party, "contest": contest, "baseline": baseline,
            "recalibrated": recalibrated, "news": news,
            "observed": observed}


def _block(reform_contests=("c1", "c2")):
    """Three contests, two fitted parties everywhere, Reform on a
    configurable subset. Constant shifts keep the arithmetic exact:
    every party_a error is its prediction minus 10, so bias equals the
    shift and dispersion is zero by construction.
    """

    rows = []
    for contest in ("c1", "c2", "c3"):
        rows.append(_row("party_a", contest, 12.0, 11.0, 10.5, 10.0))
        rows.append(_row("party_b", contest, 8.0, 9.0, 9.5, 10.0))
        if contest in reform_contests:
            rows.append(_row("reform_uk", contest, 5.0, 6.0, 3.0, 10.0))
    return rows


def test_error_split_arithmetic():
    split = error_split(np.array([2.0, 2.0, 2.0]))
    assert split == {"rows": 3, "signed_bias": 2.0, "abs_bias": 2.0,
                     "dispersion_mae": 0.0, "total_mae": 2.0}
    # Bias removed before dispersion: errors 1 and 3 have bias 2 and
    # mean absolute deviation 1.
    split = error_split(np.array([1.0, 3.0]))
    assert split["abs_bias"] == 2.0
    assert split["dispersion_mae"] == 1.0


def test_point_estimates_by_hand():
    result = block_analysis(_block(), resamples=10,
                            rng=np.random.default_rng(1))
    a = result["parties"]["party_a"]
    # |bias| moves 1.0 (recalibrated) -> 0.5 (news).
    assert a["abs_bias_change_vs_recalibrated"] == pytest.approx(-0.5)
    assert a["abs_bias_change_vs_baseline"] == pytest.approx(-1.5)
    assert a["dispersion_change_vs_recalibrated"] == pytest.approx(0.0)
    # Reform: recalibrated |bias| 4, news |bias| 7 -> worse by 3.
    reform = result["parties"]["reform_uk"]
    assert reform["abs_bias_change_vs_recalibrated"] == pytest.approx(3.0)
    # Group mean over the two fitted parties: (-0.5 + -0.5) / 2; the
    # contrast is Reform minus that mean.
    q = "abs_bias_change_vs_recalibrated"
    assert result["group_point"][q] == pytest.approx(-0.5)
    assert result["contrast_point"][q] == pytest.approx(3.5)


def test_bootstrap_is_deterministic_and_paired():
    kwargs = dict(resamples=60, return_draws=True)
    first = block_analysis(_block(), rng=np.random.default_rng(7), **kwargs)
    second = block_analysis(_block(), rng=np.random.default_rng(7), **kwargs)
    assert first["bootstrap"] == second["bootstrap"]

    # Pairing: inside every draw where Reform and the group both exist,
    # the contrast draw is exactly Reform minus the group mean.
    q = "abs_bias_change_vs_recalibrated"
    draws = first["draws"][q]
    both = (~np.isnan(draws["reform_uk"])) & (~np.isnan(draws["group_mean"]))
    assert both.any()
    np.testing.assert_allclose(
        draws["contrast"][both],
        draws["reform_uk"][both] - draws["group_mean"][both])


def test_absent_party_draws_are_dropped_not_zeroed():
    # Reform stands in one contest of three, so a resample misses it
    # with probability (2/3)^3; over 300 seeded draws some must drop.
    result = block_analysis(_block(reform_contests=("c1",)), resamples=300,
                            rng=np.random.default_rng(11))
    summary = result["bootstrap"]["units"]["reform_uk"][
        "abs_bias_change_vs_recalibrated"]
    assert 0 < summary["effective_draws"] < 300


def test_single_contest_guard():
    rows = [r for r in _block() if r["contest"] == "c1"]
    result = block_analysis(rows, resamples=50,
                            rng=np.random.default_rng(3))
    assert result["bootstrap"]["resamples"] == 0
    # Point estimates still exist; only the interval is refused.
    assert "reform_uk" in result["parties"]
