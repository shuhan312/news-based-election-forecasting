"""ISSUE_GROUPS must stay consistent with the extraction prompt's enum.

The feature builder's issue buckets and the extraction prompt's
``issue_code`` enum are maintained in different files, and they drifted:
the frozen map's member strings are feature-plan shorthand ("crime",
"housing", ...) that match no enum value, so ``crime_policing`` and
``housing_planning`` are structurally empty in the frozen v1/v2 tables
and 166 coded records fell into ``issue_other`` (61 crime_policing,
50 planning_housing, 50 schools_send, 5 waste_recycling). The frozen
map cannot change - the byte-identical rebuild tests and the blinded-
freeze rule pin it - so these tests pin BOTH behaviours: the frozen
defect stays exactly as recorded, and the corrected map used by any
post-freeze build routes every enum value deliberately.
"""

import re
from pathlib import Path

from news_features.build_feature_table import (ISSUE_GROUPS,
                                               ISSUE_GROUPS_CORRECTED,
                                               issue_group)

PROMPT = Path("llm_context/context_extraction_prompt_v1_final.md")

# Enum codes that intentionally aggregate to `issue_other` under the
# corrected map: real coverage the six pre-registered features do not
# single out.
INTENTIONALLY_OTHER = {
    "environment_flooding", "healthcare", "local_business",
    "candidate_party_conduct", "protest", "service_closure",
    "investment_funding", "local_government_reorganisation",
    "candidate_selection_withdrawal", "resignation_defection",
    "new_party_emergence", "voter_switching", "anti_incumbent_sentiment",
    "election_administration", "other",
}

EXPECTED_BUCKET = {
    "immigration": "immigration",
    "crime_policing": "crime_policing",
    "planning_housing": "housing_planning",
    "council_finance": "council_services",
    "council_tax": "council_services",
    "roads_transport": "council_services",
    "schools_send": "council_services",
    "social_care": "council_services",
    "waste_recycling": "council_services",
    "council_performance": "council_services",
    "national_politics": "national_politics",
    "national_economy": "national_politics",
    "scandal": "national_politics",
}


def prompt_enum() -> list[str]:
    text = PROMPT.read_text(encoding="utf-8")
    block = re.search(r'"issue_code":\s*\{\s*"enum":\s*\[(.*?)\]', text,
                      flags=re.S)
    assert block, "issue_code enum not found in the extraction prompt"
    return re.findall(r'"([a-z_]+)"', block.group(1))


def test_prompt_enum_is_recovered():
    codes = prompt_enum()
    assert len(codes) >= 25 and "crime_policing" in codes


def test_frozen_map_keeps_its_recorded_defect():
    """The frozen v1/v2 behaviour is a recorded fact: do not "fix" it here.

    Changing ISSUE_GROUPS breaks the byte-identical rebuild tests for the
    frozen tables, which may not be regenerated. Route corrections belong
    in ISSUE_GROUPS_CORRECTED and post-freeze builds only.
    """
    assert issue_group("crime_policing") == "issue_other"
    assert issue_group("planning_housing") == "issue_other"
    assert issue_group("schools_send") == "issue_other"
    assert issue_group("waste_recycling") == "issue_other"


def test_corrected_map_routes_every_enum_code_deliberately():
    for code in prompt_enum():
        bucket = issue_group(code, ISSUE_GROUPS_CORRECTED)
        if code in EXPECTED_BUCKET:
            assert bucket == EXPECTED_BUCKET[code], (
                f"{code} routed to {bucket}, expected {EXPECTED_BUCKET[code]}")
        else:
            assert code in INTENTIONALLY_OTHER and bucket == "issue_other", (
                f"{code} is neither pinned to a bucket nor listed as "
                f"intentionally-other (routed to {bucket}); add it to one "
                f"list deliberately")


def test_no_corrected_bucket_is_structurally_dead():
    codes = set(prompt_enum())
    for bucket, members in ISSUE_GROUPS_CORRECTED.items():
        assert codes.intersection(members), (
            f"bucket {bucket} matches no enum value - every one of its "
            f"member strings is dead")
