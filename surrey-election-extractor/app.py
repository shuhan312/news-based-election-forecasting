"""Single-page Streamlit interface for the Surrey election extractor.

The page collects only the source URL and temporary indexed-search credential.
All discovery, extraction, validation and workbook rules remain in
``election_extractor.workflow`` so they can be tested without a browser.
"""

from __future__ import annotations

import streamlit as st

from election_extractor.workflow import (
    WorkflowError,
    WorkflowProgress,
    WorkflowResult,
    run_extraction_workflow,
)


# Streamlit reruns this file whenever a widget changes. These names identify the
# small pieces of state that must survive a rerun: the finished workbook, a safe
# user-facing error, and the instruction to clear the temporary password field.
RESULT_STATE_KEY = "surrey_extraction_result"
ERROR_STATE_KEY = "surrey_extraction_error"
API_KEY_WIDGET_KEY = "indexed_results_api_key"
CLEAR_KEY_STATE = "clear_indexed_results_api_key"


def _clear_finished_api_key_before_render() -> None:
    """Remove the previous credential before recreating the password widget.

    Streamlit does not allow widget state to be changed after that widget has
    been rendered in the current run. The extraction therefore requests a
    rerun and this function clears the value at the start of the next run.
    """

    if st.session_state.pop(CLEAR_KEY_STATE, False):
        st.session_state[API_KEY_WIDGET_KEY] = ""


def _progress_fraction(progress: WorkflowProgress) -> float:
    """Translate workflow counts into a stable value for the progress bar."""

    if progress.stage == "validation":
        return 0.05
    if progress.stage == "discovery":
        return 0.10
    if progress.stage == "workbook":
        return 0.95
    if progress.stage == "complete":
        return 1.0
    if progress.areas_discovered:
        # Reserve the first and last 10% for validation/discovery and workbook
        # generation; extraction progress occupies the middle of the bar.
        completed_share = progress.areas_completed / progress.areas_discovered
        return min(0.90, 0.10 + (0.80 * completed_share))
    return 0.05


def _show_progress(progress: WorkflowProgress, progress_bar, status_box) -> None:
    """Render one safe progress update without request or credential details."""

    progress_bar.progress(_progress_fraction(progress))
    status_box.markdown(
        "\n".join(
            (
                f"**Current stage:** {progress.stage.replace('_', ' ').title()}",
                f"**Status:** {progress.message}",
                f"**Wards or divisions discovered:** {progress.areas_discovered}",
                f"**Current ward or division:** {progress.current_area or '—'}",
                f"**Completed:** {progress.areas_completed}",
                f"**Complete / Incomplete / Failed:** "
                f"{progress.complete} / {progress.incomplete} / {progress.failed}",
            )
        )
    )


def _show_result(result: WorkflowResult) -> None:
    """Display the final audit totals and the generated workbook download."""

    st.success("Extraction finished and the Excel workbook is ready.")
    complete_column, incomplete_column, failed_column = st.columns(3)
    complete_column.metric("Complete", result.complete)
    incomplete_column.metric("Incomplete", result.incomplete)
    failed_column.metric("Failed", result.failed)
    st.caption(
        f"Processed {result.areas_discovered} ward(s) or division(s). "
        "Blank source values remain blank and are recorded in the workbook audit."
    )
    # Streamlit receives the workbook in memory. The application does not need
    # to create a permanent server-side copy before the user downloads it.
    st.download_button(
        "Download Excel workbook",
        data=result.workbook_bytes,
        file_name=result.filename,
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        type="primary",
    )


def main() -> None:
    """Render and run the complete single-page extraction interface."""

    st.set_page_config(
        page_title="Surrey Election Results Extractor",
        page_icon="🗳️",
        layout="centered",
    )
    _clear_finished_api_key_before_render()

    st.title("Surrey Election Results Extractor")
    st.write(
        "Extract indexed Surrey County Council election results into an "
        "auditable Excel workbook. Missing source values are never guessed."
    )

    # These three widgets correspond directly to the controls named in the
    # supervisor prompt. The password type masks the credential in the browser.
    source_url = st.text_input(
        "Surrey election results URL",
        placeholder=(
            "Paste an election index URL or one ward/division result URL"
        ),
        help="Only official Surrey County Council election-result URLs are accepted.",
    )
    api_key = st.text_input(
        "Indexed results API key",
        type="password",
        key=API_KEY_WIDGET_KEY,
        help=(
            "Enter a SerpAPI key for this extraction. The application does not "
            "write the key to the workbook or project files."
        ),
    )
    run_targeted_searches = st.checkbox(
        "Run targeted searches for missing information",
        value=True,
        help=(
            "Run additional ward-, election- and field-specific indexed searches. "
            "Missing information remains blank when it is not explicitly published."
        ),
    )

    # Prevent a request that cannot succeed. Detailed Surrey URL validation is
    # still performed by the workflow after the user presses the button.
    inputs_present = bool(source_url.strip() and api_key.strip())
    extract = st.button(
        "Extract election results",
        type="primary",
        disabled=not inputs_present,
        help=(
            None
            if inputs_present
            else "Enter both a Surrey election results URL and an API key."
        ),
    )

    if extract:
        # Remove an older workbook before starting so a failed new request can
        # never leave a previous result looking like the current extraction.
        st.session_state.pop(RESULT_STATE_KEY, None)
        st.session_state.pop(ERROR_STATE_KEY, None)
        # The workflow reports structured updates through its callback; these
        # placeholders are updated in place rather than adding a new block for
        # every ward or division.
        progress_bar = st.progress(0.0)
        status_box = st.empty()

        try:
            result = run_extraction_workflow(
                source_url,
                api_key=api_key,
                run_targeted_searches=run_targeted_searches,
                progress_callback=lambda update: _show_progress(
                    update,
                    progress_bar,
                    status_box,
                ),
            )
            # Workbook bytes, filename and non-sensitive audit totals persist
            # across the rerun so the download button remains available.
            st.session_state[RESULT_STATE_KEY] = result
        except WorkflowError as error:
            # WorkflowError is deliberately safe for display and never contains
            # the API key or a provider traceback. Retain this safe text across
            # the credential-clearing rerun so the user can still read it.
            st.session_state[ERROR_STATE_KEY] = str(error)
        except Exception:
            # Unexpected technical details stay out of the browser. They can be
            # investigated locally without exposing request or credential data.
            st.session_state[ERROR_STATE_KEY] = (
                "The extraction could not be completed. Check the connection "
                "and try again; no workbook has been presented as complete."
            )
        finally:
            # Request credential clearing on the next render. The local
            # ``api_key`` variable ends with this run and is not stored.
            st.session_state[CLEAR_KEY_STATE] = True

        # Start a clean render so _clear_finished_api_key_before_render can
        # empty the password widget. The saved result or safe error remains.
        st.rerun()

    # After the credential-clearing rerun, restore only non-sensitive output to
    # the page: either a safe error or the finished workbook summary.
    saved_error = st.session_state.get(ERROR_STATE_KEY)
    if isinstance(saved_error, str):
        st.error(saved_error)

    saved_result = st.session_state.get(RESULT_STATE_KEY)
    if isinstance(saved_result, WorkflowResult):
        _show_result(saved_result)


if __name__ == "__main__":
    main()
