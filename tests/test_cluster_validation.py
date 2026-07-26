"""Phase 5 / Step 6 tests: coherence, false-transitivity prevention,
deterministic conflict resolution, temporal safety, integrity and
reproducibility of the validated families."""

import copy
import random

from src.dedup.cluster_validation import (RULE_VERSION, validate_graph)


def art(words=500, quality="ready_full_text", avail="2021-05-01",
        status="confirmed_available_at"):
    return {"words": words, "quality": quality, "pub_date": "2021-05-01",
            "availability_status": status, "available_from": avail}


def edge(a, b, etype, cls, j=0.9, c=0.9, step="step3", decision=""):
    return {"a": min(a, b), "b": max(a, b), "edge_type": etype,
            "source_step": step, "classification": cls,
            "confidence": "high",
            "evidence": {"jaccard": j, "containment": c},
            "review_status": "human_resolved" if decision else "",
            "human_decision": decision}


ARTS3 = {"A": art(), "B": art(), "C": art()}

# ---------------------------------------------------------- coherence

def test_exact_family_coherent_and_typed():
    r = validate_graph({"A": art(), "B": art()},
                       [edge("A", "B", "exact_duplicate",
                             "exact_duplicate", j=1.0, step="step1")])
    f = r["families"][0]
    assert f["family_type"] == "exact_duplicate_family"
    assert f["validation_status"] == "validated_retained"


def test_near_duplicate_cluster_with_full_support_retained():
    r = validate_graph(ARTS3, [
        edge("A", "B", "near_duplicate", "high_confidence_near_duplicate",
             j=0.8),
        edge("B", "C", "near_duplicate", "high_confidence_near_duplicate",
             j=0.8),
        edge("A", "C", "near_duplicate", "probable_near_duplicate",
             j=0.6)])
    f = r["families"][0]
    assert f["family_type"] == "near_duplicate_family"
    assert f["validation_status"] == "validated_retained"
    assert f["unsupported_pairs"] == []


def test_version_family_typed_and_temporally_consistent():
    arts = {"A": art(avail="2021-05-01"), "B": art(avail="2021-05-02")}
    r = validate_graph(arts, [
        edge("A", "B", "version", "substantive_update", j=0.8,
             step="step5")])
    f = r["families"][0]
    assert f["family_type"] == "same_article_version_family"
    assert "members_have_different_temporal_availability" in f["warnings"]


def test_syndication_layer_stays_distinct_from_version_layer():
    # A-B are same-publisher versions; B-C is cross-publisher
    # syndication. Two families in two layers; never one merged blob.
    arts = {"A": art(), "B": art(), "C": art()}
    r = validate_graph(arts, [
        edge("A", "B", "version", "minor_update", j=0.9, step="step5"),
        edge("B", "C", "syndication", "confirmed_syndicated_copy",
             j=0.9, step="step4")])
    layers = {(f["layer"], tuple(f["members"])) for f in r["families"]}
    assert ("same_article", ("A", "B")) in layers
    assert ("syndication", ("B", "C")) in layers
    assert r["article_status"]["B"]["status"] == "in_validated_family"
    assert len(r["article_status"]["B"]["families"]) == 2


def test_independent_same_event_articles_never_merge():
    r = validate_graph(ARTS3, [
        edge("A", "B", "near_duplicate",
             "same_event_independent_reporting", j=0.15)])
    assert r["families"] == []
    assert r["article_status"]["A"]["status"] == "independent_article"

# ------------------------------------------------------- transitivity

def test_chain_endpoints_without_overlap_flagged_not_merged_silently():
    # A-B and B-C are strong, but A and C share almost nothing: the
    # component survives as a REVIEW case with the unsupported bridge
    # named - never a silently validated family
    r = validate_graph(ARTS3, [
        edge("A", "B", "near_duplicate", "high_confidence_near_duplicate",
             j=0.8),
        edge("B", "C", "near_duplicate", "high_confidence_near_duplicate",
             j=0.8),
        edge("A", "C", "near_duplicate", "not_near_duplicate",
             j=0.05, c=0.05)])
    f = r["families"][0]
    assert f["validation_status"] == "review"
    assert "A|C" in f["unsupported_pairs"]
    assert "unsupported_transitive_bridge" in f["warnings"]


