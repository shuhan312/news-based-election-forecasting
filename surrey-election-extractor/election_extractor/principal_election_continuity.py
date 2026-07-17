"""Build a separate legal-continuity audit for pre-2024 principal elections.

The 2013, 2017 and 2021 Surrey County Council elections used the statutory
arrangements made in 2012.  This additive layer uses that legal continuity only
where an exact published division name occurs once in each configured adjacent
principal election.  It is deliberately separate from the 2021-to-2026 GIS
crosswalk, which has different boundary evidence and stricter area-by-area
permission requirements.

No candidate name is used as an identity key.  Party totals, swing, incumbency,
candidate history and vote-ranking margin calculations remain unavailable.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from election_extractor.election_history import build_election_history


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTINUITY_CONFIGURATION_PATH = (
    PROJECT_ROOT / "config/principal_election_continuity_permissions.json"
)
APPROVED_STATUS = "approved_pre_2024_legal_continuity"
UNAVAILABLE_STATUS = "not_approved_or_not_applicable"


@dataclass(frozen=True)
class OfficialContinuitySource:
    """One public legal or official source used by the continuity policy."""

    source_id: str
    source_type: str
    source_url: str
    evidence_text: str
    scope: str


@dataclass(frozen=True)
class PrincipalElectionContinuityPolicy:
    """Keep approved transitions and feature boundaries in reviewable data."""

    framework_id: str
    purpose: str
    required_source_ids: tuple[str, ...]
    matching_rule: str
    permitted_features: tuple[str, ...]
    prohibited_features: tuple[str, ...]
    limitation: str


@dataclass(frozen=True)
class PrincipalElectionTransition:
    """Describe one adjacent principal-election transition with no name guessing."""

    transition_id: str
    previous_election_id: str
    current_election_id: str
    expected_exact_area_count: int


def _required_text(value: object, field_name: str) -> str:
    """Require explicit configuration text instead of silently using a default."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Principal-election continuity requires non-empty {field_name}.")
    return value.strip()


def _https_url(value: object, field_name: str) -> str:
    """Allow only citable public HTTPS source locations in the audit."""

    url = _required_text(value, field_name)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"Principal-election continuity requires HTTPS {field_name}.")
    return url


def _required_positive_int(value: object, field_name: str) -> int:
    """Reject an unspecified expected count rather than weakening the check."""

    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Principal-election continuity requires positive {field_name}.")
    return value


def _source_registry(raw_sources: object) -> dict[str, OfficialContinuitySource]:
    """Load citable sources and reject duplicate or opaque provenance."""

    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("Principal-election continuity requires source_registry.")
    sources: dict[str, OfficialContinuitySource] = {}
    for raw_source in raw_sources:
        if not isinstance(raw_source, Mapping):
            raise ValueError("Principal-election continuity sources must be objects.")
        source = OfficialContinuitySource(
            source_id=_required_text(raw_source.get("source_id"), "source_id"),
            source_type=_required_text(raw_source.get("source_type"), "source_type"),
            source_url=_https_url(raw_source.get("source_url"), "source_url"),
            evidence_text=_required_text(raw_source.get("evidence_text"), "evidence_text"),
            scope=_required_text(raw_source.get("scope"), "scope"),
        )
        if source.source_id in sources:
            raise ValueError(f"Duplicate principal-election continuity source: {source.source_id}.")
        sources[source.source_id] = source
    return sources


