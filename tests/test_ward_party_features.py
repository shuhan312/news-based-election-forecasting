"""Tests for the ward-party-election feature layer.

The table is large and mostly empty, which makes it easy to write tests that
pass because nothing happened. So the fixtures below build a small corpus with
known contents, and most assertions are about the cases that go wrong
silently: a party that did not stand being read as a party that scored zero, a
contest split across two folds, a holdout prediction presented as out-of-fold,
Reform UK collapsing into UKIP, and a window assembled from a bucket wider
than itself.
"""

from __future__ import annotations

import pytest

from news_modelling.ward_party_build import (
    IDENTIFIER_COLUMNS,
    TARGET_PREFIX,
    VIEW_PREFIXES,
    blind,
    build_master_rows,
    classify_split,
    columns_for_view,
    feature_dictionary,
    leakage_audit,
    split_lookup,
    validate,
)
from news_modelling.ward_party_features import (
    CUMULATIVE_SNAPSHOTS,
    PRINCIPAL_WINDOWS,
    REFORM_KEY,
    UKIP_KEY,
    WindowMappingError,
    aggregate_baseline_to_party,
    build_observation_grid,
    index_coverage,
    index_news_rows,
    normalise_area,
    party_key,
    selected_feature_columns,
    verify_window_mapping,
)

FEATURES = ["cov_n_articles"]


def contract_row(party="Conservative", division="d1", election="e2021",
                 reform=False, ukip=False, candidate="c1"):
    return {
        "candidate_contest_id": candidate, "election_id": election,
        "election_date": "6 May 2021", "division_id": division,
        "division_name": "Guildford East", "standard_party_name": party,
        "is_reform_uk": reform, "is_ukip": ukip,
        "analysis_number_of_seats": 1,
        "geographic_reference_eligibility": "approved",
    }


def prediction(party="Conservative", division="d1", election="e2021",
               predicted=20.0, observed=25.0, candidate="c1",
               reform=False, ukip=False):
    return {
        "candidate_contest_id": candidate, "election_id": election,
        "division_id": division, "standard_party_name": party,
        "is_reform_uk": reform, "is_ukip": ukip,
        "predicted_vote_share": predicted, "observed_vote_share": observed,
        "model_id": "m1", "split_id": "s1",
    }


def news_row(party_id="P-CON", division="Guildford East", window="previous_30_days",
             election="SCC-2021-05", scope="surrey_wide_local", articles=3):
    return {
        "election_id": election,
        "geographic_target_id": f"{election}:{division}",
        "focal_party_id": party_id, "window": window,
        "scope_classification": scope, "cov_n_articles": articles,
    }


PARTY_NAMES = {"P-CON": "Conservative", "P-REF": "Reform UK",
               "P-UKIP": "UK Independence Party"}


# ---------------------------------------------------------------------------
# Window construction
# ---------------------------------------------------------------------------


def test_a_window_whose_days_hold_no_articles_is_empty_not_assembled():
    """The case that first broke the build.

    `final_complete_day` means day 1; the old bucket it would be assembled
    from spans days 1 to 3. With day 1 empty and day 2 occupied, assembling
    would fill an empty window with articles belonging to the next one.
    """

    report = verify_window_mapping([2, 2, 5, 6, 8, 14])
    check = report["checks"]["final_complete_day"]
    assert check["construction"] == "empty_no_articles_in_day_range"
    assert check["assembled_from"] == []
    assert check["exact"]


def test_a_window_with_articles_in_a_wider_bucket_is_refused():
    """Day 1 and day 3 both occupied: the bucket cannot be split."""

    with pytest.raises(WindowMappingError, match="final_complete_day"):
        verify_window_mapping([1, 3, 5])


def test_an_exactly_covered_window_assembles():
    report = verify_window_mapping([10, 20])
    check = report["checks"]["30_to_8_complete_days"]
    assert check["construction"] == "assembled_from_legacy_windows"
    assert check["assembled_from"] == ["14_to_8_days", "30_to_15_days"]


def test_cumulative_snapshots_and_principal_windows_are_both_defined():
    assert set(PRINCIPAL_WINDOWS) == {
        "final_complete_day", "7_to_2_complete_days", "30_to_8_complete_days"}
    assert set(CUMULATIVE_SNAPSHOTS) == {
        "information_available_at_1_day", "information_available_at_7_days",
        "information_available_at_30_days"}


