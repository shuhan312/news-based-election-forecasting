"""Tests for loading and validating the frozen Stage 1 bundle.

Prompt 2 requires the application to "fail safely if the selected Stage 1
model bundle is incomplete or incompatible", so nearly every test here builds
a broken bundle and asserts that loading it raises rather than proceeding. A
loader that has only been run against a good bundle has not been tested.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from news_modelling.stage1_bundle import (
    REQUIRED_FILES,
    BundleIncompatible,
    load_stage1_bundle,
)

REAL_BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")


def oof_rows():
    return [
        {"candidate_contest_id": "a", "election_id": "e1", "division_id": "d1",
         "split_role": "rolling_origin_fold", "standard_party_name": "Conservative",
         "is_reform_uk": "False", "is_ukip": "False",
         "predicted_vote_share": "20.0", "observed_vote_share": "25.0"},
        {"candidate_contest_id": "b", "election_id": "e1", "division_id": "d1",
         "split_role": "rolling_origin_fold", "standard_party_name": "Reform UK",
         "is_reform_uk": "True", "is_ukip": "False",
         "predicted_vote_share": "10.0", "observed_vote_share": "12.0"},
    ]


def make_bundle(tmp_path: Path, *, rows=None, manifest=True) -> Path:
    """A minimal bundle that passes validation, for tests to then break."""

    directory = tmp_path / "bundle"
    directory.mkdir()
    rows = rows if rows is not None else oof_rows()

    for name in REQUIRED_FILES:
        (directory / name).write_text("placeholder\n", encoding="utf-8")
    (directory / "architecture.json").write_text(json.dumps({
        "bundle_version": "test_v1", "selected_model_type": "A_regularised_linear",
        "training_date": "2026-07-29", "selection": {"selected_automatically": True},
    }), encoding="utf-8")
    (directory / "metrics.json").write_text(json.dumps({
        "out_of_fold": {"overall": {"mae": 9.0}},
        "primary_holdout": {"overall": {"mae": 4.0}},
    }), encoding="utf-8")
    (directory / "reform_metrics.json").write_text(json.dumps({
        "out_of_fold": {"reform_uk": {"mae": 10.0}, "small_sample_warning": True},
    }), encoding="utf-8")

    for name, data in (("out_of_fold_predictions.csv", rows),
                       ("holdout_predictions.csv", rows),
                       ("split_manifest.csv", [{"split_id": "s", "role": "r"}])):
        with (directory / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)

    if manifest:
        (directory / "bundle_manifest.json").write_text(json.dumps({
            "files": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(directory.iterdir())
                if path.is_file() and path.name != "bundle_manifest.json"
            }
        }), encoding="utf-8")
    return directory


# ---------------------------------------------------------------------------
# The real bundle
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_BUNDLE.exists(), reason="Stage 1 bundle not built")
def test_the_real_bundle_loads_and_verifies_its_own_hashes():
    bundle = load_stage1_bundle(REAL_BUNDLE)
    assert bundle.out_of_fold
    assert bundle.summary()["baseline_out_of_fold_rows"] == len(bundle.out_of_fold)
    assert bundle.warnings == ()


@pytest.mark.skipif(not REAL_BUNDLE.exists(), reason="Stage 1 bundle not built")
def test_loading_does_not_modify_the_bundle():
    """Stage 2 must treat Stage 1 as frozen."""

    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(REAL_BUNDLE.iterdir()) if path.is_file()
    }
    load_stage1_bundle(REAL_BUNDLE)
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(REAL_BUNDLE.iterdir()) if path.is_file()
    }
    assert before == after


# ---------------------------------------------------------------------------
# Failing safely
# ---------------------------------------------------------------------------


def test_a_missing_directory_is_reported_clearly(tmp_path):
    with pytest.raises(BundleIncompatible, match="not found"):
        load_stage1_bundle(tmp_path / "absent")


def test_an_incomplete_bundle_names_what_is_missing(tmp_path):
    directory = make_bundle(tmp_path)
    (directory / "feature_schema.json").unlink()
    with pytest.raises(BundleIncompatible, match="feature_schema.json"):
        load_stage1_bundle(directory)


def test_a_bundle_that_does_not_match_its_manifest_is_refused(tmp_path):
    """The metrics would describe different files from the ones being read."""

    directory = make_bundle(tmp_path)
    (directory / "model.pkl").write_text("something else\n", encoding="utf-8")
    with pytest.raises(BundleIncompatible, match="does not match its own manifest"):
        load_stage1_bundle(directory)


def test_hash_verification_can_be_switched_off_but_is_on_by_default(tmp_path):
    directory = make_bundle(tmp_path)
    (directory / "model.pkl").write_text("something else\n", encoding="utf-8")
    assert load_stage1_bundle(directory, verify_hashes=False).out_of_fold


def test_a_bundle_without_a_manifest_warns_rather_than_failing(tmp_path):
    directory = make_bundle(tmp_path, manifest=False)
    bundle = load_stage1_bundle(directory)
    assert any("not verified" in warning for warning in bundle.warnings)


def test_in_sample_predictions_are_refused(tmp_path):
    """Prompt 2: the news layer must train on out-of-fold predictions."""

    rows = oof_rows()
    rows[0]["split_role"] = "primary_holdout"
    directory = make_bundle(tmp_path, rows=rows)
    with pytest.raises(BundleIncompatible, match="genuinely out of fold"):
        load_stage1_bundle(directory)


def test_duplicate_predictions_for_one_candidate_are_refused(tmp_path):
    """A residual is defined per candidate; two baselines would pick one by read order."""

    rows = oof_rows()
    rows[1]["candidate_contest_id"] = rows[0]["candidate_contest_id"]
    directory = make_bundle(tmp_path, rows=rows)
    with pytest.raises(BundleIncompatible, match="more than one out-of-fold"):
        load_stage1_bundle(directory)


def test_a_row_labelled_both_reform_and_ukip_is_refused(tmp_path):
    """The separation requirement, restated as a property of the data."""

    rows = oof_rows()
    rows[1]["is_ukip"] = "True"
    directory = make_bundle(tmp_path, rows=rows)
    with pytest.raises(BundleIncompatible, match="both Reform UK and UKIP"):
        load_stage1_bundle(directory)


def test_missing_required_columns_are_named(tmp_path):
    rows = [{k: v for k, v in row.items() if k != "observed_vote_share"}
            for row in oof_rows()]
    directory = make_bundle(tmp_path, rows=rows)
    with pytest.raises(BundleIncompatible, match="observed_vote_share"):
        load_stage1_bundle(directory)


def test_rows_without_an_observed_share_are_warned_about(tmp_path):
    rows = oof_rows()
    rows[1]["observed_vote_share"] = ""
    directory = make_bundle(tmp_path, rows=rows)
    bundle = load_stage1_bundle(directory)
    assert any("cannot contribute a residual" in w for w in bundle.warnings)
