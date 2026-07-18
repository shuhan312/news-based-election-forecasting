"""Publish analysis-ready voting-summary values without changing official fields.

The supervisor needs Seats, issued ballots, turnout and rejected ballots for
modelling.  Surrey publishes these through a mixture of official result pages,
separately cited official evidence and narrowly governed calculations.  This
module selects the strongest already-audited value for analysis while retaining
the official column and the source/provenance layer unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping


_FIELD_SOURCES = {
    "number_of_seats": ("official_number_of_seats", "secondary_number_of_seats", None),
    "ballot_papers_issued": (
        "ballot_papers_issued",
        "secondary_division_ballot_papers_issued",
        "derived_ballot_papers_issued",
    ),
    "turnout": ("turnout", "secondary_division_turnout", None),
    "rejected_ballots": ("rejected_ballots", None, "derived_rejected_ballots"),
}


def build_analysis_voting_summary(
    divisions: Iterable[Mapping[str, object]],
    supplementary_metadata: Iterable[Mapping[str, object]],
    derived_metadata: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Return one provenance-labelled analysis value per requested field.

    Precedence is deliberately fixed: official result-page value, then a
    separately cited official supplementary record, then a governed derived
    value.  An absent value remains NULL; this function never estimates a
    statistic or treats a supplementary/derived value as official.
    """

    supplementary = {
        (str(row["division_id"]), str(row["field_name"])): row
        for row in supplementary_metadata
        if row.get("division_id") is not None
    }
    derived = {
        (str(row["division_id"]), str(row["field_name"])): row
        for row in derived_metadata
        if row.get("division_id") is not None
    }
    rows: list[dict[str, object]] = []
    for division in divisions:
        division_id = str(division["division_id"])
        for analysis_field, (official_field, supplementary_field, derived_field) in _FIELD_SOURCES.items():
            official_value = division.get(official_field)
            selected_value = official_value
            provenance = "official_result_page" if official_value is not None else "unavailable"
            source_id = None
            if selected_value is None and supplementary_field:
                # Seats evidence is already denormalised into the division
                # table; the other supplementary values remain in metadata.
                source = supplementary.get((division_id, supplementary_field))
                secondary_value = (
                    division.get(supplementary_field)
                    if supplementary_field == "secondary_number_of_seats"
                    else source.get("value") if source is not None else None
                )
                if secondary_value is not None:
                    selected_value = secondary_value
                    provenance = "supplementary_official_evidence"
                    source_id = source.get("metadata_id") if source is not None else None
            if selected_value is None and derived_field:
                source = derived.get((division_id, derived_field))
                if source is not None:
                    selected_value = source.get("value")
                    provenance = "governed_derived_value"
                    source_id = source.get("metadata_id")
            rows.append(
                {
                    "election_id": division["election_id"],
                    "division_id": division_id,
                    "division_name": division["division_name"],
                    "field_name": f"analysis_{analysis_field}",
                    "value": selected_value,
                    "provenance_layer": provenance,
                    "source_metadata_id": source_id,
                    "official_field_name": official_field,
                    "official_value": official_value,
                }
            )
    return tuple(rows)
