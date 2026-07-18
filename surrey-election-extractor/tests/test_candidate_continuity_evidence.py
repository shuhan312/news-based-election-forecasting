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


def test_multi_source_review_accepts_profile_and_two_exact_result_pages(tmp_path) -> None:
    """A reviewed profile plus target and prior results may evidence continuity.

    The profile does not need to retain direct historical hyperlinks under this
    method, but the register must retain all three public official sources.
    """

    payload = valid_record()
    payload["evidence_method"] = "official_multi_source_match"
    payload["profile_linked_result_urls"] = []
    payload["supporting_sources"] = [
        {
            "source_type": "official_member_profile",
            "source_authority": "Surrey County Council",
            "source_url": payload["member_profile_url"],
            "published_candidate_name": "Example Candidate",
            "evidence_text": "The official profile uses the same published name and term.",
        },
        {
            "source_type": "official_result_page",
            "source_authority": "Surrey County Council",
            "source_url": payload["candidate_source_url"],
            "published_candidate_name": "Example Candidate",
            "evidence_text": "The official target result page publishes the candidate name.",
        },
        {
            "source_type": "official_result_page",
            "source_authority": "Surrey County Council",
            "source_url": payload["prior_official_elections"][0]["source_url"],
            "published_candidate_name": "Example Candidate",
            "evidence_text": "The earlier official result page publishes the same name.",
        },
    ]

    evidence = load_one(tmp_path, payload)[0]

    assert evidence.evidence_method == "official_multi_source_match"
    assert len(evidence.supporting_sources) == 3


def test_multi_source_review_rejects_two_sources_only(tmp_path) -> None:
    """Two URLs are not enough to turn a repeated name into a personal claim."""

    payload = valid_record()
    payload["evidence_method"] = "official_multi_source_match"
    payload["profile_linked_result_urls"] = []
    payload["supporting_sources"] = [
        {
            "source_type": "official_member_profile",
            "source_authority": "Surrey County Council",
            "source_url": payload["member_profile_url"],
            "published_candidate_name": "Example Candidate",
            "evidence_text": "The official profile uses the same published name.",
        },
        {
            "source_type": "official_result_page",
            "source_authority": "Surrey County Council",
            "source_url": payload["candidate_source_url"],
            "published_candidate_name": "Example Candidate",
            "evidence_text": "The official target result publishes the candidate name.",
        },
    ]

    with pytest.raises(ValueError, match="at least three"):
        load_one(tmp_path, payload)


def test_multi_source_review_can_retain_another_authoritys_official_declaration(tmp_path) -> None:
    """A reviewed council declaration may corroborate a Surrey profile record.

    The register accepts an explicitly named public authority, but it still
    requires the target result page, stable profile and earlier dated source.
    """

    payload = valid_record()
    payload["evidence_method"] = "official_multi_source_match"
    payload["profile_linked_result_urls"] = []
    declaration_url = "https://elections.example.gov.uk/declarations/2017.pdf?utm_source=a"
    payload["prior_official_elections"][0]["source_url"] = declaration_url
    payload["supporting_sources"] = [
        {
            "source_type": "official_member_profile",
            "source_authority": "Surrey County Council",
            "source_url": payload["member_profile_url"],
            "published_candidate_name": "Example Candidate",
            "evidence_text": "The official profile uses the candidate name and term.",
        },
        {
            "source_type": "official_result_page",
            "source_authority": "Surrey County Council",
            "source_url": payload["candidate_source_url"],
            "published_candidate_name": "Example Candidate",
            "evidence_text": "The official target result publishes the candidate name.",
        },
        {
            "source_type": "official_declaration",
            "source_authority": "Example Borough Council",
            "source_url": declaration_url,
            "published_candidate_name": "Example Candidate",
            "evidence_text": "The official declaration publishes the same candidate name.",
        },
    ]

    evidence = load_one(tmp_path, payload)[0]

    assert evidence.prior_official_elections[0].source_url == (
        "https://elections.example.gov.uk/declarations/2017.pdf"
    )
