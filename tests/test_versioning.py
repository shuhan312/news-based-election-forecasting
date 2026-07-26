"""Phase 5 / Step 5 tests: version identity, separated temporal
evidence, leakage prevention (a post-election update can never enter
a pre-election window), family integrity and reproducibility."""

from src.dedup.versioning import (PREDICTION_WINDOWS, RULE_VERSION,
                                  availability, build_version_families,
                                  classify_version_pair, normalise_ts,
                                  temporal_profile, window_flags)

PARA1 = ("The returning officer for the Ashtead division confirmed on "
         "Thursday night that the count would continue into the early "
         "hours after a higher than expected turnout across the area.")
PARA2 = ("Party agents from all four campaigns watched as officials "
         "verified the postal ballots first, starting with the village "
         "hall boxes and the leisure centre boxes in strict order.")
PARA3 = ("A brief dispute over a bundle of doubtful papers was resolved "
         "by the deputy returning officer shortly after midnight without "
         "any formal objection from the agents present at the stage.")
RESULT_PARA = ("The Conservative candidate was declared the winner at "
               "half past two with a majority of 412 votes over the "
               "Liberal Democrat challenger after a single full count.")


def ev(aid, paras, title="Ashtead count continues", pub="", cap="",
       ret="", url="", author="", body_hash="", standfirst="",
       election="SCC-2021-05"):
    body = " ".join(paras)
    return {"article_id": aid, "source": "surreylive", "title": title,
            "standfirst": standfirst, "body": body,
            "paragraphs": list(paras), "author": author,
            "body_hash": body_hash, "canonical_url": url,
            "original_url": url, "election_id": election,
            "pub_date": pub, "update_ts": "", "capture_ts": cap,
            "retrieved_at": ret}


V_EARLY = ev("A", [PARA1, PARA2], pub="2021-05-01")
V_FULL = ev("B", [PARA1, PARA2, PARA3, RESULT_PARA], pub="2021-05-02")

# ------------------------------------------------- version identity

def test_identical_recapture():
    a = ev("A", [PARA1, PARA2, PARA3], pub="2021-05-01", body_hash="h1")
    b = ev("B", [PARA1, PARA2, PARA3], pub="2021-05-02", body_hash="h1")
    r = classify_version_pair(a, b)
    assert r["classification"] == "identical_recapture"
    assert r["chronology"] == "A->B"


def test_partial_to_full_version_linked():
    r = classify_version_pair(V_EARLY, V_FULL)
    assert r["classification"] == "partial_to_full_version"
    assert r["chronology"] == "A->B"
    assert r["paragraphs_added"] == 2         # PARA3 + result paragraph


def test_minor_vs_substantive_update_distinguished():
    base = [PARA1, PARA2, PARA3, RESULT_PARA]
    minor = ev("B", [PARA1.replace("Thursday night", "late Thursday"),
                     PARA2, PARA3, RESULT_PARA], pub="2021-05-02")
    r1 = classify_version_pair(ev("A", base, pub="2021-05-01"), minor)
    assert r1["classification"] == "minor_update"
    assert r1["paragraphs_modified"] == 1     # the edited PARA1 pairs up
    # a real substantive update keeps most text but rewrites one
    # paragraph and adds fresh reporting - replacing half the body is
    # follow-up-article grade and deliberately NOT this class
    rewritten = ev("C", [PARA1, PARA2,
                         PARA3.replace(
                             "without any formal objection from the "
                             "agents present at the stage",
                             "after the bundle was inspected a second "
                             "time at the request of two agents"),
                         RESULT_PARA,
                         "Recounts were ruled out after agents from all "
                         "campaigns accepted the verified totals at the "
                         "declaration table early on Friday morning."],
                   pub="2021-05-03")
    r2 = classify_version_pair(ev("A", base, pub="2021-05-01"), rewritten)
    assert r2["classification"] == "substantive_update"
    assert r2["paragraphs_added"] >= 1 and r2["paragraphs_modified"] >= 1


def test_archive_current_variant():
    a = ev("A", [PARA1, PARA2, PARA3], pub="2021-05-01",
           url="https://x/y", cap="20210501120000")
    b = ev("B", [PARA1, PARA2, PARA3 + " Updated line."],
           pub="2021-05-02", url="https://x/y", ret="2026-07-23T13:00")
    r = classify_version_pair(a, b)
    assert r["classification"] in ("archive_current_version",
                                   "identical_recapture")


def test_same_event_separate_articles_not_linked():
    a = ev("A", ["Voters queued outside polling stations across "
                 "Ashtead from early morning as the by-election opened "
                 "with four candidates standing for the vacant seat."],
           pub="2021-05-01")
    b = ev("B", ["The by-election in Ashtead closed at ten with agents "
                 "reporting brisk turnout throughout the day and a "
                 "count scheduled to begin immediately at the hall."],
           pub="2021-05-01")
    r = classify_version_pair(a, b)
    assert r["classification"] == "same_event_separate_article"
    assert build_version_families([r], {}) == []


