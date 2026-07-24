"""Assemble the 48 hard E5 disagreements for transparent human review.

This script prepares data; it does not adjudicate any disagreement. The
original human and v1 LLM decisions are copied verbatim into a separate
review dataset, while all diagnostic fields start empty. Keeping source
values and later interpretation separate preserves the audit trail required
for a publishable development analysis.

The output is JSON rather than an edited copy of either source CSV. A
separate workbook export can therefore add formatting and data validation
without changing the research records from which the review was derived.

Usage:
    python3 -m src.news_collection.build_e5_disagreement_review_data
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

HUMAN = Path("news_collection/manual_review_sample.csv")
LLM = Path("news_collection/manual_review_llm_pilot.csv")
AUDIT = Path("news_collection/llm_v1_disagreement_audit.csv")
QUERY_INVENTORY = Path("news_collection/query_inventory.csv")
DIVISION_SAMPLE = Path("news_protocol/division_sample.csv")
RECORDS_DIR = Path("data/raw/news/records")
OUT = Path("news_collection/e5_hard_disagreement_review_data.json")

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
NON_WORD = re.compile(r"[^a-z0-9]+")

# These expressions identify possible council-level evidence only. A match is
# deliberately described as a "signal", not as proof of L3 or L4: the human
# reviewer must still decide whether the council issue affects a sampled area
# or whether the coverage is genuinely county-wide and political.
SURREY_AUTHORITY_PATTERNS = (
    (
        "Surrey County Council",
        re.compile(r"\bSurrey County Council\b", re.IGNORECASE),
    ),
    ("Surrey council", re.compile(r"\bSurrey council\b", re.IGNORECASE)),
    (
        "Surrey councillor",
        re.compile(r"\bSurrey councillors?\b", re.IGNORECASE),
    ),
)

DIRECTIONAL_OR_ADMIN_SUFFIX = re.compile(
    r"\s+(?:Central|East|West|North|South|Hill|Downs|Village)$",
    re.IGNORECASE,
)


def _load_rows(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV without changing values or normalising labels."""
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_raw_record(
    article_id: str, records_dir: Path = RECORDS_DIR
) -> dict[str, Any]:
    """Return the preserved raw article record, or an explicit empty record."""
    path = records_dir / f"{article_id}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def _normalise_place_name(value: str) -> str:
    """Return a comparison key while retaining meaningful place words.

    Ampersands and ``and`` are treated as equivalent, and a trailing "Ward"
    is removed because the same area may be written with or without that
    administrative suffix. This helper is used only to deduplicate labels;
    it does not decide whether an article is geographically eligible.
    """
    value = value.strip().removesuffix(" Ward")
    return NON_WORD.sub(" ", value.lower().replace("&", " and ")).strip()


def _place_aliases(place: str) -> set[str]:
    """Generate conservative written variants for exact phrase matching."""
    base = place.strip()
    without_ward = re.sub(r"\s+Ward$", "", base, flags=re.IGNORECASE)
    aliases = {base, without_ward}
    for value in tuple(aliases):
        aliases.add(value.replace(" & ", " and "))
        aliases.add(value.replace(" and ", " & "))
    return {alias.strip() for alias in aliases if alias.strip()}


def _load_place_names(path: Path, field: str) -> list[str]:
    """Load unique place labels in stable order from a project CSV."""
    seen: set[str] = set()
    places: list[str] = []
    for row in _load_rows(path):
        place = row.get(field, "").strip()
        key = _normalise_place_name(place)
        if place and key not in seen:
            seen.add(key)
            places.append(place)
    return places


def _sample_place_names(sampled_divisions: list[str]) -> list[str]:
    """Derive transparent settlement candidates from sampled labels.

    The derivation intentionally uses only the 17 sampled divisions, rather
    than every historic Surrey ward. The larger list contains labels such as
    "Town", "Court", and "College" that are ordinary English words and caused
    false matches in national stories. Composite labels are split on commas,
    ampersands, and "and"; directional/admin suffixes are also removed so
    "Guildford East" can yield the cautious candidate "Guildford".
    """
    candidates: list[str] = []
    seen: set[str] = set()
    for division in sampled_divisions:
        base = re.sub(r"\s+Ward$", "", division, flags=re.IGNORECASE)
        components = re.split(r"\s*(?:,|&|\band\b)\s*", base)
        for component in components:
            component = component.strip()
            variants = {component}
            shortened = DIRECTIONAL_OR_ADMIN_SUFFIX.sub("", component)
            if shortened:
                variants.add(shortened)
            if component.lower().startswith("lower "):
                variants.add(component[6:])
            for candidate in variants:
                key = _normalise_place_name(candidate)
                # Very short labels are especially prone to ordinary-word
                # collisions and are not useful as unattended search aids.
                if len(key) < 4 or key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
    return candidates


