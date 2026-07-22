"""Tests for the four-way no-news model comparison on common support."""

from no_news_baseline.model_comparison import compare_models_on_common_support


def _feature(
    contest_id: str,
    election_id: str,
    election_date: str,
    area: str,
    party: str,
    *,
    previous_party_vote_share: float = 30.0,
    party_was_previous_winner: bool = False,
    baseline_eligibility: str = "eligible_primary_single_member_party_share",
) -> dict[str, object]:
    return {
        "party_contest_id": contest_id,
        "election_id": election_id,
        "election_date": election_date,
        "election_year": int(election_date[-4:]),
        "election_type": "County Council election",
        "division_id": area,
        "division_name": area,
        "standard_party_name": party,
        "contest_structure": "single_member",
        "geographic_reference_eligibility": "approved_historical_reference",
        "party_identity_scope": "reviewed_standard_party",
        "baseline_eligibility": baseline_eligibility,
        "previous_party_vote_share": previous_party_vote_share,
        "analysis_previous_turnout": 35.0,
        "previous_electorate": 10000,
        "party_was_previous_winner": party_was_previous_winner,
        "incumbent_candidate_any_yes_no": "No",
        "incumbent_party_yes_no": "No",
        "party_previously_contested": True,
        "first_appearance_of_party_in_area": False,
        "historical_source_url": "https://official.example/previous",
    }


def _target(contest_id: str, party: str, share: float, elected: str) -> dict[str, object]:
    return {
        "party_contest_id": contest_id,
        "standard_party_name": party,
        "target_party_vote_share": share,
        "target_party_elected": elected,
        "target_source_urls": "https://official.example/current",
    }


def _two_party_area(prefix: str, election_id: str, date: str, a_prev: float, b_prev: float):
    # A single-member area with two parties, both share-cohort eligible.
    features = (
        _feature(f"{prefix}-a", election_id, date, f"{prefix}-area", "Party A",
                 previous_party_vote_share=a_prev, party_was_previous_winner=a_prev > b_prev),
        _feature(f"{prefix}-b", election_id, date, f"{prefix}-area", "Party B",
                 previous_party_vote_share=b_prev, party_was_previous_winner=b_prev > a_prev),
    )
    return features


def test_all_models_scored_on_identical_shared_contests() -> None:
    # Two elections so the later one forms a fold with the earlier as training.
    features = (
        *_two_party_area("e17", "2017", "4 May 2017", 55.0, 45.0),
        *_two_party_area("e21", "2021", "6 May 2021", 52.0, 48.0),
    )
    targets = (
        _target("e17-a", "Party A", 55.0, "Yes"),
        _target("e17-b", "Party B", 45.0, "No"),
        _target("e21-a", "Party A", 50.0, "Yes"),
        _target("e21-b", "Party B", 50.0, "No"),
    )

    result = compare_models_on_common_support(features, targets, l2_penalty=1.0)

    metrics = result["common_support_share_metrics"]
    # Every model reports a metric block and they are all scored on the same
    # number of contests as the declared shared-contest count.
    assert set(metrics) == {
        "ridge_fundamentals_v1",
        "previous_result_persistence_v1",
        "equal_share_reference_v1",
        "party_historical_mean_reference_v1",
    }
    for model_metrics in metrics.values():
        assert model_metrics["party_share_rows"] == result["shared_contest_count"]
    # Only the 2021 election forms a fold (2017 is the study-start with no
    # earlier training election), so 2 shared contests are scored.
    assert result["shared_contest_count"] == 2


def test_equal_share_is_beaten_by_persistence_on_a_stable_case() -> None:
    # Construct a stable two-election series where the previous share carries
    # forward almost exactly, so persistence must have lower share MAE than
    # the uninformed equal-share split. This checks the comparison surfaces a
    # sensible ordering, not just equal numbers.
    features = (
        *_two_party_area("e17", "2017", "4 May 2017", 70.0, 30.0),
        *_two_party_area("e21", "2021", "6 May 2021", 70.0, 30.0),
    )
    targets = (
        _target("e17-a", "Party A", 70.0, "Yes"),
        _target("e17-b", "Party B", 30.0, "No"),
        _target("e21-a", "Party A", 71.0, "Yes"),
        _target("e21-b", "Party B", 29.0, "No"),
    )

    result = compare_models_on_common_support(features, targets, l2_penalty=1.0)
    metrics = result["common_support_share_metrics"]

    persistence_mae = metrics["previous_result_persistence_v1"][
        "party_share_mae_percentage_points"
    ]
    equal_share_mae = metrics["equal_share_reference_v1"][
        "party_share_mae_percentage_points"
    ]
    assert persistence_mae < equal_share_mae


def test_per_model_counts_expose_wider_benchmark_eligibility() -> None:
    # The naive benchmarks are eligible on more rows than the fitted model,
    # which only scores fold test rows. The per-model counts must record that,
    # while the shared set stays the narrow intersection.
    features = (
        *_two_party_area("e17", "2017", "4 May 2017", 55.0, 45.0),
        *_two_party_area("e21", "2021", "6 May 2021", 52.0, 48.0),
    )
    targets = (
        _target("e17-a", "Party A", 55.0, "Yes"),
        _target("e17-b", "Party B", 45.0, "No"),
        _target("e21-a", "Party A", 50.0, "Yes"),
        _target("e21-b", "Party B", 50.0, "No"),
    )

    result = compare_models_on_common_support(features, targets, l2_penalty=1.0)
    counts = result["per_model_scored_contest_counts"]

    # Equal-share predicts for every single-member contest (all four),
    # while the ridge model only scores the 2021 fold's two contests.
    assert counts["equal_share_reference_v1"] == 4
    assert counts["ridge_fundamentals_v1"] == 2
    assert result["shared_contest_count"] == 2
