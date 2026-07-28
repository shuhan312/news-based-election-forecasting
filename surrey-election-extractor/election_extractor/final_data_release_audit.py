"""Create a release-readiness audit for the source-preserving master database.

This module is intentionally a *reporting* layer.  It does not perform
discovery, download pages, alter extracted values, or turn an official NULL
into a value from supplementary or derived evidence.  Its purpose is to make
the final remaining gaps, materialised supervisor fields, and source-to-row
reconciliation checks explicit before the election database is used further.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from election_extractor.master_database import MasterDatabasePayload


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_INDEX_PATH = PROJECT_ROOT / "config/final_missing_field_evidence_index.json"

# Supplementary and derived registers use evidence-layer field names.  These
# mappings identify which official division field they can support while still
# leaving that official field untouched in the master table.
SUPPLEMENTARY_TARGET_FIELDS = {
    "secondary_division_ballot_papers_issued": "ballot_papers_issued",
    "secondary_division_turnout": "turnout",
    "secondary_number_of_seats": "official_number_of_seats",
}


def load_missing_field_evidence_index(
    path: str | Path = DEFAULT_EVIDENCE_INDEX_PATH,
) -> tuple[dict[str, object], ...]:
    """Load a small reviewed index for values still unresolved after all layers.

    The index is deliberately limited to residual gaps.  It records sources
    already reviewed and a conservative decision, but does not make the
    stronger and unsupported claim that no historical document can exist.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = payload.get("entries") if isinstance(payload, Mapping) else None
    if not isinstance(entries, list):
        raise ValueError("Final missing-field evidence index requires an entries list.")
    required = {
        "election_id",
        "division_name",
        "field_name",
        "record_count",
        "official_source_url",
        "reviewed_source_urls",
        "reviewed_documentation",
        "decision",
    }
    reviewed: list[dict[str, object]] = []
    keys: set[tuple[str, str, str]] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or required - set(entry):
            raise ValueError("Every final missing-field entry requires complete provenance.")
        key = (str(entry["election_id"]), str(entry["division_name"]), str(entry["field_name"]))
        if key in keys:
            raise ValueError(f"Duplicate final missing-field entry: {key!r}.")
        keys.add(key)
        if not isinstance(entry["record_count"], int) or entry["record_count"] < 1:
            raise ValueError("Final missing-field record_count must be a positive integer.")
        urls = entry["reviewed_source_urls"]
        if not isinstance(urls, list) or not urls or not all(isinstance(url, str) and url.startswith("https://") for url in urls):
            raise ValueError("Final missing-field entries require reviewed HTTPS source URLs.")
        reviewed.append(dict(entry))
    return tuple(sorted(reviewed, key=lambda item: (str(item["election_id"]), str(item["field_name"]))))


def _supporting_records_by_target(
    payload: MasterDatabasePayload,
) -> dict[tuple[str, str], list[Mapping[str, object]]]:
    """Index accepted separate evidence by division and target official field."""

    support: defaultdict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for record in payload.supplementary_metadata:
        target = SUPPLEMENTARY_TARGET_FIELDS.get(str(record.get("field_name")))
        division_id = record.get("division_id")
        if target and isinstance(division_id, str):
            support[(division_id, target)].append(record)
    for record in payload.derived_metadata:
        target = record.get("target_official_field")
        division_id = record.get("division_id")
        if isinstance(target, str) and isinstance(division_id, str):
            support[(division_id, target)].append(record)
    return dict(support)


def _residual_division_gaps(
    payload: MasterDatabasePayload,
    support: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
) -> tuple[dict[str, object], ...]:
    """Return only division values without official or accepted separate evidence."""

    fields = ("electorate", "ballot_papers_issued", "rejected_ballots", "turnout")
    gaps: list[dict[str, object]] = []
    for row in payload.divisions_and_wards:
        division_id = str(row["division_id"])
        for field_name in fields:
            if row.get(field_name) is not None or support.get((division_id, field_name)):
                continue
            gaps.append(
                {
                    "election_id": row["election_id"],
                    "division_name": row["division_name"],
                    "field_name": field_name,
                    "record_count": 1,
                    "official_source_url": row["official_source_url"],
                }
            )
    return tuple(sorted(gaps, key=lambda item: (str(item["election_id"]), str(item["division_name"]), str(item["field_name"]))))


