"""Build read-only policies for supplementary Surrey election metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final


SURREY_NEWS_URL: Final = "https://news.surreycc.gov.uk/2013/05/03/election-results-special/"
ELECTORAL_COMMISSION_URL: Final = (
    "https://www.electoralcommission.org.uk/research-reports-and-data/"
    "our-reports-and-data-past-elections-and-referendums/"
    "results-and-turnout-may-2017-england-local-elections"
)
WOKING_RESULTS_URL: Final = (
    "https://www.woking.gov.uk/sites/default/files/documents/"
    "council-and-democracy/elections/ElectionResults/resultsscc.pdf"
)
WIKIPEDIA_URL: Final = "https://en.wikipedia.org/wiki/2013_Surrey_County_Council_election"


def source_evaluations() -> list[dict[str, object]]:
    """Return only sources inspected for the bounded pre-extraction audit."""

    return [
        {
            "source_name": "Surrey News: Election results declared",
            "source_type": "Surrey County Council official publication",
            "source_url": SURREY_NEWS_URL,
            "fields_provided": ["overall_turnout", "division_turnout"],
            "geographic_level": "Surrey-wide summary and named divisions",
            "evidence_text": (
                "The votes have been counted in all 81 divisions for the 2013 Surrey "
                "County Council elections; Turnout 30%. The article also gives named "
                "division result entries with turnout, for example ‘RESULT – WORPLESDON’ "
                "followed by ‘Turnout 32%’."
            ),
            "reliability_assessment": "High: published by Surrey County Council.",
            "use_decision": (
                "Use the 30% value only as supplementary election-level turnout. "
                "A future division-by-division evidence audit may use named turnout "
                "entries as supplementary metadata, but this audit does not bulk-load them."
            ),
        },
        {
            "source_name": "Electoral Commission: Results and turnout at the May 2017 England local elections",
            "source_type": "Electoral Commission official report",
            "source_url": ELECTORAL_COMMISSION_URL,
            "fields_provided": ["overall_turnout"],
            "geographic_level": "Surrey-wide",
            "evidence_text": (
                "Table 3.2 lists Surrey ballot-box turnout as 30.0% for 2013 and "
                "35.8% for 2017."
            ),
            "reliability_assessment": "High: statutory electoral authority; independently corroborates the Surrey Council rounded 30% summary.",
            "use_decision": (
                "Use as corroborating supplementary election-level evidence only; "
                "it does not identify individual Surrey divisions."
            ),
        },
        {
            "source_name": "Woking Borough Council: Election of Councillors",
            "source_type": "Official local authority / Deputy Returning Officer document",
            "source_url": WOKING_RESULTS_URL,
            "fields_provided": [
                "division_turnout",
                "ballot_papers_issued",
                "electorate",
                "seats",
                "candidate_results",
            ],
            "geographic_level": "Named Woking Surrey County Council divisions only",
            "evidence_text": (
                "The PDF gives named division summaries, for example Knaphill & Goldsworth West: "
                "‘Vacant Seats: 1 Electorate: 11,021 Ballot Papers Issued: 3,642 Turnout: 33.05%’."
            ),
            "reliability_assessment": "High for the named Woking divisions; not a Surrey-wide source.",
            "use_decision": (
                "A future exact division-name match may store turnout or ballot papers issued "
                "as supplementary division metadata for named Woking divisions only. It must "
                "not replace the official Surrey result-page fields or be generalised to other divisions."
            ),
        },
        {
            "source_name": "Wikipedia: 2013 Surrey County Council election",
            "source_type": "Wikipedia secondary source",
            "source_url": WIKIPEDIA_URL,
            "fields_provided": ["election_date", "county_seat_total", "party_summary", "division_turnout"],
            "geographic_level": "Election-wide and division tables",
            "evidence_text": (
                "The page describes the election date and presents election and division summaries."
            ),
            "reliability_assessment": "Lower than Electoral Commission and official council publications.",
            "use_decision": (
                "Do not use. Higher-priority official sources exist for the audited election-level "
                "information, and the project policy does not permit Wikipedia for division-level replacement."
            ),
        },
    ]


def field_policies() -> list[dict[str, object]]:
    """Define storage choices without assigning any secondary value to official data."""

    return [
        {
            "field": "election_name",
            "level": "election",
            "official_status": "Available from the configured official archive context.",
            "can_be_supplemented": False,
            "recommended_storage_location": "official election-level configuration field",
            "policy": "Do not add a secondary value.",
        },
        {
            "field": "election_date",
            "level": "election",
            "official_status": "Published in the official archive/result-page context as 2 May 2013.",
            "can_be_supplemented": False,
            "recommended_storage_location": "official election-level field",
            "policy": "Do not add a secondary value.",
        },
        {
            "field": "authority",
            "level": "election",
            "official_status": "Published by official result pages as Surrey County Council; absent from the current declarative configuration.",
            "can_be_supplemented": False,
            "recommended_storage_location": "official election-level field when sourced from an official page",
            "policy": "Do not treat an external source as a replacement for the missing configuration entry.",
        },
        {
            "field": "overall_turnout",
            "level": "election",
            "official_status": "Not published as an overall value in representative individual official result pages.",
            "can_be_supplemented": True,
            "recommended_storage_location": "supplementary election metadata field",
            "recommended_value": "30%",
            "policy": (
                "Store only as secondary_election_turnout with separate source URL, evidence text, "
                "geographic level and confidence. Do not copy it to any division turnout field."
            ),
        },
        {
            "field": "turnout",
            "level": "division",
            "official_status": "Not published in the three representative official Surrey result-page Voting Summary tables.",
            "can_be_supplemented": "conditionally",
            "recommended_storage_location": "supplementary division metadata field, otherwise remain missing",
            "policy": (
                "Only store a value after the source identifies the same division and preserves an exact "
                "supporting passage. Never propagate the 30% Surrey-wide turnout to divisions."
            ),
        },
        {
            "field": "ballot_papers_issued",
            "level": "division",
            "official_status": "Not published in the three representative official Surrey result-page Voting Summary tables.",
            "can_be_supplemented": "conditionally",
            "recommended_storage_location": "supplementary division metadata field, otherwise remain missing",
            "policy": (
                "The Woking document may support named Woking divisions after exact matching. "
                "No Surrey-wide value or inferred calculation is permitted."
            ),
        },
        {
            "field": "rejected_ballots",
            "level": "division",
            "official_status": "Published in the representative official Surrey result-page Voting Summary tables.",
            "can_be_supplemented": False,
            "recommended_storage_location": "official division-level field",
            "policy": "Retain the published official value; any unreported division remains missing.",
        },
        {
            "field": "seats",
            "level": "division",
            "official_status": "Published in the representative official Surrey result-page Voting Summary tables.",
            "can_be_supplemented": False,
            "recommended_storage_location": "official division-level field",
            "policy": "Retain the published official value; never infer seats from the election year or candidate count.",
        },
        {
            "field": "candidate_name, original_party_name, votes, vote_share, outcome",
            "level": "candidate",
            "official_status": "Published in representative official Surrey result-page candidate tables.",
            "can_be_supplemented": False,
            "recommended_storage_location": "official candidate-level fields",
            "policy": "Never replace official candidate-level values with a secondary source.",
        },
    ]


def build_2013_supplementary_metadata_audit() -> dict[str, object]:
    """Build a policy report only; it does not integrate metadata into any record."""

    sources = source_evaluations()
    policies = field_policies()
    return {
        "audit_title": "2013 Surrey County Council Supplementary Metadata Audit",
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": (
            "Pre-extraction source and storage-policy audit. No full candidate extraction, "
            "field replacement, calculation or pipeline integration was performed."
        ),
        "data_principle": {
            "official_data": "Values directly published by Surrey official individual result pages.",
            "supplementary_metadata": "Approved external or separate official-document evidence stored in distinct metadata fields.",
            "prohibition": "Supplementary evidence never overwrites an official field or converts a missing official value into a published value.",
        },
        "source_evaluations": sources,
        "field_policies": policies,
        "approved_supplementary_policy": {
            "election_level_turnout": {
                "value": "30%",
                "storage": "secondary_election_turnout",
                "confidence": "High",
                "primary_evidence_source": SURREY_NEWS_URL,
                "corroborating_source": ELECTORAL_COMMISSION_URL,
                "restriction": "Election-wide only; not copied to any division record.",
            },
            "division_level_values": {
                "status": "Not integrated by this audit.",
                "restriction": (
                    "Each value requires a named division, exact evidence text, source URL and a separate "
                    "supplementary field before it can be added."
                ),
            },
        },
        "candidate_data_policy": (
            "Candidate-level values remain official-result-page data only. No secondary candidate "
            "source is approved for replacement or completion."
        ),
        "wikipedia_policy": (
            "Wikipedia was evaluated but is not used because higher-priority official Council and Electoral "
            "Commission sources are available. It must not supply division-level replacements."
        ),
        "recommended_next_step": (
            "If supplementary division metadata is later required, perform a separate named-division evidence "
            "audit before integration. Do not start full 2013 extraction as part of this audit."
        ),
    }


def audit_markdown(audit: dict[str, object]) -> str:
    """Render a concise human-readable version of the policy report."""

    lines = [
        "# 2013 Surrey County Council Supplementary Metadata Audit",
        "",
        "## Scope and data principle",
        "",
        "- This is a pre-extraction source and policy audit only. No 2013 candidate extraction or metadata integration was run.",
        "- Official Surrey result-page fields remain official. Secondary evidence is stored separately and never overwrites them.",
        "",
        "## Source evaluation",
        "",
    ]
    for source in audit["source_evaluations"]:
        lines.extend(
            [
                f"### {source['source_name']}",
                "",
                f"- URL: {source['source_url']}",
                f"- Geographic level: {source['geographic_level']}",
                f"- Fields: {', '.join(source['fields_provided'])}",
                f"- Evidence: {source['evidence_text']}",
                f"- Reliability: {source['reliability_assessment']}",
                f"- Decision: {source['use_decision']}",
                "",
            ]
        )
    lines.extend(["## Field policy", ""])
    for policy in audit["field_policies"]:
        lines.extend(
            [
                f"### {policy['field']} ({policy['level']})",
                "",
                f"- Official status: {policy['official_status']}",
                f"- Can supplement: {policy['can_be_supplemented']}",
                f"- Storage: {policy['recommended_storage_location']}",
                f"- Policy: {policy['policy']}",
                "",
            ]
        )
    turnout = audit["approved_supplementary_policy"]["election_level_turnout"]
    lines.extend(
        [
            "## Approved supplementary policy",
            "",
            f"- Election-level turnout: {turnout['value']} ({turnout['confidence']} confidence), stored only as `{turnout['storage']}`.",
            f"- Restriction: {turnout['restriction']}",
            f"- {audit['candidate_data_policy']}",
            f"- {audit['wikipedia_policy']}",
            "",
            "## Recommendation",
            "",
            str(audit["recommended_next_step"]),
            "",
        ]
    )
    return "\n".join(lines)