def load_principal_election_continuity_configuration(
    path: str | Path = DEFAULT_CONTINUITY_CONFIGURATION_PATH,
) -> tuple[
    PrincipalElectionContinuityPolicy,
    dict[str, OfficialContinuitySource],
    tuple[PrincipalElectionTransition, ...],
]:
    """Load explicit legal-continuity evidence without fetching any websites."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Principal-election continuity configuration must be an object.")
    sources = _source_registry(payload.get("source_registry"))
    raw_rule = payload.get("approval_rule")
    if not isinstance(raw_rule, Mapping):
        raise ValueError("Principal-election continuity requires approval_rule.")
    source_ids = raw_rule.get("required_sources")
    if not isinstance(source_ids, list) or not source_ids:
        raise ValueError("Principal-election continuity requires required_sources.")
    required_source_ids = tuple(
        _required_text(source_id, "required source ID") for source_id in source_ids
    )
    if len(set(required_source_ids)) != len(required_source_ids):
        raise ValueError("Principal-election continuity required source IDs must be unique.")
    unknown_sources = set(required_source_ids) - set(sources)
    if unknown_sources:
        raise ValueError(
            "Principal-election continuity references unknown sources: "
            f"{sorted(unknown_sources)}."
        )
    policy = PrincipalElectionContinuityPolicy(
        framework_id=_required_text(payload.get("framework_id"), "framework_id"),
        purpose=_required_text(payload.get("purpose"), "purpose"),
        required_source_ids=required_source_ids,
        matching_rule=_required_text(raw_rule.get("matching_rule"), "matching_rule"),
        permitted_features=tuple(
            _required_text(item, "permitted feature")
            for item in raw_rule.get("permitted_features", ())
        ),
        prohibited_features=tuple(
            _required_text(item, "prohibited feature")
            for item in raw_rule.get("prohibited_features", ())
        ),
        limitation=_required_text(raw_rule.get("limitation"), "limitation"),
    )
    if policy.matching_rule != "exact_published_area_name":
        raise ValueError("Principal-election continuity only permits exact_published_area_name.")
    if not policy.permitted_features or not policy.prohibited_features:
        raise ValueError("Principal-election continuity requires permitted and prohibited features.")

    raw_transitions = payload.get("approved_transitions")
    if not isinstance(raw_transitions, list) or not raw_transitions:
        raise ValueError("Principal-election continuity requires approved_transitions.")
    transitions = []
    identifiers: set[str] = set()
    targets: set[str] = set()
    for raw_transition in raw_transitions:
        if not isinstance(raw_transition, Mapping):
            raise ValueError("Principal-election continuity transitions must be objects.")
        transition = PrincipalElectionTransition(
            transition_id=_required_text(raw_transition.get("transition_id"), "transition_id"),
            previous_election_id=_required_text(
                raw_transition.get("previous_election_id"), "previous_election_id"
            ),
            current_election_id=_required_text(
                raw_transition.get("current_election_id"), "current_election_id"
            ),
            expected_exact_area_count=_required_positive_int(
                raw_transition.get("expected_exact_area_count"), "expected_exact_area_count"
            ),
        )
        if transition.transition_id in identifiers:
            raise ValueError(f"Duplicate principal-election transition: {transition.transition_id}.")
        if transition.current_election_id in targets:
            raise ValueError(
                "Principal-election continuity allows one approved predecessor per "
                f"current election: {transition.current_election_id}."
            )
        identifiers.add(transition.transition_id)
        targets.add(transition.current_election_id)
        transitions.append(transition)
    return policy, sources, tuple(transitions)


def _rows_by_event_and_area(
    history: Mapping[str, object],
) -> dict[tuple[str, str], tuple[dict[str, object], ...]]:
    """Index source rows by the exact published division name, never a fuzzy key."""

    candidates = history.get("canonical_candidate_results")
    if not isinstance(candidates, list):
        raise ValueError("Election history has no canonical candidate results.")
    rows: defaultdict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for raw_row in candidates:
        if not isinstance(raw_row, Mapping):
            raise ValueError("Canonical candidate rows must be objects.")
        election_id = _required_text(raw_row.get("election_id"), "candidate election_id")
        area_name = _required_text(raw_row.get("area_name"), "candidate area_name")
        rows[(election_id, area_name)].append(dict(raw_row))
    return {key: tuple(value) for key, value in rows.items()}


def _area_names_for_event(
    rows: Mapping[tuple[str, str], Sequence[Mapping[str, object]]], election_id: str
) -> set[str]:
    """Return exact published names only; no normalisation creates a mapping."""

    return {area_name for source_election_id, area_name in rows if source_election_id == election_id}


def _shared_value(rows: Sequence[Mapping[str, object]], field_name: str) -> object | None:
    """Copy one repeated official value or retain null if source rows disagree."""

    values = []
    for row in rows:
        value = row.get(field_name)
        if value is not None and value not in values:
            values.append(value)
    return values[0] if len(values) == 1 else None


def _source_reported_winner(rows: Sequence[Mapping[str, object]]) -> Mapping[str, object] | None:
    """Return one explicit Elected row without selecting a candidate by votes."""

    elected = [row for row in rows if str(row.get("elected_status")).casefold() == "elected"]
    return elected[0] if len(elected) == 1 else None


def _reference_for_exact_area(
    transition: PrincipalElectionTransition,
    area_name: str,
    previous_rows: Sequence[Mapping[str, object]],
    source_urls: tuple[str, ...],
    policy: PrincipalElectionContinuityPolicy,
) -> dict[str, object]:
    """Expose only source-reported prior data allowed by the legal-continuity rule."""

    winner = _source_reported_winner(previous_rows)
    source_url = _shared_value(previous_rows, "source_url")
    if not isinstance(source_url, str):
        raise ValueError(
            "A legal-continuity reference requires one official source URL for "
            f"{transition.previous_election_id} / {area_name}."
        )
    mapping_id = f"{transition.transition_id}:{area_name}"
    return {
        "historical_reference_status": APPROVED_STATUS,
        "previous_election_event_id": transition.previous_election_id,
        "previous_election_date": _shared_value(previous_rows, "election_date"),
        "previous_area_name": area_name,
        "previous_winning_candidate_name": winner.get("candidate_name") if winner else None,
        "previous_winning_party": winner.get("original_party_name") if winner else None,
        "previous_winning_candidate_vote_share": winner.get("vote_share") if winner else None,
        "previous_turnout": _shared_value(previous_rows, "turnout"),
        "previous_electorate": _shared_value(previous_rows, "electorate"),
        "source_result_url": source_url,
        "geographic_mapping_id": mapping_id,
        "permission_evidence": (
            f"Exact published division name within the statutory pre-2024 Surrey "
            f"arrangements ({transition.previous_election_id} to "
            f"{transition.current_election_id}). {policy.limitation}"
        ),
        "permission_source_urls": source_urls,
        "candidate_history_allowed": False,
        "incumbency_allowed": False,
        "party_vote_share_change_allowed": False,
    }


def _party_history_for_exact_area(
    current_rows: Sequence[Mapping[str, object]],
    previous_rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Derive exact-label party history without collapsing similar party names."""

    previous_labels = {
        row.get("original_party_name")
        for row in previous_rows
        if isinstance(row.get("original_party_name"), str) and row["original_party_name"].strip()
    }
    result = []
    for party_name in sorted(
        {
            row.get("original_party_name")
            for row in current_rows
            if isinstance(row.get("original_party_name"), str) and row["original_party_name"].strip()
        },
        key=lambda value: str(value).casefold(),
    ):
        assert isinstance(party_name, str)
        previously_contested = party_name in previous_labels
        result.append(
            {
                "original_party_name": party_name,
                "party_previously_contested": previously_contested,
                "first_observed_appearance": not previously_contested,
                "provenance": "deterministically_derived",
            }
        )
    return tuple(result)