def test_principal_windows_do_not_overlap():
    """The same article must sit in only one non-overlapping window."""

    covered: set[int] = set()
    for spec in PRINCIPAL_WINDOWS.values():
        first, last = spec["days"]
        days = set(range(first, last + 1))
        assert not (covered & days)
        covered |= days


# ---------------------------------------------------------------------------
# Observation grid
# ---------------------------------------------------------------------------


def test_the_grid_has_one_row_per_election_area_party():
    grid = build_observation_grid(
        [contract_row(party="Conservative", candidate="c1"),
         contract_row(party="Conservative", candidate="c2"),
         contract_row(party="Labour", candidate="c3")], [])
    assert len(grid) == 2
    conservative = next(r for r in grid if r["party_id"] == party_key("Conservative"))
    assert conservative["candidates_fielded"] == 2
    assert conservative["party_contested"] and not conservative["did_not_contest"]


def test_a_party_that_did_not_stand_appears_and_is_marked():
    grid = build_observation_grid([contract_row()], [{
        "election_id": "e2021", "election_date": "6 May 2021",
        "division_id": "d1", "division_name": "Guildford East",
        "standard_party_name": "Reform UK", "is_reform_uk": True,
        "is_ukip": False, "contestation_status": "did_not_contest",
        "candidates_fielded": 0, "analysis_number_of_seats": 1}])
    reform = next(r for r in grid if r["is_reform_uk"])
    assert reform["did_not_contest"] and not reform["party_contested"]


def test_reform_and_ukip_get_different_party_ids():
    assert REFORM_KEY != UKIP_KEY
    grid = build_observation_grid(
        [contract_row(party="Reform UK", reform=True, candidate="c1"),
         contract_row(party="UK Independence Party", ukip=True, candidate="c2")], [])
    assert len({row["party_id"] for row in grid}) == 2


def test_area_names_normalise_without_merging_different_areas():
    assert normalise_area("Guildford East Ward") == normalise_area("Guildford East")
    assert normalise_area("Guildford East") != normalise_area("Guildford West")


# ---------------------------------------------------------------------------
# Baseline attachment
# ---------------------------------------------------------------------------


def test_candidate_predictions_are_summed_to_the_party_not_averaged():
    """A party fielding two candidates in a two-member ward holds both shares."""

    baseline = aggregate_baseline_to_party(
        [prediction(predicted=20.0, observed=22.0, candidate="c1"),
         prediction(predicted=18.0, observed=19.0, candidate="c2")],
        provenance="stage1_out_of_fold")
    entry = baseline[("e2021", "d1", party_key("Conservative"))]
    assert entry["baseline__predicted_party_vote_share"] == pytest.approx(38.0)
    assert entry["target__party_vote_share"] == pytest.approx(41.0)
    assert entry["baseline__candidates_predicted"] == 2


def test_provenance_records_which_stage_1_split_a_prediction_came_from():
    out_of_fold = aggregate_baseline_to_party(
        [prediction()], provenance="stage1_out_of_fold")
    holdout = aggregate_baseline_to_party(
        [prediction(election="e2026")], provenance="stage1_holdout")
    assert next(iter(out_of_fold.values()))[
        "baseline__prediction_provenance"] == "stage1_out_of_fold"
    assert next(iter(holdout.values()))[
        "baseline__prediction_provenance"] == "stage1_holdout"


def test_a_party_with_no_prediction_gets_none_not_zero():
    baseline = aggregate_baseline_to_party(
        [prediction(predicted="", observed="")], provenance="stage1_out_of_fold")
    entry = next(iter(baseline.values()))
    assert entry["baseline__predicted_party_vote_share"] is None
    assert entry["target__party_vote_share"] is None


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------


def test_may_2026_east_and_west_share_one_holdout_period():
    east = classify_split("surrey-county-council-2026-east-surrey", "", None)
    west = classify_split("surrey-county-council-2026-west-surrey", "", None)
    assert east == west
    assert east["modelling_split"] == "final_test_2026"
    assert east["holdout_indicator"] and east["blinded_outcome_indicator"]


def test_the_july_2026_by_election_is_a_separate_secondary_test():
    result = classify_split(
        "surrey-county-council-by-election-haslemere-2026-07-07", "", None)
    assert result["modelling_split"] == "secondary_test_2026_07"
    assert result["holdout_indicator"]
    assert not result["blinded_outcome_indicator"]


