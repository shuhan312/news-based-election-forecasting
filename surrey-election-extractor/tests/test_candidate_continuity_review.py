"""Tests for the evidence-safe repeated-name continuity review queue."""

from election_extractor.candidate_continuity_evidence import (
    CandidateContinuityEvidence,
    PriorOfficialElection,
    evidence_by_candidate_key,
)
from election_extractor.candidate_continuity_review import (
    ContinuityReviewTier,
    build_candidate_continuity_review,
    review_as_dict,
)


TARGET_URL = "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=272"
PRIOR_URL = "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=187"


def row(name: str, *, election_id: str, year: int, source_url: str, division: str = "Example") -> dict[str, object]:
    """Use minimal published fields; no test relies on a live website."""

    return {
        "candidate_name": name,
        "election_id": election_id,
        "election_year": year,
        "division_name": division,
        "original_party_name": "Conservative",
        "outcome": "Elected",
        "source_url": source_url,
    }


def evidence(method: str = "official_member_profile") -> CandidateContinuityEvidence:
    """Create explicit evidence for exactly one target row, never a name group."""

    return CandidateContinuityEvidence(
        evidence_id="example:reviewed",
        election_id="surrey-county-council-2021",
        candidate_name="Alex Example",
        division_name="Example",
        candidate_source_url=TARGET_URL,
        member_profile_url="https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=192",
        member_uid="192",
        term_start=__import__("datetime").date(2017, 5, 5),
        profile_linked_result_urls=(PRIOR_URL, TARGET_URL),
        prior_official_elections=(
            PriorOfficialElection("surrey-county-council-2017", __import__("datetime").date(2017, 5, 4), PRIOR_URL),
        ),
        candidate_previously_stood=True,
        incumbent_candidate=True,
        incumbent_party="Conservative",
        evidence_text="Explicit official evidence.",
        retrieval_date="2026-07-18",
        confidence="High",
        notes=None,
        evidence_method=method,
    )


def test_only_exact_repeated_names_enter_the_queue() -> None:
    """A single appearance must not create an identity-review task."""

    groups = build_candidate_continuity_review(
        [
            row("Alex Example", election_id="surrey-county-council-2017", year=2017, source_url=PRIOR_URL),
            row("Alex Example", election_id="surrey-county-council-2021", year=2021, source_url=TARGET_URL),
            row("Single Candidate", election_id="surrey-county-council-2021", year=2021, source_url="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=300"),
        ],
        {},
    )

    assert [group.candidate_name for group in groups] == ["Alex Example"]
    assert all(item.review_tier is ContinuityReviewTier.C for item in groups[0].appearances)


def test_direct_profile_evidence_marks_only_its_exact_target_row() -> None:
    """Evidence must not spread from a verified row to an earlier same-name row."""

    groups = build_candidate_continuity_review(
        [
            row("Alex Example", election_id="surrey-county-council-2017", year=2017, source_url=PRIOR_URL),
            row("Alex Example", election_id="surrey-county-council-2021", year=2021, source_url=TARGET_URL),
        ],
        evidence_by_candidate_key((evidence(),)),
    )
    prior, target = groups[0].appearances

    assert prior.review_tier is ContinuityReviewTier.C
    assert prior.candidate_previously_stood is None
    assert target.review_tier is ContinuityReviewTier.A
    assert target.candidate_previously_stood is True
    assert target.incumbent_candidate is True


def test_multi_source_evidence_is_reported_as_tier_b() -> None:
    """A reviewed multi-source decision remains distinct from a direct profile link."""

    groups = build_candidate_continuity_review(
        [
            row("Alex Example", election_id="surrey-county-council-2017", year=2017, source_url=PRIOR_URL),
            row("Alex Example", election_id="surrey-county-council-2021", year=2021, source_url=TARGET_URL),
        ],
        evidence_by_candidate_key((evidence("official_multi_source_match"),)),
    )

    assert groups[0].appearances[1].review_tier is ContinuityReviewTier.B


def test_tier_c_retains_every_source_url_and_no_person_claim() -> None:
    """The queue should expose source URLs while keeping unresolved identities NULL."""

    groups = build_candidate_continuity_review(
        [
            row("Alex Example", election_id="surrey-county-council-2017", year=2017, source_url=PRIOR_URL),
            row("Alex Example", election_id="surrey-county-council-2021", year=2021, source_url=TARGET_URL),
        ],
        {},
    )
    report = review_as_dict(groups)
    appearances = report["groups"][0]["appearances"]

    assert appearances[0]["evidence_source_urls"] == (PRIOR_URL,)
    assert appearances[1]["candidate_previously_stood"] is None
    assert report["summary"]["tier_c_review_required_rows"] == 2
