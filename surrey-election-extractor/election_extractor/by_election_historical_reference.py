"""Audit by-election eligibility for a prior exact-label party-share baseline."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import urlsplit

from election_extractor.by_election_results import load_by_election_catalogue
from election_extractor.election_history import build_election_history


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIGURATION_PATH = PROJECT_ROOT / "config/by_election_historical_reference_permissions.json"
APPROVED = "approved_same_statutory_division"


def build_by_election_historical_reference_audit(
    path: str | Path = DEFAULT_CONFIGURATION_PATH,
    history: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate all by-election decisions and materialise only approved links.

    The configuration records a decision for every catalogued by-election.  An
    approved decision is rechecked against the official candidate rows, so a
    later source change cannot silently turn a multi-member or duplicate-label
    contest into a usable party-share baseline.
    """

    config = json.loads(Path(path).read_text(encoding="utf-8"))
    decisions = config.get("decisions")
    # One decision per catalogued by-election. The count is read from the
    # catalogue rather than written here as a literal: the guard's purpose is
    # that no catalogued event goes undecided, and a hard-coded number
    # enforces that only until the next event is added, at which point it
    # blocks the addition instead of checking it.
    catalogued = len(load_by_election_catalogue())
    if not isinstance(decisions, list) or len(decisions) != catalogued:
        raise ValueError(
            "By-election historical audit requires exactly one decision per "
            f"catalogued by-election ({catalogued}); found "
            f"{len(decisions) if isinstance(decisions, list) else 'none'}."
        )
    raw_history = history if history is not None else build_election_history()
    raw_rows = raw_history.get("canonical_candidate_results")
    if not isinstance(raw_rows, list):
        raise ValueError("Election history has no canonical candidate rows.")
    rows_by_event_area: defaultdict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    by_election_ids: set[str] = set()
    for row in raw_rows:
        if not isinstance(row, Mapping):
            raise ValueError("Canonical candidate rows must be objects.")
        event_id, area = row.get("election_id"), row.get("area_name")
        if not isinstance(event_id, str) or not isinstance(area, str):
            raise ValueError("Candidate rows require election ID and area name.")
        rows_by_event_area[(event_id, area)].append(dict(row))
        if "by-election" in event_id:
            by_election_ids.add(event_id)

    seen: set[str] = set()
    division_references, party_references, audit_rows = [], [], []
    for decision in decisions:
        event_id = decision.get("election_id")
        status = decision.get("decision")
        if not isinstance(event_id, str) or not isinstance(status, str) or event_id in seen:
            raise ValueError("By-election decisions require unique election_id and decision.")
        seen.add(event_id)
        target_matches = [(key, rows) for key, rows in rows_by_event_area.items() if key[0] == event_id]
        if len(target_matches) != 1:
            raise ValueError(f"By-election decision has no unique target area: {event_id}.")
        (_, target_name), target_rows = target_matches[0]
        audit_row = {"election_id": event_id, "division_name": target_name, **decision}
        if status != APPROVED:
            audit_rows.append(audit_row)
            continue
        previous_id, previous_name = decision.get("previous_election_id"), decision.get("previous_division_name")
        if not isinstance(previous_id, str) or not isinstance(previous_name, str):
            raise ValueError("Approved by-election decision requires prior event and exact division.")
        previous_rows = rows_by_event_area.get((previous_id, previous_name))
        if previous_rows is None:
            raise ValueError(f"Approved by-election predecessor is unavailable: {event_id}.")
        _validate_single_member_exact_label_rows(
            target_rows,
            previous_rows,
            event_id,
            single_member_evidence_url=decision.get("single_member_evidence_url"),
        )
        previous_labels: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
        for row in previous_rows:
            previous_labels[str(row["original_party_name"])].append(row)
        prior_source = _shared(previous_rows, "source_url")
        winner = [row for row in previous_rows if row.get("elected_status") == "Elected"]
        division_references.append({
            "current_election_id": event_id, "current_area_name": target_name,
            "historical_reference_status": APPROVED,
            "previous_election_event_id": previous_id, "previous_election_date": _shared(previous_rows, "election_date"),
            "previous_area_name": previous_name,
            "previous_winning_candidate_name": winner[0].get("candidate_name") if len(winner) == 1 else None,
            "previous_winning_party": winner[0].get("original_party_name") if len(winner) == 1 else None,
            "previous_winning_candidate_vote_share": winner[0].get("vote_share") if len(winner) == 1 else None,
            "previous_turnout": _shared(previous_rows, "turnout"), "previous_electorate": _shared(previous_rows, "electorate"),
            "source_result_url": prior_source, "geographic_mapping_id": f"{event_id}:prior:{previous_id}:{previous_name}",
            "permission_evidence": str(decision["reason"]),
            "permission_source_urls": tuple(
                dict.fromkeys(
                    [str(prior_source)]
                    + ([str(decision["continuity_evidence_url"])] if decision.get("continuity_evidence_url") else [])
                    + ([str(decision["single_member_evidence_url"])] if decision.get("single_member_evidence_url") else [])
                )
            ),
        })
        for row in target_rows:
            label = str(row["original_party_name"])
            prior_matches = previous_labels[label]
            prior_share = None
            status = "not_derived_prior_exact_label_not_unique"
            if len(prior_matches) <= 1:
                prior_share = prior_matches[0].get("vote_share") if prior_matches else 0.0
                status = (
                    "derived_single_member_exact_label_prior_candidate_share"
                    if prior_share is not None
                    else "not_derived_matching_prior_share_missing"
                )
            party_references.append({
                "current_election_id": event_id, "current_area_name": target_name,
                "original_party_name": label, "provenance": "deterministically_derived",
                "party_previously_contested": bool(prior_matches),
                "first_observed_appearance": not prior_matches,
                "previous_party_vote_share": prior_share,
                "previous_party_vote_share_status": status,
            })
        audit_rows.append(audit_row)
    if seen != by_election_ids:
        raise ValueError(f"By-election audit coverage mismatch: missing={sorted(by_election_ids-seen)!r}.")
    return {"audit_rows": tuple(audit_rows), "division_references": tuple(division_references), "party_history_references": tuple(party_references), "summary": dict(sorted(Counter(str(row['decision']) for row in audit_rows).items()))}


