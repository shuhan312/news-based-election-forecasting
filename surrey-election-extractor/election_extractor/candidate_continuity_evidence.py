"""Load explicit evidence for candidate history and incumbency.

This module deliberately does not try to discover a person from a candidate
name.  The register permits two reviewed methods:

* ``official_member_profile`` is the strongest route: one stable Surrey member
  profile directly links the target and earlier official result pages.
* ``official_multi_source_match`` is a high-confidence alternative: a stable
  official profile, the exact target result page, and at least one earlier
  official result page are manually reviewed together.  It is useful where a
  profile names the elections but does not retain direct links to every page.
* ``official_council_record_match`` permits a narrowly defined archival case:
  an official Council record explicitly records the named candidate taking up
  the prior office, alongside exact target and prior official result pages.
  It is not a fallback to matching names; the Council record must provide the
  person-to-office link that a stable profile would otherwise provide.

Both methods require explicit source URLs and exact published names.  They are
evidence registers, not matching algorithms: repeated names in the database
never create a history or incumbency claim by themselves.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from election_extractor.url_utils import (
    SURREY_HOST,
    TRACKING_PARAMETERS,
    normalise_area_result_url,
)


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
class OfficialEvidenceSource:
    """Describe one public official source used in a manual review.

    ``published_candidate_name`` records the exact visible name reviewed on a
    result page or member profile.  It lets a reviewer check the human
    identity decision without the code trying to resolve names automatically.
    """

    source_url: str
    source_type: str
    source_authority: str
    published_candidate_name: str
    evidence_text: str


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
    member_profile_url: str | None
    member_uid: str | None
    term_start: date
    profile_linked_result_urls: tuple[str, ...]
    prior_official_elections: tuple[PriorOfficialElection, ...]
    candidate_previously_stood: bool
    incumbent_candidate: bool | None
    incumbent_party: str | None
    evidence_text: str
    retrieval_date: str
    confidence: str
    notes: str | None
    # Existing profile records keep their original compact shape.  New
    # multi-source records make every reviewed source visible in this field.
    evidence_method: str = "official_member_profile"
    supporting_sources: tuple[OfficialEvidenceSource, ...] = ()
    # Council minutes and declarations need their own publication date.  This
    # prevents a later Council record from being used to claim incumbency at
    # an earlier election.
    office_record_date: date | None = None


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


def official_election_source_identity(url: str) -> str:
    """Return a stable identity for an audited public election source.

    Surrey result pages keep the published area-result ``ID`` identity. Other
    manually reviewed public-authority pages or declarations may be PDFs or
    use another council's URL structure, so they retain their HTTPS path and
    meaningful query values instead. The evidence register, rather than URL
    shape alone, records which public authority published the source.
    """

    try:
        return result_page_identity(url)
    except ValueError:
        pass
    parsed = urlsplit(url.strip())
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("Official election evidence must use a public HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("Official election evidence URL must not contain credentials.")
    query = sorted(
        {
            (name, value)
            for name, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not (name.casefold().startswith("utm_") or name.casefold() in TRACKING_PARAMETERS)
        },
        key=lambda item: (item[0].casefold(), item[1]),
    )
    return urlunsplit(("https", parsed.hostname.casefold(), parsed.path, urlencode(query), ""))


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

    return (election_id, official_election_source_identity(candidate_source_url), candidate_name)


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
        "prior_official_elections",
        "evidence_text",
        "retrieval_date",
        "confidence",
    )
    for field_name in required:
        if field_name not in item:
            raise ValueError(f"Candidate continuity evidence is missing {field_name}.")

    evidence_method = str(item.get("evidence_method", "official_member_profile"))
    if evidence_method not in {
        "official_member_profile",
        "official_multi_source_match",
        "official_council_record_match",
    }:
        raise ValueError("Candidate continuity evidence has an unsupported evidence_method.")

    candidate_previously_stood = item.get("candidate_previously_stood")
    incumbent_candidate = item.get("incumbent_candidate")
    # This register makes only positive, directly evidenced claims. Omission
    # means unknown, rather than an unsupported assertion that the answer is No.
    if candidate_previously_stood is not True or incumbent_candidate not in {True, None}:
        raise ValueError(
            "Candidate continuity evidence may record only directly verified True values or unknown incumbency."
        )
    candidate_source_url = str(item["candidate_source_url"])
    source_identity = official_election_source_identity(candidate_source_url)
    prior_elections = tuple(
        _prior_election_from_mapping(value) for value in _required_list(
            item["prior_official_elections"], "prior_official_elections"
        )
    )
    target_date = _iso_date(item.get("candidate_election_date"), "candidate_election_date")
    if not prior_elections:
        raise ValueError("Candidate continuity evidence requires an earlier official election.")
    if any(prior.election_date >= target_date for prior in prior_elections):
        raise ValueError("Prior official election dates must predate the candidate election.")

    # A member profile is mandatory for the two profile-based routes. The
    # archival Council-record route has no invented UID: it instead requires
    # an explicit official record that names the councillor and office.
    if evidence_method == "official_council_record_match":
        profile_url = None
        member_uid = None
    else:
        profile_url = _validate_profile_url(
            str(item.get("member_profile_url", "")), str(item.get("member_uid", ""))
        )
        member_uid = str(item["member_uid"])
    term_start = _iso_date(item.get("term_start"), "term_start")
    office_record_date = (
        _iso_date(item.get("office_record_date"), "office_record_date")
        if evidence_method == "official_council_record_match"
        else None
    )
    linked_urls = tuple(
        result_page_identity(str(url))
        for url in item.get("profile_linked_result_urls", [])
    )
    if len(set(linked_urls)) != len(linked_urls):
        raise ValueError("Profile-linked official result URLs must be unique.")

    supporting_sources = tuple(
        _official_source_from_mapping(
            value,
            candidate_name=str(item["candidate_name"]),
            member_uid=member_uid,
        )
        for value in item.get("supporting_sources", [])
    )
    if evidence_method == "official_member_profile":
        if not linked_urls:
            raise ValueError("Official member-profile evidence requires profile_linked_result_urls.")
        if source_identity not in linked_urls:
            raise ValueError(
                "Candidate source URL must be directly listed by the official member profile."
            )
        if any(prior.source_url not in linked_urls for prior in prior_elections):
            raise ValueError("Each prior result page must be directly listed by the member profile.")
    elif evidence_method == "official_multi_source_match":
        _validate_multi_source_match(
            supporting_sources=supporting_sources,
            profile_url=profile_url,
            candidate_source_url=source_identity,
            prior_elections=prior_elections,
        )
    else:
        _validate_council_record_match(
            supporting_sources=supporting_sources,
            candidate_source_url=source_identity,
            prior_elections=prior_elections,
            office_record_date=office_record_date,
            term_start=term_start,
            target_date=target_date,
        )

    incumbent_party = _optional_text(item.get("incumbent_party"))
    if incumbent_candidate is True:
        if term_start >= target_date:
            raise ValueError("An incumbent term must start before the candidate election.")
        if incumbent_party is None:
            raise ValueError("Verified incumbent evidence requires the published incumbent party.")
    elif incumbent_party is not None:
        raise ValueError("incumbent_party must remain missing when incumbency is unknown.")
    return CandidateContinuityEvidence(
        evidence_id=str(item["evidence_id"]),
        election_id=str(item["election_id"]),
        candidate_name=str(item["candidate_name"]),
        division_name=str(item["division_name"]),
        candidate_source_url=source_identity,
        member_profile_url=profile_url,
        member_uid=member_uid,
        term_start=term_start,
        profile_linked_result_urls=linked_urls,
        prior_official_elections=prior_elections,
        candidate_previously_stood=True,
        incumbent_candidate=incumbent_candidate,
        incumbent_party=incumbent_party,
        evidence_text=str(item["evidence_text"]),
        retrieval_date=str(item["retrieval_date"]),
        confidence=str(item["confidence"]),
        notes=_optional_text(item.get("notes")),
        evidence_method=evidence_method,
        supporting_sources=supporting_sources,
        office_record_date=office_record_date,
    )


def _official_source_from_mapping(
    item: object, *, candidate_name: str, member_uid: str | None
) -> OfficialEvidenceSource:
    """Validate one explicitly reviewed official source in a multi-source claim."""

    if not isinstance(item, Mapping):
        raise ValueError("Each supporting official source must be an object.")
    try:
        source_type = str(item["source_type"])
        source_url = str(item["source_url"])
        source_authority = str(item["source_authority"])
        published_name = str(item["published_candidate_name"])
        evidence_text = str(item["evidence_text"])
    except KeyError as exc:
        raise ValueError(f"Supporting official source is missing {exc.args[0]}.") from exc
    if source_type not in {
        "official_member_profile",
        "official_result_page",
        "official_declaration",
        "official_nomination",
        "official_council_record",
    }:
        raise ValueError("Supporting source must be an approved public official source type.")
    if not source_authority.strip():
        raise ValueError("Supporting source must identify its public authority.")
    if published_name != candidate_name:
        raise ValueError("Supporting source must retain the exact published candidate name.")
    if not evidence_text.strip():
        raise ValueError("Supporting source must contain a manual evidence note.")
    if source_type == "official_member_profile":
        # The caller compares this canonical URL with the declared stable UID.
        if member_uid is None:
            raise ValueError("Council-record evidence cannot include an undeclared member profile.")
        source_url = _validate_profile_url(source_url, member_uid)
    else:
        source_url = official_election_source_identity(source_url)
    return OfficialEvidenceSource(
        source_url=source_url,
        source_type=source_type,
        source_authority=source_authority,
        published_candidate_name=published_name,
        evidence_text=evidence_text,
    )


def _validate_multi_source_match(
    *,
    supporting_sources: tuple[OfficialEvidenceSource, ...],
    profile_url: str | None,
    candidate_source_url: str,
    prior_elections: tuple[PriorOfficialElection, ...],
) -> None:
    """Require three explicit official sources before relaxing direct-link evidence.

    The target and previous official result pages establish published-name
    continuity.  The stable profile independently establishes the public
    councillor identity and term.  This is deliberately stricter than a
    repeated-name heuristic, while avoiding a false requirement that old
    member profiles must retain every historical hyperlink.
    """

    if profile_url is None:
        raise ValueError("Multi-source evidence requires an official member profile.")
    if len(supporting_sources) < 3:
        raise ValueError("Multi-source evidence requires at least three official sources.")
    profile_sources = {
        source.source_url for source in supporting_sources if source.source_type == "official_member_profile"
    }
    result_sources = {
        source.source_url
        for source in supporting_sources
        if source.source_type
        in {"official_result_page", "official_declaration", "official_nomination", "official_council_record"}
    }
    if profile_sources != {profile_url}:
        raise ValueError("Multi-source evidence must include its declared official member profile.")
    required_results = {candidate_source_url, *(prior.source_url for prior in prior_elections)}
    if not required_results.issubset(result_sources):
        raise ValueError(
            "Multi-source evidence must include the exact target and prior official result pages."
        )
    if len({(source.source_type, source.source_url) for source in supporting_sources}) != len(
        supporting_sources
    ):
        raise ValueError("Supporting official sources must be unique.")


def _validate_council_record_match(
    *,
    supporting_sources: tuple[OfficialEvidenceSource, ...],
    candidate_source_url: str,
    prior_elections: tuple[PriorOfficialElection, ...],
    office_record_date: date | None,
    term_start: date,
    target_date: date,
) -> None:
    """Require an official person-to-office record where no profile is available.

    A declaration alone proves only that an identically named candidate won a
    prior contest.  This route additionally requires a Council-published
    record that explicitly identifies the named person as having taken the
    office.  It is intentionally limited to the exact target result and dated
    prior results listed in the register.
    """

    if len(supporting_sources) < 3:
        raise ValueError("Council-record evidence requires target, prior and Council-record sources.")
    if office_record_date is None:
        raise ValueError("Council-record evidence requires an office_record_date.")
    if not (term_start <= office_record_date < target_date):
        raise ValueError(
            "Council-record dates must place the verified term before the target election."
        )
    if any(prior.election_date > office_record_date for prior in prior_elections):
        raise ValueError(
            "Council-record evidence must be published on or after each cited prior election."
        )
    council_records = {
        source.source_url
        for source in supporting_sources
        if source.source_type == "official_council_record"
    }
    result_sources = {
        source.source_url
        for source in supporting_sources
        if source.source_type in {"official_result_page", "official_declaration"}
    }
    if not council_records:
        raise ValueError("Council-record evidence requires an official Council record.")
    required_results = {candidate_source_url, *(prior.source_url for prior in prior_elections)}
    if not required_results.issubset(result_sources):
        raise ValueError("Council-record evidence must include the exact target and prior result pages.")
    if len({(source.source_type, source.source_url) for source in supporting_sources}) != len(
        supporting_sources
    ):
        raise ValueError("Supporting official sources must be unique.")


def _prior_election_from_mapping(item: object) -> PriorOfficialElection:
    """Validate a dated earlier official election link used for continuity."""

    if not isinstance(item, Mapping):
        raise ValueError("Each prior official election must be an object.")
    try:
        return PriorOfficialElection(
            election_id=str(item["election_id"]),
            election_date=_iso_date(item["election_date"], "prior election_date"),
            source_url=official_election_source_identity(str(item["source_url"])),
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
