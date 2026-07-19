"""Create the reproducible Electoral Fundamentals Feature Table release.

The release is built once in memory and then serialised into three consistent
CSV files plus a Markdown quality report.  Predictor and realised-outcome
columns are kept in separate allow-lists so current results cannot enter the
matrix later supplied to a no-news model.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from no_news_baseline.electoral_fundamentals_builder import (
    CONSTRUCTION_COLUMNS,
    build_electoral_fundamentals_features,
)
from no_news_baseline.electoral_fundamentals_rows import load_party_feature_rows
from no_news_baseline.electoral_fundamentals_report import render_quality_report
from no_news_baseline.electoral_fundamentals_schema import (
    EVALUATION_COLUMNS,
    IDENTIFIER_COLUMNS,
    PREDICTOR_COLUMNS,
    PROVENANCE_COLUMNS,
    ROW_KEY_COLUMNS,
)


# Fixed publication order prevents accidental column drift between reruns.
FULL_FEATURE_COLUMNS = (
    IDENTIFIER_COLUMNS
    + PREDICTOR_COLUMNS
    + PROVENANCE_COLUMNS
    + tuple(sorted(CONSTRUCTION_COLUMNS))
    + EVALUATION_COLUMNS
)
PREDICTORS_ONLY_COLUMNS = IDENTIFIER_COLUMNS + PREDICTOR_COLUMNS

DICTIONARY_COLUMNS = (
    "field_name",
    "role",
    "data_type",
    "definition",
    "temporal_availability",
    "source",
    "missing_value_policy",
    "allowed_in_no_news_model",
)

DEFAULT_METADATA_PATH = (
    Path(__file__).resolve().parents[1] / "config/electoral_feature_metadata.csv"
)

# Increment this label only when a published construction or evaluation method
# changes. Input hashes alone cannot distinguish two methods run on the same
# official data, so the quality report records both dimensions.
RELEASE_METHOD_VERSION = "electoral-fundamentals-v4-independent-null-semantics"


def create_electoral_fundamentals_release(
    feature_path: Path,
    target_path: Path,
    master_path: Path,
    overlap_path: Path,
    output_directory: Path,
    generated_at: datetime | None = None,
    metadata_path: Path = DEFAULT_METADATA_PATH,
) -> tuple[Path, Path, Path, Path]:
    """Build the table once and write the complete four-file release package."""

    party_features = load_party_feature_rows(feature_path)
    master = _load_json_object(master_path)
    overlap = _load_json_object(overlap_path)
    targets = _load_rows_payload(target_path)
    rows = build_electoral_fundamentals_features(party_features, master, overlap)
    candidates = _payload_table(master, "Candidate Results")
    released_rows = _attach_evaluation_columns(rows, targets, candidates)

    output_directory.mkdir(parents=True, exist_ok=True)
    full_path = output_directory / "electoral_fundamentals_features.csv"
    predictors_path = output_directory / "electoral_fundamentals_predictors_only.csv"
    dictionary_path = output_directory / "electoral_feature_dictionary.csv"
    report_path = output_directory / "electoral_fundamentals_data_quality.md"

    _write_csv(full_path, released_rows, FULL_FEATURE_COLUMNS)
    _write_csv(predictors_path, released_rows, PREDICTORS_ONLY_COLUMNS)
    _write_csv(
        dictionary_path,
        load_feature_dictionary(metadata_path),
        DICTIONARY_COLUMNS,
    )
    report_path.write_text(
        render_quality_report(
            released_rows,
            (feature_path, target_path, master_path, overlap_path),
            generated_at or datetime.now(UTC),
            RELEASE_METHOD_VERSION,
        ),
        encoding="utf-8",
    )
    return full_path, predictors_path, dictionary_path, report_path


def load_feature_dictionary(
    metadata_path: Path = DEFAULT_METADATA_PATH,
) -> tuple[dict[str, object], ...]:
    """Read and validate the human-reviewable field metadata table.

    Definitions live in CSV because they are research documentation rather
    than calculation code. Strict validation still makes the metadata part of
    the executable release contract: a missing, reordered or misclassified
    field stops publication instead of producing a misleading dictionary.
    """

    with metadata_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != DICTIONARY_COLUMNS:
            raise ValueError("Feature metadata has an invalid column schema.")
        rows = tuple(dict(row) for row in reader)

    fields = tuple(str(row["field_name"]) for row in rows)
    if fields != FULL_FEATURE_COLUMNS:
        raise ValueError("Feature metadata must document released columns in order.")
    for row in rows:
        field = str(row["field_name"])
        expected_role, expected_model_use = _expected_dictionary_role(field)
        if row["role"] != expected_role:
            raise ValueError(f"Feature metadata has the wrong role for {field!r}.")
        if row["allowed_in_no_news_model"] != expected_model_use:
            raise ValueError(f"Feature metadata has invalid model use for {field!r}.")
        if any(not str(row[column]).strip() for column in DICTIONARY_COLUMNS):
            raise ValueError(f"Feature metadata is incomplete for {field!r}.")
    return rows


def _expected_dictionary_role(field: str) -> tuple[str, str]:
    """Derive roles from the central schema rather than trusting CSV labels."""

    if field in IDENTIFIER_COLUMNS:
        return "identifier", "No"
    if field in PREDICTOR_COLUMNS:
        return "predictor", "Yes"
    if field in PROVENANCE_COLUMNS or field in CONSTRUCTION_COLUMNS:
        return "provenance", "No"
    if field in EVALUATION_COLUMNS:
        return "evaluation", "No"
    raise ValueError(f"Undeclared feature metadata field: {field!r}.")


def _attach_evaluation_columns(
    rows: Sequence[Mapping[str, object]],
    targets: Sequence[Mapping[str, object]],
    candidates: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Join target outcomes only after every predictor has been constructed.

    Single-member shares come from the extractor target contract. For a
    multi-member ward there is no separate party ballot: voters cast candidate
    votes and may use fewer votes than vacancies. The primary party outcome
    therefore follows the conventional UK reporting rule documented in House
    of Commons Standard Note SN05064: take each party's best-placed candidate
    and normalise those party values within the ward. An average-candidate
    alternative discussed by Ware et al. (Electoral Studies, 2006,
    doi:10.1016/j.electstud.2005.04.003) is released for sensitivity analysis.
    """

    by_id: dict[str, Mapping[str, object]] = {}
    for target in targets:
        contest_id = str(target.get("party_contest_id", ""))
        if not contest_id or contest_id in by_id:
            raise ValueError("Target contract contains a missing or duplicate party_contest_id.")
        by_id[contest_id] = target

    used_ids: set[str] = set()
    multi_member_shares = _multi_member_party_shares(rows, candidates)
    released: list[dict[str, object]] = []
    for row in rows:
        source_ids = tuple(str(value) for value in row["source_party_contest_ids"])
        components = []
        for source_id in source_ids:
            if source_id not in by_id:
                raise ValueError(f"No evaluation target for source row {source_id!r}.")
            components.append(by_id[source_id])
            used_ids.add(source_id)
        outcomes = _aggregate_targets(components)
        if int(row["number_of_seats"]) > 1:
            key = tuple(str(row[column]) for column in ROW_KEY_COLUMNS)
            primary_share, sensitivity_share = multi_member_shares[key]
            outcomes.update(
                {
                    "evaluation_current_party_vote_share": primary_share,
                    "evaluation_party_vote_share_method": (
                        "multi_member_best_placed_candidate_normalised"
                    ),
                    "evaluation_current_party_vote_share_average_candidate_sensitivity": sensitivity_share,
                    "evaluation_party_vote_share_sensitivity_gap_pp": abs(
                        primary_share - sensitivity_share
                    ),
                }
            )
        else:
            current_share = outcomes["evaluation_current_party_vote_share"]
            outcomes.update(
                {
                    "evaluation_party_vote_share_method": (
                        "single_member_candidate_share"
                        if current_share is not None
                        else None
                    ),
                    "evaluation_current_party_vote_share_average_candidate_sensitivity": current_share,
                    "evaluation_party_vote_share_sensitivity_gap_pp": (
                        0.0 if current_share is not None else None
                    ),
                }
            )
        released.append({**row, **outcomes})

    if used_ids != set(by_id):
        raise ValueError("Feature and target contracts do not contain identical source IDs.")
    return tuple(released)


