"""Regression checks that prevent release documentation drifting from data."""

from pathlib import Path

from election_extractor.candidate_continuity_evidence import (
    evidence_by_candidate_key,
    load_candidate_continuity_evidence,
)
from election_extractor.master_database import build_master_database, load_audited_elections
from election_extractor.no_news_baseline import build_no_news_electoral_baseline
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


def test_current_counts_present_in_each_core_document() -> None:
    """Require each core document to carry the current headline counts itself.

    The union check above cannot tell which document a matching string came
    from, so a document left on an earlier release's figures could still pass
    as long as some other file carried the current value.  This check pins the
    headline counts to each document individually.
    """

    payload = _release_payload()
    summary = payload.audit_summary
    events = summary["elections_loaded"]
    areas = summary["division_rows"]
    rows = f"{summary['candidate_rows']:,}"
    approved = summary["approved_historical_reference_rows"]
    previous_share = f"{summary['candidate_rows_with_previous_party_vote_share']:,}"

    required_by_document = {
        "docs/election_data_readiness_audit.md": (
            f"{events} election events",
            f"{rows} candidate rows and {areas} division or ward rows",
            f"{approved} approved historical references",
            f"{previous_share}/{rows} candidate rows",
        ),
        "docs/supervisor_field_coverage_matrix.md": (
            f"{events} elections, {areas} areas and {rows} candidate rows",
            f"{events}/{events} events",
            f"{approved}/{areas} areas",
            f"{previous_share}/{rows} candidate rows",
            f"{summary['candidate_previously_stood_true']:,} True; "
            f"{summary['candidate_previously_stood_false']:,} False; "
            f"{summary['candidate_previously_stood_unknown']:,} Unknown",
        ),
        "docs/historical_longitudinal_field_provenance_audit.md": (
            f"{approved} approved predecessor relations",
            f"{previous_share}/{rows} candidate rows",
        ),
    }

    for path, required in required_by_document.items():
        text = (PROJECT_ROOT / path).read_text(encoding="utf-8")
        for needle in required:
            assert needle in text, f"{path} is missing the current count {needle!r}"


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