def test_shared_names_alone_never_link():
    a = ev("A", [("Reform UK and the Conservatives clashed over council "
                  "tax in Woking while Labour and the Liberal Democrats "
                  "responded with their own detailed spending plans.")],
           pub="2021-05-01")
    b = ev("B", [("In Guildford the Liberal Democrats criticised Reform "
                  "UK and the Conservatives over planning policy while "
                  "Labour concentrated on the housing waiting list.")],
           pub="2021-05-01")
    assert classify_version_pair(a, b)["classification"] \
        == "same_event_separate_article"


def test_descriptive_change_booleans_recorded():
    changed_result = RESULT_PARA.replace("412", "398")
    a = ev("A", [PARA1, RESULT_PARA], title="Count continues",
           pub="2021-05-01", standfirst="First edition")
    b = ev("B", [PARA1, changed_result], title="Result declared",
           pub="2021-05-02", standfirst="Updated edition")
    r = classify_version_pair(a, b)
    assert r["title_changed"] and r["standfirst_changed"]
    assert r["numbers_changed"]
    assert isinstance(r["word_count_diff"], int)

# ------------------------------------------------- temporal evidence

def test_timestamp_kinds_stay_separate():
    a = ev("A", [PARA1, PARA2], pub="2021-05-01",
           cap="20210501120000", ret="2026-07-23T13:00:00+00:00")
    t = temporal_profile(a)
    assert t["published_at"]["value"] == "2021-05-01"
    assert t["archived_at"]["value"].startswith("2021-05-01T12")
    assert t["retrieved_at"]["value"].startswith("2026-07-23T13")
    # updated_at is absent in the v1 layer and is never substituted
    assert t["updated_at"]["value"] == ""
    assert t["updated_at"]["resolution_status"] \
        == "not_available_in_v1_layer"
    for k in ("published_at", "retrieved_at", "archived_at"):
        assert t[k]["provenance"] and t[k]["evidence_source"]


def test_timezones_normalised_to_utc():
    norm, tz = normalise_ts("2021-05-01T01:00:00+02:00")
    assert norm == "2021-04-30T23:00:00+00:00" and tz == "utc"
    norm2, tz2 = normalise_ts("20210501120000")
    assert norm2.endswith("+00:00") and tz2 == "utc"
    assert normalise_ts("2021-05-01")[1] == "date_only_no_time"


def test_bounded_interval_preserved_not_invented():
    a = ev("A", [PARA1, PARA2], pub="2021-05-01")     # no capture at all
    av = availability(a)
    assert av["availability_status"] == "bounded_available_interval"
    assert av["version_available_at"] == ""           # no exact invention
    assert av["available_lower_bound"] == "2021-05-01"
    assert av["available_upper_bound"] == ""


def test_missing_timestamps_enter_review_unordered():
    a = ev("A", [PARA1, PARA2, PARA3], pub="")
    b = ev("B", [PARA1, PARA2, PARA3], pub="2021-05-02")
    r = classify_version_pair(a, b)
    assert r["chronology"] == "unordered"
    assert "unordered" in r["review_reason"]
    fams = build_version_families([r], {"A": a, "B": b})
    assert fams[0]["ordered"] is False
    assert "unordered_timestamps_insufficient" in fams[0]["flags"]
    assert all(m["version_sequence"] is None for m in fams[0]["members"])


def test_capture_order_never_orders_versions():
    a = ev("A", [PARA1, PARA2, PARA3], pub="", cap="20210501120000")
    b = ev("B", [PARA1, PARA2, PARA3], pub="", cap="20210601120000")
    assert classify_version_pair(a, b)["chronology"] == "unordered"

# ---------------------------------------------- leakage prevention

def test_later_paragraphs_never_assigned_to_earlier_version():
    r = classify_version_pair(V_EARLY, V_FULL)
    # the added paragraphs are recorded AGAINST the pair, and the
    # early version's availability stays its own - text does not
    # travel backwards
    assert r["paragraphs_added"] == 2
    assert r["available_from_a"] == "2021-05-01"
    assert r["available_from_b"] == "2021-05-02"


def test_post_election_update_cannot_enter_pre_election_window():
    # SCC-2021-05 polling day is 2021-05-06. This update is published
    # AND first observed after polling day: every pre-election window
    # flag must be "no" - never yes_* of any kind.
    late = ev("B", [PARA1, PARA2, RESULT_PARA], pub="2021-05-08",
              ret="2026-07-23T13:00:00+00:00")
    flags = window_flags(late, "SCC-2021-05")
    assert all(v == "no" for v in flags.values())