def _multi_member_party_shares(
    rows: Sequence[Mapping[str, object]],
    candidates: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, str], tuple[float, float]]:
    """Calculate primary and sensitivity shares from complete candidate votes.

    Both definitions are normalised separately within a ward, so each set of
    party shares sums to 100%. Votes are never averaged or summed across wards.
    Generic Independent records follow the declared standardised-party row
    unit and retain their component IDs for audit in the full release.
    """

    multi_area_keys = {
        (str(row["election_id"]), str(row["area_id"]))
        for row in rows
        if int(row["number_of_seats"]) > 1
    }
    votes_by_party: dict[tuple[str, str], dict[str, list[float]]] = {}
    for candidate in candidates:
        area_key = (
            str(candidate.get("election_id")),
            str(candidate.get("division_id")),
        )
        if area_key not in multi_area_keys:
            continue
        party = candidate.get("standard_party_name")
        votes = candidate.get("votes")
        if not isinstance(party, str) or not party:
            raise ValueError("Multi-member candidate has no standardised party name.")
        if not isinstance(votes, (int, float)) or isinstance(votes, bool) or votes < 0:
            raise ValueError("Multi-member party-share calculation requires complete votes.")
        votes_by_party.setdefault(area_key, {}).setdefault(party, []).append(float(votes))

    output: dict[tuple[str, str, str], tuple[float, float]] = {}
    for area_key in sorted(multi_area_keys):
        parties = votes_by_party.get(area_key)
        if not parties:
            raise ValueError(f"No candidate votes found for multi-member area {area_key!r}.")
        top_votes = {party: max(votes) for party, votes in parties.items()}
        average_votes = {
            party: sum(votes) / len(votes) for party, votes in parties.items()
        }
        top_total = sum(top_votes.values())
        average_total = sum(average_votes.values())
        if top_total <= 0 or average_total <= 0:
            raise ValueError("Multi-member party-share denominator must be positive.")
        for party in parties:
            output[(*area_key, party)] = (
                100.0 * top_votes[party] / top_total,
                100.0 * average_votes[party] / average_total,
            )

    expected_keys = {
        tuple(str(row[column]) for column in ROW_KEY_COLUMNS)
        for row in rows
        if int(row["number_of_seats"]) > 1
    }
    if set(output) != expected_keys:
        raise ValueError("Multi-member candidate votes do not match released party rows.")
    return output


