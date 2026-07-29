"""Tests for the Streamlit app.

Two layers. The first covers what the app does *before* it renders: the CLI
command it builds, the workbook validation it performs, and the loaders'
behaviour when a bundle is absent. Those are the parts that can be wrong in a
way that misleads somebody rather than merely looking wrong.

The second runs every page through Streamlit's own ``AppTest`` and asserts
that none raised. Layout is not asserted - that would test Streamlit - but
"does this page still render against the bundle on disk" is a real question,
and it is the one a manual click-through answers slowly and only once.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook
from streamlit.testing.v1 import AppTest

from app.loaders import REQUIRED_SHEETS, load_bundle, load_csv, validate_workbook
from app.views import _training_command


def base_choices(**overrides) -> dict:
    choices = {
        "mode": "auto",
        "material_improvement": 0.05,
        "max_adverse_folds": 1,
        "seed": 20260728,
        "bootstrap_resamples": 2000,
        "reform_interactions": True,
        "ukip_interactions": False,
        "output_directory": "outputs/model_bundle_v1",
    }
    choices.update(overrides)
    return choices


# ---------------------------------------------------------------------------
# The command the app runs
# ---------------------------------------------------------------------------


def test_default_choices_produce_an_automatic_run():
    command = _training_command(base_choices())
    assert "train" in command
    assert "--architecture" not in command
    assert "--ukip-interactions" not in command
    assert "--no-reform-interactions" not in command


def test_manual_architecture_reaches_the_command():
    command = _training_command(base_choices(mode="C_partial_pooling"))
    assert command[command.index("--architecture") + 1] == "C_partial_pooling"


def test_ukip_and_reform_switches_reach_the_command():
    command = _training_command(
        base_choices(ukip_interactions=True, reform_interactions=False))
    assert "--ukip-interactions" in command
    assert "--no-reform-interactions" in command


def test_seed_and_resamples_reach_the_command():
    command = _training_command(base_choices(seed=7, bootstrap_resamples=50))
    assert command[command.index("--seed") + 1] == "7"
    assert command[command.index("--bootstrap-resamples") + 1] == "50"


def test_output_directory_reaches_the_command():
    """The sidebar directory must win, or a run writes into the wrong bundle."""

    command = _training_command(base_choices(output_directory="outputs/elsewhere"))
    assert command[command.index("--output") + 1] == "outputs/elsewhere"


# ---------------------------------------------------------------------------
# Workbook validation
# ---------------------------------------------------------------------------


def workbook_bytes(sheets: dict[str, list[str]]) -> io.BytesIO:
    book = Workbook()
    book.remove(book.active)
    for name, headers in sheets.items():
        sheet = book.create_sheet(title=name)
        if headers:
            sheet.append(headers)
            sheet.append(["x"] * len(headers))
    buffer = io.BytesIO()
    book.save(buffer)
    buffer.seek(0)
    return buffer


def complete_sheets() -> dict[str, list[str]]:
    return {name: list(fields) or ["placeholder"]
            for name, fields in REQUIRED_SHEETS.items()}


def test_a_complete_workbook_passes():
    result = validate_workbook(workbook_bytes(complete_sheets()))
    assert result["passed"], result


def test_a_missing_sheet_is_reported():
    sheets = complete_sheets()
    del sheets["Geographic Mapping"]
    result = validate_workbook(workbook_bytes(sheets))
    assert not result["passed"]
    assert "Geographic Mapping" in result["missing_sheets"]


def test_a_missing_field_is_reported_without_hiding_the_others():
    sheets = complete_sheets()
    sheets["Candidate Results"] = [
        f for f in sheets["Candidate Results"] if f != "analysis_vote_share"
    ]
    result = validate_workbook(workbook_bytes(sheets))
    assert not result["passed"]
    assert result["missing_fields"]["Candidate Results"] == ["analysis_vote_share"]
    # The rest of the workbook still reported, rather than the run stopping.
    assert "Elections" not in result["missing_fields"]


def test_convenience_sheets_are_flagged_when_present():
    """The brief warns these must not be appended to Candidate Results."""

    sheets = complete_sheets()
    sheets["2026 East Surrey"] = ["election_id"]
    result = validate_workbook(workbook_bytes(sheets))
    assert result["convenience_sheets_present"] == ["2026 East Surrey"]


def test_an_unreadable_upload_is_reported_not_raised():
    result = validate_workbook(io.BytesIO(b"this is not a workbook"))
    assert "error" in result


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def test_loading_an_absent_bundle_returns_none_rather_than_raising():
    """A missing bundle is a normal state the app must render around."""

    assert load_bundle("outputs/a_bundle_that_does_not_exist") is None


def test_loading_an_absent_csv_returns_an_empty_list():
    assert load_csv("outputs/nothing/here.csv") == []


# ---------------------------------------------------------------------------
# Every page renders
# ---------------------------------------------------------------------------
#
# Streamlit's own AppTest runs the app headlessly and records any exception a
# page raised. This is the check that a manual click-through can only
# approximate: it covers all six pages, on every test run, against the bundle
# actually on disk.


APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")

PAGE_LABELS = (
    "1 · Upload and validation",
    "2 · Model configuration",
    "3 · Training",
    "4 · Results",
    "5 · Explainability",
    "6 · Export",
)


def run_page(label: str):
    """Render one page and return the finished AppTest."""

    app = AppTest.from_file(APP, default_timeout=120)
    app.run()
    app.sidebar.radio[0].set_value(label).run()
    return app


@pytest.mark.parametrize("label", PAGE_LABELS)
def test_page_renders_without_raising(label):
    app = run_page(label)
    assert not app.exception, [str(error) for error in app.exception]
    # A page that renders nothing has not really rendered.
    assert app.header, f"{label} produced no header"


def test_the_six_pages_are_the_six_the_brief_names():
    app = AppTest.from_file(APP, default_timeout=120)
    app.run()
    assert tuple(app.sidebar.radio[0].options) == PAGE_LABELS


def test_holdout_pages_carry_the_blinding_disclosure():
    """A 2026 figure must never look like one that came from anywhere else."""

    app = run_page("4 · Results")
    captions = " ".join(element.value for element in app.caption)
    assert "reported rather than blind" in captions


def test_explainability_page_carries_the_causal_warning():
    app = run_page("5 · Explainability")
    warnings = " ".join(element.value for element in app.warning)
    assert "not causal effects" in warnings


def test_export_page_offers_the_bundle_as_one_download():
    app = run_page("6 · Export")
    assert not app.exception, [str(error) for error in app.exception]
