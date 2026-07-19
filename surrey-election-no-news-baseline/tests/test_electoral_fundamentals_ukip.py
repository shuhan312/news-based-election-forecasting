"""Tests for keeping Reform UK history separate from earlier UKIP support."""

import json
from pathlib import Path

import pytest

from no_news_baseline.electoral_fundamentals_history import (
    add_previous_election_features,
)
from no_news_baseline.electoral_fundamentals_rows import (
    build_fundamentals_row_index,
    load_party_feature_rows,
)
from no_news_baseline.electoral_fundamentals_ukip import (
    add_previous_ukip_feature,
)


def _elections(*, previous_date: str = "2017-05-04") -> list[dict[str, object]]:
    """Create an earlier source election and a later Reform UK target election."""

    return [
        {"election_id": "previous-election", "election_date": previous_date},
        {"election_id": "target-election", "election_date": "2021-05-06"},
    ]


def _reform_row(*, approved: bool = True) -> dict[str, object]:
    """Create one Reform UK fundamentals row after the history stage."""

    return {
        "election_id": "target-election",
        "election_date": "2021-05-06",
        "area_id": "target-area",
        "area_name": "Target Area",
        "standard_party_name": "Reform UK",
        # Reform did not contest the previous result in this fixture. This value
        # must remain zero even when a separate UKIP share is later recovered.
        "previous_party_vote_share": 0.0 if approved else None,
        "previous_election_id": "previous-election" if approved else None,
        "previous_area_id": "previous-area" if approved else None,
    }


def _candidate(
    *,
    party: str = "UK Independence Party",
    share: float = 12.0,
) -> dict[str, object]:
    """Create one candidate in the approved previous result."""

    return {
        "election_id": "previous-election",
        "division_id": "previous-area",
        "standard_party_name": party,
        "analysis_vote_share": share,
    }


def test_reform_keeps_own_previous_share_separate_from_ukip() -> None:
    """UKIP context must not replace Reform UK's own previous party share."""

    completed = add_previous_ukip_feature(
        [_reform_row()], _elections(), [_candidate()]
    )
    row = completed[0]

    # The two values answer different questions and must remain in different
    # columns even though they come from the same approved previous area.
    assert row["previous_party_vote_share"] == 0.0
    assert row["previous_ukip_vote_share_in_area"] == 12.0


def test_complete_previous_result_without_ukip_records_zero() -> None:
    """UKIP absence from a complete approved result should produce observed zero."""

    row = add_previous_ukip_feature(
        [_reform_row()],
        _elections(),
        [_candidate(party="Conservative", share=55.0)],
    )[0]

    assert row["previous_ukip_vote_share_in_area"] == 0.0


def test_reform_without_approved_previous_area_keeps_ukip_unknown() -> None:
    """No UKIP value should be created without an approved geographic reference."""

    row = add_previous_ukip_feature(
        [_reform_row(approved=False)], _elections(), [_candidate()]
    )[0]

    assert row["previous_ukip_vote_share_in_area"] is None


def test_non_reform_party_does_not_receive_reform_context_feature() -> None:
    """The separate UKIP context is populated only for Reform UK target rows."""

    conservative = _reform_row()
    conservative["standard_party_name"] = "Conservative"
    conservative["previous_party_vote_share"] = 55.0

    row = add_previous_ukip_feature(
        [conservative], _elections(), [_candidate()]
    )[0]

    assert row["previous_party_vote_share"] == 55.0
    assert row["previous_ukip_vote_share_in_area"] is None


def test_same_day_ukip_source_is_rejected() -> None:
    """UKIP history must be known strictly before the Reform UK target election."""

    with pytest.raises(ValueError, match="must precede"):
        add_previous_ukip_feature(
            [_reform_row()],
            _elections(previous_date="2021-05-06"),
            [_candidate()],
        )


def test_multiple_ukip_candidates_are_not_summed_or_selected() -> None:
    """An unexpected ambiguous UKIP result should stop feature construction."""

    candidates = [
        _candidate(party="UK Independence Party", share=12.0),
        _candidate(party="UKIP", share=8.0),
    ]

    with pytest.raises(ValueError, match="multiple UKIP"):
        add_previous_ukip_feature([_reform_row()], _elections(), candidates)


def test_real_release_keeps_reform_and_ukip_values_separate() -> None:
    """The real release should recover only approved earlier UKIP area shares."""

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
    # Generated extractor files are optional in a clean clone; the focused unit
    # tests above still check every separation and leakage rule without them.
    if not feature_path.exists() or not master_path.exists():
        pytest.skip("Regenerate extractor outputs for integration QA.")

    party_rows = load_party_feature_rows(feature_path)
    master = json.loads(master_path.read_text(encoding="utf-8"))
    row_index = build_fundamentals_row_index(party_rows)
    historical_rows = add_previous_election_features(row_index, party_rows, master)
    completed = add_previous_ukip_feature(
        historical_rows, master["Elections"], master["Candidate Results"]
    )
    reform_rows = [
        row for row in completed if row["standard_party_name"] == "Reform UK"
    ]

    assert len(completed) == 1_592
    assert len(reform_rows) == 94
    assert sum(
        row["previous_ukip_vote_share_in_area"] is not None for row in reform_rows
    ) == 37
    assert sorted(
        row["previous_ukip_vote_share_in_area"]
        for row in reform_rows
        if row["previous_ukip_vote_share_in_area"] not in {None, 0.0}
    ) == [3.0, 3.0, 3.0, 4.0, 8.0]
    assert all(
        row["previous_party_vote_share"] == 0.0
        for row in reform_rows
        if row["previous_ukip_vote_share_in_area"] not in {None, 0.0}
    )