def _exact_place_matches(text: str, places: list[str]) -> list[str]:
    """Return labels whose complete written name occurs in the article.

    Matches are case-insensitive and bounded by non-alphanumeric characters,
    so, for example, ``Ash`` cannot match ``Ashtead``. Results remain
    *candidates*: an incidental place mention may still fail L1.
    """
    matches: list[str] = []
    for place in places:
        if any(
            re.search(
                rf"(?<![A-Za-z0-9]){re.escape(alias)}"
                rf"(?![A-Za-z0-9])",
                text,
                flags=re.IGNORECASE,
            )
            for alias in _place_aliases(place)
        ):
            matches.append(place)
    return matches


def _evidence_sentences(
    text: str,
    sample_matches: list[str],
    area_matches: list[str],
) -> list[str]:
    """Keep up to five verbatim sentences containing an automated signal."""
    aliases = {
        alias.lower()
        for place in sample_matches + area_matches
        for alias in _place_aliases(place)
    }
    evidence: list[str] = []
    for sentence in SENTENCE_BOUNDARY.split(" ".join(text.split())):
        lowered = sentence.lower()
        has_place = any(
            re.search(
                rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])",
                lowered,
            )
            for alias in aliases
        )
        has_authority = any(
            pattern.search(sentence)
            for _, pattern in SURREY_AUTHORITY_PATTERNS
        )
        if has_place or has_authority:
            evidence.append(sentence)
        if len(evidence) == 5:
            break
    return evidence


def _geographic_candidates(
    text: str,
    arm: str,
    sampled_divisions: list[str],
    sample_places: list[str],
) -> dict[str, Any]:
    """Prepare reproducible linkage candidates without adjudicating E5.

    National-arm articles do not require L1-L4 linkage and are marked
    not-applicable. For local-arm articles, an exact sampled-area match is
    stronger than a general Surrey-area match, but neither is automatically
    converted into an include decision.
    """
    if arm != "local":
        return {
            "automated_linkage_status": "not_applicable_national",
            "automated_exact_sample_division_candidates": [],
            "automated_sample_place_candidates": [],
            "automated_authority_signals": [],
            "automated_geographic_evidence": [],
        }

    division_matches = _exact_place_matches(text, sampled_divisions)
    division_keys = {
        _normalise_place_name(place) for place in division_matches
    }
    place_matches = [
        place
        for place in _exact_place_matches(text, sample_places)
        if _normalise_place_name(place) not in division_keys
    ]
    authority_signals = [
        label
        for label, pattern in SURREY_AUTHORITY_PATTERNS
        if pattern.search(text)
    ]
    evidence = _evidence_sentences(
        text, division_matches, place_matches
    )
    return {
        "automated_linkage_status": (
            "candidates_found"
            if division_matches or place_matches or authority_signals
            else "no_candidate_found"
        ),
        "automated_exact_sample_division_candidates": division_matches,
        "automated_sample_place_candidates": place_matches,
        "automated_authority_signals": authority_signals,
        "automated_geographic_evidence": evidence,
    }


def _article_text(
    human_row: dict[str, str], raw_record: dict[str, Any]
) -> tuple[str, str]:
    """Load full text where available and disclose any excerpt fallback.

    The source is stored alongside the text so a reviewer can distinguish
    genuine content ambiguity from a limitation in the available input.
    """
    candidate_paths = [
        human_row.get("article_text_path", ""),
        (raw_record.get("content") or {}).get("text_path", ""),
    ]
    for candidate in candidate_paths:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace"), str(path)
    return (
        human_row.get("article_text_excerpt", ""),
        "sample_excerpt_fallback",
    )


