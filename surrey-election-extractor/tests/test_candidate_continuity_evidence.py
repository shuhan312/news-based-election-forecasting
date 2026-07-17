"""Tests for the reviewed official member-profile continuity register."""

import json

import pytest

from election_extractor.candidate_continuity_evidence import (
    candidate_evidence_key,
    evidence_by_candidate_key,
    load_candidate_continuity_evidence,
)


def valid_record() -> dict[str, object]:
    """Create one fully explicit profile-to-result relationship for validation."""

    return {
        "evidence_id": "example:member-profile",
        "election_id": "surrey-county-council-2021",
        "candidate_name": "Example Candidate",
        "division_name": "Example Division",
        "candidate_source_url": (
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?"
            "ID=272&RPID=999&XXR=0"
        ),
        "candidate_election_date": "2021-05-06",
        "member_profile_url": "https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=192",
        "member_uid": "192",
        "term_start": "2017-05-05",
        "profile_linked_result_urls": [
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=187",
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=272",
        ],
        "prior_official_elections": [
            {
                "election_id": "surrey-county-council-2017",
                "election_date": "2017-05-04",
                "source_url": (
                    "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=187"
                ),
            }
        ],
        "candidate_previously_stood": True,
        "incumbent_candidate": True,
        "incumbent_party": "Conservative",
        "evidence_text": "Official profile directly links both official result pages.",
        "retrieval_date": "2026-07-17",
        "confidence": "High",
    }


def load_one(tmp_path, payload: dict[str, object]):
    """Write a temporary register so every test stays offline and deterministic."""

    path = tmp_path / "candidate_continuity_evidence.json"
    path.write_text(json.dumps({"records": [payload]}), encoding="utf-8")
    return load_candidate_continuity_evidence(
        path,
        permitted_election_ids={"surrey-county-council-2021"},
    )


def test_profile_evidence_normalises_result_page_variants(tmp_path) -> None:
    """RPID and XXR variants must still identify the same published result page."""

    evidence = load_one(tmp_path, valid_record())
    indexed = evidence_by_candidate_key(evidence)
    key = candidate_evidence_key(
        "surrey-county-council-2021",
        "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=272",
        "Example Candidate",
    )

    assert indexed[key].candidate_previously_stood is True
    assert indexed[key].incumbent_candidate is True


def test_profile_must_directly_link_the_candidate_result_page(tmp_path) -> None:
    """A member profile cannot support a candidate row merely by sharing a name."""

    payload = valid_record()
    payload["profile_linked_result_urls"] = [
        "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=187"
    ]

    with pytest.raises(ValueError, match="directly listed"):
        load_one(tmp_path, payload)


def test_prior_election_must_precede_the_candidate_election(tmp_path) -> None:
    """A later profile link cannot be misrepresented as earlier participation."""

    payload = valid_record()
    payload["prior_official_elections"] = [
        {
            "election_id": "surrey-county-council-2021",
            "election_date": "2021-05-06",
            "source_url": (
                "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=272"
            ),
        }
    ]

    with pytest.raises(ValueError, match="predate"):
        load_one(tmp_path, payload)


def test_profile_uid_must_match_its_public_url(tmp_path) -> None:
    """The stable official identifier cannot be substituted by another profile."""

    payload = valid_record()
    payload["member_uid"] = "193"

    with pytest.raises(ValueError, match="matching numeric UID"):
        load_one(tmp_path, payload)