def _residual_candidate_gaps(payload: MasterDatabasePayload) -> tuple[dict[str, object], ...]:
    """Group unresolved candidate shares without treating all final positions as errors.

    Official final position is recorded separately as a publication limitation:
    no audited format exposes a rank column.  It is not included in this
    remediation list because searching the same pages again cannot produce a
    field they do not publish.
    """

    grouped: defaultdict[tuple[str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in payload.candidate_results:
        if row.get("vote_share") is None:
            key = (
                str(row["election_id"]),
                str(row["division_name"]),
                "vote_share",
                str(row["source_url"]),
            )
            grouped[key].append(row)
    return tuple(
        {
            "election_id": election_id,
            "division_name": division_name,
            "field_name": field_name,
            "record_count": len(rows),
            "candidate_names": tuple(str(row["candidate_name"]) for row in rows),
            "official_source_url": source_url,
        }
        for (election_id, division_name, field_name, source_url), rows in sorted(grouped.items())
    )


def _validate_evidence_index(
    gaps: Sequence[Mapping[str, object]],
    evidence_index: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Join each residual field to its reviewed-source boundary and reject drift."""

    indexed = {
        (str(item["election_id"]), str(item["division_name"]), str(item["field_name"])): item
        for item in evidence_index
    }
    gap_keys = {
        (str(item["election_id"]), str(item["division_name"]), str(item["field_name"]))
        for item in gaps
    }
    if set(indexed) != gap_keys:
        raise ValueError(
            "Final missing-field evidence index does not exactly match residual gaps: "
            f"index_only={sorted(set(indexed) - gap_keys)!r}; "
            f"gap_only={sorted(gap_keys - set(indexed))!r}."
        )
    checked: list[dict[str, object]] = []
    for gap in gaps:
        key = (str(gap["election_id"]), str(gap["division_name"]), str(gap["field_name"]))
        evidence = indexed[key]
        if gap["official_source_url"] != evidence["official_source_url"]:
            raise ValueError(f"Final evidence index has a different official URL for {key!r}.")
        if gap["record_count"] != evidence["record_count"]:
            raise ValueError(f"Final evidence index has a different missing-record count for {key!r}.")
        checked.append({**gap, **{name: evidence[name] for name in ("reviewed_source_urls", "reviewed_documentation", "decision")}})
    return tuple(checked)


def _source_reconciliation_samples(payload: MasterDatabasePayload) -> tuple[dict[str, object], ...]:
    """Prepare one deterministic official-source review target for every event.

    This is a reproducible audit pack, not a claim that a browser has re-read
    every live page.  The sample checks that the source-backed master rows
    agree with their audited source record and gives a reviewer the exact URL
    and values to compare visually without selecting candidates by vote rank.
    """

    candidates_by_source: defaultdict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    divisions_by_source: dict[tuple[str, str], Mapping[str, object]] = {}
    for candidate in payload.candidate_results:
        key = (str(candidate["election_id"]), str(candidate["source_url"]))
        candidates_by_source[key].append(candidate)
    for division in payload.divisions_and_wards:
        key = (str(division["election_id"]), str(division["official_source_url"]))
        divisions_by_source[key] = division

    samples: list[dict[str, object]] = []
    event_ids = sorted({str(row["election_id"]) for row in payload.elections})
    for election_id in event_ids:
        choices = sorted(
            (key for key in candidates_by_source if key[0] == election_id),
            key=lambda key: (str(divisions_by_source[key]["division_name"]).casefold(), key[1]),
        )
        if not choices:
            raise ValueError(f"No candidate source is available for {election_id}.")
        key = choices[0]
        division = divisions_by_source[key]
        candidates = candidates_by_source[key]
        elected = [row for row in candidates if row.get("elected_yes_no") == "Yes"]
        # Prefer an explicit official winner for the human review line. This is
        # not a winner inference: if none exists, a stable name sort is used.
        sample_candidate = elected[0] if elected else sorted(candidates, key=lambda row: str(row["candidate_name"]).casefold())[0]
        candidate_fields_present = all(
            sample_candidate.get(field) is not None
            for field in ("candidate_name", "votes", "outcome", "source_url")
        )
        samples.append(
            {
                "election_id": election_id,
                "division_name": division["division_name"],
                "source_url": key[1],
                "sample_candidate_name": sample_candidate["candidate_name"],
                "sample_candidate_party": sample_candidate["original_party_name"],
                "sample_candidate_votes": sample_candidate["votes"],
                "sample_candidate_outcome": sample_candidate["outcome"],
                "official_seats": division["official_number_of_seats"],
                "official_total_votes": division["total_votes"],
                "official_electorate": division["electorate"],
                "official_issued_ballots": division["ballot_papers_issued"],
                "official_rejected_ballots": division["rejected_ballots"],
                "official_turnout": division["turnout"],
                "candidate_fields_reconciled": candidate_fields_present,
                "source_url_reconciled": sample_candidate["source_url"] == division["official_source_url"],
                "review_status": "prepared_for_visual_official_source_check",
            }
        )
    return tuple(samples)


def build_final_data_release_audit(
    payload: MasterDatabasePayload,
    *,
    evidence_index: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build a non-mutating release audit from the current master payload."""

    support = _supporting_records_by_target(payload)
    gaps = (*_residual_division_gaps(payload, support), *_residual_candidate_gaps(payload))
    unresolved = _validate_evidence_index(gaps, evidence_index)
    samples = _source_reconciliation_samples(payload)

    candidate_headers = set(payload.candidate_results[0]) if payload.candidate_results else set()
    division_headers = set(payload.divisions_and_wards[0]) if payload.divisions_and_wards else set()
    required_materialised = {
        "candidate_results": {
            "notes",
            "source_url",
            "elected_yes_no",
            "change_in_vote_share",
            "change_in_vote_share_provenance",
            "change_in_vote_share_model_role",
            "candidate_previously_stood",
            "candidate_history_status",
            "candidate_history_source_urls",
            "candidate_history_event_ids",
            "incumbent_candidate_yes_no",
            "incumbent_candidate_yes_no_source_urls",
            "incumbent_party_yes_no",
            "incumbent_party_name",
        },
        "divisions_and_wards": {
            "winning_candidate_name",
            "winning_party_name",
            "official_elected_candidate_names",
            "winning_margin",
            "winning_margin_status",
        },
    }
    missing_materialised = {
        table: sorted(required - headers)
        for table, required, headers in (
            ("candidate_results", required_materialised["candidate_results"], candidate_headers),
            ("divisions_and_wards", required_materialised["divisions_and_wards"], division_headers),
        )
    }
    if any(missing_materialised.values()):
        raise ValueError(f"Required supervisor fields are not materialised: {missing_materialised!r}.")

    return {
        "audit_title": "Surrey Final Election Data Release Audit",
        # The event count is interpolated rather than written as a literal.
        # It was "20-event" while the counts immediately below were already
        # computed, so adding an election left the scope sentence contradicting
        # the table in the same document.
        "audit_scope": (
            f"Read-only audit of the {len(payload.elections)}-event master "
            "payload; no extraction or source values are changed."
        ),
        "dataset_counts": {
            "election_events": len(payload.elections),
            "candidate_rows": len(payload.candidate_results),
            "division_or_ward_rows": len(payload.divisions_and_wards),
        },
        "materialised_supervisor_fields": {
            "candidate_notes": sum(row.get("notes") is not None for row in payload.candidate_results),
            "candidate_source_urls": sum(row.get("source_url") is not None for row in payload.candidate_results),
            "single_official_winners": sum(row.get("winning_candidate_name") is not None for row in payload.divisions_and_wards),
            "multi_member_elected_name_lists": sum(
                row.get("official_elected_candidate_count", 0) > 1
                and row.get("official_elected_candidate_names") is not None
                for row in payload.divisions_and_wards
            ),
            "separate_derived_winning_margins": sum(
                row.get("field_name") == "derived_winning_margin"
                for row in payload.derived_metadata
            ),
            "candidate_change_in_vote_share_diagnostics": sum(
                row.get("change_in_vote_share") is not None
                for row in payload.candidate_results
            ),
            "candidate_previously_stood_yes": sum(
                row.get("candidate_previously_stood") is True
                for row in payload.candidate_results
            ),
            "candidate_previously_stood_no": sum(
                row.get("candidate_previously_stood") is False
                for row in payload.candidate_results
            ),
            "candidate_previously_stood_unknown": sum(
                row.get("candidate_previously_stood") is None
                for row in payload.candidate_results
            ),
            "verified_incumbent_candidate_yes": sum(
                row.get("incumbent_candidate_yes_no") == "Yes"
                for row in payload.candidate_results
            ),
            "verified_incumbent_candidate_no": sum(
                row.get("incumbent_candidate_yes_no") == "No"
                for row in payload.candidate_results
            ),
            "unresolved_incumbent_candidate_unknown": sum(
                row.get("incumbent_candidate_yes_no") == "Unknown"
                for row in payload.candidate_results
            ),
            "incumbent_candidate_yes_from_consecutive_official_results": sum(
                row.get("incumbent_candidate_yes_no_status")
                == "verified_consecutive_official_results_approved_area_continuity"
                for row in payload.candidate_results
            ),
            "decidable_incumbent_party_yes_no": sum(
                row.get("incumbent_party_yes_no") in {"Yes", "No"}
                for row in payload.candidate_results
            ),
            "missing_columns": missing_materialised,
        },
        "residual_missing_after_all_permitted_layers": list(unresolved),
        "residual_missing_counts": dict(sorted(Counter(str(item["field_name"]) for item in unresolved).items())),
        "officially_unavailable_or_prohibited": {
            "final_position_candidate_rows": sum(row.get("final_position") is None for row in payload.candidate_results),
            "previous_party_vote_share_not_materialised": sum(row.get("previous_party_vote_share") is None for row in payload.divisions_and_wards),
            "change_in_vote_share_not_materialised": sum(row.get("change_in_vote_share") is None for row in payload.candidate_results),
            "reason": "Change is available only as a post-election diagnostic for approved exact-label single-member comparisons. Residual values are not reconstructed from name matching, party-share aggregation, multi-member candidate shares or altered geography.",
        },
        "source_to_database_reconciliation_samples": list(samples),
        "reconciliation_summary": {
            "event_samples": len(samples),
            "candidate_field_checks_passed": sum(item["candidate_fields_reconciled"] for item in samples),
            "source_url_checks_passed": sum(item["source_url_reconciled"] for item in samples),
            "scope_note": "Each row is a deterministic review target. A reviewer can visually compare the cited official source; this program does not claim to re-download or alter that source.",
        },
        "release_decision": "ready_with_visible_evidence_boundaries",
    }


def final_data_release_audit_markdown(report: Mapping[str, object]) -> str:
    """Render a concise, reviewable Markdown release report."""

    counts = report["dataset_counts"]
    materialised = report["materialised_supervisor_fields"]
    unresolved = report["residual_missing_after_all_permitted_layers"]
    reconciliation = report["reconciliation_summary"]
    assert isinstance(counts, Mapping) and isinstance(materialised, Mapping)
    assert isinstance(unresolved, list) and isinstance(reconciliation, Mapping)
    lines = [
        "# Surrey Final Election Data Release Audit",
        "",
        "## Scope",
        "",
        str(report["audit_scope"]),
        "",
        f"- Election events: {counts['election_events']}",
        f"- Candidate rows: {counts['candidate_rows']}",
        f"- Division or ward rows: {counts['division_or_ward_rows']}",
        "## Materialised supervisor fields",
        "",
        f"- Candidate source URLs: {materialised['candidate_source_urls']}",
        f"- Candidate Notes with a recorded source limitation: {materialised['candidate_notes']}",
        f"- Single official winner/party summaries: {materialised['single_official_winners']}",
        f"- Multi-member official elected-name lists: {materialised['multi_member_elected_name_lists']}",
        f"- Separate governed derived winning margins: {materialised['separate_derived_winning_margins']}",
        f"- Post-election change-in-vote-share diagnostics: {materialised['candidate_change_in_vote_share_diagnostics']}",
        "",
        "## Residual values after all permitted layers",
        "",
        "These values remain `NULL` in official fields. The register records reviewed sources and does not claim that an unindexed historical document cannot exist.",
        "",
        "| Election | Division or ward | Field | Rows | Official source | Reviewed-source decision |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for item in unresolved:
        assert isinstance(item, Mapping)
        lines.append(
            "| {election_id} | {division_name} | {field_name} | {record_count} | {official_source_url} | {decision} |".format(
                **item
            )
        )
    unavailable = report["officially_unavailable_or_prohibited"]
    assert isinstance(unavailable, Mapping)
    lines.extend(
        [
            "",
            "## Fields intentionally not reconstructed",
            "",
            f"- Final position: {unavailable['final_position_candidate_rows']} candidate rows remain NULL because audited source tables do not publish rank.",
            f"- Change in vote share: {unavailable['change_in_vote_share_not_materialised']} candidate rows remain NULL where no exact-label single-member comparison is permitted; available values are outcome diagnostics and excluded from the no-news baseline.",
            "- Candidate continuity and incumbency remain NULL without an exact reviewed authoritative link; names alone are never matched.",
            "",
            "## Source-to-database review pack",
            "",
            f"- Deterministic event samples prepared: {reconciliation['event_samples']}",
            f"- Candidate-field reconciliation checks passed: {reconciliation['candidate_field_checks_passed']}",
            f"- Source-URL reconciliation checks passed: {reconciliation['source_url_checks_passed']}",
            f"- Scope: {reconciliation['scope_note']}",
            "",
            "## Release decision",
            "",
            "The database is ready as an auditable election-results baseline with visible evidence boundaries. It must not be described as proof that unindexed historical documents do not exist.",
            "",
        ]
    )
    return "\n".join(lines)