def test_2021_is_validation_and_earlier_elections_train():
    assert classify_split("surrey-county-council-2021", "", None)[
        "modelling_split"] == "validation_2021"
    assert classify_split("surrey-county-council-2017", "", None)[
        "modelling_split"] == "historical_training"


def test_a_contest_that_appears_in_a_holdout_split_stays_there():
    """A contest ever held out must never also be trained on."""

    placement = split_lookup([
        {"contest_id": "x", "split_id": "rolling", "split_role": "rolling_origin_fold"},
        {"contest_id": "x", "split_id": "hold", "split_role": "primary_holdout"},
        {"contest_id": "x", "split_id": "rolling2", "split_role": "rolling_origin_fold"},
    ])
    assert placement["x"]["split_role"] == "primary_holdout"


# ---------------------------------------------------------------------------
# News joins
# ---------------------------------------------------------------------------


def test_local_news_only_reaches_its_own_party():
    index = index_news_rows([news_row(party_id="P-CON")], PARTY_NAMES, arm="local")
    key = ("SCC-2021-05", normalise_area("Guildford East"),
           party_key("Conservative"), "previous_30_days")
    assert key in index
    reform_key = ("SCC-2021-05", normalise_area("Guildford East"),
                  REFORM_KEY, "previous_30_days")
    assert reform_key not in index


def test_national_rows_are_keyed_without_an_area():
    index = index_news_rows(
        [{"election_id": "SCC-2021-05",
          "geographic_target_id": "SCC-2021-05:ELECTION_WIDE",
          "focal_party_id": "P-REF", "window": "previous_30_days",
          "scope_classification": "national_political", "cov_n_articles": 4}],
        PARTY_NAMES, arm="national")
    assert ("SCC-2021-05", REFORM_KEY, "previous_30_days") in index


def test_an_arm_never_indexes_the_other_arm_s_rows():
    """Otherwise the local and national models would overlap."""

    rows = [news_row(scope="surrey_wide_local"),
            {"election_id": "SCC-2021-05",
             "geographic_target_id": "SCC-2021-05:ELECTION_WIDE",
             "focal_party_id": "P-CON", "window": "previous_30_days",
             "scope_classification": "national_political", "cov_n_articles": 2}]
    local = index_news_rows(rows, PARTY_NAMES, arm="local")
    national = index_news_rows(rows, PARTY_NAMES, arm="national")
    assert all(len(key) == 4 for key in local)
    assert all(len(key) == 3 for key in national)


def test_selected_columns_pick_the_named_families_only():
    columns = ["cov_n_articles", "issue_crime_n", "frame_conflict_n",
               "reform_in_headline_n", "election_id", "geographic_target_id"]
    selected = selected_feature_columns(columns)
    assert "election_id" not in selected
    assert "geographic_target_id" not in selected
    assert set(selected) >= {"cov_n_articles", "issue_crime_n"}


# ---------------------------------------------------------------------------
# The assembled table
# ---------------------------------------------------------------------------


@pytest.fixture
def master():
    grid = build_observation_grid(
        [contract_row(party="Conservative", candidate="c1"),
         contract_row(party="Reform UK", reform=True, candidate="c2")],
        [{"election_id": "e2021", "election_date": "6 May 2021",
          "division_id": "d1", "division_name": "Guildford East",
          "standard_party_name": "Labour", "is_reform_uk": False,
          "is_ukip": False, "contestation_status": "did_not_contest",
          "candidates_fielded": 0, "analysis_number_of_seats": 1}])
    baseline = aggregate_baseline_to_party(
        [prediction(party="Conservative", candidate="c1"),
         prediction(party="Reform UK", candidate="c2", reform=True,
                    predicted=5.0, observed=8.0)],
        provenance="stage1_out_of_fold")
    news = [news_row(party_id="P-CON")]
    return build_master_rows(
        grid, baseline,
        index_news_rows(news, PARTY_NAMES, arm="local"),
        index_news_rows(news, PARTY_NAMES, arm="national"),
        index_coverage([], PARTY_NAMES),
        {}, {}, {},
        feature_columns=FEATURES, weighted_feature_columns=[])


def test_every_row_has_a_unique_key_and_one_split(master):
    checks = validate(master)
    assert checks["duplicate_row_keys"] == 0
    assert checks["contests_split_across_more_than_one_split"] == {}