def _validate_single_member_exact_label_rows(
    target: Sequence[Mapping[str, object]],
    previous: Sequence[Mapping[str, object]],
    event_id: str,
    *,
    single_member_evidence_url: object = None,
) -> None:
    """Check contest structure while allowing a cited statutory seat source.

    A missing Seats cell on an official result page is an extraction/source
    limitation, not evidence that the division was multi-member.  A configured
    HTTPS statutory source may therefore establish the prior contest structure;
    it never fills or overwrites the official Seats field.
    """

    prior_single_member = {row.get("seats") for row in previous} == {1}
    if not prior_single_member and isinstance(single_member_evidence_url, str):
        parsed = urlsplit(single_member_evidence_url)
        # The only configured substitute for a missing source-page Seats cell
        # is the statutory instrument that created the pre-2024 divisions and
        # specified one councillor for each. An arbitrary HTTPS page cannot
        # satisfy this structural gate.
        prior_single_member = (
            parsed.scheme == "https"
            and parsed.netloc == "www.legislation.gov.uk"
            and parsed.path.startswith("/uksi/2012/1872/")
        )
    if {row.get("seats") for row in target} != {1} or not prior_single_member:
        raise ValueError(f"Approved by-election is not evidenced as single-member: {event_id}.")
    for rows in (target, previous):
        labels = [row.get("original_party_name") for row in rows]
        if any(not isinstance(label, str) or not label.strip() for label in labels):
            raise ValueError(f"Approved by-election has a blank party label: {event_id}.")
    target_labels = [str(row["original_party_name"]) for row in target]
    if len(target_labels) != len(set(target_labels)):
        raise ValueError(f"Approved by-election has duplicate current party labels: {event_id}.")
    if any(row.get("vote_share") is None for row in previous):
        raise ValueError(f"Approved by-election prior shares are incomplete: {event_id}.")


def _shared(rows: Sequence[Mapping[str, object]], field: str) -> object | None:
    values = {row.get(field) for row in rows if row.get(field) is not None}
    return next(iter(values)) if len(values) == 1 else None
