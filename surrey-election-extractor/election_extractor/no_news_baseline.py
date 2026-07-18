"""Publish a provenance-labelled electoral baseline before any news features.

This module is deliberately downstream of the source-preserving master
database.  It does not add evidence, estimate missing values, or change an
official field.  It makes the permitted pre-election electoral information
explicit, so later news models can be compared against one reproducible
``no-news`` baseline rather than against an implicit mixture of fields.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from election_extractor.master_database import MasterDatabasePayload


_APPROVED_REFERENCE_STATUSES = frozenset(
    {
        "approved_pre_2024_legal_continuity",
        "approved_for_historical_reference",
        "approved_same_statutory_division",
    }
)


def build_no_news_electoral_baseline(
    payload: MasterDatabasePayload,
) -> tuple[tuple[dict[str, object], ...], dict[str, int]]:
    """Return one division-level baseline row and a transparent coverage audit.

    A row is included for every target division or ward, including those with
    no approved predecessor.  This makes exclusions observable.  Prior turnout
    alone may use separately audited official supplementary evidence after an
    absent official result-page value; all other prior fields retain the
    already-governed master values unchanged.
    """

    divisions_by_event_and_name = {
        (str(row["election_id"]), str(row["division_name"])): row
        for row in payload.divisions_and_wards
    }
    supplementary_turnout = {
        str(row["division_id"]): row
        for row in payload.supplementary_metadata
        if row.get("field_name") == "secondary_division_turnout"
        and row.get("division_id") is not None
    }

    rows: list[dict[str, object]] = []
    for target in payload.divisions_and_wards:
        reference_status = str(target["historical_reference_status"])
        previous_turnout, turnout_provenance, turnout_source_id = _previous_turnout(
            target, divisions_by_event_and_name, supplementary_turnout
        )
        approved = reference_status in _APPROVED_REFERENCE_STATUSES
        rows.append(
            {
                "election_id": target["election_id"],
                "division_id": target["division_id"],
                "division_name": target["division_name"],
                "baseline_eligibility": (
                    "approved_historical_reference" if approved else "no_approved_predecessor"
                ),
                "historical_reference_status": reference_status,
                "previous_election_id": target["previous_election_id"],
                "previous_division_name": target["previous_division_name"],
                "previous_winning_party": target["previous_winning_party"],
                "previous_winning_candidate_vote_share": target[
                    "previous_winning_candidate_vote_share"
                ],
                "previous_electorate": target["previous_electorate"],
                "analysis_previous_turnout": previous_turnout,
                "analysis_previous_turnout_provenance": turnout_provenance,
                "analysis_previous_turnout_source_metadata_id": turnout_source_id,
                "historical_source_url": target["historical_source_url"],
                # Older unavailable-reference rows legitimately pre-date this
                # optional provenance column.  They remain excluded rather
                # than failing the whole baseline publication.
                "historical_permission_source_urls": target.get(
                    "historical_permission_source_urls"
                ),
                "exclusion_reason": None if approved else reference_status,
            }
        )

    summary = Counter()
    for row in rows:
        summary["division_rows"] += 1
        summary[f"baseline_{row['baseline_eligibility']}"] += 1
        summary[f"previous_turnout_{row['analysis_previous_turnout_provenance']}"] += 1
    return tuple(rows), dict(sorted(summary.items()))


def _previous_turnout(
    target: Mapping[str, object],
    divisions_by_event_and_name: Mapping[tuple[str, str], Mapping[str, object]],
    supplementary_turnout: Mapping[str, Mapping[str, object]],
) -> tuple[object | None, str, str | None]:
    """Select prior turnout without disguising evidence layers as official data."""

    previous_event = target.get("previous_election_id")
    previous_name = target.get("previous_division_name")
    if not isinstance(previous_event, str) or not isinstance(previous_name, str):
        return None, "unavailable_no_approved_predecessor", None
    previous = divisions_by_event_and_name.get((previous_event, previous_name))
    if previous is None:
        # A permitted reference without a loaded source row is an integrity
        # error, rather than a reason to substitute an inferred turnout.
        raise ValueError("Approved historical reference has no prior division row.")
    if previous.get("turnout") is not None:
        return previous["turnout"], "official_result_page", None
    evidence = supplementary_turnout.get(str(previous["division_id"]))
    if evidence is not None and evidence.get("value") is not None:
        return evidence["value"], "supplementary_official_evidence", str(
            evidence["metadata_id"]
        )
    return None, "unavailable_after_permitted_layers", None
