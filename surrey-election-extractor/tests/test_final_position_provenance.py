"""Regression tests for the read-only final-position provenance audit."""

import importlib.util
from pathlib import Path


# The project's command-line scripts are intentionally not installed as an
# application package. Load this one by its repository path so the test checks
# the real executable without changing that project structure.
SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_final_position_provenance.py"
SPEC = importlib.util.spec_from_file_location("audit_final_position_provenance", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT_MODULE)

ELECTION_AUDITS = AUDIT_MODULE.ELECTION_AUDITS
_candidate_headers = AUDIT_MODULE._candidate_headers
_final_position_conclusion = AUDIT_MODULE._final_position_conclusion


def test_final_position_audit_covers_every_principal_election_dataset() -> None:
    """The conclusion must not be based solely on the 2017/2021 baseline years."""

    assert tuple(ELECTION_AUDITS) == (
        "Surrey County Council Election 2013",
        "Surrey County Council Election 2017",
        "Surrey County Council Election 2021",
        "East Surrey Council Election 2026",
        "West Surrey Council Election 2026",
    )


def test_candidate_table_without_rank_does_not_create_final_position() -> None:
    """Display order is not a substitute for a published ranking field."""

    headers, position_headers, table_count = _candidate_headers(
        """
        <table>
          <tr><th>Election Candidate</th><th>Party</th><th>Votes</th><th>%</th><th>Outcome</th></tr>
          <tr><td>Candidate A</td><td>Example</td><td>100</td><td>60%</td><td>Elected</td></tr>
        </table>
        """
    )

    assert headers == (("Election Candidate", "Party", "Votes", "%", "Outcome"),)
    assert position_headers == ()
    assert table_count == 1


def test_candidate_table_with_published_rank_is_detected() -> None:
    """A real position header remains available for a future official source."""

    _, position_headers, table_count = _candidate_headers(
        """
        <table>
          <tr><th>Candidate</th><th>Party</th><th>Votes</th><th>Position</th></tr>
          <tr><td>Candidate A</td><td>Example</td><td>100</td><td>1</td></tr>
        </table>
        """
    )

    assert position_headers == ("position",)
    assert table_count == 1


def test_unavailable_page_does_not_prove_final_position_is_absent() -> None:
    """A blocked request must produce an honest inconclusive audit result."""

    conclusion = _final_position_conclusion(
        [{"page_classification": "unavailable"}],
        [],
    )

    assert conclusion.startswith("Inconclusive:")
