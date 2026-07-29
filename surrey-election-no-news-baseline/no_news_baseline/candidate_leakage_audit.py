"""The formal leakage audit for the candidate-level no-news model.

Step 3 of the supervisor's ordering, and one of the sixteen files the Stage 1
brief requires in the model bundle. The brief specifies the columns:

    field name; source sheet; permitted or excluded; reason; earliest
    availability date; restrictions; relevant permission field

and the rule the audit exists to evidence:

    "Only information that existed before the election being predicted may be
    used as a predictor."

Why the audit lists permitted fields too
----------------------------------------
An exclusion list alone cannot be checked. If a reader only sees what was
excluded, they cannot tell whether a permitted field was reasoned about or
merely never noticed. Every column of the published release therefore appears
exactly once with an explicit verdict, and the brief's named prohibitions
appear as well even where the release never publishes them - recorded as
``excluded_by_construction``, which is the stronger statement: the field could
not enter the feature matrix because it is not in the feature table at all.

Why "earliest availability" is an event, not a calendar date
------------------------------------------------------------
The brief asks for an "earliest availability date". A field-level audit cannot
carry a single calendar date, because the date differs per row: the previous
party vote share for a 2017 contest became available in May 2013, and for a
2026 contest in May 2021. What is constant per field is the *event* at which
the value first exists. The audit therefore publishes a controlled event label
plus, where the event is row-dependent, the column that carries the actual
date. That is auditable; a single fabricated date would not be.

Availability events, earliest first:

``statutory_order_publication``
    Boundary and seat structure fixed by statutory instrument, well before
    polling.
``previous_election_declaration``
    The value is a result of a strictly earlier election, available from that
    election's declaration. The specific date is in ``previous_election_id``.
``nomination_close``
    Known once nominations close, about nineteen working days before polling:
    who stood, for which party, how many candidates and parties are on the
    ballot.
``release_construction``
    Assigned by the extractor when the release is built; carries no election
    information at all (row identifiers, provenance labels).
``target_election_declaration``
    Exists only after the count. Never permitted.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping


PERMITTED = "permitted"
EXCLUDED = "excluded"
EXCLUDED_BY_CONSTRUCTION = "excluded_by_construction"

# Roles a permitted column can play. Only ``predictor`` may enter a feature
# matrix; the others are published for linkage, provenance or cohort
# bookkeeping and are filtered out by contract, not by memory.
PREDICTOR = "predictor"
IDENTIFIER = "identifier"
LINKAGE = "linkage_only"
PROVENANCE = "provenance"
COHORT = "cohort_label"


# One entry per published feature column:
#   column -> (role, source sheet, availability event, restrictions,
#              permission field, reason)
#
# "Source sheet" names the master workbook sheet the value originates from, as
# the brief requests, so the audit can be read against the workbook the
# supervisor holds.
FEATURE_COLUMNS: dict[str, tuple[str, str, str, str, str, str]] = {
    # --- row identity -----------------------------------------------------
    "candidate_contest_id": (
        IDENTIFIER, "Candidate Results", "release_construction", "",
        "",
        "Deterministic hash of election, area and candidate. Carries no "
        "election information.",
    ),
    "election_id": (
        IDENTIFIER, "Elections", "statutory_order_publication", "",
        "",
        "Names the contest being predicted; used for grouping and splitting, "
        "never as a predictor.",
    ),
    "division_id": (
        IDENTIFIER, "Divisions and Wards", "statutory_order_publication", "",
        "",
        "Area identity; used with election_id as the split grouping unit.",
    ),
    "candidate_id": (
        LINKAGE, "Candidates", "nomination_close", "",
        "",
        "Person identity for historical linkage only. The brief: candidate "
        "names and IDs must not be unrestricted high-cardinality predictors "
        "that allow memorisation.",
    ),
    "candidate_name": (
        LINKAGE, "Candidate Results", "nomination_close", "",
        "",
        "Published wording, retained for provenance and linkage.",
    ),
    "standard_candidate_name": (
        LINKAGE, "Candidates", "nomination_close", "",
        "",
        "Display standardisation of the published name; linkage only.",
    ),
    "division_name": (
        LINKAGE, "Divisions and Wards", "statutory_order_publication", "",
        "",
        "Readable area name. Area effects enter through history, not through "
        "the name string.",
    ),
    # --- pre-election structure (permitted predictors) --------------------
    "election_date": (
        PREDICTOR, "Elections", "statutory_order_publication", "",
        "",
        "Polling date. Fixed before the campaign and required for every "
        "chronological ordering in the design.",
    ),
    "election_year": (
        PREDICTOR, "Elections", "statutory_order_publication", "",
        "",
        "Cycle identity. The brief lists election year among permitted "
        "features.",
    ),
    "election_type": (
        PREDICTOR, "Elections", "statutory_order_publication", "",
        "",
        "Principal election versus by-election, named in the brief's feature "
        "list.",
    ),
    "authority": (
        PREDICTOR, "Elections", "statutory_order_publication", "",
        "",
        "Administering authority; constant within an election.",
    ),
    "analysis_number_of_seats": (
        PREDICTOR, "Analysis Voting Summary", "statutory_order_publication", "",
        "analysis_number_of_seats_provenance",
        "Seats returned by the contest. Fixed by statutory instrument before "
        "nominations and required to allocate predicted winners.",
    ),
    "contest_structure": (
        PREDICTOR, "Analysis Voting Summary", "statutory_order_publication", "",
        "analysis_number_of_seats_provenance",
        "Single- or multi-member. Carries the estimand difference explicitly "
        "rather than leaving it as unexplained variance.",
    ),
    "candidate_count_in_contest": (
        PREDICTOR, "Candidate Results", "nomination_close", "",
        "",
        "Number of candidates on the ballot, known at nomination close. The "
        "brief lists number of candidates among permitted features.",
    ),
    "party_count_in_contest": (
        PREDICTOR, "Candidate Results", "nomination_close", "",
        "",
        "Number of distinct political identities on the ballot.",
    ),
    "party_candidate_count_in_contest": (
        PREDICTOR, "Candidate Results", "nomination_close", "",
        "",
        "How many candidates this party fielded here. Mechanically depresses "
        "per-candidate share in multi-member wards, so it is supplied as "
        "information rather than left to be inferred.",
    ),
    # --- party identity ---------------------------------------------------
    "standard_party_name": (
        PREDICTOR, "Political Parties", "nomination_close", "",
        "",
        "Reviewed party identity. The brief requires party identity retained "
        "and Reform UK evaluated separately.",
    ),
    "original_party_name": (
        PROVENANCE, "Candidate Results", "nomination_close", "",
        "",
        "Published label, retained unchanged beside the standardised name.",
    ),
    "party_category": (
        PREDICTOR, "Political Parties", "nomination_close", "",
        "",
        "Established, emerging, local or independent, as the supervisor's "
        "field list requires.",
    ),
    "party_group_key": (
        IDENTIFIER, "Political Parties", "nomination_close", "",
        "",
        "Grouping key that keeps generic Independent labels candidate-specific.",
    ),
    "party_identity_scope": (
        PROVENANCE, "Political Parties", "nomination_close", "",
        "",
        "Whether the row's identity is a reviewed party or a specific "
        "independent.",
    ),
    "is_reform_uk": (
        PREDICTOR, "Political Parties", "nomination_close",
        "Never combined with is_ukip; the release build fails if a row sets both.",
        "",
        "The study-party indicator the brief requires, permitting Reform-"
        "specific interactions and partial pooling.",
    ),
    "is_ukip": (
        PREDICTOR, "Political Parties", "nomination_close",
        "Strictly separate from Reform UK. A UKIP observation is never "
        "relabelled as, or pooled with, a Reform UK observation.",
        "",
        "Contextual party identity only. The brief permits UKIP history as a "
        "clearly labelled sensitivity feature, never as Reform history.",
    ),
    # --- area history (permission-governed predictors) --------------------
    "previous_party_vote_share": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "Usable only where geographic mapping approves the comparison and the "
        "status field permits it. Never imputed as zero when absent.",
        "geographic_reference_eligibility",
        "The single most important lagged predictor. The brief permits "
        "previous party vote share where it relates to a completed earlier "
        "election and mapping permits comparison.",
    ),
    "previous_winning_party": (
        PREDICTOR, "Divisions and Wards", "previous_election_declaration",
        "Approved historical relations only.",
        "historical_reference_status",
        "Previous winner, named in the brief's permitted feature list.",
    ),
    "party_was_previous_winner": (
        PREDICTOR, "Divisions and Wards", "previous_election_declaration",
        "None where no approved previous winner exists; never collapsed to False.",
        "historical_reference_status",
        "Row-level form of the previous-winner feature.",
    ),
    "analysis_previous_turnout": (
        PREDICTOR, "Analysis Voting Summary", "previous_election_declaration",
        "Previous turnout only. Current turnout is excluded.",
        "analysis_previous_turnout_provenance",
        "The brief permits previous turnout and prohibits current turnout; "
        "the two are different columns and this is the permitted one.",
    ),
    "previous_electorate": (
        PREDICTOR, "Divisions and Wards", "previous_election_declaration",
        "Approved historical relations only.",
        "historical_reference_status",
        "Previous electorate, named in the brief's permitted feature list.",
    ),
    "previous_election_id": (
        PROVENANCE, "Geographic Mapping", "previous_election_declaration", "",
        "historical_reference_status",
        "Identifies which earlier election supplied the lagged values, and so "
        "carries their actual availability date.",
    ),
    "previous_division_name": (
        PROVENANCE, "Geographic Mapping", "previous_election_declaration", "",
        "historical_reference_status",
        "Identifies the approved predecessor area.",
    ),
    # --- candidate and party history --------------------------------------
    "candidate_previously_stood": (
        PREDICTOR, "Candidates", "nomination_close",
        "Unknown is a third value, confined to the 2013 study-start boundary; "
        "it is never converted to No.",
        "candidate_history_status",
        "Named in the brief's permitted feature list.",
    ),
    "incumbent_candidate_yes_no": (
        PREDICTOR, "Candidate Results", "nomination_close",
        "Unknown preserved as a distinct value.",
        "incumbent_candidate_yes_no_status",
        "Incumbency of the person, named in the brief's feature list.",
    ),
    "incumbent_party_yes_no": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "Unknown preserves unavailable or non-comparable historical geography.",
        "incumbent_party_yes_no_status",
        "Incumbency of the party, named in the brief's feature list.",
    ),
    "party_previously_contested": (
        PREDICTOR, "Party History and New Entrants", "previous_election_declaration",
        "Approved project lineage only.",
        "party_history_status",
        "Whether the party previously contested the area, named in the brief.",
    ),
    "first_appearance_of_party_in_area": (
        PREDICTOR, "Party History and New Entrants", "previous_election_declaration",
        "First observed exact label in an approved lineage; not a claim about "
        "the party's historical origin.",
        "party_history_status",
        "New-entrant status, named in the brief's feature list and central to "
        "modelling a party with little history.",
    ),
    # --- derived county-level history (candidate_historical_strength) -----
    # These are aggregations over strictly earlier elections, computed in the
    # modelling layer because the extractor's contract is source-preserving
    # and a county-wide party mean is an analytical construct. They read
    # earlier elections' outcomes, which is history rather than leakage - the
    # same basis on which previous_party_vote_share is permitted - and the
    # date rule is verified against each row's recorded contribution sources.
    "party_county_strength_previous": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "Pooled across strictly earlier elections until at least three contests "
        "are covered, within a five-year window. Never sourced from the "
        "embargoed 7 May 2026 holdout.",
        "party_county_strength_status",
        "The party's contest-weighted mean vote share across the county in "
        "earlier elections. It is the only historical signal a party with no "
        "division-level record possesses, which is the situation Reform UK is "
        "in for most divisions.",
    ),
    "party_county_strength_trend": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "Difference between the two most recent pooled windows; null where "
        "only one window exists.",
        "party_county_strength_status",
        "Whether that county strength was rising or falling before the target "
        "election.",
    ),
    "party_contests_fought_previous": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "Distinct areas, not candidate rows: a party fielding two candidates "
        "in a two-member ward fought one contest.",
        "party_county_strength_status",
        "How many contests the pooled window rests on. A strength drawn from "
        "three contests is weaker evidence than one drawn from eighty.",
    ),
    "party_contest_rate_previous": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "Bounded to 0-1 by construction once contests are counted by area.",
        "party_county_strength_status",
        "The share of available contests the party chose to fight. Distinct "
        "from how well it did where it stood, and a signal in its own right: "
        "Reform UK moved from 7 per cent of divisions in 2021 to 100 per cent "
        "in 2026.",
    ),
    "years_since_previous_comparable_election": (
        PREDICTOR, "Geographic Mapping", "previous_election_declaration",
        "Measured to the approved predecessor contest only, since the gap is "
        "meaningless between areas that are not comparable.",
        "historical_reference_status",
        "Named in the brief's feature list as years since previous contest.",
    ),
    "area_parties_in_previous_contest": (
        PREDICTOR, "Candidate Results", "nomination_close",
        "Counted from the contest's own ballot.",
        "",
        "Local-area historical competitiveness: how many distinct political "
        "identities contested this area.",
    ),
    "party_county_strength_status": (
        PROVENANCE, "Candidate Results", "previous_election_declaration",
        "Names the elections pooled, so the date rule can be verified from the "
        "published row rather than from the code that produced it.",
        "party_county_strength_status",
        "Which earlier elections contributed to the pooled county strength.",
    ),
    # --- Reform UK and UKIP interaction terms (candidate_interactions) ----
    "reform_x_previous_party_vote_share": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "Product of the is_reform_uk indicator and a permitted historical "
        "predictor. Adds no information - both factors are already in the "
        "matrix - only the ability to hold a second slope for one party. "
        "Zero on non-Reform rows because the indicator is off; null where the "
        "base predictor is itself missing.",
        "party_county_strength_status",
        "SHAP showed this feature contributing +0.0498 to Conservative predictions and -0.0880 to Reform ones, so one global slope cannot serve both.",
    ),
    "ukip_x_previous_party_vote_share": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "The brief's optional, clearly labelled UKIP sensitivity term. Off by "
        "default and switched on deliberately; UKIP is never merged into "
        "Reform UK and a UKIP observation is never evidence about Reform.",
        "party_county_strength_status",
        "Counterpart to the Reform term, for the comparison the brief "
        "requires between a model that uses UKIP context and one that does not.",
    ),
    "reform_x_party_county_strength_previous": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "Product of the is_reform_uk indicator and a permitted historical "
        "predictor. Adds no information - both factors are already in the "
        "matrix - only the ability to hold a second slope for one party. "
        "Zero on non-Reform rows because the indicator is off; null where the "
        "base predictor is itself missing.",
        "party_county_strength_status",
        "Adding county strength made the linear architectures worse on Reform, because Reform's county figure comes from single-member by-elections and its 2026 contests are two-member wards.",
    ),
    "ukip_x_party_county_strength_previous": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "The brief's optional, clearly labelled UKIP sensitivity term. Off by "
        "default and switched on deliberately; UKIP is never merged into "
        "Reform UK and a UKIP observation is never evidence about Reform.",
        "party_county_strength_status",
        "Counterpart to the Reform term, for the comparison the brief "
        "requires between a model that uses UKIP context and one that does not.",
    ),
    "reform_x_party_county_strength_trend": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "Product of the is_reform_uk indicator and a permitted historical "
        "predictor. Adds no information - both factors are already in the "
        "matrix - only the ability to hold a second slope for one party. "
        "Zero on non-Reform rows because the indicator is off; null where the "
        "base predictor is itself missing.",
        "party_county_strength_status",
        "A rising county trend plausibly means something different for a party entering a division for the first time.",
    ),
    "ukip_x_party_county_strength_trend": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "The brief's optional, clearly labelled UKIP sensitivity term. Off by "
        "default and switched on deliberately; UKIP is never merged into "
        "Reform UK and a UKIP observation is never evidence about Reform.",
        "party_county_strength_status",
        "Counterpart to the Reform term, for the comparison the brief "
        "requires between a model that uses UKIP context and one that does not.",
    ),
    "reform_x_party_contest_rate_previous": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "Product of the is_reform_uk indicator and a permitted historical "
        "predictor. Adds no information - both factors are already in the "
        "matrix - only the ability to hold a second slope for one party. "
        "Zero on non-Reform rows because the indicator is off; null where the "
        "base predictor is itself missing.",
        "party_county_strength_status",
        "Reform moved from contesting 7 per cent of divisions to 100 per cent; for established parties this figure barely moves.",
    ),
    "ukip_x_party_contest_rate_previous": (
        PREDICTOR, "Candidate Results", "previous_election_declaration",
        "The brief's optional, clearly labelled UKIP sensitivity term. Off by "
        "default and switched on deliberately; UKIP is never merged into "
        "Reform UK and a UKIP observation is never evidence about Reform.",
        "party_county_strength_status",
        "Counterpart to the Reform term, for the comparison the brief "
        "requires between a model that uses UKIP context and one that does not.",
    ),
    # --- evidence-quality and missingness indicators ----------------------
    "historical_predictor_availability": (
        PREDICTOR, "Geographic Mapping", "statutory_order_publication",
        "Describes evidence, never substitutes for an outcome.",
        "geographic_reference_eligibility",
        "The missingness indicator the brief asks for. Distinguishes a proven "
        "absence of previous support from an unavailable comparison.",
    ),
    "geographic_reference_eligibility": (
        PREDICTOR, "Geographic Mapping", "statutory_order_publication",
        "Permission status only.",
        "geographic_reference_eligibility",
        "Evidence-quality indicator; whether any history may be transferred.",
    ),
    "historical_reference_status": (
        PROVENANCE, "Geographic Mapping", "statutory_order_publication", "",
        "historical_reference_status",
        "Which statutory permission governs this area's history.",
    ),
    "previous_party_vote_share_status": (
        PROVENANCE, "Candidate Results", "previous_election_declaration", "",
        "previous_party_vote_share_status",
        "How the lagged share was established, or why it is absent.",
    ),
    "candidate_history_status": (
        PROVENANCE, "Candidates", "nomination_close", "",
        "candidate_history_status",
        "Evidence chain behind candidate_previously_stood.",
    ),
    "incumbent_candidate_yes_no_status": (
        PROVENANCE, "Candidate Results", "nomination_close", "",
        "incumbent_candidate_yes_no_status",
        "Evidence chain behind person incumbency.",
    ),
    "incumbent_party_yes_no_status": (
        PROVENANCE, "Candidate Results", "previous_election_declaration", "",
        "incumbent_party_yes_no_status",
        "Evidence chain behind party incumbency.",
    ),
    "party_history_status": (
        PROVENANCE, "Party History and New Entrants", "previous_election_declaration", "",
        "party_history_status",
        "Evidence chain behind the party-history fields.",
    ),
    "analysis_number_of_seats_provenance": (
        PROVENANCE, "Analysis Voting Summary", "statutory_order_publication", "",
        "analysis_number_of_seats_provenance",
        "Whether the seat count is official or supplementary statutory evidence.",
    ),
    "analysis_previous_turnout_provenance": (
        PROVENANCE, "Analysis Voting Summary", "previous_election_declaration", "",
        "analysis_previous_turnout_provenance",
        "Evidence layer behind the previous turnout value.",
    ),
    # --- cohort bookkeeping ------------------------------------------------
    "candidate_baseline_eligibility": (
        COHORT, "Candidate Results", "release_construction",
        "Cohort membership only.",
        "",
        "Whether the row can serve as a prediction target. Selecting rows is "
        "not predicting from them.",
    ),
    # --- source URLs (never predictive) ------------------------------------
    "current_result_source_url": (
        LINKAGE, "Candidate Results", "target_election_declaration",
        "Provenance only. The brief: do not use raw source URLs as predictive "
        "features. Published after the count, so it must never enter a feature "
        "matrix.",
        "",
        "Official provenance for the target value.",
    ),
    "historical_source_url": (
        LINKAGE, "Geographic Mapping", "previous_election_declaration",
        "Provenance only; the brief prohibits raw source URLs as features.",
        "historical_reference_status",
        "Official provenance for the lagged values.",
    ),
    "historical_permission_source_urls": (
        LINKAGE, "Geographic Mapping", "statutory_order_publication",
        "Provenance only; the brief prohibits raw source URLs as features.",
        "historical_reference_status",
        "Statutory instruments establishing the approved comparison.",
    ),
}


# The fields the brief names as prohibited. Each is recorded even though the
# candidate feature table never publishes it, because "considered and kept
# out" is a stronger, checkable statement than silence. ``source_sheet`` says
# where the value does live, so a reader can verify it is genuinely absent
# from the features.
PROHIBITED_FIELDS: dict[str, tuple[str, str]] = {
    "votes": (
        "Candidate Results",
        "The count itself.",
    ),
    "vote_share": (
        "Candidate Results",
        "Official share of the target election; the quantity being predicted.",
    ),
    "analysis_vote_share": (
        "Candidate Results",
        "The prediction target. Published only in the separate target table.",
    ),
    "outcome": (
        "Candidate Results",
        "Published result wording.",
    ),
    "elected_yes_no": (
        "Candidate Results",
        "Outcome label; a secondary target, never an input.",
    ),
    "final_position": (
        "Candidate Results",
        "Rank within the count.",
    ),
    "derived_final_position": (
        "Candidate Results",
        "Rank derived from the count; a secondary target.",
    ),
    "derived_final_position_tied": (
        "Candidate Results",
        "Tie flag derived from the count.",
    ),
    "winning_margin": (
        "Divisions and Wards",
        "Derived from the count of the election being predicted.",
    ),
    "turnout": (
        "Divisions and Wards",
        "Current turnout is published with the result. Previous turnout is a "
        "different, permitted column.",
    ),
    "ballot_papers_issued": (
        "Divisions and Wards",
        "Recorded at the count for the election being predicted.",
    ),
    "total_votes": (
        "Divisions and Wards",
        "The denominator of the target; known only after the count.",
    ),
    "rejected_ballots": (
        "Divisions and Wards",
        "Recorded at the count for the election being predicted.",
    ),
    "change_in_vote_share": (
        "Candidate Results",
        "Current minus previous share, so it contains the target by "
        "construction even though it looks historical. The workbook itself "
        "identifies it as unsuitable as a baseline predictor.",
    ),
    "electorate": (
        "Divisions and Wards",
        "Current electorate is published with the result table. Previous "
        "electorate is a different, permitted column.",
    ),
}


def build_leakage_audit(
    feature_columns: Iterable[str],
    target_columns: Iterable[str],
) -> tuple[dict[str, object], ...]:
    """Return one audit row per column, in the brief's requested schema.

    Raises if the published release contains a column this module has never
    classified. That is deliberate: an unclassified column must stop the
    bundle rather than default to permitted, because the failure mode of a
    leakage audit is silently blessing something new.
    """

    published = sorted(set(feature_columns))
    unclassified = [column for column in published if column not in FEATURE_COLUMNS]
    if unclassified:
        raise ValueError(
            "The candidate feature release contains columns with no leakage "
            f"classification: {unclassified!r}. Classify them before exporting "
            "a model bundle."
        )

    rows: list[dict[str, object]] = []

    for column in published:
        role, sheet, availability, restrictions, permission, reason = FEATURE_COLUMNS[
            column
        ]
        rows.append(
            {
                "field_name": column,
                "source_sheet": sheet,
                "table": "candidate_features",
                "verdict": PERMITTED,
                "role": role,
                "allowed_as_predictor": "yes" if role == PREDICTOR else "no",
                "reason": reason,
                "earliest_availability_event": availability,
                "restrictions": restrictions,
                "permission_field": permission,
            }
        )

    for column in sorted(set(target_columns)):
        rows.append(
            {
                "field_name": column,
                "source_sheet": "Candidate Results",
                "table": "candidate_targets",
                "verdict": EXCLUDED,
                "role": "target",
                "allowed_as_predictor": "no",
                "reason": "Published in the separate target table. Features and "
                          "targets are joined explicitly by candidate_contest_id "
                          "so an outcome cannot be discovered while selecting "
                          "features.",
                "earliest_availability_event": "target_election_declaration",
                "restrictions": "Never joined into a feature matrix.",
                "permission_field": "",
            }
        )

    for column, (sheet, reason) in sorted(PROHIBITED_FIELDS.items()):
        rows.append(
            {
                "field_name": column,
                "source_sheet": sheet,
                "table": "master_workbook_not_published_in_features",
                "verdict": EXCLUDED_BY_CONSTRUCTION,
                "role": "prohibited",
                "allowed_as_predictor": "no",
                "reason": reason,
                "earliest_availability_event": "target_election_declaration",
                "restrictions": "Absent from the candidate feature table; the "
                                "release build fails if it appears.",
                "permission_field": "",
            }
        )

    return tuple(rows)


def permitted_predictors(
    feature_columns: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """The only columns a feature matrix may contain.

    Later modelling code selects from this function rather than from a list
    typed out again, so the audit and the model cannot disagree about what is
    permitted. A model that wants a column not returned here must first add a
    classification above, which forces the reasoning to be written down.
    """

    columns = (
        sorted(set(feature_columns))
        if feature_columns is not None
        else sorted(FEATURE_COLUMNS)
    )
    return tuple(
        column
        for column in columns
        if FEATURE_COLUMNS.get(column, (None,))[0] == PREDICTOR
    )


def assert_no_prohibited_column(columns: Iterable[str]) -> None:
    """Fail if a feature matrix contains a prohibited or non-predictor column.

    The brief: "Add automated tests that fail if a prohibited field enters the
    feature matrix." This is that check, callable at build time as well as in
    tests, so the guarantee holds in production and not only under pytest.
    """

    supplied = list(columns)
    prohibited = sorted(set(supplied) & set(PROHIBITED_FIELDS))
    if prohibited:
        raise ValueError(
            f"Prohibited outcome columns in the feature matrix: {prohibited!r}"
        )
    non_predictors = sorted(
        column
        for column in supplied
        if FEATURE_COLUMNS.get(column, (None,))[0] not in {PREDICTOR}
    )
    if non_predictors:
        raise ValueError(
            "Non-predictor columns in the feature matrix: "
            f"{non_predictors!r}. Identifiers, linkage, provenance and cohort "
            "labels are published but must not be modelled."
        )
