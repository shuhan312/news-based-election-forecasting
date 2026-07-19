"""Tests for party-level candidacy, incumbency and new-party predictors."""

import json
from pathlib import Path

import pytest

from no_news_baseline.electoral_fundamentals_participation import (
    add_participation_features,
)
from no_news_baseline.electoral_fundamentals_rows import (
    build_fundamentals_row_index,
    load_party_feature_rows,
)


def _party_feature(
    *,
    contest_id: str = "party-a",
    party: str = "Party A",
    candidate_count: int = 1,
    incumbent_party: str = "Yes",
    incumbent_candidate: str = "Yes",
    previously_contested: bool | None = True,
    first_appearance: bool | None = False,
    category: str | None = "established",
) -> dict[str, object]:
    """Create one predictor-side party record for a target contest."""

    return {
        "party_contest_id": contest_id,
        "election_id": "target-election",
        "election_date": "2021-05-06",
        "division_id": "target-area",
        "division_name": "Target Area",
        "standard_party_name": party,
        "candidate_count_for_party": candidate_count,
        "incumbent_candidate_any_yes_no": incumbent_candidate,
        "incumbent_party_yes_no": incumbent_party,
        "party_previously_contested": previously_contested,
        "first_appearance_of_party_in_area": first_appearance,
        "party_category": category,
    }


def _candidate(
    *,
    candidate_name: str = "Candidate A",
    party: str = "Party A",
    previously_stood: bool | None = True,
    incumbent: str = "Yes",
) -> dict[str, object]:
    """Create one target candidate with audited pre-election history states."""

    return {
        "election_id": "target-election",
        "division_id": "target-area",
        "standard_party_name": party,
        "candidate_name": candidate_name,
        "candidate_previously_stood": previously_stood,
        "incumbent_candidate_yes_no": incumbent,
    }


def _build(
    party_rows: list[dict[str, object]],
    candidates: list[dict[str, object]],
):
    """Create the row index before adding the participation fields under test."""

    # Tests follow the real pipeline order: first establish one unique
    # election-area-party row, then attach participation predictors to it.
    row_index = build_fundamentals_row_index(party_rows)
    return add_participation_features(row_index, party_rows, candidates)


def test_adds_verified_participation_and_incumbency_fields() -> None:
    """A fully evidenced party row should receive all six predictor states."""

    row = _build([_party_feature()], [_candidate()])[0]

    # The fixture describes an established incumbent party with a returning
    # incumbent candidate and an approved local contest history.
    assert row["incumbent_party"] is True
    assert row["incumbent_candidate_present"] is True
    assert row["candidate_previously_stood"] is True
    assert row["party_previously_stood"] is True
    assert row["first_party_appearance_in_area"] is False
    assert row["new_party_indicator"] is False


def test_any_verified_candidate_sets_party_row_presence() -> None:
    """One verified returning candidate should set the party-level flag to True."""

    feature = _party_feature(candidate_count=2, incumbent_candidate="Yes")
    candidates = [
        _candidate(candidate_name="Returning", previously_stood=True, incumbent="Yes"),
        _candidate(candidate_name="New", previously_stood=False, incumbent="No"),
    ]

    row = _build([feature], candidates)[0]

    # These fields ask whether the party has at least one such candidate, so a
    # verified Yes takes precedence over another candidate's verified No.
    assert row["candidate_previously_stood"] is True
    assert row["incumbent_candidate_present"] is True


def test_unknown_candidate_evidence_is_not_changed_to_no() -> None:
    """Incomplete candidate history should remain Unknown rather than become False."""

    feature = _party_feature(
        incumbent_party="Unknown",
        incumbent_candidate="Unknown",
        previously_contested=None,
        first_appearance=None,
    )
    candidate = _candidate(previously_stood=None, incumbent="Unknown")

    row = _build([feature], [candidate])[0]

    # None is the in-memory representation of Unknown. It is different from
    # False, which is used only after the extractor has verified a negative.
    assert row["incumbent_party"] is None
    assert row["incumbent_candidate_present"] is None
    assert row["candidate_previously_stood"] is None
    assert row["party_previously_stood"] is None
    assert row["first_party_appearance_in_area"] is None


