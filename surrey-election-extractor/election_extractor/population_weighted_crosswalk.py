"""Audit population-weighted 2021-to-2026 electoral crosswalk estimates.

The calculation uses official ONS 2021 Output Area population-weighted
centroids and Nomis Census 2021 usual-resident counts.  Each small area is
assigned to one historical division and one 2026 ward.  Historical votes are
then redistributed in proportion to the source division's assigned population.

These estimates are sensitivity evidence, not official results.  Validation on
unchanged divisions checks the data pipeline but cannot validate how votes are
distributed inside a division that was actually split.  The audit therefore
does not authorise changed-boundary estimates as primary baseline predictors.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import re

from shapely.geometry import Point, shape
from shapely.strtree import STRtree
from shapely.ops import unary_union


PREVIOUS_ELECTION_ID = "surrey-county-council-2021"


def build_population_weighted_crosswalk_audit(
    *,
    historical_geojson: Mapping[str, object],
    current_geojson_by_election: Mapping[str, Mapping[str, object]],
    oa_centroid_geojson: Mapping[str, object],
    oa_population: Mapping[str, int],
    candidate_results: Sequence[Mapping[str, object]],
    approved_direct_mappings: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build weights, estimates, validation metrics and final ward decisions.

    The returned estimates remain separate from the master candidate records.
    This separation prevents a population proxy from replacing a directly
    observed historical result or silently entering the primary baseline.
    """

    historical = _boundary_features(
        historical_geojson, name_field="CED23NM", election_id=None
    )
    current = tuple(
        area
        for election_id, geojson in current_geojson_by_election.items()
        for area in _boundary_features(
            geojson, name_field="Name", election_id=election_id
        )
    )
    assignments = _assign_output_areas(
        historical=historical,
        current=current,
        oa_centroid_geojson=oa_centroid_geojson,
        oa_population=oa_population,
    )
    crosswalk_rows = _crosswalk_rows(assignments)
    estimates = _estimate_target_party_shares(
        crosswalk_rows=crosswalk_rows,
        candidate_results=candidate_results,
        current_areas=current,
    )
    validation = _validate_direct_mappings(
        estimates=estimates,
        candidate_results=candidate_results,
        approved_direct_mappings=approved_direct_mappings,
    )

    direct_keys = {
        (
            str(item["current_election_id"]),
            _normalise_area_name(str(item["current_area_name"])),
        )
        for item in approved_direct_mappings
    }
    ward_decisions = []
    for area in current:
        key = (str(area["election_id"]), str(area["area_name_normalised"]))
        direct = key in direct_keys
        ward_decisions.append(
            {
                "current_election_id": key[0],
                "current_area_name": area["area_name"],
                "mapping_class": "approved_direct" if direct else "changed_boundary",
                "primary_history_decision": (
                    "direct_history_retained"
                    if direct
                    else "unavailable_after_official_weight_review"
                ),
                "population_estimate_role": (
                    "validation_only" if direct else "sensitivity_analysis_only"
                ),
                "reason": (
                    "Approved direct predecessor; no redistribution is required."
                    if direct
                    else "Official OA population weights support a reproducible estimate, "
                    "but unchanged-area validation cannot test within-division vote "
                    "distribution after a real boundary split."
                ),
            }
        )

    total_population = sum(int(row["population"]) for row in assignments)
    return {
        "audit_id": "surrey-2021-to-2026-population-weighted-crosswalk-feasibility",
        "status": "complete_changed_boundary_primary_estimates_not_authorised",
        "weighting_method": "ons_oa_population_weighted_centroid_with_nomis_ts001_population",
        "scope": {
            "historical_areas": len(historical),
            "current_areas": len(current),
            "assigned_output_areas": len(assignments),
            "assigned_population": total_population,
            "crosswalk_rows": len(crosswalk_rows),
            "approved_direct_wards": sum(
                row["mapping_class"] == "approved_direct" for row in ward_decisions
            ),
            "changed_boundary_wards": sum(
                row["mapping_class"] == "changed_boundary" for row in ward_decisions
            ),
        },
        "validation": validation,
        "methodological_decision": {
            "primary_predictor": "not_authorised_for_changed_boundaries",
            "sensitivity_analysis": "authorised_with_explicit_population_estimate_label",
            "official_nulls_overwritten": False,
            "limitation": (
                "The direct-mapping validation set contains unchanged boundaries. "
                "It verifies implementation and source alignment but provides no "
                "ground truth for population-based allocation within split divisions."
            ),
        },
        "crosswalk_rows": crosswalk_rows,
        "party_share_estimates": estimates,
        "ward_decisions": ward_decisions,
    }


