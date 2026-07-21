"""Tests for the non-geographic naive reference rules.

Fixtures are built by hand rather than loaded from the real extractor
release, so each test can isolate exactly one behaviour (equal-share
arithmetic, strictly-earlier-only climatology pooling, tie handling, ...)
without depending on the size or shape of the live Surrey dataset.
"""

from no_news_baseline.naive_benchmarks import (
    evaluate_equal_share_reference,
    evaluate_party_historical_mean_reference,
)


def _feature(
    contest_id: str,
    election_id: str,
    election_date: str,
    area: str,
    party: str,
    *,
    contest_structure: str = "single_member",
    baseline_eligibility: str = "eligible_primary_single_member_party_share",
    geographic_reference_eligibility: str = "approved_historical_reference",
) -> dict[str, object]:
    # Minimal valid pre-election record. Only the fields the naive rules and
    # the persistence-cohort predicates actually read are included.
    return {
        "party_contest_id": contest_id,
        "election_id": election_id,
        "election_date": election_date,
        "election_year": int(election_date[-4:]),
        "election_type": "County Council election",
        "division_id": area,
        "division_name": area,
        "standard_party_name": party,
        "contest_structure": contest_structure,
        "geographic_reference_eligibility": geographic_reference_eligibility,
        "baseline_eligibility": baseline_eligibility,
    }


def _target(contest_id: str, party: str, share: float, elected: str) -> dict[str, object]:
    return {
        "party_contest_id": contest_id,
        "standard_party_name": party,
        "target_party_vote_share": share,
        "target_party_elected": elected,
        "target_source_urls": "https://official.example/current",
    }


def test_equal_share_splits_evenly_and_never_predicts_a_winner() -> None:
    # Two parties on one ballot: the uninformed floor predicts 50% each,
    # regardless of the (unused) previous result.
    features = (
        _feature("a-a", "2017", "4 May 2017", "area-a", "Party A"),
        _feature("a-b", "2017", "4 May 2017", "area-a", "Party B"),
    )
    targets = (
        _target("a-a", "Party A", 60.0, "Yes"),
        _target("a-b", "Party B", 40.0, "No"),
    )

    predictions, metrics, _audit = evaluate_equal_share_reference(features, targets)

    predicted = {row["party_contest_id"]: row["predicted_party_vote_share"] for row in predictions}
    assert predicted == {"a-a": 50.0, "a-b": 50.0}
    assert {row["predicted_party_elected"] for row in predictions} == {"Unknown"}
    assert metrics["full_cohort"]["overall"]["party_share_mae_percentage_points"] == 10.0
    assert metrics["full_cohort"]["overall"]["winner_party_rows_scored"] == 0


def test_climatology_uses_only_strictly_earlier_elections() -> None:
    # Party A appears in 2013 (share 20) and 2017 (share 30). The 2021
    # prediction should average both; the 2017 row's own prediction should
    # use only the 2013 figure; the 2013 row itself has no prior at all.
    features = (
        _feature("p-2013", "2013", "2 May 2013", "area-x", "Party A"),
        _feature("p-2017", "2017", "4 May 2017", "area-y", "Party A"),
        _feature("p-2021", "2021", "6 May 2021", "area-z", "Party A"),
    )
    # Each row is the sole candidate in a single-member area, so the
    # electorally consistent outcome is that each one wins its own contest.
    targets = (
        _target("p-2013", "Party A", 20.0, "Yes"),
        _target("p-2017", "Party A", 30.0, "Yes"),
        _target("p-2021", "Party A", 28.0, "Yes"),
    )

    predictions, _metrics, audit = evaluate_party_historical_mean_reference(features, targets)

    by_id = {row["party_contest_id"]: row for row in predictions}
    assert by_id["p-2013"]["predicted_party_vote_share"] is None
    assert by_id["p-2017"]["predicted_party_vote_share"] == 20.0
    assert by_id["p-2021"]["predicted_party_vote_share"] == 25.0
    assert by_id["p-2021"]["climatology_source_election_count"] == 2
    assert audit["party_rows_without_qualifying_history"] == 1


