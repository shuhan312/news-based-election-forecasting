"""Phase 4 / Step 6 tests: status assignment, quality signals,
safety/coverage, reproducibility."""

from src.normalisation.text_quality import (RULE_VERSION,
                                            assess_quality)

FULL_PARA = ("The returning officer confirmed the result shortly "
             "after two o'clock, thanking the count staff. ")


def art(title="A title here", body_paras=None, standfirst=""):
    paras = body_paras if body_paras is not None else [
        FULL_PARA * 3 + f"Distinct closing sentence number {i}."
        for i in range(4)]
    return {"article_id": "NEWS-test-0001", "title": title,
            "standfirst": standfirst,
            "body_text": "\n\n".join(paras), "body_paragraphs": paras,
            "status": "structured", "warning_flags": []}


def q(article, **up):
    return assess_quality(article, up)

# ------------------------------------------------------ status assignment

def test_complete_body_is_valid_full():
    r = q(art(), step1_status="full_text")
    assert r["quality_status"] == "valid_full_text"
    assert r["review_required"] is False


def test_genuine_short_article_valid_not_unusable():
    body = ["The by-election will be held on Thursday. Ten candidates "
            "are standing across the division. Polls open at 7am and "
            "close at 10pm sharp. Counting begins immediately after "
            "the polls close at the leisure centre."]
    r = q(art(body_paras=body), step1_status="full_text")
    assert r["quality_status"] == "valid_full_text"
    assert "short_article" in r["warning_flags"]


def test_short_truncated_body_is_partial():
    body = ["Votes were still being counted late into the night when "
            "the returning officer, flanked by exhausted agents from "
            "all four parties, suddenly announced to the waiting hall "
            "that because of an unexplained discrepancy the process would"]
    r = q(art(body_paras=body))
    assert r["quality_status"] == "valid_partial_text"
    assert "possible_truncation" in r["warning_flags"]


def test_upstream_partial_source_is_partial():
    r = q(art(), step1_status="partial_text")
    assert r["quality_status"] == "valid_partial_text"


def test_snippet_only_never_full():
    r = q(art(body_paras=[]), step1_status="snippet_only")
    assert r["quality_status"] == "snippet_only"


def test_title_only_record_goes_to_review():
    r = q(art(title="A very long headline about the local elections",
              body_paras=["Short echo."]), step1_status="full_text")
    assert r["quality_status"] == "review_required"
    assert "title_only_shape" in r["warning_flags"]


def test_missing_body_without_resolution_reviews():
    r = q(art(body_paras=[]))
    assert r["quality_status"] == "missing_body"
    assert r["review_required"] is True


def test_resolved_media_only_missing_body_no_review():
    r = q(art(body_paras=[]), media_resolution=True)
    assert r["quality_status"] == "missing_body"
    assert r["review_required"] is False
    assert "media_only_resolved" in r["warning_flags"]


def test_challenge_shell_unusable():
    r = q(art(body_paras=["Just a moment... checking your browser "
                          "before accessing the site." + FULL_PARA]))
    assert r["quality_status"] == "unusable_text"

# -------------------------------------------------------- quality signals

def test_word_count_alone_does_not_decide():
    # Same tiny word count, three different outcomes depending on
    # other signals: truncation -> partial; clean prose -> full(short);
    # upstream-full conflict at near-empty -> review.
    trunc = q(art(body_paras=["Fifty voters and a dozen party agents "
                              "waited in the hall through the early "
                              "hours as the returning officer checked "
                              "two disputed bundles and the count was"]))
    assert trunc["quality_status"] == "valid_partial_text"
    clean = q(art(body_paras=["The by-election will be held on Thursday. "
                              "Ten candidates are standing across the "
                              "division. Turnout is expected to be high "
                              "according to agents from all four parties."]))
    assert clean["quality_status"] == "valid_full_text"
    conflict = q(art(body_paras=["Result declared."]),
                 step1_status="full_text")
    assert conflict["quality_status"] == "review_required"


def test_earlier_flags_carried_into_evidence():
    r = q(art(), step3_flags=["replacement_chars_present"],
          step4_flags=["single_paragraph_wall"])
    assert "step3:replacement_chars_present" in r["warning_flags"]
    assert "step4:single_paragraph_wall" in r["warning_flags"]


def test_boilerplate_dominated_flagged_unusable():
    paras = ["Sign up to our newsletter today",
             "Share this on Facebook and Twitter",
             "Subscribe now for unlimited access",
             "One real sentence about the election."]
    r = q(art(body_paras=paras))
    assert r["quality_status"] == "unusable_text"
    assert "boilerplate_dominated" in r["warning_flags"]


def test_duplicate_paragraphs_detected_and_reviewed():
    p = FULL_PARA * 2
    r = q(art(body_paras=[p, p, p, "A different closing paragraph."]))
    assert "duplicate_paragraphs" in r["warning_flags"]
    assert r["quality_status"] == "review_required"

# ------------------------------------------------------ safety / coverage

def test_every_input_gets_exactly_one_status():
    for a, up in [(art(), {}), (art(body_paras=[]), {}),
                  (art(body_paras=["x"]), {"step1_status": "full_text"})]:
        r = q(a, **up)
        assert r["quality_status"] in (
            "valid_full_text", "valid_partial_text", "snippet_only",
            "missing_body", "review_required", "unusable_text")
        assert r["status_reason"]


def test_input_article_not_mutated():
    a = art()
    before = json.loads(json.dumps(a))
    q(a, step1_status="full_text")
    assert a == before


import json  # noqa: E402  (used by the mutation test above)

# ------------------------------------------------------- reproducibility

def test_deterministic():
    a = art()
    assert q(a, step1_status="full_text") == q(a, step1_status="full_text")


def test_version_stamped():
    assert q(art())["rule_version"] == RULE_VERSION