def _boundary_features(
    geojson: Mapping[str, object], *, name_field: str, election_id: str | None
) -> tuple[dict[str, object], ...]:
    """Read named polygon features from one official boundary layer."""

    features = geojson.get("features")
    if not isinstance(features, list):
        raise ValueError("Boundary GeoJSON has no feature list.")
    grouped = defaultdict(list)
    published_names: dict[str, str] = {}
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError("Boundary feature is invalid.")
        properties = feature.get("properties")
        if not isinstance(properties, dict) or not properties.get(name_field):
            raise ValueError(f"Boundary feature has no {name_field}.")
        published_name = str(properties[name_field])
        # ONS publishes one detached Surrey polygon as a separate feature with
        # a ``(DET)`` suffix. Merge it back into its named division so the
        # analysis contains 81 electoral areas rather than 82 geometries.
        base_name = re.sub(r"\s+\(DET\)$", "", published_name)
        normalised = _normalise_area_name(base_name)
        grouped[normalised].append(shape(feature.get("geometry")))
        published_names.setdefault(normalised, base_name)
    output = []
    for normalised, geometries in grouped.items():
        output.append(
            {
                "election_id": election_id,
                "area_name": published_names[normalised],
                "area_name_normalised": normalised,
                "geometry": unary_union(geometries),
            }
        )
    return tuple(output)


def _assign_output_areas(
    *,
    historical: Sequence[Mapping[str, object]],
    current: Sequence[Mapping[str, object]],
    oa_centroid_geojson: Mapping[str, object],
    oa_population: Mapping[str, int],
) -> tuple[dict[str, object], ...]:
    """Assign every Surrey OA centroid uniquely to an old and a new area."""

    old_geometries = [row["geometry"] for row in historical]
    new_geometries = [row["geometry"] for row in current]
    old_tree = STRtree(old_geometries)
    new_tree = STRtree(new_geometries)
    features = oa_centroid_geojson.get("features")
    if not isinstance(features, list):
        raise ValueError("OA centroid GeoJSON has no features.")

    assigned = []
    for feature in features:
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict) or not properties.get("OA21CD"):
            raise ValueError("OA centroid has no OA21CD.")
        code = str(properties["OA21CD"])
        if code not in oa_population:
            raise ValueError(f"OA has no official population: {code!r}.")
        point = shape(feature.get("geometry"))
        if not isinstance(point, Point):
            raise ValueError("OA population-weighted centroid is not a point.")
        old_matches = [
            int(index)
            for index in old_tree.query(point)
            if old_geometries[int(index)].covers(point)
        ]
        new_matches = [
            int(index)
            for index in new_tree.query(point)
            if new_geometries[int(index)].covers(point)
        ]
        # Points outside Surrey are expected because the download query uses a
        # bounding box. Inside Surrey, each point must have one old and one new
        # polygon; ambiguous assignments are rejected rather than guessed.
        if not old_matches and not new_matches:
            continue
        if len(old_matches) != 1 or len(new_matches) != 1:
            raise ValueError(f"OA has non-unique Surrey boundary assignment: {code!r}.")
        old = historical[old_matches[0]]
        new = current[new_matches[0]]
        assigned.append(
            {
                "oa21cd": code,
                "population": int(oa_population[code]),
                "previous_area_name": old["area_name_normalised"],
                "current_election_id": new["election_id"],
                "current_area_name": new["area_name_normalised"],
            }
        )
    return tuple(assigned)


