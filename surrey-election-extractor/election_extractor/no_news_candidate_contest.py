"""Build the candidate-contest modelling release for the no-news baseline.

Why this module exists
----------------------
``no_news_party_contest.py`` publishes one row per election, area and party,
and its primary experiment is deliberately restricted to single-member
contests because a party vote share is not a defined quantity in a
multi-member plurality contest (each elector casts up to ``seats`` votes, so
summing a party's candidate shares does not estimate that party's support).

That restriction is correct for the party estimand, but it has a consequence
the supervisor's Stage 1 brief cannot accept: the 7 May 2026 East and West
Surrey elections were fought in two-member wards, so the entire primary
holdout period falls outside the party-share cohort.

The brief asks for a different estimand that does not have this problem:

    "The primary target is analysis_vote_share.  The model should predict
    vote share for every candidate in a contest."

A candidate's share of the votes cast in their own contest is observed and
well defined regardless of how many seats that contest returns.  This module
therefore publishes the candidate-level release, one row per candidate, so
that 2026 can be a scored holdout.

Relationship to the party release
---------------------------------
Neither release replaces the other and neither is derived from the other.

* Candidate release (this module) - primary experiment.  Target is the
  published candidate share.  Covers every candidate row.
* Party release - retained as a party-estimand sensitivity check on the
  single-member subset, where the two estimands provably coincide.

Estimand boundary (must be carried into every write-up)
-------------------------------------------------------
``analysis_vote_share`` is votes for the candidate divided by all votes cast
on that contest's ballot.  In a single-member contest that is also the party's
vote share.  In a two-member contest it is not: a party fielding two
candidates splits its support across two ballot lines, so its candidates'
individual shares are mechanically lower than the same party's support would
be in a single-member contest.

Two consequences are handled by construction rather than by hoping a model
learns them:

1. ``contest_structure``, ``analysis_number_of_seats``,
   ``candidate_count_in_contest`` and ``party_candidate_count_in_contest``
   are published as features, so the structural difference is available to
   the model as information rather than as unexplained noise.
2. The coverage audit reports cohort sizes separately by contest structure,
   so evaluation can never silently average a single-member error against a
   multi-member error and report one number.

Eligibility semantics (the substantive change from the party release)
---------------------------------------------------------------------
The party release folds two different questions into one
``baseline_eligibility`` field: "is this row a valid prediction target?" and
"does an approved lagged predictor exist for it?".  Requiring both is what
removed 2026 from the cohort, because most 2026 wards have changed boundaries
and therefore no approved predecessor share.

This module keeps them separate:

* ``candidate_baseline_eligibility`` answers only the first question.  A row
  is eligible when it has an observed target share and a known contest
  structure.
* ``historical_predictor_availability`` answers only the second, as a
  missingness label.

That follows the brief's own instruction - "Create missingness indicators
where they may be useful" and "Unknown values must remain unknown" - and it
means a changed-boundary ward is modelled as a row with a missing historical
predictor, not as a row that does not exist.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from hashlib import sha256

from election_extractor.master_database import MasterDatabasePayload
from election_extractor.no_news_baseline import build_no_news_electoral_baseline


# Outcomes observed at the target election.  These may appear only in the
# separately published target table.  ``_assert_feature_target_separation``
# fails the build if any of them reaches the feature table, which is the
# structural guard the brief asks for ("Add automated tests that fail if a
# prohibited field enters the feature matrix").
TARGET_ONLY_FIELDS = frozenset(
    {
        "target_candidate_vote_share",
        "target_candidate_votes",
        "target_candidate_elected",
        "target_candidate_rank",
        "target_candidate_rank_tied",
    }
)


# Fields that exist to link a person across elections, not to predict.  They
# are published because historical linkage is impossible without them, and
# listed here so the modelling layer can drop them from a feature matrix by
# contract rather than by remembering to.  The brief: "Candidate names and IDs
# should be used for historical linkage, not as unrestricted high-cardinality
# predictors that allow memorisation."
LINKAGE_ONLY_FIELDS = frozenset(
    {
        "candidate_id",
        "candidate_name",
        "standard_candidate_name",
        "division_name",
        "current_result_source_url",
        "historical_source_url",
        "historical_permission_source_urls",
    }
)


# The two party identities the project must never merge.  Standard names come
# from the extractor's reviewed party standardisation; the raw published
# labels are retained separately on every row.
REFORM_UK_STANDARD_NAME = "Reform UK"
UKIP_STANDARD_NAME = "UK Independence Party"


def build_no_news_candidate_contests(
    payload: MasterDatabasePayload,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...], dict[str, int]]:
    """Return leakage-safe candidate features, targets and a coverage audit.

    One row per election, area and candidate.  Every candidate row in the
    master database produces exactly one feature row and one target row; rows
    that cannot serve as prediction targets are retained and labelled, never
    dropped, so the audit can show what was excluded and why.
    """

    elections = {str(row["election_id"]): row for row in payload.elections}
    divisions = {
        (str(row["election_id"]), str(row["division_id"])): row
        for row in payload.divisions_and_wards
    }

    # The division-level no-news baseline already resolves which historical
    # area (if any) a contest may legally reference, and carries the approved
    # previous winner, turnout and electorate with their provenance.  Reusing
    # it means the candidate release cannot drift away from the permission
    # decisions the party release obeys.
    division_baseline, _ = build_no_news_electoral_baseline(payload)
    baseline_by_division = {
        (str(row["election_id"]), str(row["division_id"])): row
        for row in division_baseline
    }

    # Group candidates by contest so contest-level structure (how many
    # candidates stood, how many parties, how many candidates a given party
    # fielded) can be computed once and attached to every row in it.
    contests: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for candidate in payload.candidate_results:
        contests[
            (str(candidate["election_id"]), str(candidate["division_id"]))
        ].append(candidate)

    features: list[dict[str, object]] = []
    targets: list[dict[str, object]] = []

    for (election_id, division_id), candidates in sorted(contests.items()):
        election = elections[election_id]
        division = divisions[(election_id, division_id)]
        division_history = baseline_by_division[(election_id, division_id)]

        seats, seats_provenance = _analysis_seats(division)
        structure = _contest_structure(seats)

        # Contest-level counts.  These are pre-election facts: the ballot is
        # known once nominations close, so candidate and party counts do not
        # leak the result.
        candidate_count = len(candidates)
        party_candidate_counts = Counter(
            _party_group_key(candidate) for candidate in candidates
        )
        party_count = len(party_candidate_counts)

        for candidate in sorted(candidates, key=_candidate_sort_key):
            party_group_key = _party_group_key(candidate)
            standard_party_name = _text(candidate.get("standard_party_name"))
            candidate_contest_id = _candidate_contest_id(
                election_id, division_id, str(candidate["candidate_id"])
            )

            previous_party_share = candidate.get("previous_party_vote_share")
            historical_availability = _historical_predictor_availability(
                previous_party_share=previous_party_share,
                previous_share_status=candidate.get(
                    "previous_party_vote_share_status"
                ),
                area_eligibility=str(division_history["baseline_eligibility"]),
            )

            target_share = candidate.get("analysis_vote_share")
            eligibility = _candidate_baseline_eligibility(
                target_share=target_share,
                structure=structure,
            )

            feature = {
                # --- identity -------------------------------------------------
                "candidate_contest_id": candidate_contest_id,
                "election_id": election_id,
                "election_date": election["election_date"],
                "election_year": election["election_year"],
                "election_type": election["election_type"],
                "authority": election["authority"],
                "division_id": division_id,
                "division_name": division["division_name"],
                "candidate_id": candidate["candidate_id"],
                "candidate_name": candidate.get("candidate_name"),
                "standard_candidate_name": candidate.get("standard_candidate_name"),
                # --- party identity, Reform and UKIP kept separate ------------
                "standard_party_name": standard_party_name,
                "original_party_name": candidate.get("original_party_name"),
                "party_category": candidate.get("party_category"),
                "party_group_key": party_group_key,
                "party_identity_scope": _party_identity_scope(candidate),
                # Two independent indicators, never one shared "populist right"
                # flag.  A row can only ever set one of them, which
                # ``_assert_reform_ukip_separation`` enforces at build time.
                "is_reform_uk": standard_party_name == REFORM_UK_STANDARD_NAME,
                "is_ukip": standard_party_name == UKIP_STANDARD_NAME,
                # --- contest structure ----------------------------------------
                "analysis_number_of_seats": seats,
                "analysis_number_of_seats_provenance": seats_provenance,
                "contest_structure": structure,
                "candidate_count_in_contest": candidate_count,
                "party_count_in_contest": party_count,
                "party_candidate_count_in_contest": party_candidate_counts[
                    party_group_key
                ],
                # --- area history (permission-governed) -----------------------
                "previous_election_id": division_history["previous_election_id"],
                "previous_division_name": division_history["previous_division_name"],
                "historical_reference_status": division_history[
                    "historical_reference_status"
                ],
                "geographic_reference_eligibility": division_history[
                    "baseline_eligibility"
                ],
                "previous_party_vote_share": previous_party_share,
                "previous_party_vote_share_status": candidate.get(
                    "previous_party_vote_share_status"
                ),
                "previous_winning_party": division_history["previous_winning_party"],
                "party_was_previous_winner": _party_was_previous_winner(
                    candidate, division_history.get("previous_winning_party")
                ),
                "analysis_previous_turnout": division_history[
                    "analysis_previous_turnout"
                ],
                "analysis_previous_turnout_provenance": division_history[
                    "analysis_previous_turnout_provenance"
                ],
                "previous_electorate": division_history["previous_electorate"],
                # --- candidate and party history ------------------------------
                "candidate_previously_stood": candidate.get(
                    "candidate_previously_stood"
                ),
                "candidate_history_status": candidate.get("candidate_history_status"),
                "incumbent_candidate_yes_no": candidate.get(
                    "incumbent_candidate_yes_no"
                ),
                "incumbent_candidate_yes_no_status": candidate.get(
                    "incumbent_candidate_yes_no_status"
                ),
                "incumbent_party_yes_no": candidate.get("incumbent_party_yes_no"),
                "incumbent_party_yes_no_status": candidate.get(
                    "incumbent_party_yes_no_status"
                ),
                "party_previously_contested": candidate.get(
                    "party_previously_contested"
                ),
                "first_appearance_of_party_in_area": candidate.get(
                    "first_appearance_of_party_in_area"
                ),
                "party_history_status": candidate.get("party_history_status"),
                # --- cohort labels --------------------------------------------
                # These two answer different questions and must stay separate.
                "candidate_baseline_eligibility": eligibility,
                "historical_predictor_availability": historical_availability,
                # --- provenance -----------------------------------------------
                "historical_source_url": division_history["historical_source_url"],
                "historical_permission_source_urls": division_history[
                    "historical_permission_source_urls"
                ],
                "current_result_source_url": candidate.get("source_url"),
            }

            target = {
                "candidate_contest_id": candidate_contest_id,
                "election_id": election_id,
                "division_id": division_id,
                "candidate_id": candidate["candidate_id"],
                "standard_party_name": standard_party_name,
                # The brief's primary target.
                "target_candidate_vote_share": target_share,
                "target_candidate_vote_share_provenance": candidate.get(
                    "analysis_vote_share_provenance"
                ),
                "target_candidate_vote_share_status": candidate.get(
                    "analysis_vote_share_status"
                ),
                "target_candidate_votes": candidate.get("votes"),
                "target_candidate_elected": candidate.get("elected_yes_no"),
                # Competition rank derived from a complete official candidate
                # table.  It is a secondary target, never a feature.
                "target_candidate_rank": candidate.get("derived_final_position"),
                "target_candidate_rank_tied": candidate.get(
                    "derived_final_position_tied"
                ),
                "target_candidate_rank_status": candidate.get(
                    "derived_final_position_status"
                ),
                "target_source_url": candidate.get("source_url"),
            }

            features.append(feature)
            targets.append(target)

    _assert_unique_ids(features, "feature")
    _assert_unique_ids(targets, "target")
    _assert_feature_target_separation(features)
    _assert_reform_ukip_separation(features)
    _assert_historical_time_order(features, elections)
    _assert_target_consistency(features, targets)
    audit = _coverage_audit(features, targets)
    return tuple(features), tuple(targets), audit


# --------------------------------------------------------------------------
# Cohort labelling
# --------------------------------------------------------------------------


def _candidate_baseline_eligibility(
    *, target_share: object | None, structure: str
) -> str:
    """Answer only: can this row serve as a prediction target?

    Deliberately does NOT consult historical predictor availability.  A row
    with no approved predecessor is still a legitimate target; it simply has a
    missing predictor, which is recorded separately and handled by the model's
    missingness indicators.
    """

    if structure == "unknown_seat_structure":
        # Without a known seat count the contest's own estimand is undefined:
        # predictions could not be normalised and no winner could be selected.
        return "excluded_unknown_seat_structure"
    if target_share is None:
        return "excluded_no_observed_candidate_vote_share"
    return "eligible_candidate_vote_share"


def _historical_predictor_availability(
    *,
    previous_party_share: object | None,
    previous_share_status: object | None,
    area_eligibility: str,
) -> str:
    """Label WHY a lagged party share is or is not available for this row.

    This is a missingness reason, not an eligibility gate.  Keeping the reason
    rather than a bare null lets the modelling layer distinguish "this party
    genuinely scored nothing here before" from "the boundary changed so no
    comparable figure exists" - two situations that must never share an
    imputed value.
    """

    if previous_party_share is not None:
        return "approved_previous_party_share"
    if area_eligibility != "approved_historical_reference":
        return "no_approved_area_reference"
    status = _text(previous_share_status)
    if status and "study_start" in status:
        return "study_start_boundary"
    return "approved_area_no_previous_party_share"


# --------------------------------------------------------------------------
# Row-level helpers
# --------------------------------------------------------------------------


def _party_group_key(candidate: Mapping[str, object]) -> str:
    """Keep generic Independent labels candidate-specific.

    Mirrors the party release exactly, so the two publications count "how many
    candidates did this party field" the same way.  Two different independents
    are two political identities, not one party with two candidates.
    """

    if candidate.get("party_category") == "independent":
        return f"independent_candidate:{candidate['candidate_id']}"
    return f"party:{candidate['standard_party_name']}"


def _party_identity_scope(candidate: Mapping[str, object]) -> str:
    return (
        "candidate_specific_independent"
        if candidate.get("party_category") == "independent"
        else "reviewed_standard_party"
    )


def _candidate_contest_id(
    election_id: str, division_id: str, candidate_id: str
) -> str:
    digest = sha256(
        f"{election_id}|{division_id}|{candidate_id}".encode()
    ).hexdigest()[:16]
    return f"candidate-contest-{digest}"


def _candidate_sort_key(candidate: Mapping[str, object]) -> tuple[str, str]:
    """Deterministic within-contest ordering, independent of votes.

    Sorting by any result value would make row order a function of the
    outcome.  Sorting by identity keeps the published file byte-stable across
    rebuilds without touching the target.
    """

    return (
        str(candidate.get("standard_party_name") or ""),
        str(candidate.get("candidate_id") or ""),
    )


def _analysis_seats(division: Mapping[str, object]) -> tuple[int | None, str]:
    """Official seat count first, statutory supplementary evidence second."""

    if division.get("official_number_of_seats") is not None:
        return int(division["official_number_of_seats"]), "official_result_page"
    if division.get("secondary_number_of_seats") is not None:
        return (
            int(division["secondary_number_of_seats"]),
            "supplementary_statutory_evidence",
        )
    return None, "unavailable_after_permitted_layers"


def _contest_structure(seats: int | None) -> str:
    if seats == 1:
        return "single_member"
    if seats is not None and seats > 1:
        return "multi_member"
    return "unknown_seat_structure"


def _party_was_previous_winner(
    candidate: Mapping[str, object], previous_winner: object
) -> bool | None:
    """Unknown stays None; it is never collapsed into False.

    Matching accepts either the published label or the reviewed standard name,
    because the previous winner is recorded as published at that earlier
    election and label wording drifts between years.
    """

    if previous_winner is None:
        return None
    labels = {
        _text(candidate.get("original_party_name")),
        _text(candidate.get("standard_party_name")),
    }
    return str(previous_winner) in {label for label in labels if label}


def _text(value: object) -> str:
    return "" if value is None else str(value)


# --------------------------------------------------------------------------
# Integrity assertions - the build fails rather than publishing a bad release
# --------------------------------------------------------------------------


def _assert_unique_ids(rows: list[Mapping[str, object]], table_name: str) -> None:
    ids = [str(row["candidate_contest_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate candidate_contest_id in {table_name} table.")


def _assert_feature_target_separation(features: list[Mapping[str, object]]) -> None:
    leaked = set().union(*(set(row) for row in features)) & TARGET_ONLY_FIELDS
    if leaked:
        raise ValueError(
            f"Target leakage fields found in candidate features: {sorted(leaked)!r}"
        )


def _assert_reform_ukip_separation(features: list[Mapping[str, object]]) -> None:
    """No row may be both Reform UK and UKIP.

    A cheap check, but it is the structural expression of the supervisor's
    single hardest constraint, and it will fail loudly if a future party
    standardisation change ever maps one label onto the other.
    """

    for row in features:
        if row["is_reform_uk"] and row["is_ukip"]:
            raise ValueError(
                "A candidate row was flagged as both Reform UK and UKIP: "
                f"{row['candidate_contest_id']}"
            )


def _assert_historical_time_order(
    features: list[Mapping[str, object]], elections: Mapping[str, Mapping[str, object]]
) -> None:
    """Every referenced predecessor election must precede its target election."""

    dates = {
        election_id: _parse_election_date(str(row["election_date"]))
        for election_id, row in elections.items()
    }
    for row in features:
        previous_id = row.get("previous_election_id")
        if previous_id is None:
            continue
        if dates[str(previous_id)] >= dates[str(row["election_id"])]:
            raise ValueError(
                "No-news candidate feature references a non-prior election event."
            )


def _assert_target_consistency(
    features: list[Mapping[str, object]], targets: list[Mapping[str, object]]
) -> None:
    """Reconcile candidate targets against the official contest.

    Two checks:

    1. Range.  Every published share sits in 0-100.
    2. Contest sum.  Candidate shares are shares of the same denominator (all
       votes cast in that contest), so a complete contest sums to 100 before
       rounding - in a two-member contest as much as in a single-member one,
       because both divide by total votes cast.

    The tolerance is derived rather than guessed.  Sources publish shares
    rounded to at worst the nearest whole percentage point, so each of ``n``
    candidates contributes at most 0.5pp of rounding error, giving ``0.5n``.
    Two further points absorb the source's own rounding of the total.  A sum
    outside that band is a data-integrity failure, not rounding, and stops the
    build instead of being silently renormalised.
    """

    feature_by_id = {str(row["candidate_contest_id"]): row for row in features}
    by_contest: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)

    for target in targets:
        share = target.get("target_candidate_vote_share")
        if share is not None and not 0 <= float(share) <= 100:
            raise ValueError("target_candidate_vote_share is outside 0-100.")
        feature = feature_by_id[str(target["candidate_contest_id"])]
        previous_share = feature.get("previous_party_vote_share")
        if previous_share is not None and not 0 <= float(previous_share) <= 100:
            raise ValueError("previous_party_vote_share is outside 0-100.")
        by_contest[
            (str(target["election_id"]), str(target["division_id"]))
        ].append(target)

    for contest_targets in by_contest.values():
        shares = [
            target.get("target_candidate_vote_share") for target in contest_targets
        ]
        # A contest missing any published share cannot be reconciled; its rows
        # are already labelled ineligible by _candidate_baseline_eligibility.
        if any(share is None for share in shares):
            continue
        tolerance = 2.0 + 0.5 * len(shares)
        total = sum(float(share) for share in shares)
        if not 100 - tolerance <= total <= 100 + tolerance:
            feature = feature_by_id[str(contest_targets[0]["candidate_contest_id"])]
            raise ValueError(
                "Candidate shares do not reconcile to the contest total in "
                f"{feature['election_id']} / {feature['division_name']}: "
                f"sum={total:.2f} over {len(shares)} candidates "
                f"(tolerance +/-{tolerance:.1f})."
            )


def _parse_election_date(value: str) -> datetime:
    for date_format in ("%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            pass
    raise ValueError(f"Unsupported election date: {value!r}")


# --------------------------------------------------------------------------
# Coverage audit
# --------------------------------------------------------------------------


def _coverage_audit(
    features: list[Mapping[str, object]], targets: list[Mapping[str, object]]
) -> dict[str, int]:
    """Counts that make the 2026 holdout's presence checkable at a glance.

    Reported by contest structure and by election, because the whole point of
    this release is that a multi-member election is now inside the cohort, and
    that claim should be readable from the audit without loading the data.
    """

    audit: Counter[str] = Counter()
    target_by_id = {str(row["candidate_contest_id"]): row for row in targets}

    for row in features:
        eligibility = str(row["candidate_baseline_eligibility"])
        election_id = str(row["election_id"])
        target = target_by_id[str(row["candidate_contest_id"])]

        audit["candidate_contest_rows"] += 1
        audit[f"structure_{row['contest_structure']}"] += 1
        audit[f"eligibility_{eligibility}"] += 1
        audit[
            f"historical_{row['historical_predictor_availability']}"
        ] += 1

        if eligibility == "eligible_candidate_vote_share":
            audit["eligible_rows"] += 1
            audit[f"eligible_by_election_{election_id}"] += 1
            audit[f"eligible_by_structure_{row['contest_structure']}"] += 1
            if row["is_reform_uk"]:
                audit["eligible_reform_uk_rows"] += 1
                audit[f"eligible_reform_uk_{election_id}"] += 1
            if row["is_ukip"]:
                audit["eligible_ukip_rows"] += 1

        if target["target_candidate_elected"] in {"Yes", "No"}:
            audit["target_elected_resolved"] += 1
        if target["target_candidate_rank"] is not None:
            audit["target_rank_available"] += 1

    return dict(sorted(audit.items()))