def build_principal_election_continuity_audit(
    *,
    configuration_path: str | Path = DEFAULT_CONTINUITY_CONFIGURATION_PATH,
    history: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Audit legal continuity before exposing 2017/2021 prior-election fields.

    Every configured transition must have exactly the configured number of exact
    published names in both adjacent elections.  Any mismatch is a hard error,
    not an invitation to use fuzzy matching or to choose a predecessor.
    """

    policy, sources, transitions = load_principal_election_continuity_configuration(
        configuration_path
    )
    raw_history = history if history is not None else build_election_history()
    rows_by_event_area = _rows_by_event_and_area(raw_history)
    source_urls = tuple(sources[source_id].source_url for source_id in policy.required_source_ids)
    division_references = []
    party_references = []
    transition_rows = []

    for transition in transitions:
        previous_names = _area_names_for_event(rows_by_event_area, transition.previous_election_id)
        current_names = _area_names_for_event(rows_by_event_area, transition.current_election_id)
        only_previous = sorted(previous_names - current_names)
        only_current = sorted(current_names - previous_names)
        shared_names = sorted(previous_names & current_names)
        if only_previous or only_current or len(shared_names) != transition.expected_exact_area_count:
            raise ValueError(
                f"{transition.transition_id} does not have the required exact published "
                f"area continuity: previous_only={only_previous}, current_only={only_current}, "
                f"shared={len(shared_names)}, expected={transition.expected_exact_area_count}."
            )
        transition_rows.append(
            {
                **asdict(transition),
                "status": APPROVED_STATUS,
                "matched_exact_area_count": len(shared_names),
                "previous_only_area_names": only_previous,
                "current_only_area_names": only_current,
                "source_urls": list(source_urls),
                "limitation": policy.limitation,
            }
        )
        for area_name in shared_names:
            previous_rows = rows_by_event_area[(transition.previous_election_id, area_name)]
            current_rows = rows_by_event_area[(transition.current_election_id, area_name)]
            reference = _reference_for_exact_area(
                transition, area_name, previous_rows, source_urls, policy
            )
            division_references.append(
                {
                    "current_election_id": transition.current_election_id,
                    "current_area_name": area_name,
                    **reference,
                }
            )
            for party_reference in _party_history_for_exact_area(current_rows, previous_rows):
                party_references.append(
                    {
                        "current_election_id": transition.current_election_id,
                        "current_area_name": area_name,
                        **party_reference,
                    }
                )

    return {
        "framework_id": policy.framework_id,
        "purpose": policy.purpose,
        "policy": {
            "matching_rule": policy.matching_rule,
            "permitted_features": list(policy.permitted_features),
            "prohibited_features": list(policy.prohibited_features),
            "limitation": policy.limitation,
        },
        "source_registry": [asdict(source) for source in sources.values()],
        "transition_records": transition_rows,
        "division_references": division_references,
        "party_history_references": party_references,
        "summary": {
            "transitions_approved": len(transition_rows),
            "division_references_approved": len(division_references),
            "party_history_references_approved": len(party_references),
            "candidate_identity_references_created": 0,
            "incumbency_references_created": 0,
            "party_vote_share_change_values_created": 0,
        },
    }


def principal_election_continuity_markdown(audit: Mapping[str, object]) -> str:
    """Render a compact reproducible report without embedding raw result data."""

    summary = audit["summary"]
    assert isinstance(summary, Mapping)
    transitions = audit["transition_records"]
    assert isinstance(transitions, list)
    lines = [
        "# Surrey Principal Election Legal-Continuity Audit",
        "",
        "## Decision",
        "",
        "The 2013→2017 and 2017→2021 principal-election references are approved only because the configured statutory evidence identifies the 2012 arrangements as the divisions replaced by the 2024 Order at the May 2025 elections, and every transition has exactly 81 matching published division names.",
        "",
        "This is not a 2021→2026 boundary equivalence claim. The existing 2026 GIS permission audit remains separate and unchanged.",
        "",
        "## Coverage",
        "",
        f"- Approved transitions: {summary['transitions_approved']}",
        f"- Approved division-level prior references: {summary['division_references_approved']}",
        f"- Exact-label party-history references: {summary['party_history_references_approved']}",
        f"- Candidate-identity references created: {summary['candidate_identity_references_created']}",
        f"- Incumbency references created: {summary['incumbency_references_created']}",
        f"- Party vote-share change values created: {summary['party_vote_share_change_values_created']}",
        "",
        "## Transition checks",
        "",
        "| Transition | Exact areas matched | Status |",
        "| --- | ---: | --- |",
    ]
    for transition in transitions:
        lines.append(
            f"| {transition['transition_id']} | {transition['matched_exact_area_count']} | {transition['status']} |"
        )
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "Only source-reported Elected rows can supply a previous winner. Exact original party labels can support party-history fields. Candidate identity, incumbency, party totals, vote-share change, swing, redistribution and vote-ranking margins remain NULL/unavailable.",
            "",
            "## Sources",
            "",
        ]
    )
    sources = audit["source_registry"]
    assert isinstance(sources, list)
    for source in sources:
        assert isinstance(source, Mapping)
        lines.append(f"- [{source['source_id']}]({source['source_url']}): {source['evidence_text']}")
    lines.append("")
    return "\n".join(lines)
