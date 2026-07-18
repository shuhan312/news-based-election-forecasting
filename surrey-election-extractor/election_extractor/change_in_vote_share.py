"""Calculate an outcome-only change in exact-label party vote share.

This field answers the supervisor's descriptive election-database requirement;
it is not a pre-election predictor. Calculation is restricted to a current
single-member contest with an approved exact-label prior share. The current
analysis share may be official or transparently derived from a complete
official candidate table, but altered-boundary redistribution, fuzzy party
matching and multi-member candidate-share comparisons remain prohibited.
"""

from __future__ import annotations


APPROVED_PREVIOUS_SHARE_STATUS = (
    "derived_single_member_exact_label_prior_candidate_share"
)
OUTCOME_ONLY_MODEL_ROLE = "post_election_outcome_diagnostic_not_baseline_predictor"


def change_in_vote_share_fields(
    *,
    current_vote_share: object,
    current_vote_share_provenance: object,
    current_number_of_seats: object,
    previous_party_vote_share: object,
    previous_party_vote_share_status: object,
) -> dict[str, object]:
    """Return a governed percentage-point change and explicit audit state.

    The subtraction is allowed only after the upstream historical audit has
    approved an exact published party label in a comparable single-member
    lineage. Requiring the current contest to have one seat prevents 2026
    candidate shares from being misrepresented as party-share changes.
    """

    common = {"change_in_vote_share_model_role": OUTCOME_ONLY_MODEL_ROLE}
    if previous_party_vote_share_status != APPROVED_PREVIOUS_SHARE_STATUS:
        return {
            "change_in_vote_share": None,
            "change_in_vote_share_status": (
                "not_calculated_no_approved_exact_label_previous_share"
            ),
            "change_in_vote_share_provenance": "unavailable",
            **common,
        }
    if current_number_of_seats != 1:
        return {
            "change_in_vote_share": None,
            "change_in_vote_share_status": (
                "not_calculated_current_contest_not_single_member"
            ),
            "change_in_vote_share_provenance": "unavailable",
            **common,
        }
    if not isinstance(current_vote_share, (int, float)):
        return {
            "change_in_vote_share": None,
            "change_in_vote_share_status": "not_calculated_current_share_unavailable",
            "change_in_vote_share_provenance": "unavailable",
            **common,
        }
    if not isinstance(previous_party_vote_share, (int, float)):
        # An approved status without its required value is an integrity error,
        # not an ordinary missing-data category.
        raise ValueError("Approved previous-party-share status requires a numeric value.")

    # Percentage-point change, not proportional percentage change. Six decimal
    # places match the governed analysis_vote_share precision and prevent
    # binary floating-point artefacts from leaking into JSON or Excel.
    value = round(float(current_vote_share) - float(previous_party_vote_share), 6)
    return {
        "change_in_vote_share": value,
        "change_in_vote_share_status": (
            "outcome_diagnostic_exact_label_single_member_change_available"
        ),
        "change_in_vote_share_provenance": (
            f"{current_vote_share_provenance}_minus_approved_previous_exact_label_share"
        ),
        **common,
    }