def test_climatology_leaves_a_brand_new_party_unscored_not_zero() -> None:
    # A party with zero qualifying history (e.g. a first-ever Reform UK
    # contest) must be left unscored, never silently defaulted to a 0% share.
    features = (_feature("n-a", "2021", "6 May 2021", "area-n", "Reform UK"),)
    targets = (_target("n-a", "Reform UK", 35.0, "Yes"),)

    predictions, metrics, _audit = evaluate_party_historical_mean_reference(features, targets)

    assert predictions[0]["predicted_party_vote_share"] is None
    assert predictions[0]["share_error"] is None
    assert metrics["full_cohort"]["overall"]["party_share_rows"] == 0


def test_climatology_winner_picks_unique_leader() -> None:
    # Party A's climatology (30, from 2013) beats Party B's (10, from 2013),
    # so the 2017 target-election area should call Party A the winner.
    features = (
        _feature("hist-a", "2013", "2 May 2013", "area-hist", "Party A"),
        _feature("hist-b", "2013", "2 May 2013", "area-hist", "Party B"),
        _feature("win-a", "2017", "4 May 2017", "area-win", "Party A"),
        _feature("win-b", "2017", "4 May 2017", "area-win", "Party B"),
    )
    targets = (
        _target("hist-a", "Party A", 30.0, "Yes"),
        _target("hist-b", "Party B", 10.0, "No"),
        _target("win-a", "Party A", 32.0, "Yes"),
        _target("win-b", "Party B", 8.0, "No"),
    )

    predictions, _metrics, _audit = evaluate_party_historical_mean_reference(features, targets)
    by_id = {row["party_contest_id"]: row for row in predictions}

    assert by_id["win-a"]["predicted_party_elected"] == "Yes"
    assert by_id["win-b"]["predicted_party_elected"] == "No"
    assert by_id["win-a"]["winner_prediction_correct"] is True


def test_climatology_winner_leaves_a_tied_area_unknown() -> None:
    # Party C and Party D each carry an identical single historical
    # observation (20.0), so neither has a unique highest climatology figure
    # in the 2017 target area. The rule must not guess between them.
    features = (
        _feature("hist-c", "2013", "2 May 2013", "area-hist2", "Party C"),
        _feature("hist-d", "2013", "2 May 2013", "area-hist2", "Party D"),
        _feature("tie-c", "2017", "4 May 2017", "area-tie", "Party C"),
        _feature("tie-d", "2017", "4 May 2017", "area-tie", "Party D"),
    )
    targets = (
        _target("hist-c", "Party C", 20.0, "Yes"),
        _target("hist-d", "Party D", 20.0, "No"),
        _target("tie-c", "Party C", 22.0, "Yes"),
        _target("tie-d", "Party D", 18.0, "No"),
    )

    predictions, _metrics, _audit = evaluate_party_historical_mean_reference(features, targets)
    by_id = {row["party_contest_id"]: row for row in predictions}

    assert by_id["tie-c"]["predicted_party_vote_share"] == by_id["tie-d"]["predicted_party_vote_share"]
    assert by_id["tie-c"]["predicted_party_elected"] == "Unknown"
    assert by_id["tie-d"]["predicted_party_elected"] == "Unknown"
    assert by_id["tie-c"]["winner_prediction_correct"] is None


def test_common_support_tag_matches_persistence_cohort_definition() -> None:
    # A row outside persistence_benchmark's own cohort (no approved lagged
    # share) must be tagged False, so the common-support metric block can
    # restrict itself to a genuinely comparable set of rows.
    features = (
        _feature(
            "out-a",
            "2021",
            "6 May 2021",
            "area-out",
            "Party A",
            baseline_eligibility="excluded_no_approved_exact_label_previous_party_share",
        ),
    )
    targets = (_target("out-a", "Party A", 40.0, "No"),)

    predictions, _metrics, _audit = evaluate_equal_share_reference(features, targets)

    assert predictions[0]["within_persistence_share_cohort"] is False
