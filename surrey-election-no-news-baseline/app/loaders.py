"""Reading the bundle, the contract and an uploaded workbook, once each.

Why caching is not an optimisation here
---------------------------------------
Streamlit re-executes the whole script on every widget interaction. Without
caching, moving a slider would reload a 2,000-row contract, unpickle a model
and recompute SHAP - so the app would be unusable, and worse, a page could
show figures recomputed at a slightly different moment from the ones beside
them. Everything below is cached on its file path, so a page renders from one
consistent read.

Nothing here trains anything, and nothing here writes to the bundle. The app
reads what a reproducible command produced; it is a window onto the pipeline,
not a second way of running it.
"""

from __future__ import annotations

import csv
import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

# Repository root, from this file's location, so the app works whatever
# directory Streamlit was started in.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# Sheets and fields the brief names as canonical. Used only to validate an
# uploaded workbook: the app never extracts from it, because extraction is the
# extractor's responsibility and a second implementation would be a second
# source of truth.
REQUIRED_SHEETS: dict[str, tuple[str, ...]] = {
    "Elections": (
        "election_id", "election_name", "election_date", "election_year",
        "election_type", "authority",
    ),
    "Candidate Results": (
        "election_id", "division_id", "candidate_id", "standard_candidate_name",
        "standard_party_name", "party_category", "votes", "vote_share",
        "analysis_vote_share", "outcome", "elected_yes_no",
    ),
    "Divisions and Wards": (
        "official_number_of_seats", "electorate", "turnout", "total_votes",
    ),
    "Geographic Mapping": (
        "analytical_comparability", "historical_vote_share_status", "decision",
        "confidence", "previous_winner_allowed", "candidate_history_allowed",
        "incumbency_allowed", "party_vote_share_change_allowed",
    ),
    "Party History and New Entrants": (),
    "Analysis Voting Summary": (
        "analysis_number_of_seats", "analysis_turnout",
    ),
    "Data Dictionary": (),
}

# The brief warns that these two are convenience views and must not be
# appended to Candidate Results.
CONVENIENCE_SHEETS = ("2026 East Surrey", "2026 West Surrey")


@dataclass(frozen=True)
class Bundle:
    """One model bundle, loaded from disk."""

    directory: Path
    architecture: dict
    metrics: dict
    reform_metrics: dict
    data_quality: dict
    training_config: dict
    manifest: dict
    model_card: str

    @property
    def exists(self) -> bool:
        return self.directory.exists()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@st.cache_data(show_spinner=False)
def load_bundle(directory: str) -> Bundle | None:
    """Load a bundle's JSON artefacts, or None if it has not been built."""

    path = REPOSITORY_ROOT / directory
    if not (path / "architecture.json").exists():
        return None
    card = path / "model_card.md"
    return Bundle(
        directory=path,
        architecture=_read_json(path / "architecture.json"),
        metrics=_read_json(path / "metrics.json"),
        reform_metrics=_read_json(path / "reform_metrics.json"),
        data_quality=_read_json(path / "data_quality_report.json"),
        # Written as JSON with a .yaml name, which is valid YAML 1.2 and
        # avoids a parser dependency for a file nothing but this reads.
        training_config=_read_json(path / "training_config.yaml"),
        manifest=_read_json(path / "bundle_manifest.json"),
        model_card=card.read_text(encoding="utf-8") if card.exists() else "",
    )


@st.cache_data(show_spinner=False)
def load_csv(path_from_root: str) -> list[dict]:
    """A bundle CSV as a list of dicts. Empty list if absent."""

    path = REPOSITORY_ROOT / path_from_root
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@st.cache_data(show_spinner=False)
def load_contract(contract_directory: str) -> tuple[list[dict], dict[str, dict]]:
    """The extractor's published features and targets.

    Returned separately, exactly as published. Keeping them apart in the app
    as well as on disk means no page can accidentally show a target beside a
    predictor as though both were inputs.
    """

    base = REPOSITORY_ROOT / contract_directory
    features_path = base / "no_news_candidate_contest_features.json"
    targets_path = base / "no_news_candidate_contest_targets.json"
    if not features_path.exists():
        return [], {}
    features = json.loads(features_path.read_text(encoding="utf-8"))["rows"]
    targets = {
        str(row["candidate_contest_id"]): row
        for row in json.loads(targets_path.read_text(encoding="utf-8"))["rows"]
    } if targets_path.exists() else {}
    return features, targets


@st.cache_resource(show_spinner=False)
def load_model(directory: str) -> tuple[object, object] | None:
    """The fitted model and its encoder.

    ``cache_resource`` rather than ``cache_data`` because these are live
    objects, not serialisable values, and a LightGBM booster must not be
    copied per session.
    """

    path = REPOSITORY_ROOT / directory
    model_path, encoder_path = path / "model.pkl", path / "preprocessor.pkl"
    if not (model_path.exists() and encoder_path.exists()):
        return None
    return pickle.loads(model_path.read_bytes()), pickle.loads(encoder_path.read_bytes())


def validate_workbook(uploaded) -> dict:
    """Check an uploaded workbook's sheets and fields against the brief's list.

    This is validation, not ingestion. The app deliberately cannot build a
    modelling dataset from a workbook: that path runs through the extractor,
    which owns provenance and the evidence layers, and a second implementation
    living in a web page would be a second answer to questions that must have
    one.

    Reported findings rather than raised errors, so a workbook with one
    missing field still tells the user about the other twenty that are fine.
    """

    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover - environment dependent
        return {"error": "openpyxl is not installed, so a workbook cannot be read."}

    try:
        workbook = load_workbook(uploaded, read_only=True, data_only=True)
    except Exception as error:  # noqa: BLE001 - reported to the user
        return {"error": f"Could not open the workbook: {error}"}

    present = list(workbook.sheetnames)
    missing_sheets = [name for name in REQUIRED_SHEETS if name not in present]

    missing_fields: dict[str, list[str]] = {}
    row_counts: dict[str, int] = {}
    for sheet_name, required in REQUIRED_SHEETS.items():
        if sheet_name not in present:
            continue
        sheet = workbook[sheet_name]
        header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
        headers = {str(value).strip() for value in header_row if value is not None}
        absent = [field for field in required if field not in headers]
        if absent:
            missing_fields[sheet_name] = absent
        row_counts[sheet_name] = max((sheet.max_row or 1) - 1, 0)

    workbook.close()
    return {
        "sheets_present": present,
        "missing_sheets": missing_sheets,
        "missing_fields": missing_fields,
        "row_counts": row_counts,
        "convenience_sheets_present": [
            name for name in CONVENIENCE_SHEETS if name in present
        ],
        "passed": not missing_sheets and not missing_fields,
    }
