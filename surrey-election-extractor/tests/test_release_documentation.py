"""Regression checks that prevent release documentation drifting from data."""

from pathlib import Path

from election_extractor.candidate_continuity_evidence import (
    evidence_by_candidate_key,
    load_candidate_continuity_evidence,
)
from election_extractor.master_database import build_master_database, load_audited_elections
from election_extractor.no_news_baseline import build_no_news_electoral_baseline
from election_extractor.no_news_party_contest import build_no_news_party_contests
from scripts.generate_master_election_database import (
    reviewed_geographic_mapping_rows,
    reviewed_historical_reference_inputs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _release_payload():
    """Build the same reviewed payload used by the release generators."""

    elections = load_audited_elections()
    division_references, party_references = reviewed_historical_reference_inputs()
    return build_master_database(
        elections,
        geographic_mapping=reviewed_geographic_mapping_rows(),
        historical_division_references=division_references,
        party_history_references=party_references,
        candidate_continuity_evidence=evidence_by_candidate_key(
            load_candidate_continuity_evidence(
                permitted_election_ids=(
                    election.configuration.election_id for election in elections
                )
            )
        ),
    )


def test_release_documents_match_current_master_counts() -> None:
    """Fail when key supervisor-facing coverage claims become stale."""

    payload = _release_payload()
    summary = payload.audit_summary
    texts = "\n".join(
        (PROJECT_ROOT / path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/election_data_readiness_audit.md",
            "docs/supervisor_field_coverage_matrix.md",
            "docs/historical_longitudinal_field_provenance_audit.md",
            "docs/no_news_electoral_baseline.md",
        )
    )

    assert f"{summary['geographic_mapping_rows']} reviewed" in texts
    assert f"{summary['approved_historical_reference_rows']} approved" in texts
    assert (
        f"{summary['candidate_rows_with_previous_party_vote_share']:,}/"
        f"{summary['candidate_rows']:,}"
    ) in texts
    assert f"{summary['candidate_rows_with_derived_final_position']:,}" in texts
    assert (
        f"{summary['candidate_previously_stood_true']:,} True; "
        f"{summary['candidate_previously_stood_false']:,} False; "
        f"{summary['candidate_previously_stood_unknown']:,} Unknown"
    ) in texts


def test_no_news_documentation_matches_export_coverage() -> None:
    """Keep the model-readiness boundary tied to the generated baseline."""

    payload = _release_payload()
    _, coverage = build_no_news_electoral_baseline(payload)
    text = (PROJECT_ROOT / "docs/no_news_electoral_baseline.md").read_text(
        encoding="utf-8"
    )

    assert f"{coverage['division_rows']} rows" in text
    assert f"{coverage['baseline_approved_historical_reference']} rows have" in text
    assert f"{coverage['baseline_no_approved_predecessor']} rows visibly" in text
    assert (
        f"{coverage['previous_turnout_official_result_page']} prior-turnout"
        in text
    )
    assert (
        f"{coverage['previous_turnout_supplementary_official_evidence']} "
        "prior-turnout"
        in text
    )


def test_party_contest_documentation_matches_release_coverage() -> None:
    """Keep the modelling-cohort claims tied to generated party rows."""

    payload = _release_payload()
    features, targets, coverage = build_no_news_party_contests(payload)
    text = (PROJECT_ROOT / "docs/no_news_electoral_baseline.md").read_text(
        encoding="utf-8"
    )

    assert len(features) == len(targets) == coverage["party_contest_rows"]
    for key in (
        "party_contest_rows",
        "structure_single_member",
        "previous_party_vote_share_available",
        "eligibility_eligible_primary_single_member_party_share",
        "eligibility_excluded_no_approved_historical_area_reference",
        "eligibility_excluded_no_approved_exact_label_previous_party_share",
        "structure_multi_member",
    ):
        assert f"{coverage[key]:,}" in text