def test_a_did_not_contest_row_has_an_empty_target_not_zero(master):
    labour = next(r for r in master
                  if r["standardised_party_name"] == "Labour")
    assert labour["did_not_contest"]
    assert labour["target__party_vote_share"] is None
    assert labour["baseline__prediction_provenance"] == "not_applicable_did_not_contest"


def test_validation_flags_a_did_not_contest_row_given_a_zero_target(master):
    """The check exists because zero is the mistake that looks like data."""

    broken = [dict(row) for row in master]
    for row in broken:
        if row["did_not_contest"]:
            row["target__party_vote_share"] = 0
    checks = validate(broken)
    assert checks["did_not_contest_rows_with_a_zero_target"]
    assert not checks["all_checks_passed"]


def test_news_reaches_the_party_it_is_about_and_not_the_others(master):
    column = "local__information_available_at_30_days__cov_n_articles"
    conservative = next(r for r in master
                        if r["standardised_party_name"] == "Conservative")
    reform = next(r for r in master if r["is_reform_uk"])
    assert conservative[column] == 3
    assert reform[column] is None


def test_combined_is_the_sum_of_local_and_national(master):
    row = next(r for r in master if r["standardised_party_name"] == "Conservative")
    window = "information_available_at_30_days"
    parts = [row[f"local__{window}__cov_n_articles"],
             row[f"national__{window}__cov_n_articles"]]
    expected = sum(p for p in parts if p is not None)
    assert row[f"combined__{window}__cov_n_articles"] == expected


def test_combined_stays_empty_where_both_arms_are(master):
    """Adding two unknowns does not make a zero."""

    reform = next(r for r in master if r["is_reform_uk"])
    window = "information_available_at_30_days"
    assert reform[f"local__{window}__cov_n_articles"] is None
    assert reform[f"national__{window}__cov_n_articles"] is None
    assert reform[f"combined__{window}__cov_n_articles"] is None


# ---------------------------------------------------------------------------
# Blinding, views and the leakage audit
# ---------------------------------------------------------------------------


def test_blinding_removes_target_columns_rather_than_emptying_them():
    rows = [{"row_key": "a", "blinded_outcome_indicator": True,
             "target__party_vote_share": 30.0, "baseline__x": 1},
            {"row_key": "b", "blinded_outcome_indicator": False,
             "target__party_vote_share": 20.0, "baseline__x": 2}]
    blinded = blind(rows)
    assert len(blinded) == 1
    assert not any(c.startswith(TARGET_PREFIX) for c in blinded[0])
    assert blinded[0]["baseline__x"] == 1


def test_the_no_news_view_has_no_news_columns():
    columns = ["row_key", "baseline__p", "local__w__x", "national__w__x",
               "combined__w__x", "coverage__w__y", "target__party_vote_share"]
    view = columns_for_view("F_no_news", columns)
    assert "baseline__p" in view
    assert not any(c.startswith(("local__", "national__", "combined__")) for c in view)


def test_local_and_national_views_are_independently_selectable():
    columns = ["row_key", "baseline__p", "local__w__x", "national__w__x"]
    local = columns_for_view("C_local_news", columns)
    national = columns_for_view("D_national_news", columns)
    assert "local__w__x" in local and "national__w__x" not in local
    assert "national__w__x" in national and "local__w__x" not in national


def test_the_blinded_view_carries_no_target_prefix():
    assert TARGET_PREFIX not in VIEW_PREFIXES["B_blinded_2026"]


def test_every_column_receives_a_leakage_verdict():
    columns = ["row_key", "baseline__p", "local__w__x", "coverage__w__y",
               "target__party_vote_share", "something_unrecognised"]
    audit = {row["feature_name"]: row for row in leakage_audit(columns)}
    assert set(audit) == set(columns)
    assert audit["row_key"]["verdict"] == "identifier"
    assert audit["target__party_vote_share"]["verdict"] == "target"
    assert audit["local__w__x"]["verdict"] == "permitted"


def test_an_unrecognised_column_is_excluded_rather_than_allowed():
    """A new column from upstream must not join the predictors by default."""

    audit = {row["feature_name"]: row for row in
             leakage_audit(["a_column_nobody_declared"])}
    assert audit["a_column_nobody_declared"]["verdict"] == "excluded"


def test_a_result_derived_column_is_excluded_with_a_reason():
    audit = {row["feature_name"]: row for row in
             leakage_audit(["baseline__current_vote_share",
                            "local__w__change_in_vote_share"])}
    for row in audit.values():
        assert row["verdict"] == "excluded"
        assert "election being predicted" in row["reason"]


