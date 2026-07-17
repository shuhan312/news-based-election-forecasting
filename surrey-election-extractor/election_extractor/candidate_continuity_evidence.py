"""Load explicit official evidence for candidate history and incumbency.

This module deliberately does not try to discover a person from a candidate
name.  A record is permitted only when a Surrey County Council member profile
with a stable UID directly links to the exact official result page concerned,
and its earlier official-election links and term information support the two
claims.  The small reviewed register is therefore evidence, not a matching
algorithm.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from election_extractor.url_utils import SURREY_HOST, normalise_area_result_url


DEFAULT_EVIDENCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "candidate_continuity_evidence.json"
)


@dataclass(frozen=True)
class PriorOfficialElection:
    """Represent one earlier election page directly linked by a member profile."""

    election_id: str
    election_date: date
    source_url: str


@dataclass(frozen=True)
class CandidateContinuityEvidence:
    """Contain one manually verified person-level continuity decision.

    ``candidate_name`` identifies an already-published row on
    ``candidate_source_url``.  It is not used to search for or infer another
    person.  All links in the record are retained so a reviewer can reproduce
    the decision without relying on a private contact record or an address.
    """

    evidence_id: str
    election_id: str
    candidate_name: str
    division_name: str
    candidate_source_url: str
    member_profile_url: str
    member_uid: str
    term_start: date
    profile_linked_result_urls: tuple[str, ...]
    prior_official_elections: tuple[PriorOfficialElection, ...]
    candidate_previously_stood: bool
    incumbent_candidate: bool
    incumbent_party: str | None
    evidence_text: str
    retrieval_date: str
    confidence: str
    notes: str | None


def result_page_identity(url: str) -> str:
    """Return the stable official result-page identity without tracking variants.

    Surrey's application may add ``RPID`` or ``XXR`` query values to the same
    page.  The result-page ``ID`` is the published area-result identifier, so
    it is the only parameter used to compare a profile link with an audited
    candidate source.  This normalises a URL identity, not geography or people.
    """

    canonical = normalise_area_result_url(url)
    parsed = urlsplit(canonical)
    result_id = parse_qs(parsed.query).get("ID", ())
    if len(result_id) != 1:
        raise ValueError("Official area-result URL must contain one ID.")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?ID={result_id[0]}"


def load_candidate_continuity_evidence(
    path: str | Path = DEFAULT_EVIDENCE_PATH,
    *,
    permitted_election_ids: Iterable[str],
) -> tuple[CandidateContinuityEvidence, ...]:
    """Load only manually reviewed official person-level continuity evidence."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("Candidate continuity evidence must contain a records list.")

    permitted = set(permitted_election_ids)
    records = tuple(_record_from_mapping(item) for item in raw_records)
    seen_ids: set[str] = set()
    seen_targets: set[tuple[str, str, str]] = set()
    for record in records:
        if record.election_id not in permitted:
            raise ValueError(
                "Candidate continuity evidence references an unconfigured election: "
                f"{record.election_id}."
            )
        if record.evidence_id in seen_ids:
            raise ValueError(f"Duplicate candidate continuity evidence_id: {record.evidence_id}.")
        seen_ids.add(record.evidence_id)
        target = candidate_evidence_key(
            record.election_id,
            record.candidate_source_url,
            record.candidate_name,
        )
        if target in seen_targets:
            raise ValueError("Duplicate candidate continuity evidence for one published row.")
        seen_targets.add(target)
    return records


def evidence_by_candidate_key(
    records: Iterable[CandidateContinuityEvidence],
) -> dict[tuple[str, str, str], CandidateContinuityEvidence]:
    """Index reviewed records by election, exact official page and published name."""

    indexed: dict[tuple[str, str, str], CandidateContinuityEvidence] = {}
    for record in records:
        key = candidate_evidence_key(
            record.election_id,
            record.candidate_source_url,
            record.candidate_name,
        )
        if key in indexed:
            raise ValueError("Duplicate candidate continuity evidence key.")
        indexed[key] = record
    return indexed


def candidate_evidence_key(
    election_id: str,
    candidate_source_url: str,
    candidate_name: str,
) -> tuple[str, str, str]:
    """Build a key that cannot match records from a different result page."""

    return (election_id, result_page_identity(candidate_source_url), candidate_name)


