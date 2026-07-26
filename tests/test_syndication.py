"""Phase 5 / Step 4 tests: classification vocabulary, direction
rules, independence protection, determinism."""

from src.dedup.syndication import (RULE_VERSION, build_families,
                                   classify_pair)

BODY = ("The returning officer for the Ashtead division confirmed on "
        "Thursday night that the count would continue into the early "
        "hours after a higher than expected turnout. Party agents "
        "from all four campaigns watched as officials verified the "
        "postal ballots first, starting with the village hall boxes. "
        "A brief dispute over doubtful papers was resolved by the "
        "deputy returning officer shortly after midnight.")


def ev(aid, source, body=BODY, author="", pub="2026-05-01",
       paragraphs=None):
    return {"article_id": aid, "source": source, "body": body,
            "paragraphs": paragraphs if paragraphs is not None
            else body.split(". "), "author": author,
            "pub_date": pub, "capture_ts": ""}


def scores(j, c):
    return {"jaccard": j, "containment": c}

# ------------------------------------------------------- classification

def test_attributed_republication_confirmed_with_direction():
    src = ev("A", "surreylive", pub="2026-05-01")
    dst = ev("B", "surrey_comet",
             body=BODY + " This article originally appeared on "
                         "SurreyLive.",
             pub="2026-05-02")
    r = classify_pair(scores(0.9, 0.95), src, dst)
    assert r["classification"] == "confirmed_syndicated_copy"
    assert r["direction"] == "A->B"
    assert r["direction_confidence"] == "attribution_plus_chronology"


def test_wholesale_reuse_without_attribution_is_probable_undirected():
    r = classify_pair(scores(0.85, 0.9),
                      ev("A", "surreylive"), ev("B", "surrey_comet"))
    assert r["classification"] == "probable_syndicated_copy"
    assert r["direction"] == "undirected"


def test_shared_wire_copy_detected_by_byline():
    a = ev("A", "surreylive", author="PA Reporter")
    b = ev("B", "farnham_herald",
           body="Local intro differs here. " + BODY,
           author="PA Reporter")
    r = classify_pair(scores(0.35, 0.6), a, b)
    assert r["classification"] == "shared_wire_or_press_release"


def test_press_release_marker_beats_manual_review():
    a = ev("A", "surreylive", body=BODY + " the council said in a press "
                                          "release issued on Friday.")
    b = ev("B", "guildford_dragon", body="Intro. " + BODY)
    r = classify_pair(scores(0.3, 0.5), a, b)
    assert r["classification"] == "shared_wire_or_press_release"


def test_shared_blocks_without_markers_go_to_review():
    r = classify_pair(scores(0.3, 0.5),
                      ev("A", "surreylive"), ev("B", "bbc_surrey"))
    assert r["classification"] == "manual_review"


def test_independent_reporting_not_syndicated():
    a = ev("A", "surreylive",
           paragraphs=["Completely different paragraph one here today.",
                       "Another distinct paragraph follows the first."])
    b = ev("B", "bbc_surrey",
           body="Unrelated text about the same election entirely.",
           paragraphs=["Unrelated text about the same election entirely."])
    r = classify_pair(scores(0.1, 0.2), a, b)
    assert r["classification"] == "independent_reporting_same_event"


def test_short_shared_quote_does_not_trigger():
    quote = '"We are delighted with the result," said the candidate.'
    a = ev("A", "surreylive", paragraphs=["Own reporting here.", quote])
    b = ev("B", "bbc_surrey", paragraphs=["Different reporting.", quote])
    # one shared paragraph (< 2) and low jaccard -> never syndication
    r = classify_pair(scores(0.1, 0.15), a, b)
    assert r["classification"] in ("independent_reporting_same_event",
                                   "manual_review")
    assert r["classification"] not in ("confirmed_syndicated_copy",
                                       "probable_syndicated_copy",
                                       "shared_wire_or_press_release")


def test_missing_body_insufficient():
    r = classify_pair(scores(0.0, 0.0),
                      ev("A", "surreylive", body="", paragraphs=[]),
                      ev("B", "bbc_surrey"))
    assert r["classification"] == "insufficient_evidence"

# ------------------------------------------------------------ direction

def test_inconsistent_chronology_blocks_direction():
    src = ev("A", "surreylive", pub="2026-05-10")   # "source" LATER
    dst = ev("B", "surrey_comet",
             body=BODY + " Republished from SurreyLive.",
             pub="2026-05-02")
    r = classify_pair(scores(0.9, 0.95), src, dst)
    assert r["classification"] == "confirmed_syndicated_copy"
    assert r["direction"] == "undirected"          # marker vs dates clash


def test_capture_order_alone_never_directs():
    r = classify_pair(scores(0.85, 0.9),
                      ev("A", "surreylive", pub=""),
                      ev("B", "surrey_comet", pub=""))
    assert r["direction"] == "undirected"

# ----------------------------------------------------- families / misc

def test_families_from_syndication_grade_pairs_only():
    rels = [
        classify_pair(scores(0.9, 0.95), ev("A", "s1"), ev("B", "s2")),
        classify_pair(scores(0.1, 0.1),
                      ev("C", "s1",
                         paragraphs=["Own words entirely different."]),
                      ev("D", "s2", body="Nothing shared here at all.",
                         paragraphs=["Nothing shared here at all."])),
    ]
    fams = build_families(rels)
    assert len(fams) == 1
    assert fams[0]["member_ids"] == ["A", "B"]
    assert fams[0]["family_id"].startswith("SYN-")


def test_deterministic():
    a, b = ev("A", "s1"), ev("B", "s2")
    assert classify_pair(scores(0.5, 0.6), a, b) == \
        classify_pair(scores(0.5, 0.6), a, b)


def test_version_stamped():
    r = classify_pair(scores(0.9, 0.9), ev("A", "s1"), ev("B", "s2"))
    assert r["rule_version"] == RULE_VERSION