def build_review_rows(
    *,
    human_path: Path = HUMAN,
    llm_path: Path = LLM,
    audit_path: Path = AUDIT,
    query_path: Path = QUERY_INVENTORY,
    division_sample_path: Path = DIVISION_SAMPLE,
    records_dir: Path = RECORDS_DIR,
) -> list[dict[str, Any]]:
    """Join source records into one row per hard E5 disagreement.

    Only ``rule=E5`` and ``disagreement_type=hard_include_exclude`` are
    eligible. This fixed filter excludes field-position errors and unresolved
    answers because those are different failure mechanisms and should not be
    mixed into the substantive relevance analysis.
    """
    human = {
        row["article_id"]: row
        for row in _load_rows(human_path)
        if row["review_round"] == "initial"
    }
    llm = {
        row["article_id"]: row
        for row in _load_rows(llm_path)
        if row.get("status") == "ok"
    }
    queries = {
        row["query_id"]: row
        for row in _load_rows(query_path)
    }
    disagreements = [
        row
        for row in _load_rows(audit_path)
        if row["rule"] == "E5"
        and row["disagreement_type"] == "hard_include_exclude"
    ]
    sampled_divisions = _load_place_names(
        division_sample_path, "division"
    )
    sample_places = _sample_place_names(sampled_divisions)

    review_rows: list[dict[str, Any]] = []
    for index, audit_row in enumerate(
        sorted(disagreements, key=lambda row: row["article_id"]), start=1
    ):
        article_id = audit_row["article_id"]
        human_row = human[article_id]
        llm_row = llm[article_id]
        raw_record = _load_raw_record(article_id, records_dir)
        retrieval = raw_record.get("retrieval") or {}
        identity = raw_record.get("identity") or {}
        dates = raw_record.get("dates") or {}
        query_id = retrieval.get("search_query_id") or ""
        query = queries.get(query_id, {})
        article_text, text_source = _article_text(human_row, raw_record)
        geographic_candidates = _geographic_candidates(
            article_text,
            human_row["arm"],
            sampled_divisions,
            sample_places,
        )

        # Source fields above this line are copied or deterministically joined.
        # Review fields below start empty so no automated inference is mistaken
        # for the researcher's later diagnosis.
        review_rows.append(
            {
                "review_index": index,
                "article_id": article_id,
                "election_id": human_row["election_id"],
                "arm": human_row["arm"],
                "source_id": human_row["source_id"],
                "headline": human_row["headline"],
                "published_date": dates.get("published_date", ""),
                "ward": query.get("ward", ""),
                "query_id": query_id,
                "query_text": query.get("query_text", ""),
                "query_family": query.get("query_family", ""),
                "geographic_scope": query.get("geographic_scope", ""),
                # These flags expose missing collection context separately from
                # the later human diagnosis. In particular, a local record
                # without a ward cannot be assumed to satisfy the supervisor's
                # requested ward/town linkage merely because its source is
                # locally branded.
                "query_context_missing": (
                    "yes"
                    if not query_id
                    or not query
                    or not query.get("query_text", "").strip()
                    else "no"
                ),
                "ward_context_missing": (
                    "yes"
                    if human_row["arm"] == "local"
                    and not query.get("ward", "").strip()
                    else "no"
                ),
                "publisher_url": (
                    identity.get("canonical_url")
                    or retrieval.get("final_url")
                    or ""
                ),
                "article_text_path": human_row.get(
                    "article_text_path", ""
                ),
                "review_text_source": text_source,
                "article_text": article_text,
                # Automated fields are search aids only. They expose the exact
                # label and source sentence found by deterministic matching,
                # while the blank confirmed_* fields below reserve the
                # substantive L1-L4 decision for documented human review.
                **geographic_candidates,
                "confirmed_link_type": "",
                "confirmed_linked_place": "",
                "confirmed_sampled_division": "",
                "confirmed_geographic_evidence": "",
                "linkage_decision": "",
                "human_decision": human_row["e5_decision"],
                "human_reason_code": human_row["e5_reason_code"],
                "human_supporting_text": human_row[
                    "e5_supporting_text"
                ],
                "llm_decision": llm_row["e5_decision"],
                "llm_reason_code": llm_row["e5_reason_code"],
                "llm_supporting_text": llm_row[
                    "e5_supporting_text"
                ],
                # V1 left evidence blank for some exclusion decisions. Preserve
                # that absence and flag it explicitly instead of inventing a
                # justification during review-data preparation.
                "llm_supporting_text_missing": (
                    "yes"
                    if not llm_row["e5_supporting_text"].strip()
                    else "no"
                ),
                "direction": (
                    f"human_{human_row['e5_decision']}"
                    f"__llm_{llm_row['e5_decision']}"
                ),
                "human_evidence_location": audit_row[
                    "human_evidence_location"
                ],
                "excerpt_truncated": audit_row["excerpt_truncated"],
                "review_status": "not_started",
                "independent_reassessment": "",
                "rule_at_issue": "",
                "input_issue": "",
                "error_mechanism": "",
                "human_label_review": "",
                "recommended_action": "",
                "few_shot_candidate": "",
                "review_evidence": "",
                "review_notes": "",
                "reviewer_id": "",
                "reviewed_at": "",
            }
        )

    return review_rows


def main() -> None:
    """Write the review dataset and report its fixed inclusion count."""
    rows = build_review_rows()
    if len(rows) != 48:
        raise RuntimeError(
            "Expected 48 hard E5 disagreements from the frozen v1 audit, "
            f"found {len(rows)}. Investigate source-version drift."
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(rows)} hard E5 disagreements -> {OUT}")


if __name__ == "__main__":
    main()
