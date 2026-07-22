"""Tests for the N5 pre-implementation identifiability audit."""

from no_news_baseline.coverage_evaluation import build_evaluation_universe
from no_news_baseline.n5_specification_audit import (
    area_identifiability_audit,
    build_contest_usability_audit,
    election_cycle_audit,
    party_identifiability_audit,
    reconcile_outcome_states,
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
    party_identity_scope: str = "reviewed_standard_party",
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
        "contest_structure": contest_structure,
        "geographic_reference_eligibility": geographic_reference_eligibility,
        "party_identity_scope": party_identity_scope,
        "baseline_eligibility": baseline_eligibility,
        "previous_party_vote_share": None,
        "previous_party_vote_share_status": "derived_single_member_exact_label_prior_candidate_share",
        "party_was_previous_winner": None,
        "historical_source_url": "https://official.example/previous",
    }


def _target(
    contest_id: str,
    party: str,
    share: float | None,
    elected: str,
    *,
    status: str = "analysis_candidate_share_equals_single_member_party_share",
) -> dict[str, object]:
    return {
        "party_contest_id": contest_id,
        "standard_party_name": party,
        "target_party_vote_share": share,
        "target_party_vote_share_status": status,
        "target_party_elected": elected,
        "target_source_urls": "https://official.example/current",
    }


def _complete_contest(prefix: str, election_id: str, date: str, area: str, shares):
    features = tuple(
        _feature(f"{prefix}-{i}", election_id, date, area, party)
        for i, (party, _share) in enumerate(shares)
    )
    targets = tuple(
        _target(f"{prefix}-{i}", party, share, "Yes" if i == 0 else "No")
        for i, (party, share) in enumerate(shares)
    )
    return features, targets


def test_contest_grouping_produces_one_audit_row_per_election_area() -> None:
    f1, t1 = _complete_contest("a", "2017", "4 May 2017", "area-a", [("P1", 60.0), ("P2", 40.0)])
    f2, t2 = _complete_contest("b", "2017", "4 May 2017", "area-b", [("P1", 55.0), ("P2", 45.0)])

    audit = build_contest_usability_audit(f1 + f2, t1 + t2)

    assert len(audit) == 2
    assert {row["division_id"] for row in audit} == {"area-a", "area-b"}
    assert all(row["contesting_party_count"] == 2 for row in audit)


def test_complete_composition_is_detected_as_usable() -> None:
    features, targets = _complete_contest(
        "a", "2017", "4 May 2017", "area-a", [("P1", 60.0), ("P2", 40.0)]
    )

    audit = build_contest_usability_audit(features, targets)

    assert audit[0]["usable_complete_composition"] is True
    assert audit[0]["unusable_reason"] is None
    assert audit[0]["share_sum"] == 100.0


def test_share_sum_outside_publication_tolerance_is_unusable() -> None:
    # 60 + 30 = 90: more than 2pp from 100, so not a closed composition.
    features, targets = _complete_contest(
        "a", "2017", "4 May 2017", "area-a", [("P1", 60.0), ("P2", 30.0)]
    )

    audit = build_contest_usability_audit(features, targets)

    assert audit[0]["usable_complete_composition"] is False
    assert audit[0]["unusable_reason"] == "share_sum_outside_publication_tolerance"


def test_multi_member_contest_is_unusable_with_explicit_reason() -> None:
    features = (
        _feature("m-1", "2026", "7 May 2026", "ward-m", "P1",
                 contest_structure="multi_member",
                 baseline_eligibility="excluded_non_single_member_primary_estimand"),
        _feature("m-2", "2026", "7 May 2026", "ward-m", "P2",
                 contest_structure="multi_member",
                 baseline_eligibility="excluded_non_single_member_primary_estimand"),
    )
    targets = (
        _target("m-1", "P1", None, "Yes", status="not_defined_for_multi_member_party_contest"),
        _target("m-2", "P2", None, "No", status="not_defined_for_multi_member_party_contest"),
    )

    audit = build_contest_usability_audit(features, targets)

    assert audit[0]["usable_complete_composition"] is False
    assert audit[0]["unusable_reason"] == "multi_member_party_share_estimand_undefined"


def test_outcome_states_separate_structural_absence_from_undefined_targets() -> None:
    features = (
        _feature("s-1", "2017", "4 May 2017", "area-s", "P1"),
        _feature("m-1", "2026", "7 May 2026", "ward-m", "P2",
                 contest_structure="multi_member",
                 baseline_eligibility="excluded_non_single_member_primary_estimand",
                 geographic_reference_eligibility="no_approved_predecessor"),
    )
    targets = (
        _target("s-1", "P1", 100.0, "Yes"),
        _target("m-1", "P2", None, "Yes", status="not_defined_for_multi_member_party_contest"),
    )
    universe = build_evaluation_universe(features, targets)

    states = reconcile_outcome_states(universe)

    assert states["observed_share_available"] == 1
    assert states["participating_party_share_undefined_multi_member"] == 1
    # Absent parties have no row at all in this release: structural
    # non-participation must be reported as zero rows, never conflated
    # with a participating party whose target is undefined.
    assert states["structural_non_participation_rows"] == 0