def test_independent_keeps_person_history_but_not_party_identity() -> None:
    """Independent candidates may have personal history without party continuity."""

    first = _party_feature(
        contest_id="independent-a",
        party="Independent",
        incumbent_party="Unknown",
        incumbent_candidate="Yes",
        category="independent",
    )
    second = _party_feature(
        contest_id="independent-b",
        party="Independent",
        incumbent_party="Unknown",
        incumbent_candidate="No",
        category="independent",
    )
    candidates = [
        _candidate(candidate_name="Returning", party="Independent", incumbent="Yes"),
        _candidate(
            candidate_name="Other",
            party="Independent",
            previously_stood=False,
            incumbent="No",
        ),
    ]

    row = _build([first, second], candidates)[0]

    assert row["candidate_previously_stood"] is True
    assert row["incumbent_candidate_present"] is True
    assert row["incumbent_party"] is None
    assert row["party_previously_stood"] is None
    assert row["first_party_appearance_in_area"] is None
    assert row["new_party_indicator"] is None


def test_new_party_indicator_uses_reviewed_emerging_category() -> None:
    """The new-party flag should use the pre-election category, not future results."""

    feature = _party_feature(
        party="Reform UK",
        incumbent_party="No",
        incumbent_candidate="No",
        previously_contested=False,
        first_appearance=True,
        category="emerging",
    )
    candidate = _candidate(
        party="Reform UK", previously_stood=False, incumbent="No"
    )

    row = _build([feature], [candidate])[0]

    # Emerging-party status and first local appearance are separate concepts:
    # the first is a reviewed party category, while the second compares areas.
    assert row["new_party_indicator"] is True
    assert row["party_previously_stood"] is False
    assert row["first_party_appearance_in_area"] is True


def test_inconsistent_party_history_pair_is_rejected() -> None:
    """Previously stood and first appearance cannot both have the same state."""

    feature = _party_feature(previously_contested=True, first_appearance=True)

    with pytest.raises(ValueError, match="must be opposites"):
        # A party cannot both have contested previously and be making its first
        # appearance in the same approved area history.
        _build([feature], [_candidate()])


def test_real_release_preserves_audited_unknown_states() -> None:
    """The real extractor contracts should support all 1,592 party-level rows."""

    project_root = Path(__file__).resolve().parents[1]
    extractor_outputs = project_root.parent / "surrey-election-extractor" / "outputs"
    feature_path = (
        extractor_outputs
        / "no_news_party_contests/no_news_party_contest_features.json"
    )
    master_path = (
        extractor_outputs
        / "master_surrey_election_database/master_election_database_payload.json"
    )
    # Generated extractor outputs may be absent in a clean clone; the synthetic
    # tests above continue to enforce every transformation rule independently.
    if not feature_path.exists() or not master_path.exists():
        pytest.skip("Regenerate extractor outputs for integration QA.")

    party_rows = load_party_feature_rows(feature_path)
    row_index = build_fundamentals_row_index(party_rows)
    master_payload = json.loads(master_path.read_text(encoding="utf-8"))
    completed = add_participation_features(
        row_index, party_rows, master_payload["Candidate Results"]
    )

    assert len(completed) == 1_592
    assert all(
        # Party-level Independent history is intentionally unavailable even
        # when a specific Independent candidate has verified personal history.
        row["incumbent_party"] is None
        and row["party_previously_stood"] is None
        and row["new_party_indicator"] is None
        for row in completed
        if row["standard_party_name"] == "Independent"
    )
    assert all(
        # The current reviewed lookup contains one emerging standard party:
        # Reform UK. UKIP labels remain separate standard-party identities.
        row["new_party_indicator"] is True
        for row in completed
        if row["standard_party_name"] == "Reform UK"
    )