def _record_from_mapping(item: object) -> CandidateContinuityEvidence:
    """Validate one evidence object before it can influence output fields."""

    if not isinstance(item, Mapping):
        raise ValueError("Each candidate continuity evidence record must be an object.")
    required = (
        "evidence_id",
        "election_id",
        "candidate_name",
        "division_name",
        "candidate_source_url",
        "member_profile_url",
        "member_uid",
        "term_start",
        "profile_linked_result_urls",
        "prior_official_elections",
        "evidence_text",
        "retrieval_date",
        "confidence",
    )
    for field_name in required:
        if field_name not in item:
            raise ValueError(f"Candidate continuity evidence is missing {field_name}.")

    candidate_previously_stood = item.get("candidate_previously_stood")
    incumbent_candidate = item.get("incumbent_candidate")
    # This register makes only positive, directly evidenced claims. Omission
    # means unknown, rather than an unsupported assertion that the answer is No.
    if candidate_previously_stood is not True or incumbent_candidate is not True:
        raise ValueError(
            "Candidate continuity evidence may record only directly verified True values."
        )
    candidate_source_url = str(item["candidate_source_url"])
    source_identity = result_page_identity(candidate_source_url)
    profile_url = _validate_profile_url(str(item["member_profile_url"]), str(item["member_uid"]))
    linked_urls = tuple(
        result_page_identity(str(url))
        for url in _required_list(item["profile_linked_result_urls"], "profile_linked_result_urls")
    )
    if source_identity not in linked_urls:
        raise ValueError(
            "Candidate source URL must be directly listed by the official member profile."
        )
    if len(set(linked_urls)) != len(linked_urls):
        raise ValueError("Profile-linked official result URLs must be unique.")

    prior_elections = tuple(
        _prior_election_from_mapping(value) for value in _required_list(
            item["prior_official_elections"], "prior_official_elections"
        )
    )
    target_date = _iso_date(item.get("candidate_election_date"), "candidate_election_date")
    if not prior_elections:
        raise ValueError("Candidate continuity evidence requires an earlier official election.")
    if any(prior.source_url not in linked_urls for prior in prior_elections):
        raise ValueError("Each prior result page must be directly listed by the member profile.")
    if any(prior.election_date >= target_date for prior in prior_elections):
        raise ValueError("Prior official election dates must predate the candidate election.")
    term_start = _iso_date(item["term_start"], "term_start")
    if term_start >= target_date:
        raise ValueError("An incumbent term must start before the candidate election.")

    incumbent_party = _optional_text(item.get("incumbent_party"))
    if incumbent_party is None:
        raise ValueError("Verified incumbent evidence requires the published incumbent party.")
    return CandidateContinuityEvidence(
        evidence_id=str(item["evidence_id"]),
        election_id=str(item["election_id"]),
        candidate_name=str(item["candidate_name"]),
        division_name=str(item["division_name"]),
        candidate_source_url=source_identity,
        member_profile_url=profile_url,
        member_uid=str(item["member_uid"]),
        term_start=term_start,
        profile_linked_result_urls=linked_urls,
        prior_official_elections=prior_elections,
        candidate_previously_stood=True,
        incumbent_candidate=True,
        incumbent_party=incumbent_party,
        evidence_text=str(item["evidence_text"]),
        retrieval_date=str(item["retrieval_date"]),
        confidence=str(item["confidence"]),
        notes=_optional_text(item.get("notes")),
    )


def _prior_election_from_mapping(item: object) -> PriorOfficialElection:
    """Validate a dated earlier official election link used for continuity."""

    if not isinstance(item, Mapping):
        raise ValueError("Each prior official election must be an object.")
    try:
        return PriorOfficialElection(
            election_id=str(item["election_id"]),
            election_date=_iso_date(item["election_date"], "prior election_date"),
            source_url=result_page_identity(str(item["source_url"])),
        )
    except KeyError as exc:
        raise ValueError(f"Prior official election is missing {exc.args[0]}.") from exc


def _validate_profile_url(url: str, member_uid: str) -> str:
    """Accept only the public official Surrey councillor profile for its UID."""

    parsed = urlsplit(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() != SURREY_HOST:
        raise ValueError("Member profile evidence must use the official Surrey Council host.")
    if parsed.path.casefold() != "/mguserinfo.aspx":
        raise ValueError("Member profile evidence must use the public councillor-profile path.")
    values = parse_qs(parsed.query).get("UID", ())
    if len(values) != 1 or values[0] != member_uid or not member_uid.isdigit():
        raise ValueError("Member profile evidence must contain its matching numeric UID.")
    return f"https://{SURREY_HOST}/mgUserInfo.aspx?UID={member_uid}"


def _required_list(value: object, field_name: str) -> list[object]:
    """Reject text and empty lists where a set of audited links is required."""

    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list.")
    return value


def _iso_date(value: object, field_name: str) -> date:
    """Parse dates in the register without accepting locale-dependent text."""

    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must use ISO date format YYYY-MM-DD.") from exc


def _optional_text(value: object) -> str | None:
    """Keep optional explanatory text absent rather than creating placeholders."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None
