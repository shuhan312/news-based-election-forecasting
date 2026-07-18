"""Release-level checks for the supervisor's Previous party vote share field."""

from collections import Counter

from election_extractor.master_database import build_master_database, load_audited_elections
from scripts.generate_master_election_database import reviewed_historical_reference_inputs


def test_previous_party_vote_share_release_has_only_audited_residual_nulls() -> None:
    """Freeze coverage and ensure residual NULLs stay in defensible categories.

    This is deliberately an integration test over the audited local payload. It
    protects against both regressions (losing approved prior shares) and silent
    overreach (turning a changed boundary or generic Independent label into a
    party-history claim).
    """

    elections = load_audited_elections()
    division_references, party_references = reviewed_historical_reference_inputs()
    rows = build_master_database(
        elections,
        historical_division_references=division_references,
        party_history_references=party_references,
    ).candidate_results
    statuses = Counter(str(row["previous_party_vote_share_status"]) for row in rows)

    assert len(rows) == 1_971
    assert sum(row["previous_party_vote_share"] is not None for row in rows) == 998
    assert statuses == {
        "derived_single_member_exact_label_prior_candidate_share": 998,
        "not_derived_no_approved_exact_label_reference": 956,
        "not_derived_generic_independent_label_not_identifying": 11,
        "not_derived_current_exact_label_not_unique": 4,
        "not_derived_prior_exact_label_not_unique": 2,
    }

    # 2013 cannot be joined to 2009: the 2012 Order abolished the old
    # divisions.  Unapproved 2026 geographies likewise remain unavailable.
    assert all(
        row["previous_party_vote_share"] is None
        for row in rows
        if row["election_id"] == "surrey-county-council-2013"
    )
    assert all(
        row["previous_party_vote_share"] is None
        for row in rows
        if row["previous_party_vote_share_status"]
        == "not_derived_generic_independent_label_not_identifying"
    )