def _aggregate_targets(
    components: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Aggregate component records without selecting an arbitrary candidate.

    Multiple records occur only where several candidates share a standardised
    party/category label. Vote shares and seats are summed only when every
    component is defined; otherwise the party-level evaluation remains NULL.
    """

    shares = [item.get("target_party_vote_share") for item in components]
    seats = [item.get("target_party_seats_won") for item in components]
    elected = [item.get("target_party_elected") for item in components]
    urls = sorted(
        {
            str(url).strip()
            for item in components
            for url in str(item.get("target_source_urls") or "").split("|")
            if url.strip()
        }
    )
    return {
        "evaluation_current_party_vote_share": _sum_if_complete(shares),
        # The electoral-system-specific method and sensitivity fields are
        # assigned by _attach_evaluation_columns after this outcome join.
        "evaluation_party_vote_share_method": None,
        "evaluation_current_party_vote_share_average_candidate_sensitivity": None,
        "evaluation_party_vote_share_sensitivity_gap_pp": None,
        "evaluation_current_party_was_winner": (
            any(value == "Yes" for value in elected)
            if all(value in {"Yes", "No"} for value in elected)
            else None
        ),
        "evaluation_current_party_seats_won": _sum_if_complete(seats),
        "evaluation_source_urls": tuple(urls) or None,
    }


def _sum_if_complete(values: Sequence[object]) -> int | float | None:
    if not values or any(value is None or isinstance(value, bool) for value in values):
        return None
    if not all(isinstance(value, (int, float)) for value in values):
        raise ValueError("Evaluation target contains a non-numeric value.")
    return sum(values)  # type: ignore[arg-type]


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    columns: Sequence[str],
) -> None:
    """Write UTF-8 CSV with stable columns and unambiguous NULL cells."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    column: _serialise_value(row.get(column), column)
                    for column in columns
                }
            )


def _serialise_value(value: object, field: str) -> object:
    """Apply the fixed NULL, boolean, date, list and numeric CSV formats."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if field in {"election_date", "previous_election_date"}:
        # Extractor contracts retain both ISO dates and published long-form
        # dates. The release normalises both without changing their meaning.
        for date_format in ("%Y-%m-%d", "%d %B %Y"):
            try:
                return datetime.strptime(str(value), date_format).date().isoformat()
            except ValueError:
                continue
        raise ValueError(f"Unsupported release date in {field}: {value!r}.")
    if isinstance(value, (tuple, list)):
        return "|".join(str(item) for item in value)
    if isinstance(value, float):
        return format(value, ".12g")
    return value


def _load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON input must be an object: {path}.")
    return payload


def _load_rows_payload(path: Path) -> tuple[dict[str, object], ...]:
    payload = _load_json_object(path)
    rows = payload.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"JSON input must contain a rows list: {path}.")
    return tuple(rows)


def _payload_table(
    payload: Mapping[str, object], table_name: str
) -> tuple[Mapping[str, object], ...]:
    """Return a required master-payload table with its basic shape checked."""

    table = payload.get(table_name)
    if not isinstance(table, list) or not all(isinstance(row, dict) for row in table):
        raise ValueError(f"Master payload table is missing or invalid: {table_name!r}.")
    return tuple(table)
