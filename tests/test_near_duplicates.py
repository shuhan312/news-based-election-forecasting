"""Phase 5 / Step 3 tests: detection of edited/truncated copies,
protection of independent reporting, conservative short-text
handling, determinism and incremental stability."""

from src.dedup.near_duplicates import (RULE_VERSION,
                                       detect_near_duplicates)

BASE = ("The returning officer for the Ashtead division confirmed on "
        "Thursday night that the count would continue into the early "
        "hours after a higher than expected turnout across the "
        "division. Party agents from all four campaigns watched as "
        "officials verified the postal ballots first. Counting staff "
        "processed the boxes from twelve polling stations in order of "
        "arrival, starting with the village hall and the leisure "
        "centre. A brief dispute over a bundle of doubtful papers was "
        "resolved by the deputy returning officer shortly after "
        "midnight without any formal objection from the agents. "
        "Observers from the local press were permitted to watch the "
        "verification from a roped area beside the stage. The "
        "declaration was expected before three in the morning, and "
        "council officials said the result would be posted on the "
        "authority website within the hour. Turnout figures released "
        "earlier in the evening suggested participation well above "
        "the previous by-election in the neighbouring division.")


def art(aid, title, body, source="surreylive"):
    return {"article_id": aid, "title": title, "body_text": body,
            "source_name": source}


def run(arts, exact=None, url=None):
    return detect_near_duplicates(arts, exact or set(), url or set())


def pair_of(res, a, b):
    for p in res["pairs"]:
        if {p["article_id_a"], p["article_id_b"]} == {a, b}:
            return p
    return None

# ------------------------------------------------------------- detection

def test_lightly_edited_copy_detected():
    edited = BASE.replace("Thursday night", "late on Thursday") \
                 .replace("four campaigns", "the campaigns")
    res = run([art("A", "Count continues in Ashtead", BASE),
               art("B", "Count goes on in Ashtead", edited)])
    p = pair_of(res, "A", "B")
    assert p and p["classification"] == "high_confidence_near_duplicate"
    assert p["jaccard"] >= 0.7
    assert len(res["clusters"]) == 1


def test_truncated_copy_found_by_containment():
    truncated = " ".join(BASE.split()[:60])   # first third only
    res = run([art("A", "Full report", BASE),
               art("B", "Short version", truncated)])
    p = pair_of(res, "A", "B")
    assert p and p["classification"] == "manual_review"  # short side
    # a longer truncation (above the short-text floor) is automatic:
    longer_cut = " ".join(BASE.split()[:110])
    res2 = run([art("A", "Full report", BASE),
                art("C", "Trimmed version", longer_cut)])
    p2 = pair_of(res2, "A", "C")
    assert p2 and p2["classification"] == "partial_full_text_match"
    assert p2["containment"] >= 0.85


def test_cross_publisher_high_overlap_flags_syndication_candidate():
    res = run([art("A", "Count continues", BASE, source="surreylive"),
               art("B", "Count continues", BASE + "Extra line here.",
                   source="surrey_comet")])
    p = pair_of(res, "A", "B")
    assert p["classification"] in ("high_confidence_near_duplicate",
                                   "partial_full_text_match")
    assert "possible_syndication_candidate" in p["flags"]

# ------------------------------------------- independence protection

INDEP_A = ("Voters in Ashtead went to the polls on Thursday for a "
           "county by-election triggered by the resignation of the "
           "sitting councillor. Turnout appeared brisk at several "
           "polling stations, with queues reported in the morning. "
           "The Conservative, Labour, Liberal Democrat and Reform UK "
           "candidates all visited polling stations during the day. ") * 3
INDEP_B = ("A by-election was held in the Ashtead division on Thursday "
           "after the previous councillor stepped down earlier this "
           "year. Residents formed queues outside some stations before "
           "work, and campaigners said interest was unusually high. "
           "Candidates for Reform UK, the Liberal Democrats, Labour "
           "and the Conservatives spent the day meeting voters. ") * 3


def test_same_event_independent_reporting_not_merged():
    res = run([art("A", "Ashtead by-election: polls open", INDEP_A),
               art("B", "Ashtead goes to the polls", INDEP_B,
                   source="bbc_surrey")])
    p = pair_of(res, "A", "B")
    if p is not None:      # may not even survive blocking
        assert p["classification"] in (
            "same_event_independent_reporting", "not_near_duplicate",
            "manual_review")
        assert p["classification"] not in (
            "high_confidence_near_duplicate", "probable_near_duplicate")
    assert res["clusters"] == []


def test_shared_names_alone_never_duplicate():
    a = ("Reform UK and the Conservatives clashed over council tax in "
         "Woking on Tuesday, with Labour and the Liberal Democrats "
         "responding. ") * 6
    b = ("In Guildford, the Liberal Democrats criticised Reform UK "
         "and the Conservatives over planning policy, while Labour "
         "stayed silent. ") * 6
    res = run([art("A", "Woking row", a), art("B", "Guildford row", b)])
    p = pair_of(res, "A", "B")
    assert p is None or p["classification"] in (
        "not_near_duplicate", "same_event_independent_reporting")

# -------------------------------------------------- exactness / safety

def test_exact_pairs_referenced_not_reclassified():
    res = run([art("A", "T", BASE), art("B", "T", BASE)],
              exact={frozenset(("A", "B"))})
    p = pair_of(res, "A", "B")
    assert p["classification"] == "exact_duplicate_reference"
    assert res["clusters"] == []


def test_short_snippets_conservative():
    s = "Polls close at ten tonight in Ashtead."
    res = run([art("A", "Polls", s), art("B", "Polls", s + " Extra.")],
              url={frozenset(("A", "B"))})
    p = pair_of(res, "A", "B")
    assert p["classification"] in ("manual_review", "not_near_duplicate")


def test_every_pair_carries_scores_and_evidence():
    res = run([art("A", "T", BASE), art("B", "T", BASE + " tail.")])
    for p in res["pairs"]:
        for k in ("jaccard", "containment", "title_sim", "seq_ratio",
                  "length_ratio", "shared_shingles"):
            assert k in p

# ------------------------------------------ determinism / incremental

def test_deterministic_and_order_independent():
    arts = [art("A", "T", BASE), art("B", "T2", BASE + " x."),
            art("C", "Other", INDEP_A)]
    assert run(arts) == run(list(reversed(arts)))


def test_incremental_addition_leaves_unrelated_pairs_alone():
    before = run([art("A", "T", BASE), art("B", "T", BASE + " x.")])
    pa = pair_of(before, "A", "B")
    after = run([art("A", "T", BASE), art("B", "T", BASE + " x."),
                 art("Z", "Unrelated", INDEP_B)])
    pb = pair_of(after, "A", "B")
    assert pa["classification"] == pb["classification"]
    assert pa["jaccard"] == pb["jaccard"]


def test_version_stamped():
    assert run([art("A", "T", BASE)])["rule_version"] == RULE_VERSION
