"""Tests for the one-time unblinding module, on synthetic data only.

Nothing here reads a real outcome. The properties tested are the ones a
silent fault would falsify the final answer with: the MAE/seat maths,
the supported-row filter, the confirmatory-family matcher, and the
refusal to score files whose bytes have drifted from their freeze.
"""

import json

import pytest

from src.news_modelling import unblind_2026 as ub


def test_metric_block_mae_and_rmse():
    rows = [
        {"observed_vote_share": 40.0, "p": 30.0,
         "election_id": "e", "division_id": "d1"},
        {"observed_vote_share": 20.0, "p": 25.0,
         "election_id": "e", "division_id": "d2"},
    ]
    block = ub._metric_block(rows, "p")
    assert block["rows"] == 2 and block["contests"] == 2
    assert block["mae"] == pytest.approx((10 + 5) / 2)
    assert block["rmse"] == pytest.approx(((100 + 25) / 2) ** 0.5)


def test_seat_accuracy_compares_flags_as_strings():
    rows = [
        {"news_flag": "True", "observed_elected": "True"},
        {"news_flag": "False", "observed_elected": "True"},
    ]
    block = ub._seat_accuracy(rows, "news_flag")
    assert block["correct"] == 1 and block["accuracy"] == 0.5


def test_score_specification_filters_supported_and_reform():
    observed = {
        "a": {"observed_vote_share": 50.0, "observed_elected": "True",
              "baseline_predicted_share": 45.0,
              "baseline_predicted_elected": "True",
              "election_id": "e", "division_id": "d",
              "is_reform_uk": "True"},
        "b": {"observed_vote_share": 30.0, "observed_elected": "False",
              "baseline_predicted_share": 35.0,
              "baseline_predicted_elected": "False",
              "election_id": "e", "division_id": "d",
              "is_reform_uk": "False"},
    }
    spec_rows = [
        {"candidate_contest_id": "a", "included_in_reported_metrics": "True",
         "is_reform_uk": "True", "baseline_prediction": "45.0",
         "recalibrated_prediction": "46.0",
         "news_enhanced_prediction": "49.0",
         "news_predicted_elected": "True"},
        # Unsupported minor party: excluded from MAE, kept for seat calls.
        {"candidate_contest_id": "b", "included_in_reported_metrics": "False",
         "is_reform_uk": "False", "baseline_prediction": "35.0",
         "recalibrated_prediction": "35.0",
         "news_enhanced_prediction": "35.0",
         "news_predicted_elected": "False"},
    ]
    result = ub.score_specification(spec_rows, observed, with_bootstrap=False)
    overall = result["all_supported_parties"]
    assert overall["news_enhanced"]["rows"] == 1
    assert overall["news_enhanced"]["mae"] == pytest.approx(1.0)
    assert overall["news_vs_raw_baseline_mae"] == pytest.approx(5.0 - 1.0)
    assert result["reform_uk"]["news_enhanced"]["rows"] == 1
    assert result["seat_accuracy_news"]["accuracy"] == 1.0


def test_confirmatory_family_matches_only_the_declared_cells():
    key_yes = ("pooled_2017_2021", "combined_exploratory", "w",
               "confirmed_window", "exploratory_primary_comparison")
    key_local = ("pooled_2017_2021", "local_sensitivity", "w",
                 "confirmed_window", "sensitivity_only")
    key_cumulative = ("pooled_2017_2021", "national_exploratory", "w",
                      "cumulative_sensitivity", "exploratory_primary_comparison")
    key_wrong_variant = ("fit_2017_only", "combined_exploratory", "w",
                         "confirmed_window", "exploratory_primary_comparison")
    assert ub._is_confirmatory("v1", key_yes)
    assert not ub._is_confirmatory("v1", key_local)
    assert not ub._is_confirmatory("v1", key_cumulative)
    assert not ub._is_confirmatory("v1", key_wrong_variant)
    key_v2 = ("pooled_2017_2021_byelections", "national_exploratory", "w",
              "confirmed_window", "exploratory_primary_comparison")
    assert ub._is_confirmatory("v2", key_v2)
    assert not ub._is_confirmatory("v2", key_yes)


def _fake_freeze(directory, predictions_text, protocol: dict):
    directory.mkdir(parents=True)
    (directory / "blinded_predictions.csv").write_text(predictions_text)
    (directory / "frozen_protocol.json").write_text(json.dumps(protocol))
    manifest = {
        "blinded_predictions.csv":
            ub._sha256(directory / "blinded_predictions.csv"),
        "frozen_protocol.json": ub._sha256(directory / "frozen_protocol.json"),
    }
    (directory / "sha256_manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_integrity_check_accepts_frozen_and_refuses_tampered(tmp_path,
                                                             monkeypatch):
    v1 = tmp_path / "v1"
    v1_manifest = _fake_freeze(v1, "v1-predictions", {"any": "thing"})
    v2 = tmp_path / "v2"
    _fake_freeze(v2, "v2-predictions", {
        "v1_freeze": {
            "predictions_sha256": v1_manifest["blinded_predictions.csv"],
            "protocol_sha256": v1_manifest["frozen_protocol.json"],
        }
    })
    monkeypatch.setattr(ub, "V1_DIR", v1)
    monkeypatch.setattr(ub, "V2_DIR", v2)
    report = ub.verify_freeze_integrity()
    assert set(report) == {
        "v1/blinded_predictions.csv", "v1/frozen_protocol.json",
        "v2/blinded_predictions.csv", "v2/frozen_protocol.json",
    }

    # A single altered byte after the freeze must refuse the unblinding.
    (v1 / "blinded_predictions.csv").write_text("v1-predictions-tampered")
    with pytest.raises(ub.UnblindingRefused):
        ub.verify_freeze_integrity()
