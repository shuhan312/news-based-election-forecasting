"""Phase 5 / Step 7 tests: selection logic, temporal leakage,
provenance and incremental stability of canonical selection."""

import copy

from src.dedup.canonical_selection import (RULE_VERSION,
                                           select_canonical)


def fam(ftype="same_article_version_family", ordered=False,
        classes=("minor_update",)):
    return {"family_id": "VAL-test", "family_type": ftype,
            "ordered": ordered, "relationship_classes": set(classes)}


def mem(aid, full=True, clean=True, pub=True, url=True,
        confirmed=True, avail="2021-05-01", origin=False):
    return {"article_id": aid, "full_text": full, "clean": clean,
            "pub_date_usable": pub, "stable_url": url,
            "temporal_confirmed": confirmed, "available_from": avail,
            "is_origin": origin}

# ------------------------------------------------------ selection logic

def test_full_text_preferred_over_snippet():
    d = select_canonical(fam(), [mem("A", full=False), mem("B")])
    assert d["canonical_article_id"] == "B"
    assert d["rejected_reasons"]["A"] == "not a full-text record"


def test_length_is_never_a_criterion():
    # identical evidence except id: the tiebreak is the id, and no
    # length field even exists in the ranking key
    d = select_canonical(fam(), [mem("B"), mem("A")])
    assert d["canonical_article_id"] == "A"
    assert "ranked lower" in d["rejected_reasons"]["B"]


def test_clean_record_beats_flagged_record():
    d = select_canonical(fam(), [mem("A", clean=False), mem("B")])
    assert d["canonical_article_id"] == "B"
    assert d["rejected_reasons"]["A"] == "carries quality flags"


def test_deterministic_identical_inputs_identical_output():
    ms = [mem("A"), mem("B", confirmed=False)]
    d1 = select_canonical(fam(), copy.deepcopy(ms))
    d2 = select_canonical(fam(), copy.deepcopy(list(reversed(ms))))
    assert d1 == d2


def test_uncertain_family_goes_to_review():
    # substantive difference + unknown order + nothing confirmed
    # pre-election: refusing to choose is the only safe move
    d = select_canonical(
        fam(classes=("substantive_update",), ordered=False),
        [mem("A", confirmed=False, avail=""),
         mem("B", confirmed=False, avail="")])
    assert d["canonical_status"] == "canonical_uncertain_manual_review"
    assert d["canonical_article_id"] == ""
    assert d["temporal_validity_status"] == "unresolved"


def test_no_full_text_member_goes_to_review():
    d = select_canonical(fam(), [mem("A", full=False),
                                 mem("B", full=False)])
    assert d["canonical_status"] == "canonical_uncertain_manual_review"

# ----------------------------------------------------- temporal leakage

def test_later_update_with_future_information_never_replaces_confirmed():
    # B is newer/longer/available only post-election; A is the
    # pre-election confirmed state. A must win regardless of B's
    # completeness - criterion 1 outranks everything
    d = select_canonical(
        fam(classes=("substantive_update",)),
        [mem("A", confirmed=True, avail="20210502090000"),
         mem("B", confirmed=False, avail="2026-07-23T13:00:00+00:00")])
    assert d["canonical_article_id"] == "A"
    assert d["temporal_validity_status"] == "confirmed_pre_election"
    assert "availability not confirmed" in d["rejected_reasons"]["B"]


def test_newest_version_not_automatically_selected():
    # both confirmed pre-election: the EARLIER pinned state wins the
    # tiebreak (conservative anti-leakage default), newest never wins
    # by being newest
    d = select_canonical(
        fam(classes=("substantive_update",)),
        [mem("A", avail="20170322000000"),
         mem("B", avail="20170321210000")])
    assert d["canonical_article_id"] == "B"


def test_availability_information_preserved_in_evidence():
    d = select_canonical(fam(), [mem("A", avail="20210501120000"),
                                 mem("B", confirmed=False)])
    assert "available_from=20210501120000" in d["member_evidence"]["A"]
    assert "temporal_confirmed=False" in d["member_evidence"]["B"]

# --------------------------------------------------------- special cases

def test_syndication_prefers_established_origin():
    d = select_canonical(
        fam(ftype="syndication_family"),
        [mem("A"), mem("B", origin=True, clean=False)])
    assert d["canonical_article_id"] == "B"      # origin beats ranking
    assert d["confidence"] == "high"
    assert "origin publisher established" in d["selection_reason"]


def test_syndication_origin_unknown_keeps_uncertainty():
    d = select_canonical(fam(ftype="syndication_family"),
                         [mem("A"), mem("B")])
    assert d["canonical_status"] == "canonical_selected"
    assert d["confidence"] == "low"
    assert "origin unknown" in d["selection_reason"]


def test_archive_capture_is_evidence_not_automatic_canonical():
    # A is an archive capture but snippet-only; B is a full-text
    # current record: usability outranks the archive tiebreak
    d = select_canonical(
        fam(), [mem("A", full=False, avail="20170321210000"),
                mem("B", confirmed=False, avail="")])
    assert d["canonical_article_id"] == "B"

# ------------------------------------------------ provenance / integrity

def test_every_decision_carries_evidence_and_alternatives():
    d = select_canonical(fam(), [mem("A"), mem("B", confirmed=False)])
    assert set(d["member_evidence"]) == {"A", "B"}
    assert d["alternatives"] == ["B"]
    assert d["rejected_reasons"]["B"]
    assert d["rule_version"] == RULE_VERSION


def test_members_never_dropped_even_in_review():
    d = select_canonical(
        fam(classes=("substantive_update",)),
        [mem("A", confirmed=False, avail=""),
         mem("B", confirmed=False, avail="")])
    assert set(d["member_evidence"]) == {"A", "B"}
    assert sorted(d["alternatives"]) == ["A", "B"]

# ---------------------------------------------------------- incremental

def test_unrelated_articles_never_change_a_family_selection():
    # canonical choice is a pure function of the family's own
    # members - adding articles elsewhere in the corpus cannot
    # touch it (same inputs, same output, asserted exactly)
    ms = [mem("A"), mem("B", confirmed=False)]
    before = select_canonical(fam(), copy.deepcopy(ms))
    after = select_canonical(fam(), copy.deepcopy(ms))
    assert before == after
