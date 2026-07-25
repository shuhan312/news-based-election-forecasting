"""Phase 5 / Step 1 tests: clustering rules, safety, determinism,
incremental stability."""

from src.dedup.exact_duplicates import (RULE_VERSION,
                                        detect_exact_duplicates)

BODY_A = "The count finished at two in the morning. " * 5
BODY_B = "A completely different report about the election. " * 5


def art(aid, title="T", body=BODY_A, ds="ready_full_text", stand=""):
    return {"article_id": aid, "title": title, "standfirst": stand,
            "body_text": body, "downstream_status": ds,
            "quality_status": "valid_full_text"}


def run(arts):
    return detect_exact_duplicates(arts)


def by_id(res):
    return {r["article_id"]: r for r in res["mapping"]}

# ------------------------------------------------------------ clustering

def test_identical_bodies_cluster_together():
    res = run([art("A1"), art("A2"), art("B1", body=BODY_B)])
    m = by_id(res)
    assert m["A1"]["cluster_id"] == m["A2"]["cluster_id"] != ""
    assert m["A1"]["exact_duplicate_status"] == "exact_duplicate"
    assert m["A1"]["cluster_size"] == 2
    assert m["B1"]["exact_duplicate_status"] == "unique"


def test_different_bodies_never_share_a_cluster():
    res = run([art("A1"), art("B1", body=BODY_B)])
    m = by_id(res)
    assert m["A1"]["cluster_id"] == "" and m["B1"]["cluster_id"] == ""


def test_empty_bodies_never_group():
    res = run([art("E1", body="", ds="not_usable_for_text_analysis"),
               art("E2", body="", ds="not_usable_for_text_analysis")])
    m = by_id(res)
    assert m["E1"]["exact_duplicate_status"] == "not_clustered_unusable"
    assert m["E1"]["cluster_id"] == "" == m["E2"]["cluster_id"]


def test_snippets_not_confirmed_duplicates():
    res = run([art("S1", ds="restricted_snippet_only"),
               art("S2", ds="restricted_snippet_only")])
    m = by_id(res)
    assert m["S1"]["exact_duplicate_status"].startswith("not_clustered")
    assert m["S1"]["cluster_id"] == ""

# ----------------------------------------------------------------- flags

def test_same_title_different_body_flagged_not_clustered():
    res = run([art("A1", title="Same headline"),
               art("B1", title="Same headline", body=BODY_B)])
    m = by_id(res)
    assert m["A1"]["cluster_id"] == "" == m["B1"]["cluster_id"]
    assert "same_title_different_body" in m["A1"]["flags"]
    assert "same_title_different_body" in m["B1"]["flags"]


def test_same_body_different_title_clustered_and_flagged():
    res = run([art("A1", title="Morning headline"),
               art("A2", title="Evening headline")])
    m = by_id(res)
    assert m["A1"]["cluster_id"] == m["A2"]["cluster_id"] != ""
    assert "same_body_different_title" in m["A1"]["flags"]


def test_duplicate_article_id_flagged():
    res = run([art("X1"), art("X1", body=BODY_B)])
    assert any("duplicate_article_id" in r["flags"]
               for r in res["mapping"])

# ----------------------------------------------- determinism / stability

def test_every_record_mapped_exactly_once():
    arts = [art(f"N{i}", body=f"Body number {i}. " * 10) for i in range(7)]
    res = run(arts)
    assert len(res["mapping"]) == 7
    assert len({r["article_id"] for r in res["mapping"]}) == 7


def test_deterministic_regardless_of_input_order():
    arts = [art("A1"), art("A2"), art("B1", body=BODY_B)]
    assert run(arts) == run(list(reversed(arts)))


def test_incremental_addition_keeps_existing_cluster_ids():
    before = run([art("A1"), art("A2")])
    cid_before = by_id(before)["A1"]["cluster_id"]
    # a NEW unrelated article arrives (future release scenario)
    after = run([art("A1"), art("A2"), art("C1", body=BODY_B)])
    assert by_id(after)["A1"]["cluster_id"] == cid_before
    # and a new member of the same cluster enlarges it, same id
    grown = run([art("A1"), art("A2"), art("A3")])
    assert by_id(grown)["A1"]["cluster_id"] == cid_before
    assert by_id(grown)["A1"]["cluster_size"] == 3


def test_version_stamped():
    assert run([art("A1")])["rule_version"] == RULE_VERSION