def test_snippet_record_cannot_bridge_full_articles():
    arts = {"A": art(words=600), "B": art(words=40), "C": art(words=600)}
    r = validate_graph(arts, [
        edge("A", "B", "near_duplicate", "high_confidence_near_duplicate",
             j=0.9),
        edge("B", "C", "near_duplicate", "high_confidence_near_duplicate",
             j=0.9)])
    assert r["families"] == []          # both edges blocked at source
    assert any(c["rule"] == "snippet_cannot_bridge"
               for c in r["conflicts"])


def test_contradictory_chain_goes_to_review():
    # A-B, B-C linked, and a positive independent-reporting decision
    # on A-C sits INSIDE the component: contradiction surfaced
    r = validate_graph(ARTS3, [
        edge("A", "B", "near_duplicate", "high_confidence_near_duplicate",
             j=0.8),
        edge("B", "C", "near_duplicate", "high_confidence_near_duplicate",
             j=0.8),
        edge("A", "C", "near_duplicate",
             "same_event_independent_reporting", j=0.3)])
    f = r["families"][0]
    assert f["family_type"] == "ambiguous_family"
    assert f["validation_status"] == "review"
    assert "A|C" in f["contradictions"]


def test_no_automatic_a_c_equivalence_claim():
    # linking A-B and B-C never fabricates an A-C edge: the output
    # relationships are exactly the input pairs, annotated
    ins = [edge("A", "B", "near_duplicate",
                "high_confidence_near_duplicate", j=0.8),
           edge("B", "C", "near_duplicate",
                "high_confidence_near_duplicate", j=0.8)]
    r = validate_graph(ARTS3, ins)
    pairs = {(e["a"], e["b"]) for e in r["relationships"]}
    assert pairs == {("A", "B"), ("B", "C")}

# -------------------------------------------------- conflict rules

def test_exact_supersedes_near_duplicate_label():
    r = validate_graph({"A": art(), "B": art()}, [
        edge("A", "B", "exact_duplicate", "exact_duplicate", j=1.0,
             step="step1"),
        edge("A", "B", "near_duplicate", "probable_near_duplicate",
             j=0.6)])
    nd = [e for e in r["relationships"]
          if e["edge_type"] == "near_duplicate"][0]
    assert nd["disposition"] == "superseded"
    assert r["families"][0]["family_type"] == "exact_duplicate_family"
    assert any(c["rule"] == "exact_overrides_near_duplicate"
               for c in r["conflicts"])


def test_human_separate_decision_blocks_merge():
    r = validate_graph({"A": art(), "B": art()}, [
        edge("A", "B", "near_duplicate", "probable_near_duplicate",
             j=0.5, decision="same_event_separate_article"),
        edge("A", "B", "version", "ambiguous_version_relationship",
             j=0.5, step="step5",
             decision="same_event_separate_article")])
    assert r["families"] == []
    assert any(c["rule"] == "independent_reporting_blocks_merge"
               for c in r["conflicts"])


def test_same_url_different_content_requires_version_evidence():
    r = validate_graph({"A": art(), "B": art()}, [
        edge("A", "B", "same_canonical_url",
             "url_variant_probable_same_page", j=0.0, step="step2")])
    assert r["families"] == []
    assert any(c["rule"] == "same_url_changed_content_needs_version"
               for c in r["conflicts"])
    # with version evidence on the same pair, the link stands:
    r2 = validate_graph({"A": art(), "B": art()}, [
        edge("A", "B", "same_canonical_url",
             "url_variant_probable_same_page", j=0.0, step="step2"),
        edge("A", "B", "version", "substantive_update", j=0.75,
             step="step5")])
    assert r2["families"][0]["family_type"] \
        == "same_article_version_family"


def test_syndication_never_creates_same_article_family():
    r = validate_graph({"A": art(), "B": art()}, [
        edge("A", "B", "syndication", "confirmed_syndicated_copy",
             j=0.95, step="step4")])
    assert all(f["layer"] == "syndication" for f in r["families"])
    assert r["families"][0]["family_type"] == "syndication_family"


