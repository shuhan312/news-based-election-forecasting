"""Streamlit entry point for the Surrey no-news baseline.

Run from the repository root:

    PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m streamlit run \
        surrey-election-no-news-baseline/app/streamlit_app.py

Navigation is a sidebar radio rather than Streamlit's ``pages/`` directory
convention. The brief specifies six named pages in a fixed order; the
directory convention derives its order and labels from filenames, and would
put the ordering of the deliverable at the mercy of alphabetisation.

The configuration built on page 2 is held in session state so page 3 can act
on it. Nothing else is: every figure displayed comes from a bundle on disk, so
what the app shows and what a colleague reading the bundle sees cannot differ.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# The package lives one directory up. Added here so the app runs whether or not
# PYTHONPATH was set, which matters because `streamlit run` is usually typed by
# hand rather than scripted.
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app import views  # noqa: E402
from no_news_baseline.configuration import BaselineConfig  # noqa: E402

PAGES = (
    "1 · Upload and validation",
    "2 · Model configuration",
    "3 · Training",
    "4 · Results",
    "5 · Explainability",
    "6 · Export",
)


def main() -> None:
    st.set_page_config(
        page_title="Surrey no-news baseline",
        page_icon="🗳",
        layout="wide",
    )

    defaults = BaselineConfig.defaults()
    st.sidebar.title("Surrey no-news baseline")
    st.sidebar.caption(
        "Stage 1: predict candidate vote share from election history alone. "
        "Reform UK is the study party; Reform UK and UKIP are never merged."
    )

    bundle_directory = st.sidebar.text_input(
        "Bundle directory", str(defaults.paths.output_directory),
        help="Relative to the repository root. Point this at a sensitivity run "
             "to inspect it instead.",
    )
    contract_directory = st.sidebar.text_input(
        "Contract directory", str(defaults.paths.contract_directory),
        help="Published by the extractor. Read-only here.",
    )

    page = st.sidebar.radio("Page", PAGES, label_visibility="collapsed")

    st.sidebar.divider()
    st.sidebar.caption(
        "**The model predicts statistical patterns.** It does not establish "
        "why any individual voted as they did, and no figure here should be "
        "read as a causal claim."
    )

    if page == PAGES[0]:
        views.page_upload_and_validation(bundle_directory, contract_directory)
    elif page == PAGES[1]:
        # Kept in session state so the Training page can act on choices made
        # here without the two pages needing to be open at once.
        st.session_state["run_choices"] = views.page_model_configuration(
            bundle_directory)
    elif page == PAGES[2]:
        choices = st.session_state.get("run_choices")
        if choices is None:
            st.info(
                "Visit **Model configuration** first, or use the defaults below."
            )
            choices = {
                "mode": "auto",
                "material_improvement": defaults.selection.material_improvement,
                "max_adverse_folds": defaults.selection.max_adverse_folds,
                "seed": defaults.boosting_seed,
                "bootstrap_resamples": defaults.evaluation.bootstrap_resamples,
                "reform_interactions": defaults.features.reform_interactions,
                "ukip_interactions": defaults.features.ukip_interactions,
                "output_directory": bundle_directory,
            }
        # The sidebar wins over a stale session value, so switching bundle
        # directory cannot leave the page training into the previous one.
        choices = {**choices, "output_directory": bundle_directory}
        views.page_training(choices, bundle_directory)
    elif page == PAGES[3]:
        views.page_results(bundle_directory)
    elif page == PAGES[4]:
        views.page_explainability(bundle_directory, contract_directory)
    elif page == PAGES[5]:
        views.page_export(bundle_directory)


if __name__ == "__main__":
    main()
