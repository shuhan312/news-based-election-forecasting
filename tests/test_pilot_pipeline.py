"""Phase 6 / Step 2 tests: sampling determinism and coverage, prompt
construction, output parsing and validation wiring. NO API is called
anywhere in this file - the network-facing steps are exercised in
production and their outputs audited separately."""

import copy
import json

from src.llm_extraction.pilot_sample import (LOCAL_QUOTA,
                                             NATIONAL_QUOTA, REFORM_MIN,
                                             build_system_prompt,
                                             build_user_message,
                                             parse_model_json,
                                             select_pilot_sample)


def frame(n_per_stratum=20, reform_national=15):
    arts = []
    for e in ("SCC-2013-05", "SCC-2017-05", "SCC-2021-05",
              "ESWS-2026-05"):
        for arm in ("local", "national"):
            for i in range(n_per_stratum):
                arts.append({"article_id": f"NEWS-{e}-{arm}-{i:03d}",
                             "election_id": e, "arm": arm,
                             "mentions_reform": False})
    for i in range(reform_national):
        arts.append({"article_id": f"NEWS-reform-{i:03d}",
                     "election_id": "ESWS-2026-05", "arm": "national",
                     "mentions_reform": True})
    return arts

# ----------------------------------------------------------- sampling

def test_sample_covers_all_strata_with_quotas():
    r = select_pilot_sample(frame())
    for e in ("SCC-2013-05", "SCC-2017-05", "SCC-2021-05",
              "ESWS-2026-05"):
        assert r["strata"][f"{e}/local"]["taken"] == LOCAL_QUOTA
        assert r["strata"][f"{e}/national"]["taken"] == NATIONAL_QUOTA


def test_sample_is_deterministic_and_order_independent():
    arts = frame()
    r1 = select_pilot_sample(copy.deepcopy(arts))
    r2 = select_pilot_sample(list(reversed(copy.deepcopy(arts))))
    assert r1["selected"] == r2["selected"]


def test_reform_minimum_enforced():
    r = select_pilot_sample(frame())
    reform_ids = {a["article_id"] for a in frame()
                  if a["mentions_reform"]}
    assert len(reform_ids & set(r["selected"])) >= REFORM_MIN


def test_small_stratum_takes_what_exists():
    arts = [a for a in frame() if not (a["election_id"] == "SCC-2013-05"
                                       and a["arm"] == "local")]
    arts += [{"article_id": "NEWS-tiny-1",
              "election_id": "SCC-2013-05", "arm": "local",
              "mentions_reform": False}]
    r = select_pilot_sample(arts)
    assert r["strata"]["SCC-2013-05/local"]["taken"] == 1


def test_sampling_method_is_recorded():
    r = select_pilot_sample(frame())
    assert "sha256" in r["method"] and "No manual selection" in r["method"]

# ------------------------------------------------------------- prompts

def test_system_prompt_is_stable_and_carries_contract():
    p1, p2 = build_system_prompt(), build_system_prompt()
    assert p1 == p2                                  # byte-stable
    assert "llm-context-v1.1-2026-07-26" in p1       # pinned contract
    assert "VERBATIM" in p1 and "NO OUTCOME PREDICTION" in p1


def test_user_message_carries_metadata_and_text():
    m = build_user_message({"article_id": "A", "election_id": "SCC-2021-05"},
                           "Some title", "Some body text.")
    assert '"article_id": "A"' in m
    assert "TITLE: Some title" in m and "Some body text." in m


def test_future_stage_m_article_flows_through_same_builder():
    m = build_user_message({"article_id": "NEWS-stagem-future01"},
                           "New article", "Body.")
    assert "NEWS-stagem-future01" in m               # no special-casing

# ------------------------------------------------------------- parsing

def test_parse_plain_json():
    assert parse_model_json('{"a": 1}') == {"a": 1}


def test_parse_strips_markdown_fences():
    assert parse_model_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_rejects_non_object():
    import pytest
    with pytest.raises((ValueError, json.JSONDecodeError)):
        parse_model_json('[1, 2]')
    with pytest.raises((ValueError, json.JSONDecodeError)):
        parse_model_json('not json at all')