def test_party_audit_keeps_ukip_and_reform_separate_and_excludes_independents() -> None:
    f1, t1 = _complete_contest("a", "2017", "4 May 2017", "area-a", [("UKIP", 20.0), ("P1", 80.0)])
    f2, t2 = _complete_contest("b", "2021", "6 May 2021", "area-a", [("Reform UK", 25.0), ("P1", 75.0)])
    ind = (_feature("i-1", "2021", "6 May 2021", "area-i", "Independent",
                    party_identity_scope="candidate_specific_independent"),)
    ind_t = (_target("i-1", "Independent", 100.0, "Yes"),)
    features = f1 + f2 + ind
    targets = t1 + t2 + ind_t

    contest_audit = build_contest_usability_audit(features, targets)
    party_audit = party_identifiability_audit(features, targets, contest_audit)

    names = {row["standard_party_name"] for row in party_audit}
    assert "UKIP" in names and "Reform UK" in names
    assert "Independent" not in names
    ukip = next(row for row in party_audit if row["standard_party_name"] == "UKIP")
    assert ukip["usable_contest_count"] == 1
    assert ukip["pooling_recommendation"] == "partial_pooling_only"


def test_area_audit_counts_repeats_and_requires_a_safe_link() -> None:
    # area-a appears in 2013 (study start, no link) and 2017 (approved link):
    # two usable contests, one safely linked -> area effect supported.
    # area-b appears twice but the later contest lacks an approved link ->
    # the repeat is not safe evidence, so no area effect.
    f1, t1 = _complete_contest("a13", "2013", "2 May 2013", "area-a", [("P1", 60.0), ("P2", 40.0)])
    f2, t2 = _complete_contest("a17", "2017", "4 May 2017", "area-a", [("P1", 55.0), ("P2", 45.0)])
    f3, t3 = _complete_contest("b13", "2013", "2 May 2013", "area-b", [("P1", 70.0), ("P2", 30.0)])
    f4 = tuple(
        {**row, "geographic_reference_eligibility": "no_approved_predecessor"}
        for row in _complete_contest("b17", "2017", "4 May 2017", "area-b", [("P1", 65.0), ("P2", 35.0)])[0]
    )
    t4 = _complete_contest("b17", "2017", "4 May 2017", "area-b", [("P1", 65.0), ("P2", 35.0)])[1]
    # 2013 study-start contests carry no approved predecessor by definition.
    f1 = tuple({**row, "geographic_reference_eligibility": "no_approved_predecessor"} for row in f1)
    f3 = tuple({**row, "geographic_reference_eligibility": "no_approved_predecessor"} for row in f3)

    contest_audit = build_contest_usability_audit(f1 + f2 + f3 + f4, t1 + t2 + t3 + t4)
    area_audit, distribution = area_identifiability_audit(contest_audit)

    by_area = {row["area_key"]: row for row in area_audit}
    assert by_area["area-a"]["usable_contest_count"] == 2
    assert by_area["area-a"]["area_effect_supported"] is True
    assert by_area["area-b"]["usable_contest_count"] == 2
    assert by_area["area-b"]["area_effect_supported"] is False
    assert distribution == {"2": 2}


def test_election_cycle_audit_flags_singleton_events() -> None:
    f1, t1 = _complete_contest("a", "2017", "4 May 2017", "area-a", [("P1", 60.0), ("P2", 40.0)])
    f2, t2 = _complete_contest("b", "2017", "4 May 2017", "area-b", [("P1", 55.0), ("P2", 45.0)])
    f3, t3 = _complete_contest(
        "by", "by-2019", "10 October 2019", "area-a", [("P1", 52.0), ("P2", 48.0)]
    )

    contest_audit = build_contest_usability_audit(f1 + f2 + f3, t1 + t2 + t3)
    cycles = election_cycle_audit(contest_audit)

    by_id = {row["election_id"]: row for row in cycles}
    assert by_id["2017"]["usable_contest_count"] == 2
    assert by_id["2017"]["cycle_effect_individually_estimable"] is True
    assert by_id["by-2019"]["usable_contest_count"] == 1
    assert by_id["by-2019"]["cycle_effect_individually_estimable"] is False
    # Chronological ordering.
    assert [row["election_id"] for row in cycles] == ["2017", "by-2019"]


def test_audits_are_deterministic() -> None:
    f1, t1 = _complete_contest("a", "2017", "4 May 2017", "area-a", [("P1", 60.0), ("P2", 40.0)])
    f2, t2 = _complete_contest("b", "2021", "6 May 2021", "area-a", [("P1", 55.0), ("P2", 45.0)])

    first_contest = build_contest_usability_audit(f1 + f2, t1 + t2)
    second_contest = build_contest_usability_audit(f1 + f2, t1 + t2)
    assert first_contest == second_contest

    first_party = party_identifiability_audit(f1 + f2, t1 + t2, first_contest)
    second_party = party_identifiability_audit(f1 + f2, t1 + t2, second_contest)
    assert first_party == second_party
