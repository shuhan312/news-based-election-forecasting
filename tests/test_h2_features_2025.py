"""The H2 feature requests use V1's stance prompt unchanged (offline)."""

from forecast import h2_features_2025 as f
from src.llm_extraction import stance_rescue as v1

ART = {"headline": "Reform UK candidate visits Devon", "outlet": "devonlive",
       "text": "Reform UK and the Conservatives campaigned in Exeter.",
       "published_date": "2025-04-10", "url": "https://x/1"}


def test_stance_request_is_v1_prompt_verbatim():
    reqs = f._requests({"a1": ART})
    stance = next(r for r in reqs if r["custom_id"] == "s_a1")
    parties = v1.parties_present(ART["headline"], ART["text"])
    assert stance["params"]["system"] == v1.build_prompt(parties)
    assert stance["params"]["model"] == "claude-haiku-4-5"
    assert stance["params"]["thinking"] == {"type": "enabled",
                                            "budget_tokens": 4000}
    # the exploratory question goes in its own request
    activity = next(r for r in reqs if r["custom_id"] == "a_a1")
    assert activity["params"]["system"] == f.ACTIVITY_PROMPT


def test_no_stance_request_without_reform_named():
    farage_only = {**ART, "headline": "Farage speaks", "text": "Nigel Farage spoke."}
    ids = [r["custom_id"] for r in f._requests({"a2": farage_only})]
    assert ids == ["a_a2"]
