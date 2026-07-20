"""Application-level orchestration for one Surrey extraction request.

The Streamlit page should remain a thin user interface. This module connects
the existing provider-neutral discovery, extraction, validation and workbook
components so the complete application workflow can be tested without a web
browser or a live SerpAPI key.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from election_extractor.discovery import discover_election_areas
from election_extractor.extraction import (
    CandidateResultRecord,
    ExtractionAttempt,
    ExtractionReport,
    ExtractionStatus,
    extract_candidate_results,
)
from election_extractor.models import (
    DiscoveredElectionArea,
    DiscoveryReport,
    DiscoveryStatus,
    MetadataStatus,
)
from election_extractor.search_providers.base import SearchProvider
from election_extractor.search_providers.serpapi import (
    SearchAuthenticationError,
    SearchNetworkError,
    SearchRateLimitError,
    SearchResponseError,
    SearchTimeoutError,
    SerpApiSearchProvider,
)
from election_extractor.url_utils import normalise_area_result_url, validate_index_url
from election_extractor.validation import (
    ValidationResult,
    ValidationStatus,
    validate_election_results,
)
from election_extractor.workbook import generate_workbook


# The web page will supply a small callback that receives each progress update.
# Keeping the type here avoids importing Streamlit into the extraction code.
ProgressCallback = Callable[["WorkflowProgress"], None]


# Extraction stores only the safe exception class name in each attempt. This
# table converts a system-wide provider failure back into a useful UI message
# when the lower-level extractor has deliberately absorbed the exception for
# audit logging.
PROVIDER_FAILURE_MESSAGES = {
    SearchAuthenticationError.__name__: "The indexed-search API key was rejected.",
    SearchRateLimitError.__name__: (
        "The indexed-search rate limit was reached. Try again later."
    ),
    SearchTimeoutError.__name__: (
        "The indexed-search request timed out. Try again later."
    ),
    SearchNetworkError.__name__: (
        "The indexed-search service could not be reached. Check the connection."
    ),
    SearchResponseError.__name__: (
        "The indexed-search service returned an unusable response."
    ),
}


class WorkflowError(RuntimeError):
    """A safe application error that contains no provider credential or traceback."""


@dataclass(frozen=True)
class WorkflowProgress:
    """Provide the progress values required by the future Streamlit page."""

    # ``stage`` lets the page choose the appropriate message/progress-bar state;
    # the remaining fields provide the live numerical summary requested by the
    # supervisor without requiring the page to inspect raw extraction objects.
    stage: str
    message: str
    areas_discovered: int = 0
    current_area: str | None = None
    areas_completed: int = 0
    complete: int = 0
    incomplete: int = 0
    failed: int = 0


@dataclass(frozen=True)
class WorkflowResult:
    """Return a downloadable workbook and an auditable extraction summary."""

    # ``workbook_bytes`` is ready for st.download_button. The audit objects are
    # retained separately so the page can show evidence and validation totals.
    workbook_bytes: bytes
    filename: str
    source_type: str
    discovery: DiscoveryReport
    records: tuple[CandidateResultRecord, ...]
    extraction_attempts: tuple[ExtractionAttempt, ...]
    validations: tuple[ValidationResult, ...]
    complete: int
    incomplete: int
    failed: int

    @property
    def areas_discovered(self) -> int:
        """Expose the denominator used by the application progress display."""

        return len(self.discovery.areas)


def _notify(callback: ProgressCallback | None, progress: WorkflowProgress) -> None:
    """Keep progress reporting optional and independent of Streamlit."""

    if callback is not None:
        callback(progress)


def _raise_systemic_provider_failure(attempts: tuple[ExtractionAttempt, ...]) -> None:
    """Stop a run when retrying other areas cannot repair the provider failure."""

    for attempt in attempts:
        message = PROVIDER_FAILURE_MESSAGES.get(attempt.error or "")
        if message:
            raise WorkflowError(message)


def _source_type(source_url: str) -> tuple[str, str]:
    """Validate the submitted Surrey URL and identify its processing path."""

    # Try the narrower index-page rule first. If it does not match, test the
    # submitted value as a single official area-result page instead.
    try:
        return "index", validate_index_url(source_url)
    except ValueError:
        try:
            return "direct", normalise_area_result_url(source_url)
        except ValueError as error:
            raise WorkflowError(
                "Enter a valid Surrey election index URL or ward result URL."
            ) from error


def _direct_discovery(source_url: str) -> DiscoveryReport:
    """Represent one validated result URL without inventing missing metadata."""

    # A direct URL bypasses index discovery. Its election/area labels remain
    # explicitly missing until indexed candidate evidence publishes them.
    area = DiscoveredElectionArea(
        election_year=None,
        election_name=None,
        division_ward_name=None,
        result_url=source_url,
        source_index_url=source_url,
        discovery_status=DiscoveryStatus.MISSING_AREA_NAME,
        metadata_status=MetadataStatus.MISSING,
        missing_metadata_fields=("election_year", "election_name", "division_ward_name"),
    )
    return DiscoveryReport(source_url, (area,), ())


def _area_status(
    records: tuple[CandidateResultRecord, ...],
    validations: tuple[ValidationResult, ...],
    attempts: tuple[ExtractionAttempt, ...],
) -> str:
    """Apply the same conservative completion rules used in the workbook."""

    # A search failure or failed validation has priority over all other states.
    if any(attempt.status is ExtractionStatus.SEARCH_FAILED for attempt in attempts):
        return "Failed"
    if any(result.validation_status is ValidationStatus.FAILED for result in validations):
        return "Failed"
    # A discovered result page with no reliable candidate rows has failed the
    # extraction task. Calling it merely incomplete would understate the
    # failure and could make the application's completion count misleading.
    if not records or not validations:
        return "Failed"
    # Existing but partial evidence is Incomplete rather than Failed. This
    # distinction keeps genuine missing source values visible in the audit.
    if any(record.extraction_status is not ExtractionStatus.COMPLETE for record in records):
        return "Incomplete"
    if any(attempt.status is not ExtractionStatus.COMPLETE for attempt in attempts):
        return "Incomplete"
    if any(
        result.validation_status in {ValidationStatus.INCOMPLETE, ValidationStatus.WARNING}
        for result in validations
    ):
        return "Incomplete"
    return "Complete"


def _safe_filename(
    discovery: DiscoveryReport,
    records: tuple[CandidateResultRecord, ...],
) -> str:
    """Create a readable filename without inserting URL or credential text."""

    # Prefer metadata parsed from candidate evidence, then discovery metadata,
    # and finally a neutral fallback if the source never published a title.
    election_name = next(
        (record.election_name for record in records if record.election_name),
        None,
    ) or next(
        (area.election_name for area in discovery.areas if area.election_name),
        None,
    ) or "Surrey Election Results"
    year = next(
        (area.election_year for area in discovery.areas if area.election_year is not None),
        None,
    )
    label = f"{election_name} {year}" if year and str(year) not in election_name else election_name
    # Remove punctuation that could be unsafe or confusing in a downloaded
    # filename. No URL, search query or API credential is included.
    safe = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
    return f"{safe or 'Surrey_Election_Results'}.xlsx"


def run_extraction_workflow(
    source_url: str,
    *,
    api_key: str | None = None,
    provider: SearchProvider | None = None,
    run_targeted_searches: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> WorkflowResult:
    """Run one complete, downloadable, indexed-search extraction.

    Tests inject a provider and therefore need no live credential. The real
    application supplies the key directly to the SerpAPI adapter; it is held in
    a local object only and is never copied into the result, progress messages,
    workbook or exception text.
    """

    # Stage 1: validate and canonicalise the URL before any external request.
    source_type, canonical_url = _source_type(source_url)
    if provider is None:
        if not api_key or not api_key.strip():
            raise WorkflowError("An indexed results API key is required.")
        # The key stays inside the provider instance for this function call.
        provider = SerpApiSearchProvider(api_key=api_key.strip())

    _notify(progress_callback, WorkflowProgress("validation", "URL validated."))
    try:
        # Stage 2: an index URL expands to all discovered areas. A direct URL
        # becomes a one-area report and therefore follows the same later loop.
        discovery = (
            discover_election_areas(
                canonical_url,
                provider,
                indexed_search_only=True,
            )
            if source_type == "index"
            else _direct_discovery(canonical_url)
        )
    except SearchAuthenticationError as error:
        raise WorkflowError("The indexed-search API key was rejected.") from error
    except SearchRateLimitError as error:
        raise WorkflowError(
            "The indexed-search rate limit was reached. Try again later."
        ) from error
    except SearchTimeoutError as error:
        raise WorkflowError(
            "The indexed-search request timed out. Try again later."
        ) from error
    except SearchNetworkError as error:
        raise WorkflowError(
            "The indexed-search service could not be reached. Check the connection."
        ) from error
    except SearchResponseError as error:
        raise WorkflowError(
            "The indexed-search service returned an unusable response."
        ) from error
    except Exception as error:
        # Provider exceptions can contain request details. Keep those details
        # out of the user-facing workflow error and Streamlit page.
        raise WorkflowError(
            "Election-area discovery failed. Check the API key, rate limit and network connection."
        ) from error
    if not discovery.areas:
        raise WorkflowError("No Surrey wards or divisions were discovered for this URL.")

    _notify(
        progress_callback,
        WorkflowProgress(
            "discovery",
            f"Discovered {len(discovery.areas)} ward(s) or division(s).",
            areas_discovered=len(discovery.areas),
        ),
    )

    # Stage 3: process one area at a time so progress and status counts describe
    # completed work rather than an opaque all-at-once operation.
    records: list[CandidateResultRecord] = []
    attempts: list[ExtractionAttempt] = []
    validations: list[ValidationResult] = []
    counts = {"Complete": 0, "Incomplete": 0, "Failed": 0}
    for position, area in enumerate(discovery.areas, start=1):
        area_label = area.division_ward_name or "Direct ward result"
        _notify(
            progress_callback,
            WorkflowProgress(
                "extraction",
                f"Processing {area_label}.",
                areas_discovered=len(discovery.areas),
                current_area=area_label,
                areas_completed=position - 1,
                complete=counts["Complete"],
                incomplete=counts["Incomplete"],
                failed=counts["Failed"],
            ),
        )
        report: ExtractionReport = extract_candidate_results(
            (area,),
            provider,
            # The prompt requires indexed evidence rather than depending on a
            # direct council-page request that may be blocked.
            official_page_client=None,
            run_targeted_searches=run_targeted_searches,
        )
        # Authentication, rate-limit and network failures apply to the whole
        # extraction, not merely one ward. Stop instead of spending requests on
        # every remaining area or presenting a workbook as a completed run.
        _raise_systemic_provider_failure(report.attempts)
        # Validation reads the extracted rows but never fills or alters them.
        area_validations = validate_election_results(report.records)
        status = _area_status(report.records, area_validations, report.attempts)
        counts[status] += 1
        # Preserve every area's evidence and search attempts for the final
        # workbook, including incomplete and failed areas.
        records.extend(report.records)
        attempts.extend(report.attempts)
        validations.extend(area_validations)
        _notify(
            progress_callback,
            WorkflowProgress(
                "extraction",
                f"Completed {area_label}: {status}.",
                areas_discovered=len(discovery.areas),
                current_area=area_label,
                areas_completed=position,
                complete=counts["Complete"],
                incomplete=counts["Incomplete"],
                failed=counts["Failed"],
            ),
        )

    # Freeze the accumulated lists before passing them into the workbook layer;
    # this makes the returned result stable after the function has completed.
    record_rows = tuple(records)
    validation_rows = tuple(validations)
    attempt_rows = tuple(attempts)
    filename = _safe_filename(discovery, record_rows)
    _notify(
        progress_callback,
        WorkflowProgress(
            "workbook",
            "Generating Excel workbook.",
            areas_discovered=len(discovery.areas),
            areas_completed=len(discovery.areas),
            complete=counts["Complete"],
            incomplete=counts["Incomplete"],
            failed=counts["Failed"],
        ),
    )
    # Stage 4: build the workbook in an automatically cleaned temporary folder,
    # then retain only its bytes for the Streamlit download button.
    with TemporaryDirectory(prefix="surrey-election-workflow-") as temporary_directory:
        workbook_path = Path(temporary_directory) / filename
        generate_workbook(
            workbook_path,
            record_rows,
            validation_rows,
            discovery.areas,
            attempt_rows,
        )
        workbook_bytes = workbook_path.read_bytes()

    _notify(
        progress_callback,
        WorkflowProgress(
            "complete",
            "Extraction workbook is ready.",
            areas_discovered=len(discovery.areas),
            areas_completed=len(discovery.areas),
            complete=counts["Complete"],
            incomplete=counts["Incomplete"],
            failed=counts["Failed"],
        ),
    )
    # The result contains no provider object or API key. It includes only the
    # workbook and non-sensitive audit records needed by the application.
    return WorkflowResult(
        workbook_bytes=workbook_bytes,
        filename=filename,
        source_type=source_type,
        discovery=discovery,
        records=record_rows,
        extraction_attempts=attempt_rows,
        validations=validation_rows,
        complete=counts["Complete"],
        incomplete=counts["Incomplete"],
        failed=counts["Failed"],
    )