def test_wire_family_typed_separately():
    r = validate_graph({"A": art(), "B": art()}, [
        edge("A", "B", "syndication", "shared_wire_or_press_release",
             j=0.4, step="step4")])
    assert r["families"][0]["family_type"] \
        == "shared_press_release_family"


def test_unresolved_ambiguous_stays_out_and_visible():
    r = validate_graph({"A": art(), "B": art()}, [
        edge("A", "B", "version", "ambiguous_version_relationship",
             j=0.5, step="step5")])
    assert r["families"] == []
    e = r["relationships"][0]
    assert e["disposition"] == "non_linking"   # visible, never guessed

# ---------------------------------------------------- temporal safety

def test_member_availability_copied_verbatim_never_altered():
    arts = {"A": art(avail="20210501120000"),
            "B": art(avail="2026-07-23T13:00:00+00:00")}
    snapshot = copy.deepcopy(arts)
    r = validate_graph(arts, [
        edge("A", "B", "version", "substantive_update", j=0.8,
             step="step5")])
    assert arts == snapshot                    # inputs untouched
    m = {x["article_id"]: x for x in r["families"][0]["member_temporal"]}
    assert m["A"]["available_from"] == "20210501120000"
    assert m["B"]["available_from"] == "2026-07-23T13:00:00+00:00"
    assert r["families"][0]["temporal_safety"] == "preserved"


def test_different_availability_flagged_against_collapse():
    arts = {"A": art(avail="2021-05-01"), "B": art(avail="2021-06-01")}
    r = validate_graph(arts, [
        edge("A", "B", "version", "minor_update", j=0.9, step="step5")])
    assert "members_have_different_temporal_availability" \
        in r["families"][0]["warnings"]

# ------------------------------------------ integrity / reproducibility

def test_every_article_gets_explicit_status():
    arts = {"A": art(), "B": art(), "Z": art()}
    r = validate_graph(arts, [
        edge("A", "B", "near_duplicate", "high_confidence_near_duplicate",
             j=0.8)])
    assert set(r["article_status"]) == {"A", "B", "Z"}
    assert r["article_status"]["Z"]["status"] == "independent_article"


def test_every_input_relationship_retained():
    ins = [edge("A", "B", "near_duplicate", "not_near_duplicate", j=0.1),
           edge("B", "C", "near_duplicate",
                "same_event_independent_reporting", j=0.2)]
    r = validate_graph(ARTS3, ins)
    assert len(r["relationships"]) == 2
    assert all(e["disposition"] == "non_linking"
               for e in r["relationships"])


def test_deterministic_and_order_independent():
    ins = [edge("A", "B", "near_duplicate",
                "high_confidence_near_duplicate", j=0.8),
           edge("B", "C", "near_duplicate",
                "high_confidence_near_duplicate", j=0.8),
           edge("A", "C", "near_duplicate", "probable_near_duplicate",
                j=0.6)]
    r1 = validate_graph(ARTS3, [copy.deepcopy(e) for e in ins])
    shuffled = [copy.deepcopy(e) for e in ins]
    random.Random(7).shuffle(shuffled)
    r2 = validate_graph(dict(reversed(list(ARTS3.items()))), shuffled)
    assert r1["families"] == r2["families"]


def test_unrelated_addition_keeps_family_id_membership_change_does_not():
    ins = [edge("A", "B", "version", "minor_update", j=0.9, step="step5")]
    base = validate_graph({"A": art(), "B": art()},
                          [copy.deepcopy(e) for e in ins])
    fid = base["families"][0]["family_id"]
    grown = validate_graph(
        {"A": art(), "B": art(), "Z": art()},
        [copy.deepcopy(ins[0])])
    assert grown["families"][0]["family_id"] == fid    # Z is unrelated
    changed = validate_graph(
        {"A": art(), "B": art(), "C": art()},
        [copy.deepcopy(ins[0]),
         edge("B", "C", "version", "minor_update", j=0.9, step="step5")])
    assert changed["families"][0]["family_id"] != fid  # new membership,
    assert changed["families"][0]["size"] == 3         # new id


def test_rule_version_stamped():
    r = validate_graph({"A": art(), "B": art()}, [
        edge("A", "B", "version", "minor_update", j=0.9, step="step5")])
    assert r["rule_version"] == RULE_VERSION
    assert r["families"][0]["rule_version"] == RULE_VERSION
