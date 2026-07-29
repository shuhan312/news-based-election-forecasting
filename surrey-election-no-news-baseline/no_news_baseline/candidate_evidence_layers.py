"""Which evidence layer each published column's values come from.

The brief asks the data validation to "identify fields whose values are
official, supplementary or derived", and separately to "preserve the
distinction between official values, supplementary official evidence and
governed derived values". The leakage audit already answers *when* a column
became available and *whether* it may be modelled; it does not answer *what
kind of evidence it is*. Those are different questions, and conflating them
would let a governed derived quantity be read as an official one because it
happened to be permitted.

The four layers
---------------
``official``
    The value appears on, or is counted directly from, an official source for
    the relevant election - a returning officer's result page, a candidate
    list, a statutory notice of poll.

``official_or_supplementary_per_row``
    The field carries its own provenance column, because different rows were
    established from different kinds of official evidence. Declaring one layer
    for the whole field would be a claim about rows it is not true of, so the
    per-row distribution is published instead of a label.

``governed_derived``
    Computed by this project from official values under a documented rule.
    Every one of these is reproducible from the contract; none is an
    observation.

``not_an_evidence_value``
    Identifiers, linkage keys, provenance and status strings, cohort labels.
    These are not measurements of anything, so asking which layer they belong
    to is a category error - but leaving them unclassified would make the
    audit incomplete, and an incomplete audit is one nobody can rely on.

Why party identity is derived, not official
-------------------------------------------
``standard_party_name`` is the most consequential classification here. The
name printed on an official result page is the *original* name, kept as
``original_party_name``. The standardised label is this project's own mapping
of that string onto a governed party list, and it is the mapping that keeps
Reform UK and UKIP separate. Calling it official would present a project
decision as a source fact - and it is precisely the decision the brief is most
insistent about.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .candidate_leakage_audit import FEATURE_COLUMNS

OFFICIAL = "official"
PER_ROW = "official_or_supplementary_per_row"
DERIVED = "governed_derived"
NOT_A_VALUE = "not_an_evidence_value"

LAYERS: tuple[str, ...] = (OFFICIAL, PER_ROW, DERIVED, NOT_A_VALUE)


# column -> (layer, why). The reason is stored rather than implied, because
# "derived" without a rule is an assertion and "official" without a source is
# worth less than nothing.
EVIDENCE_LAYERS: dict[str, tuple[str, str]] = {
    # -- official: read from, or counted off, an official source ------------
    "election_date": (OFFICIAL, "Polling date as published by the authority."),
    "election_year": (OFFICIAL, "Calendar year of the official polling date."),
    "election_type": (OFFICIAL, "Principal election or by-election, as declared."),
    "authority": (OFFICIAL, "Administering authority named on the official source."),
    "candidate_count_in_contest": (
        OFFICIAL, "Counted from the official candidate list for the contest."),
    "party_candidate_count_in_contest": (
        OFFICIAL, "Counted from the official candidate list for the contest."),
    "party_count_in_contest": (
        OFFICIAL, "Distinct parties on the official candidate list."),
    "previous_electorate": (
        OFFICIAL, "Electorate published for the earlier election."),
    "previous_winning_party": (
        OFFICIAL, "Winner declared at the earlier election."),
    "previous_party_vote_share": (
        OFFICIAL, "Share computed from the earlier election's official votes."),

    # -- per-row provenance published rather than a single claim -----------
    "analysis_number_of_seats": (
        PER_ROW, "See analysis_number_of_seats_provenance: most rows from the "
                 "official result page, the remainder from supplementary "
                 "statutory evidence."),
    "analysis_previous_turnout": (
        PER_ROW, "See analysis_previous_turnout_provenance: official result "
                 "page, supplementary official evidence, or unavailable."),

    # -- governed derived: computed here, from official values -------------
    "standard_party_name": (
        DERIVED, "Governed standardisation of the printed party name. Keeps "
                 "Reform UK and UKIP separate; original_party_name retains "
                 "the official string."),
    "party_category": (DERIVED, "Governed grouping of standardised parties."),
    "is_reform_uk": (DERIVED, "Indicator derived from the standardised name."),
    "is_ukip": (DERIVED, "Indicator derived from the standardised name."),
    "contest_structure": (
        DERIVED, "Single- or multi-member, derived from the seat count."),
    "candidate_previously_stood": (
        DERIVED, "Candidate linkage across elections under the mapping rules."),
    "incumbent_candidate_yes_no": (
        DERIVED, "Derived from candidate linkage to the previous winner."),
    "incumbent_party_yes_no": (
        DERIVED, "Derived from the previous winning party under mapping rules."),
    "party_was_previous_winner": (
        DERIVED, "Comparison of this party against the previous winner."),
    "party_previously_contested": (
        DERIVED, "Whether the party stood earlier in a permitted predecessor."),
    "first_appearance_of_party_in_area": (
        DERIVED, "First permitted observation of the party in the area."),
    "years_since_previous_comparable_election": (
        DERIVED, "Interval between the row's date and its permitted predecessor."),
    "area_parties_in_previous_contest": (
        DERIVED, "Party count in the permitted predecessor contest."),
    "party_contests_fought_previous": (
        DERIVED, "Contests the party fought before this date, pooled backwards."),
    "party_contest_rate_previous": (
        DERIVED, "Contests fought divided by contests available, before this date."),
    "party_county_strength_previous": (
        DERIVED, "County-wide mean share before this date; see "
                 "docs/historical_strength_features.md."),
    "party_county_strength_trend": (
        DERIVED, "Change between consecutive pooled county windows."),
    "geographic_reference_eligibility": (
        DERIVED, "Whether Geographic Mapping permits a historical reference."),
    "historical_predictor_availability": (
        DERIVED, "Which historical predictors this row may legitimately use."),

    # Interaction terms: products of columns already present, added so a
    # linear model can hold a separate slope for one party.
    **{
        name: (DERIVED, "Product of a party indicator and a historical "
                        "predictor; see docs/reform_interaction_terms.md.")
        for name in (
            "reform_x_previous_party_vote_share",
            "reform_x_party_county_strength_previous",
            "reform_x_party_county_strength_trend",
            "reform_x_party_contest_rate_previous",
            "ukip_x_previous_party_vote_share",
            "ukip_x_party_county_strength_previous",
            "ukip_x_party_county_strength_trend",
            "ukip_x_party_contest_rate_previous",
        )
    },

    # -- not measurements of anything --------------------------------------
    **{
        name: (NOT_A_VALUE, "Identifier or linkage key, not an observation.")
        for name in (
            "candidate_contest_id", "election_id", "division_id", "division_name",
            "party_group_key", "candidate_id", "candidate_name",
            "standard_candidate_name", "current_result_source_url",
            "historical_source_url", "historical_permission_source_urls",
            "previous_election_id", "previous_division_name",
        )
    },
    **{
        name: (NOT_A_VALUE, "Provenance or status metadata describing another "
                            "field, not a value in its own right.")
        for name in (
            "analysis_number_of_seats_provenance",
            "analysis_previous_turnout_provenance",
            "previous_party_vote_share_status", "candidate_history_status",
            "incumbent_candidate_yes_no_status", "incumbent_party_yes_no_status",
            "party_history_status", "historical_reference_status",
            "party_county_strength_status", "party_identity_scope",
            "original_party_name", "candidate_baseline_eligibility",
        )
    },
}

# Fields that publish their own per-row provenance, and the column that does it.
PROVENANCE_COLUMNS: dict[str, str] = {
    "analysis_number_of_seats": "analysis_number_of_seats_provenance",
    "analysis_previous_turnout": "analysis_previous_turnout_provenance",
}


def assert_every_column_classified() -> None:
    """Fail if a published column has no evidence layer, or an unknown one.

    Same discipline as the leakage audit: an unclassified column stops the
    build rather than defaulting to a layer. A default here would silently
    label new derived features as whatever the default was.
    """

    missing = sorted(set(FEATURE_COLUMNS) - set(EVIDENCE_LAYERS))
    if missing:
        raise ValueError(
            f"{len(missing)} published column(s) have no evidence layer: "
            f"{missing}. Classify them in candidate_evidence_layers.py."
        )
    extra = sorted(set(EVIDENCE_LAYERS) - set(FEATURE_COLUMNS))
    if extra:
        raise ValueError(
            f"{len(extra)} column(s) are classified but not published: {extra}. "
            "A layer for a column nobody publishes is a stale entry."
        )
    unknown = sorted(
        {layer for layer, _ in EVIDENCE_LAYERS.values()} - set(LAYERS)
    )
    if unknown:
        raise ValueError(f"Unknown evidence layer(s): {unknown}")


def layer_of(column: str) -> str:
    """The evidence layer of one column."""

    try:
        return EVIDENCE_LAYERS[column][0]
    except KeyError as error:
        raise KeyError(
            f"{column!r} has no evidence layer. Classify it in "
            "candidate_evidence_layers.py rather than assuming one."
        ) from error


def evidence_layer_report(
    rows: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """The brief's official / supplementary / derived identification.

    ``rows`` is optional. Without it the report is the static classification;
    with it, the fields carrying per-row provenance also report their actual
    distribution, which is the only way to say how much of the data rests on
    supplementary rather than primary evidence.
    """

    assert_every_column_classified()

    by_layer: dict[str, list[str]] = {layer: [] for layer in LAYERS}
    for column, (layer, _) in sorted(EVIDENCE_LAYERS.items()):
        by_layer[layer].append(column)

    report: dict[str, object] = {
        "columns_by_layer": by_layer,
        "counts_by_layer": {layer: len(names) for layer, names in by_layer.items()},
        # Predictors only, because that is the set that reaches a model and
        # therefore the set whose evidence quality affects a result.
        "predictor_counts_by_layer": {
            layer: sum(
                1 for name in names
                if FEATURE_COLUMNS[name][0] == "predictor"
            )
            for layer, names in by_layer.items()
        },
        "reasons": {
            column: {"layer": layer, "reason": reason}
            for column, (layer, reason) in sorted(EVIDENCE_LAYERS.items())
        },
    }

    if rows:
        distributions: dict[str, dict[str, int]] = {}
        for field, provenance_column in PROVENANCE_COLUMNS.items():
            counts: dict[str, int] = {}
            for row in rows:
                value = str(row.get(provenance_column))
                counts[value] = counts.get(value, 0) + 1
            distributions[field] = dict(sorted(counts.items()))
        report["per_row_provenance"] = distributions

        # Classified and present are not the same number, and the difference
        # is not noise: the four UKIP interaction columns are classified but
        # absent unless the sensitivity option is on. Quoting the classified
        # count as the model's input count would overstate it by four, so the
        # columns actually present are counted rather than assumed.
        present = {
            column for column in rows[0]
            if column in EVIDENCE_LAYERS and FEATURE_COLUMNS[column][0] == "predictor"
        }
        report["predictors_present_in_this_run"] = len(present)
        report["predictor_counts_by_layer_present"] = {
            layer: sum(1 for column in present if EVIDENCE_LAYERS[column][0] == layer)
            for layer in LAYERS
        }
        report["classified_predictors_absent_from_this_run"] = sorted(
            column for column, (_, _) in EVIDENCE_LAYERS.items()
            if FEATURE_COLUMNS[column][0] == "predictor" and column not in present
        )

    return report