def test_the_dictionary_describes_every_column():
    columns = ["row_key", "local__30_to_8_complete_days__cov_n_articles"]
    entries = {row["feature_name"]: row for row in feature_dictionary(columns)}
    assert set(entries) == set(columns)
    described = entries["local__30_to_8_complete_days__cov_n_articles"]
    assert described["block"] == "local"
    assert "8-30" in described["window_definition"]
    assert described["traceability"]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_building_twice_gives_the_same_table(master):
    again = build_master_rows(
        build_observation_grid(
            [contract_row(party="Conservative", candidate="c1"),
             contract_row(party="Reform UK", reform=True, candidate="c2")],
            [{"election_id": "e2021", "election_date": "6 May 2021",
              "division_id": "d1", "division_name": "Guildford East",
              "standard_party_name": "Labour", "is_reform_uk": False,
              "is_ukip": False, "contestation_status": "did_not_contest",
              "candidates_fielded": 0, "analysis_number_of_seats": 1}]),
        aggregate_baseline_to_party(
            [prediction(party="Conservative", candidate="c1"),
             prediction(party="Reform UK", candidate="c2", reform=True,
                        predicted=5.0, observed=8.0)],
            provenance="stage1_out_of_fold"),
        index_news_rows([news_row(party_id="P-CON")], PARTY_NAMES, arm="local"),
        index_news_rows([news_row(party_id="P-CON")], PARTY_NAMES, arm="national"),
        index_coverage([], PARTY_NAMES), {}, {}, {},
        feature_columns=FEATURES, weighted_feature_columns=[])
    assert again == master


# ---------------------------------------------------------------------------
# Secondary targets
# ---------------------------------------------------------------------------


def test_party_seats_won_counts_elected_candidates():
    baseline = aggregate_baseline_to_party([
        {**prediction(candidate="c1"), "observed_elected": True},
        {**prediction(candidate="c2"), "observed_elected": True},
        {**prediction(party="Labour", candidate="c3"), "observed_elected": False},
    ], provenance="stage1_out_of_fold")
    conservative = baseline[("e2021", "d1", party_key("Conservative"))]
    labour = baseline[("e2021", "d1", party_key("Labour"))]
    assert conservative["target__party_seats_won"] == 2
    assert labour["target__party_seats_won"] == 0
    assert conservative["target__party_won_contest"] is True
    assert labour["target__party_won_contest"] is False


def test_party_rank_orders_by_share_within_the_contest():
    baseline = aggregate_baseline_to_party([
        {**prediction(party="Conservative", observed=40.0, candidate="c1")},
        {**prediction(party="Labour", observed=35.0, candidate="c2")},
        {**prediction(party="Reform UK", observed=25.0, candidate="c3", reform=True)},
    ], provenance="stage1_out_of_fold")
    ranks = {key[2]: entry["target__party_rank"] for key, entry in baseline.items()}
    assert ranks[party_key("Conservative")] == 1
    assert ranks[party_key("Labour")] == 2
    assert ranks[REFORM_KEY] == 3


def test_the_winning_party_is_recorded_on_every_row_of_the_contest():
    baseline = aggregate_baseline_to_party([
        {**prediction(party="Conservative", observed=40.0, candidate="c1")},
        {**prediction(party="Labour", observed=35.0, candidate="c2")},
    ], provenance="stage1_out_of_fold")
    winners = {entry["target__winning_party_in_contest"]
               for entry in baseline.values()}
    assert winners == {"Conservative"}


def test_a_contest_with_an_unknown_share_gets_no_rank_for_anyone():
    """A rank against a partial field looks like a measurement and is not one."""

    baseline = aggregate_baseline_to_party([
        {**prediction(party="Conservative", observed=40.0, candidate="c1")},
        {**prediction(party="Labour", observed="", candidate="c2")},
    ], provenance="stage1_out_of_fold")
    for entry in baseline.values():
        assert entry["target__party_rank"] is None
        assert entry["target__winning_party_in_contest"] is None


def test_a_party_with_no_observed_result_has_no_seat_count():
    """Absent is not zero: a seat count of zero is a real result."""

    baseline = aggregate_baseline_to_party(
        [prediction(observed="")], provenance="stage1_out_of_fold")
    entry = next(iter(baseline.values()))
    assert entry["target__party_seats_won"] is None
    assert entry["target__party_vote_share"] is None
