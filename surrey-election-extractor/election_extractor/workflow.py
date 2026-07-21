"""Application-level orchestration for one Surrey extraction request.

The Streamlit page should remain a thin user interface. This module connects
the existing provider-neutral discovery, extraction, validation and workbook
components so the complete application workflow can be tested without a web
browser or a live SerpAPI key.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from election_extractor.discovery import (
    IncompleteElectionDiscoveryError,
    OfficialArchiveClient,
    discover_election_areas,
)
from election_extractor.extraction import (
    CandidateResultRecord,
    ExtractionAttempt,
    ExtractionReport,
    ExtractionStatus,
    EvidenceSourceType,
    extract_candidate_results,
)
from election_extractor.models import (
    DiscoveredElectionArea,
    DiscoveryReport,
    DiscoveryStatus,
    MetadataStatus,
)
from election_extractor.official_archive_fallback import (
    ARCHIVED_OFFICIAL_COPY,
    ArchiveFallbackOfficialArchiveClient,
    ArchiveFallbackOfficialPageClient,
)
from election_extractor.official_source import (
    OfficialPageClassification,
    OfficialPageClient,
    fetch_and_diagnose_official_page,
)
from election_extractor.search_providers.base import (
    BudgetedSearchProvider,
    SearchProvider,
    SearchRequestLimitError,
)
from election_extractor.search_providers.serpapi import (
    SearchAuthenticationError,
    SearchNetworkError,
    SearchRateLimitError,
    SearchResponseError,
    SearchTimeoutError,
    SerpApiSearchProvider,
)
from election_extractor.url_utils import (
    normalise_area_result_url,
    normalise_principal_election_url,
    validate_index_url,
)
from election_extractor.validation import (
    PublishedVotingSummary,
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
    SearchRequestLimitError.__name__: (
        "The extraction reached its indexed-search request limit. "
        "No further searches were sent."
    ),
}


class WorkflowError(RuntimeError):
    """A safe application error that contains no provider credential or traceback."""


class _PreflightSearchProvider:
    """Exercise discovery locally without sending an indexed API request."""

    provider_name = "ZeroQuotaPreflight"

    def search(self, query: str):
        # Discovery normally falls back to its search provider when official
        # HTML is missing. Returning an empty tuple here keeps that code path
        # testable while guaranteeing that preflight cannot consume quota.
        return ()


@dataclass(frozen=True)
class _OfficialPreflightResult:
    """Select a source mode without turning official blocking into failure."""

    official_pages_available: bool
    discovery: DiscoveryReport | None = None
    # True when at least one sampled page was served from a lawful archived
    # official copy rather than the live council site. This only informs the
    # user-facing progress message; the provenance of every individual page is
    # recorded separately in its own diagnostic and extraction attempt.
    served_from_archive: bool = False


def _run_official_preflight(
    source_type: str,
    canonical_url: str,
    archive_client: OfficialArchiveClient | None,
    page_client: OfficialPageClient,
) -> _OfficialPreflightResult:
    """Check official HTML without spending indexed-search quota.

    For an election index, three spread-out result pages are sampled after the
    full official denominator has been verified. A direct URL checks its single
    result page. The page client may itself fall back to archived official
    copies; preflight only reports the outcome. Protection selects indexed-only
    mode; it does not stop the prompt-required indexed workflow or attempt to
    bypass the protection.
    """

    if source_type == "direct":
        # A direct result URL has no election-wide denominator to verify.
        discovery = None
        sample_urls = (canonical_url,)
    else:
        try:
            discovery = discover_election_areas(
                canonical_url,
                _PreflightSearchProvider(),
                archive_client=archive_client,
                indexed_search_only=False,
                require_indexed_search=True,
            )
        except Exception:
            # Direct scraping is explicitly described as unreliable in the
            # project prompt. Treat protection as a mode decision rather than
            # an application error; the real indexed provider has not yet run.
            return _OfficialPreflightResult(False)
        # Sampling across the index catches a site-wide protection response
        # without downloading every result page before the real run starts.
        positions = {0, len(discovery.areas) // 2, len(discovery.areas) - 1}
        sample_urls = tuple(discovery.areas[position].result_url for position in positions)

    # A HTTP 200 response alone is insufficient: Incapsula also returns 200.
    # The diagnostic must recognise an actual election-result table.
    diagnostics = {
        url: fetch_and_diagnose_official_page(url, page_client).diagnostic
        for url in sample_urls
    }
    # Walking a paginated official index (above) can itself use several
    # sequential public requests to the archive. In live testing this
    # occasionally left the archive service in a short-lived rate-limited
    # state exactly when these sample checks ran immediately afterwards,
    # even though the same pages were reliably available moments later. One
    # bounded retry of only the still-failing samples, after a short pause,
    # prevents that brief coincidence from discarding archived-copy access
    # for an entire multi-area run. This is a single extra pass, not
    # indefinite retrying.
    failing_urls = [
        url
        for url, diagnostic in diagnostics.items()
        if diagnostic.classification is not OfficialPageClassification.VALID_ELECTION_RESULT_PAGE
    ]
    if failing_urls:
        time.sleep(5.0)
        for url in failing_urls:
            diagnostics[url] = fetch_and_diagnose_official_page(url, page_client).diagnostic
    official_pages_available = all(
        diagnostic.classification
        is OfficialPageClassification.VALID_ELECTION_RESULT_PAGE
        for diagnostic in diagnostics.values()
    )
    served_from_archive = any(
        diagnostic.retrieval_source == ARCHIVED_OFFICIAL_COPY
        for diagnostic in diagnostics.values()
    )
    return _OfficialPreflightResult(
        official_pages_available,
        discovery if official_pages_available else None,
        served_from_archive,
    )


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
    voting_summaries: tuple[PublishedVotingSummary, ...]
    extraction_attempts: tuple[ExtractionAttempt, ...]
    validations: tuple[ValidationResult, ...]
    complete: int
    incomplete: int
    failed: int
    search_queries_used: int

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


def _published_summary(
    records: tuple[CandidateResultRecord, ...],
) -> tuple[PublishedVotingSummary, ...]:
    """Preserve one published total-vote summary when candidate rows agree.

    Indexed evidence can repeat the same area-level total on every candidate
    row. This helper copies that published value into the separate validation
    model; it does not calculate a replacement from candidate votes. Conflicts
    deliberately produce ``None`` and are handled as missing/review evidence.
    """

    if not records:
        return ()
    source_urls = {record.source_url for record in records}
    if len(source_urls) != 1:
        # The workflow calls extraction one area at a time, so mixed URLs would
        # indicate an internal grouping error rather than evidence to combine.
        return ()

    total_votes = {record.total_votes for record in records if record.total_votes is not None}
    valid_votes = {record.valid_votes for record in records if record.valid_votes is not None}
    return (
        PublishedVotingSummary(
            source_url=source_urls.pop(),
            total_votes=next(iter(total_votes)) if len(total_votes) == 1 else None,
            valid_votes=next(iter(valid_votes)) if len(valid_votes) == 1 else None,
        ),
    )


def _complete_attempt_audit(
    attempts: tuple[ExtractionAttempt, ...],
    validations: tuple[ValidationResult, ...],
    final_status: str,
) -> tuple[ExtractionAttempt, ...]:
    """Attach validation warnings and the final ward status to every attempt."""

    validation_warnings = tuple(
        dict.fromkeys(
            message
            for validation in validations
            for message in (
                *validation.warnings,
                *validation.failed_checks,
            )
            if message
        )
    )
    # ExtractionAttempt is immutable so earlier evidence cannot be changed in
    # place. ``replace`` returns a new audit record with only the post-validation
    # fields added.
    return tuple(
        replace(
            attempt,
            validation_warnings=validation_warnings,
            final_status=final_status,
        )
        for attempt in attempts
    )


def _source_type(source_url: str) -> tuple[str, str]:
    """Validate the submitted Surrey URL and identify its processing path."""

    # Try the native area index first. Preserve a validated principal-election
    # landing page so discovery can search both that original URL and its
    # related EID area index; some older pages are indexed under only one form.
    try:
        return "index", validate_index_url(source_url)
    except ValueError:
        try:
            return "index", normalise_principal_election_url(source_url)
        except ValueError:
            try:
                return "direct", normalise_area_result_url(source_url)
            except ValueError as error:
                raise WorkflowError(
                    "Enter a valid Surrey election, election index, or ward result URL."
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
    # When exact official rows are selected, an empty indexed audit query does
    # not make those source-complete rows incomplete. The indexed attempt stays
    # in the log, but completion is assessed against the evidence tier that
    # actually supports the exported candidate records.
    record_source_types = {record.source_type for record in records}
    status_attempts = attempts
    if record_source_types == {EvidenceSourceType.OFFICIAL}:
        status_attempts = tuple(
            attempt
            for attempt in attempts
            if attempt.source_type is EvidenceSourceType.OFFICIAL
        )

    # Existing but partial evidence is Incomplete rather than Failed. This
    # distinction keeps genuine missing source values visible in the audit.
    if any(record.extraction_status is not ExtractionStatus.COMPLETE for record in records):
        return "Incomplete"
    if any(attempt.status is not ExtractionStatus.COMPLETE for attempt in status_attempts):
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
    max_search_queries: int = 500,
    progress_callback: ProgressCallback | None = None,
    use_official_sources: bool = False,
    require_indexed_search: bool = False,
    official_archive_client: OfficialArchiveClient | None = None,
    official_page_client: OfficialPageClient | None = None,
) -> WorkflowResult:
    """Run one complete, downloadable election-result extraction.

    Tests inject a provider and therefore need no live credential. The real
    application supplies the key directly to the SerpAPI adapter; it is held in
    a local object only and is never copied into the result, progress messages,
    workbook or exception text. The Streamlit application also enables the
    ordinary public official-source clients, which fall back to lawful
    archived copies of the same official pages (with cited snapshots) when the
    live council site returns its protection page. In the Streamlit
    configuration, indexed discovery and one exact-result query remain
    mandatory audit steps; exact council table cells then supply the selected
    values when available.
    """

    # Stage 1: validate and canonicalise the URL before any external request.
    if max_search_queries < 1:
        raise WorkflowError("The indexed-search query limit must be at least 1.")

    source_type, canonical_url = _source_type(source_url)
    if provider is None:
        if not api_key or not api_key.strip():
            raise WorkflowError("An indexed results API key is required.")
        # The key stays inside the provider instance for this function call.
        # Apply the same ceiling to physical HTTP requests as to logical
        # queries. Pagination and retries must not silently spend more provider
        # credits than the user-facing run limit.
        provider = SerpApiSearchProvider(
            api_key=api_key.strip(),
            max_requests=max_search_queries,
        )

    # One wrapper is shared by discovery and every area extraction, so the
    # stated limit applies to the complete user task rather than resetting for
    # each ward or division.
    budgeted_provider = BudgetedSearchProvider(provider, max_search_queries)
    active_official_page_client = official_page_client
    active_archive_client = official_archive_client
    if use_official_sources and active_official_page_client is None:
        # The layered client tries one ordinary live request per page and then
        # the lawful archived official copy. Reusing one instance lets it stop
        # contacting the live site for the whole run after the first
        # protection response.
        active_official_page_client = ArchiveFallbackOfficialPageClient()
    if use_official_sources and active_archive_client is None:
        # Discovery reads the official election archive/area-index pages, which
        # sit behind the same protection; give it the same layered fallback.
        active_archive_client = ArchiveFallbackOfficialArchiveClient()

    preflight_result = None
    if use_official_sources and require_indexed_search:
        # This check deliberately precedes every call to budgeted_provider.
        # Incapsula therefore costs zero SerpAPI searches rather than hundreds.
        _notify(
            progress_callback,
            WorkflowProgress(
                "preflight",
                "Checking the official Surrey pages before using indexed-search quota.",
            ),
        )
        preflight_result = _run_official_preflight(
            source_type,
            canonical_url,
            active_archive_client,
            active_official_page_client,
        )
        if not preflight_result.official_pages_available:
            # Do not repeat a blocked direct request for every area. Indexed
            # search is the required primary path when ordinary HTTP is blocked
            # and no lawful archived official copy is available either.
            active_official_page_client = None
            _notify(
                progress_callback,
                WorkflowProgress(
                    "preflight",
                    "Official pages are protected and no archived official "
                    "copies were found; continuing in indexed-only mode.",
                ),
            )
        elif preflight_result.served_from_archive:
            # Transparency for the researcher: values will come from archived
            # copies of the official pages, with each capture cited in the log.
            _notify(
                progress_callback,
                WorkflowProgress(
                    "preflight",
                    "Live official pages are protected; using archived "
                    "official copies (Wayback Machine) with cited snapshots.",
                ),
            )

    _notify(progress_callback, WorkflowProgress("validation", "URL validated."))
    try:
        # Stage 2: an index URL expands to all discovered areas. A direct URL
        # becomes a one-area report and therefore follows the same later loop.
        if source_type == "index":
            if preflight_result is not None and preflight_result.discovery is not None:
                # Search discovery still runs as the prompt requires. The full
                # official denominator proved by preflight is reused so the
                # same official index is not requested twice.
                indexed_discovery = discover_election_areas(
                    canonical_url,
                    budgeted_provider,
                    indexed_search_only=True,
                )
                # Indexed discovery is retained in the audit, but the verified
                # official list defines the denominator. Search-engine coverage
                # is therefore never mistaken for the full election universe.
                discovery = DiscoveryReport(
                    canonical_url,
                    preflight_result.discovery.areas,
                    tuple(
                        (
                            *indexed_discovery.search_attempts,
                            *preflight_result.discovery.search_attempts,
                        )
                    ),
                )
            elif require_indexed_search:
                # When public HTML is protected, run the indexed workflow the
                # prompt requires. A configured official ID inventory supplies
                # the known 81-URL denominator if Google exposes only a sample;
                # every URL must still obtain its candidate evidence by search.
                discovery = discover_election_areas(
                    canonical_url,
                    budgeted_provider,
                    indexed_search_only=True,
                    allow_configured_inventory=True,
                )
            else:
                discovery_arguments = {}
                if use_official_sources and active_archive_client is not None:
                    discovery_arguments["archive_client"] = active_archive_client
                discovery = discover_election_areas(
                    canonical_url,
                    budgeted_provider,
                    indexed_search_only=not use_official_sources,
                    require_indexed_search=False,
                    **discovery_arguments,
                )
        else:
            discovery = _direct_discovery(canonical_url)
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
    except SearchRequestLimitError as error:
        raise WorkflowError(
            "The extraction reached its indexed-search request limit. "
            "No further searches were sent."
        ) from error
    except IncompleteElectionDiscoveryError as error:
        raise WorkflowError(
            "The complete official election index could not be retrieved: "
            f"expected {error.expected} areas but indexed search found only "
            f"{error.discovered}. No partial workbook was created."
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
    summaries: list[PublishedVotingSummary] = []
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
            budgeted_provider,
            official_page_client=(
                active_official_page_client if use_official_sources else None
            ),
            run_targeted_searches=run_targeted_searches,
            require_exact_indexed_search=require_indexed_search,
            # One complementary summary query per area keeps a complete
            # 81-area run within the application's 200-query allowance.
            max_targeted_queries_per_area=(1 if require_indexed_search else None),
        )
        # Authentication, rate-limit and network failures apply to the whole
        # extraction, not merely one ward. Stop instead of spending requests on
        # every remaining area or presenting a workbook as a completed run.
        _raise_systemic_provider_failure(report.attempts)
        # Keep published area totals separate from candidate rows. Validation
        # may compare them, but it never calculates or writes replacements.
        area_summaries = _published_summary(report.records)
        area_validations = validate_election_results(report.records, area_summaries)
        status = _area_status(report.records, area_validations, report.attempts)
        audited_attempts = _complete_attempt_audit(
            report.attempts,
            area_validations,
            status,
        )
        counts[status] += 1
        # Preserve every area's evidence and search attempts for the final
        # workbook, including incomplete and failed areas.
        records.extend(report.records)
        summaries.extend(area_summaries)
        attempts.extend(audited_attempts)
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
    summary_rows = tuple(summaries)
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
            summary_rows,
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
        voting_summaries=summary_rows,
        extraction_attempts=attempt_rows,
        validations=validation_rows,
        complete=counts["Complete"],
        incomplete=counts["Incomplete"],
        failed=counts["Failed"],
        search_queries_used=budgeted_provider.queries_used,
    )
