"""Tests for the governed, separate single-seat winning-margin layer."""

from election_extractor.derived_winning_margin import derive_single_member_winning_margins
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus


def _record(
    name: str,
    votes: int | None,
    outcome: str | None,
    *,
    seats: int | None = 1,
    official_margin: int | None = None,
) -> CandidateResultRecord:
    """Create one published row for a small single-source contest fixture."""

    return CandidateResultRecord(
        election_name="Example election",
        election_date="1 May 2026",
        authority="Surrey County Council",
        division_ward_name="Example Division",
        number_of_seats=seats,
        candidate_name=name,
        original_party_name="Example Party",
        votes_received=votes,
        vote_share=50.0,
        outcome=outcome,
        electorate=100,
        ballot_papers_issued=80,
        ballot_papers_rejected=0,
        turnout=80.0,
        source_url="https://example.test/result",
        extraction_status=ExtractionStatus.COMPLETE,
        missing_fields=(),
        winning_margin=official_margin,
    )


def _derive(*records: CandidateResultRecord):
    """Use a stable fixture division ID without making an HTTP request."""

    return derive_single_member_winning_margins(
        election_id="example-election",
        records=records,
        division_id_for_source_url=lambda _: "example-election:result:1",
    )


def test_margin_uses_explicit_elected_outcome_not_vote_order_to_choose_winner() -> None:
    """A valid single-seat page yields a reproducible runner-up margin."""

    margins = _derive(
        _record("Official winner", 120, "Elected"),
        _record("Runner-up", 95, "Not elected"),
        _record("Third", 10, "Not elected"),
    )

    assert len(margins) == 1
    assert margins[0].value == 25
    assert margins[0].elected_candidate_name == "Official winner"
    assert margins[0].runner_up_candidate_name == "Runner-up"
    assert margins[0].retrieval_date == "2026-07-17"


def test_multi_member_contest_is_not_given_an_arbitrary_margin() -> None:
    """A two-seat contest is not given an arbitrary margin convention."""

    assert _derive(
        _record("Elected one", 120, "Elected", seats=2),
        _record("Elected two", 110, "Elected", seats=2),
        _record("Not elected", 100, "Not elected", seats=2),
    ) == ()


def test_missing_or_inconsistent_official_evidence_prevents_derivation() -> None:
    """Neither missing votes nor a contradictory outcome can produce a value."""

    assert _derive(
        _record("Winner", None, "Elected"),
        _record("Runner-up", 95, "Not elected"),
    ) == ()
    assert _derive(
        _record("Claimed winner", 90, "Elected"),
        _record("Higher non-winner", 95, "Not elected"),
    ) == ()


def test_directly_published_margin_is_never_duplicated_as_derived() -> None:
    """Official data takes precedence over the separate calculated layer."""

    assert _derive(
        _record("Winner", 120, "Elected", official_margin=25),
        _record("Runner-up", 95, "Not elected", official_margin=25),
    ) == ()


def test_supplementary_seats_cannot_act_as_a_same_page_derivation_input() -> None:
    """A missing official Seats value blocks a margin even if a user knows it was one seat.

    This fixture represents the 2021 boundary: statutory supplementary Seats
    evidence is useful metadata, but it is not a value published on the same
    official result page and therefore cannot authorise this derived formula.
    """

    assert _derive(
        _record("Official winner", 120, "Elected", seats=None),
        _record("Runner-up", 95, "Not elected", seats=None),
    ) == ()
