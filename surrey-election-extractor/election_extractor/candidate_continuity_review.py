"""Build a review queue for repeated published candidate names.

The queue is deliberately an audit aid, not an identity-resolution engine.
An exact name appearing more than once may refer to one person or to different
people.  Consequently, a repeated name produces a review item only.  It can
never create a ``candidate_previously_stood`` or incumbency value by itself.

Approved claims are read only from the separate reviewed continuity-evidence
register.  Every other repeated appearance is labelled tier C so that a future
reviewer knows both what has been checked and what has *not* been concluded.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from enum import Enum

from election_extractor.candidate_continuity_evidence import (
    CandidateContinuityEvidence,
    candidate_evidence_key,
)


class ContinuityReviewTier(str, Enum):
    """Describe the evidence available for one published candidate row."""

    A = "A_direct_official_profile"
    B = "B_reviewed_multi_source_official_evidence"
    C = "C_repeated_name_requires_review"


@dataclass(frozen=True)
class CandidateAppearanceReview:
    """Retain one exact published occurrence inside a repeated-name group."""

    election_id: str
    election_year: int | None
    division_name: str | None
    original_party_name: str | None
    outcome: str | None
    source_url: str
    review_tier: ContinuityReviewTier
    evidence_id: str | None
    evidence_method: str | None
    evidence_source_urls: tuple[str, ...]
    candidate_previously_stood: bool | None
    incumbent_candidate: bool | None
    incumbent_party: str | None
    review_reason: str
    next_review_action: str | None


@dataclass(frozen=True)
class CandidateNameReviewGroup:
    """Group all exact-name occurrences without asserting person identity."""

    candidate_name: str
    appearances: tuple[CandidateAppearanceReview, ...]
    group_status: str


def build_candidate_continuity_review(
    candidate_rows: Iterable[Mapping[str, object]],
    evidence_by_key: Mapping[tuple[str, str, str], CandidateContinuityEvidence],
) -> tuple[CandidateNameReviewGroup, ...]:
    """Return every exact repeated name and its evidence-safe review status.

    Rows with a missing candidate name or source URL are not useful for this
    specific audit and are skipped.  This is not a data-quality correction:
    it simply prevents an invalid audit key from becoming a false identity
    relationship.  The returned groups are deterministically sorted so later
    review runs can be compared without relying on input order.
    """

    grouped: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in candidate_rows:
        name = row.get("candidate_name")
        source_url = row.get("source_url")
        if isinstance(name, str) and name.strip() and isinstance(source_url, str) and source_url.strip():
            grouped[name].append(row)

    groups: list[CandidateNameReviewGroup] = []
    for candidate_name, appearances in grouped.items():
        if len(appearances) < 2:
            continue
        reviewed = tuple(
            _appearance_review(candidate_name, row, evidence_by_key)
            for row in sorted(appearances, key=_appearance_sort_key)
        )
        approved_count = sum(item.review_tier is not ContinuityReviewTier.C for item in reviewed)
        group_status = (
            "partially_or_fully_evidenced"
            if approved_count
            else "review_required_no_identity_claim"
        )
        groups.append(
            CandidateNameReviewGroup(
                candidate_name=candidate_name,
                appearances=reviewed,
                group_status=group_status,
            )
        )
    return tuple(sorted(groups, key=lambda group: (group.candidate_name.casefold(), group.candidate_name)))


def review_as_dict(groups: Iterable[CandidateNameReviewGroup]) -> dict[str, object]:
    """Serialise the queue with transparent counts for JSON and Markdown reports."""

    group_list = tuple(groups)
    appearances = tuple(item for group in group_list for item in group.appearances)
    return {
        "summary": {
            "repeated_exact_name_groups": len(group_list),
            "candidate_appearances_in_review": len(appearances),
            "tier_a_direct_profile_rows": sum(item.review_tier is ContinuityReviewTier.A for item in appearances),
            "tier_b_multi_source_rows": sum(item.review_tier is ContinuityReviewTier.B for item in appearances),
            "tier_c_review_required_rows": sum(item.review_tier is ContinuityReviewTier.C for item in appearances),
            "identity_inference_policy": "Exact repeated names are review candidates only; they create no person-level claim.",
        },
        "groups": [asdict(group) for group in group_list],
    }


def _appearance_review(
    candidate_name: str,
    row: Mapping[str, object],
    evidence_by_key: Mapping[tuple[str, str, str], CandidateContinuityEvidence],
) -> CandidateAppearanceReview:
    """Attach approved evidence only to the exact published target row."""

    election_id = _text(row, "election_id")
    source_url = _text(row, "source_url")
    evidence: CandidateContinuityEvidence | None = None
    if election_id and source_url:
        # This key includes the result-page identity.  It intentionally cannot
        # carry a positive decision from one similarly named row to another.
        try:
            evidence = evidence_by_key.get(
                candidate_evidence_key(election_id, source_url, candidate_name)
            )
        except ValueError:
            evidence = None

    if evidence is None:
        return CandidateAppearanceReview(
            election_id=election_id or "",
            election_year=_integer(row.get("election_year")),
            division_name=_optional_text(row.get("division_name")),
            original_party_name=_optional_text(row.get("original_party_name")),
            outcome=_optional_text(row.get("outcome")),
            source_url=source_url or "",
            review_tier=ContinuityReviewTier.C,
            evidence_id=None,
            evidence_method=None,
            evidence_source_urls=(source_url,) if source_url else (),
            candidate_previously_stood=None,
            incumbent_candidate=None,
            incumbent_party=None,
            review_reason=(
                "An exact repeated published name exists, but no reviewed person-level "
                "official evidence is registered for this result row."
            ),
            next_review_action=(
                "Check a stable official councillor profile and independently verify the "
                "target and earlier official result or declaration pages; do not infer identity "
                "from name, party or division alone."
            ),
        )

    tier = (
        ContinuityReviewTier.A
        if evidence.evidence_method == "official_member_profile"
        else ContinuityReviewTier.B
    )
    evidence_urls = tuple(source.source_url for source in evidence.supporting_sources)
    if not evidence_urls:
        evidence_urls = (evidence.member_profile_url, *evidence.profile_linked_result_urls)
    return CandidateAppearanceReview(
        election_id=election_id or "",
        election_year=_integer(row.get("election_year")),
        division_name=_optional_text(row.get("division_name")),
        original_party_name=_optional_text(row.get("original_party_name")),
        outcome=_optional_text(row.get("outcome")),
        source_url=source_url or "",
        review_tier=tier,
        evidence_id=evidence.evidence_id,
        evidence_method=evidence.evidence_method,
        evidence_source_urls=evidence_urls,
        candidate_previously_stood=True,
        incumbent_candidate=evidence.incumbent_candidate,
        incumbent_party=evidence.incumbent_party if evidence.incumbent_candidate else None,
        review_reason="Explicit reviewed official person-level evidence is registered for this exact row.",
        next_review_action=None,
    )


def _appearance_sort_key(row: Mapping[str, object]) -> tuple[int, str, str]:
    """Sort occurrences chronologically while keeping non-standard years stable."""

    year = _integer(row.get("election_year"))
    return (year if year is not None else 9999, _text(row, "election_id") or "", _text(row, "source_url") or "")


def _text(row: Mapping[str, object], field_name: str) -> str | None:
    """Read a required audit key without converting missing values into text."""

    value = row.get(field_name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_text(value: object) -> str | None:
    """Keep absent source values as ``None`` in the review output."""

    return value.strip() if isinstance(value, str) and value.strip() else None


def _integer(value: object) -> int | None:
    """Accept a source year only when it is already represented as an integer."""

    return value if isinstance(value, int) and not isinstance(value, bool) else None
