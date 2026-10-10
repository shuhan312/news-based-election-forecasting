"""Tests for llm_eval's dataset, metrics and audit modules.

Unit tests use hand-made cases with known answers. The integration tests at
the end use committed repository data and check the toolkit's acceptance
criteria 1 and 2: it reproduces V2's B0 result exactly and rediscovers the
V1 labelling defect. All tests run offline.
"""

import csv

import numpy as np
import pytest

from llm_eval.audit import (base_rate_drift, provenance_warning,
                            rule_consistency, run_audit)
from llm_eval.dataset import Example, hash_split, load_labels, load_split_file
from llm_eval.metrics import f1, kappa, precision, recall, score


def ex(i, label, origin="a", reason="", provenance="human", **group):
    return Example(id=str(i), label=label, provenance=provenance,
                   origin=origin, reason=reason, group=group)


# --- metrics ---------------------------------------------------------------------

def test_metrics_on_a_hand_computed_case():
    # 10 items: TP=3, FN=1, FP=2, TN=4.
    y = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    p = np.array([1, 1, 1, 0, 1, 1, 0, 0, 0, 0])
    assert recall(y, p) == pytest.approx(3 / 4)
    assert precision(y, p) == pytest.approx(3 / 5)
    assert f1(y, p) == pytest.approx(2 * 0.75 * 0.6 / 1.35)
    # po = 0.7; pe = 0.4*0.5 + 0.6*0.5 = 0.5; kappa = 0.2/0.5
    assert kappa(y, p) == pytest.approx(0.4)


def test_perfect_and_chance_agreement():
    y = np.array([1, 0, 1, 0])
    assert kappa(y, y) == pytest.approx(1.0)
    # A constant classifier carries no information beyond the base rate.
    assert kappa(y, np.zeros(4, dtype=int)) == pytest.approx(0.0)


def test_undefined_metrics_are_reported_as_none_not_zero():
    out = score([0, 0, 0], [0, 0, 0], resamples=50)
    assert out["recall"] is None        # no reference positives
    assert out["precision"] is None     # no predicted positives


def test_score_rejects_mismatched_inputs():
    with pytest.raises(ValueError):
        score([1, 0], [1])


# --- dataset ---------------------------------------------------------------------

def test_split_is_deterministic_stratified_and_respects_forced_dev():
    items = [ex(i, i % 2) for i in range(40)] + [ex("seen", 1, origin="old")]
    s1 = hash_split(items, salt="s", force_dev_origins=("old",))
    s2 = hash_split(list(reversed(items)), salt="s", force_dev_origins=("old",))
    assert s1 == s2                                   # order-independent
    assert s1["seen"] == "dev"
    for label in (0, 1):
        test = sum(1 for e in items[:40]
                   if e.label == label and s1[e.id] == "test")
        assert test == 10                             # half of each label


def test_example_rejects_bad_labels_and_provenance():
    with pytest.raises(ValueError):
        ex(1, 2)
    with pytest.raises(ValueError):
        ex(1, 1, provenance="guess")


# --- audit -----------------------------------------------------------------------

LOCAL_RULES = {"local": ["E5-L", "E5-NO-"]}


def test_rule_consistency_flags_an_injected_mismatch():
    items = ([ex(i, 1, origin="batch1", reason="E5-L1-PLACE", arm="local")
              for i in range(5)]
             + [ex(f"bad{i}", 1, origin="batch2", reason="E5-N1-PARTY",
                   arm="local") for i in range(3)])
    flags = rule_consistency(items, stratum_field="arm",
                             allowed_prefixes=LOCAL_RULES)
    assert len(flags) == 1
    assert flags[0]["origin"] == "batch2" and flags[0]["violations"] == 3


def test_rule_consistency_is_silent_on_clean_labels():
    items = [ex(i, i % 2, reason="E5-L1-PLACE", arm="local") for i in range(9)]
    assert rule_consistency(items, stratum_field="arm",
                            allowed_prefixes=LOCAL_RULES) == []


def test_base_rate_drift_flags_a_large_gap_only():
    big = ([ex(f"a{i}", int(i < 18), origin="a", source="s") for i in range(20)]
           + [ex(f"b{i}", int(i < 2), origin="b", source="s") for i in range(20)])
    assert len(base_rate_drift(big, within="source")) == 1
    small = ([ex(f"a{i}", int(i < 11), origin="a", source="s") for i in range(20)]
             + [ex(f"b{i}", int(i < 9), origin="b", source="s") for i in range(20)])
    assert base_rate_drift(small, within="source") == []


def test_provenance_warning_only_for_ai_assisted_labels_and_llms():
    assisted = [ex(1, 1, provenance="ai_assisted")]
    assert provenance_warning(assisted, classifier_is_llm=True)
    assert not provenance_warning(assisted, classifier_is_llm=False)
    assert not provenance_warning([ex(1, 1)], classifier_is_llm=True)


# --- acceptance on committed repository data --------------------------------------

def _v1_local_labels():
    common = dict(id_col="article_id", label_col="e5_decision",
                  positive="include", negative="exclude",
                  reason_col="e5_reason_code", group_cols=("arm", "source_id"),
                  where={"arm": "local"})
    corpus = load_labels("news_collection/full_corpus_review.csv",
                         origin="corpus_manual", provenance="ai_assisted",
                         **common)
    validation = load_labels("news_collection/llm_validation_sample.csv",
                             origin="v1_validation_seen",
                             provenance="ai_assisted", **common)
    return corpus + validation


def test_toolkit_split_reproduces_the_committed_split():
    labels = _v1_local_labels()
    split = hash_split(labels, salt="v2-local-relevance-2026-10-07",
                       force_dev_origins=("v1_validation_seen",))
    committed = load_split_file("v2_design/local_relevance_v1/split.csv")
    assert split == committed


def test_toolkit_reproduces_b0_exactly():
    labels = {e.id: e.label for e in _v1_local_labels()}
    split = load_split_file("v2_design/local_relevance_v1/split.csv")
    preds = {}
    for path in ("news_collection/manual_review_llm_v2_corpus.csv",
                 "news_collection/manual_review_llm_v2_validation.csv"):
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for r in csv.DictReader(handle):
                preds[r["article_id"]] = int(r["e5_decision"] == "include")
    test_ids = [i for i, s in split.items() if s == "test"]
    out = score([labels[i] for i in test_ids], [preds[i] for i in test_ids])
    assert out["kappa"] == 0.7031
    assert out["recall"] == 0.8333
    assert out["kappa_ci95"] == [0.5793, 0.8099]


def test_audit_rediscovers_the_v1_labelling_defect():
    result = run_audit(_v1_local_labels(), stratum_field="arm",
                       allowed_prefixes={"local": ["E5-L", "E5-NO-",
                                                   "E5-BORDERLINE-"]},
                       drift_within="source_id")
    rules = [f for f in result["flags"] if f["check"] == "rule_consistency"]
    # The defect sits in the validation batch: 31 includes on national rules.
    hit = [f for f in rules
           if f["origin"] == "v1_validation_seen" and f["label"] == 1]
    assert hit and hit[0]["violations"] == 31
    # And the same source's include rate differs sharply between batches.
    drift = [f for f in result["flags"] if f["check"] == "base_rate_drift"]
    assert any(f["source_id"] == "guardian_api" for f in drift)
    assert not result["clean"]