def test_unarchived_pre_election_claim_is_flagged_not_confirmed():
    # published within the window, but the text state is first
    # observed only in 2026 - the pre-election claim rests on the
    # page's own date and must be marked for sensitivity testing,
    # never silently confirmed
    a = ev("A", [PARA1, PARA2], pub="2021-05-01",
           ret="2026-07-23T13:00:00+00:00")
    flags = window_flags(a, "SCC-2021-05")
    assert flags["in_window_one_week"] == "yes_publication_claim_only"
    assert "yes_confirmed" not in flags.values()


def test_archived_pre_election_text_is_confirmed():
    a = ev("A", [PARA1, PARA2], pub="2021-05-01", cap="20210502090000")
    flags = window_flags(a, "SCC-2021-05")
    assert flags["in_window_one_week"] == "yes_confirmed"
    assert flags["in_window_six_months"] == "yes_confirmed"


def test_uncertain_availability_never_silently_usable():
    a = ev("A", [PARA1], pub="")                      # no date, no capture
    flags = window_flags(a, "SCC-2021-05")
    assert set(flags.values()) == {"excluded_uncertain"}
    empty = ev("E", [], pub="")
    assert availability(empty)["availability_status"] \
        == "not_temporally_usable"
    assert set(window_flags(empty, "SCC-2021-05").values()) \
        == {"not_usable"}


def test_window_flags_cover_all_configured_windows():
    a = ev("A", [PARA1, PARA2], pub="2021-03-01", cap="20210302090000")
    flags = window_flags(a, "SCC-2021-05")
    assert set(flags) == {f"in_window_{w}" for w in PREDICTION_WINDOWS}
    # 66 days before polling: inside six/three months, outside shorter
    assert flags["in_window_six_months"] == "yes_confirmed"
    assert flags["in_window_three_months"] == "yes_confirmed"
    assert flags["in_window_one_month"] == "no"
    assert flags["in_window_final_72_hours"] == "no"

# --------------------------------------------------- family integrity

def test_version_numbers_and_links_follow_publication_dates():
    r = classify_version_pair(V_EARLY, V_FULL)
    fams = build_version_families([r], {"A": V_EARLY, "B": V_FULL})
    assert fams[0]["ordered"] is True
    m = {x["article_id"]: x for x in fams[0]["members"]}
    assert m["A"]["version_sequence"] == 1
    assert m["B"]["version_sequence"] == 2
    assert m["A"]["successor"] == "B" and m["B"]["predecessor"] == "A"
    assert m["A"]["predecessor"] is None and m["B"]["successor"] is None


def test_no_cycles_in_ordered_chain():
    v3 = ev("C", [PARA1, PARA2, PARA3, RESULT_PARA,
                  "Reaction from the defeated candidates followed at "
                  "the declaration with each thanking their agents."],
            pub="2021-05-03")
    rels = [classify_version_pair(V_EARLY, V_FULL),
            classify_version_pair(V_FULL, v3),
            classify_version_pair(V_EARLY, v3)]
    fams = build_version_families(
        rels, {"A": V_EARLY, "B": V_FULL, "C": v3})
    chain = sorted(fams[0]["members"],
                   key=lambda m: m["version_sequence"])
    seen = set()
    for m in chain:                       # linear: no member repeats,
        assert m["article_id"] not in seen  # predecessor precedes
        seen.add(m["article_id"])
        if m["predecessor"]:
            assert m["predecessor"] in seen


def test_all_versions_and_hashes_preserved():
    r = classify_version_pair(V_EARLY, V_FULL)
    fams = build_version_families([r], {"A": V_EARLY, "B": V_FULL})
    assert fams[0]["size"] == 2
    assert {m["article_id"] for m in fams[0]["members"]} == {"A", "B"}
    assert all("body_hash" in m and "available_from" in m
               for m in fams[0]["members"])


def test_missing_body_goes_to_review():
    a = ev("A", [], pub="2021-05-01")
    r = classify_version_pair(a, V_FULL)
    assert r["classification"] == "manual_review"
    assert r["relationship_confidence"] == "none"

# ------------------------------------------ determinism / incremental

def test_deterministic():
    assert classify_version_pair(V_EARLY, V_FULL) == \
        classify_version_pair(V_EARLY, V_FULL)


def test_incremental_addition_leaves_unrelated_family_alone():
    r1 = classify_version_pair(V_EARLY, V_FULL)
    before = build_version_families([r1], {"A": V_EARLY, "B": V_FULL})
    other_a = ev("X", [PARA3, RESULT_PARA], pub="2021-05-03")
    other_b = ev("Y", [PARA3, RESULT_PARA], pub="2021-05-04")
    r2 = classify_version_pair(other_a, other_b)
    after = build_version_families(
        [r1, r2], {"A": V_EARLY, "B": V_FULL,
                   "X": other_a, "Y": other_b})
    fam_ab = [f for f in after if f["family_id"] == before[0]["family_id"]]
    assert fam_ab and fam_ab[0]["members"] == before[0]["members"]


def test_version_stamped():
    r = classify_version_pair(V_EARLY, V_FULL)
    assert r["rule_version"] == RULE_VERSION