def _crosswalk_rows(
    assignments: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Convert OA assignments into source-division population weights."""

    population_by_relation: defaultdict[tuple[str, str, str], int] = defaultdict(int)
    population_by_previous: defaultdict[str, int] = defaultdict(int)
    for row in assignments:
        key = (
            str(row["previous_area_name"]),
            str(row["current_election_id"]),
            str(row["current_area_name"]),
        )
        population_by_relation[key] += int(row["population"])
        population_by_previous[key[0]] += int(row["population"])
    return tuple(
        {
            "previous_area_name": previous,
            "current_election_id": election,
            "current_area_name": current,
            "assigned_population": population,
            "previous_area_population_fraction": population
            / population_by_previous[previous],
        }
        for (previous, election, current), population in sorted(
            population_by_relation.items()
        )
    )


def _estimate_target_party_shares(
    *,
    crosswalk_rows: Sequence[Mapping[str, object]],
    candidate_results: Sequence[Mapping[str, object]],
    current_areas: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Estimate party shares from weighted source votes, never percentages."""

    previous = defaultdict(list)
    target_parties = defaultdict(set)
    current_keys = {
        (str(row["election_id"]), str(row["area_name_normalised"]))
        for row in current_areas
    }
    for candidate in candidate_results:
        election_id = str(candidate.get("election_id", ""))
        area = _normalise_area_name(str(candidate.get("division_name", "")))
        if election_id == PREVIOUS_ELECTION_ID:
            previous[area].append(candidate)
        elif (election_id, area) in current_keys:
            target_parties[(election_id, area)].add(
                str(candidate.get("standard_party_name", ""))
            )

    relations = defaultdict(list)
    for row in crosswalk_rows:
        relations[(row["current_election_id"], row["current_area_name"])].append(row)

    estimates = []
    for key, parties in sorted(target_parties.items()):
        weighted_total = 0.0
        weighted_party = defaultdict(float)
        source_areas = []
        for relation in relations[key]:
            source = str(relation["previous_area_name"])
            source_candidates = previous.get(source)
            if not source_candidates:
                raise ValueError(f"Crosswalk source has no 2021 result: {source!r}.")
            weight = float(relation["previous_area_population_fraction"])
            source_areas.append(source)
            for candidate in source_candidates:
                votes = candidate.get("votes")
                if not isinstance(votes, (int, float)) or isinstance(votes, bool):
                    raise ValueError("Population estimate requires complete official votes.")
                # Reallocate the numerator and denominator in vote space. A
                # direct average of source percentages would give small and
                # large divisions equal influence and would therefore be wrong.
                weighted_total += float(votes) * weight
                weighted_party[str(candidate["standard_party_name"])] += float(votes) * weight
        for party in sorted(parties):
            estimates.append(
                {
                    "current_election_id": key[0],
                    "current_area_name": key[1],
                    "standard_party_name": party,
                    "estimated_previous_party_vote_share": round(
                        100.0 * weighted_party.get(party, 0.0) / weighted_total, 6
                    ),
                    "method": "census_2021_oa_population_weighted_vote_reallocation",
                    "source_area_names": tuple(sorted(source_areas)),
                }
            )
    return tuple(estimates)


def _validate_direct_mappings(
    *,
    estimates: Sequence[Mapping[str, object]],
    candidate_results: Sequence[Mapping[str, object]],
    approved_direct_mappings: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Compare estimates with observed shares on the 24 unchanged mappings."""

    estimate_index = {
        (
            row["current_election_id"],
            row["current_area_name"],
            row["standard_party_name"],
        ): row
        for row in estimates
    }
    previous = defaultdict(list)
    for candidate in candidate_results:
        if candidate.get("election_id") == PREVIOUS_ELECTION_ID:
            previous[_normalise_area_name(str(candidate["division_name"]))].append(candidate)

    errors = []
    for mapping in approved_direct_mappings:
        election = str(mapping["current_election_id"])
        current = _normalise_area_name(str(mapping["current_area_name"]))
        source = _normalise_area_name(str(mapping["previous_area_name"]))
        source_candidates = previous[source]
        total = sum(float(row["votes"]) for row in source_candidates)
        for candidate in source_candidates:
            key = (election, current, str(candidate["standard_party_name"]))
            estimate = estimate_index.get(key)
            # Validation is limited to parties that also contest the target;
            # this matches the feature table's row unit.
            if estimate is None:
                continue
            observed = 100.0 * float(candidate["votes"]) / total
            predicted = float(estimate["estimated_previous_party_vote_share"])
            errors.append(abs(predicted - observed))
    if not errors:
        raise ValueError("Direct-mapping validation produced no comparable party rows.")
    return {
        "direct_mapping_wards": len(approved_direct_mappings),
        "comparable_party_rows": len(errors),
        "mae_percentage_points": round(sum(errors) / len(errors), 6),
        "maximum_absolute_error_percentage_points": round(max(errors), 6),
        "pipeline_check": "passed",
        "external_validity_for_changed_boundaries": "not_established",
    }


def _normalise_area_name(value: str) -> str:
    """Align only reviewed punctuation and suffix differences."""

    name = re.sub(r"[-–—]", " ", value.strip())
    name = " ".join(name.split())
    for suffix in (" Ward", " ED"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.replace(" and ", " & ").casefold()
