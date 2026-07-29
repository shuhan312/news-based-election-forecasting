"""The six pages the brief specifies.

One rule runs through all of them: **the app shows what a reproducible command
produced.** Training happens by invoking the CLI, in a subprocess, with a
command the page displays in full. Nothing is fitted inside a Streamlit
callback, because a figure that exists only inside a browser session is a
figure nobody can check and nobody can cite.

A second rule concerns the holdout. Pages that display 7 May 2026 results say
so, and the model card's blinding disclosure is repeated wherever those
figures appear. A number that arrived from the holdout should never look, to
somebody scrolling, exactly like a number that did not.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from no_news_baseline.candidate_architecture_selection import COMPLEXITY_ORDER
from no_news_baseline.candidate_leakage_audit import (
    FEATURE_COLUMNS,
    PROHIBITED_FIELDS,
)
from no_news_baseline.configuration import DEFAULT_CONFIG_PATH, load_config

from .loaders import (
    REPOSITORY_ROOT,
    load_bundle,
    load_contract,
    load_csv,
    load_model,
    validate_workbook,
)

HOLDOUT_NOTE = (
    "These are 7 May 2026 figures. They took no part in architecture "
    "selection or hyperparameter choice, but they were read during "
    "development, so the holdout is reported rather than blind."
)


def _frame(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records) if records else pd.DataFrame()


def _metric_row(values: list[tuple[str, object]]) -> None:
    columns = st.columns(len(values))
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)


def _missing_bundle(directory: str) -> None:
    st.warning(f"No bundle at `{directory}`. Build one on the **Training** page.")


# ---------------------------------------------------------------------------
# 1. Upload and validation
# ---------------------------------------------------------------------------


def page_upload_and_validation(bundle_directory: str, contract_directory: str) -> None:
    st.header("1 · Upload and validation")

    st.info(
        "The workbook is owned by `surrey-election-extractor`, which publishes "
        "a modelling contract that this app and the model both read. Uploading "
        "here **validates** a workbook's sheets and fields; it does not extract "
        "from it. A second extraction implementation living in a web page would "
        "be a second answer to questions that must have one."
    )

    uploaded = st.file_uploader(
        "Workbook to validate (optional)", type=["xlsx"],
        help="Surrey_Master_Election_Database_Final_2026-07-21.xlsx or similar.",
    )
    if uploaded is not None:
        result = validate_workbook(uploaded)
        if "error" in result:
            st.error(result["error"])
        else:
            if result["passed"]:
                st.success("All required sheets and fields are present.")
            else:
                if result["missing_sheets"]:
                    st.error(f"Missing sheets: {result['missing_sheets']}")
                for sheet, fields in result["missing_fields"].items():
                    st.error(f"`{sheet}` is missing fields: {fields}")
            if result["convenience_sheets_present"]:
                st.warning(
                    "Convenience views present: "
                    f"{result['convenience_sheets_present']}. These must not be "
                    "appended to Candidate Results; the contract build excludes "
                    "them and a test asserts the 2026 rows are not doubled."
                )
            st.dataframe(
                pd.DataFrame(
                    sorted(result["row_counts"].items()),
                    columns=["sheet", "data rows"],
                ),
                width="stretch", hide_index=True,
            )

    st.divider()
    bundle = load_bundle(bundle_directory)
    if bundle is None:
        _missing_bundle(bundle_directory)
        return

    quality = bundle.data_quality
    st.subheader("Data-quality report")
    _metric_row([
        ("candidate rows", quality.get("rows", "—")),
        ("contests", quality.get("contests", "—")),
        ("elections", quality.get("elections", "—")),
        ("duplicate ids", quality.get("duplicate_row_identifiers", "—")),
    ])

    # The brief asks for Reform UK and UKIP counts by election, separately.
    st.subheader("Reform UK and UKIP by election — never combined")
    party_counts = quality.get("party_counts_by_election", {})
    if party_counts:
        table = _frame([
            {"election": election, "rows": values["rows"],
             "Reform UK": values["reform_uk"], "UKIP": values["ukip"]}
            for election, values in party_counts.items()
        ])
        st.dataframe(table, width="stretch", hide_index=True)
        st.caption(
            f"Reform UK {int(table['Reform UK'].sum())} rows, "
            f"UKIP {int(table['UKIP'].sum())} rows. They are separate parties "
            "throughout; no UKIP row is ever counted as evidence about Reform."
        )

    st.subheader("Structural validation")
    seats = quality.get("seat_validation", {})
    dates = quality.get("election_date_validation", {})
    left, right = st.columns(2)
    with left:
        st.markdown("**Seat counts**")
        if seats.get("all_checks_passed"):
            st.success(f"{seats.get('contests_checked')} contests coherent.")
        elif seats:
            st.error("Seat-count problems found.")
            st.json(seats)
        st.caption(
            "The seat count decides which candidates are predicted elected, "
            "so an incoherent one produces a different prediction rather than "
            "a worse one."
        )
        if seats.get("contest_counts_by_structure_and_seats"):
            st.json(seats["contest_counts_by_structure_and_seats"])
    with right:
        st.markdown("**Election dates**")
        if dates.get("all_checks_passed"):
            st.success(
                f"{dates.get('elections_checked')} elections, "
                f"{len(dates.get('distinct_polling_dates', []))} polling days, "
                f"{dates.get('earliest_polling_date')} to "
                f"{dates.get('latest_polling_date')}."
            )
        elif dates:
            st.error("Date problems found.")
            st.json(dates)
        st.caption(
            "Every fold boundary is a date comparison, so a wrong date moves "
            "a row between training and test rather than merely mislabelling it."
        )

    st.subheader("Evidence layers — official, supplementary or derived")
    layers = quality.get("evidence_layers", {})
    if layers:
        # The columns actually present in the run, not the classified total:
        # the four UKIP interaction columns are classified but absent unless
        # the sensitivity option is on.
        counts = layers.get(
            "predictor_counts_by_layer_present",
            layers.get("predictor_counts_by_layer", {}),
        )
        st.dataframe(
            pd.DataFrame(
                [{"layer": k, "predictor columns": v} for k, v in counts.items()],
            ),
            width="stretch", hide_index=True,
        )
        st.warning(
            f"**{counts.get('governed_derived', 0)} of the "
            f"{layers.get('predictors_present_in_this_run', sum(counts.values()))} "
            "predictors in this run are quantities this project computed**, "
            f"against {counts.get('official', 0)} read directly from official "
            "sources. "
            "That is not a defect — county strength and contest rates cannot be "
            "read off a results page — but it means most of the model's inputs "
            "depend on rules documented here rather than on published values."
        )
        if layers.get("per_row_provenance"):
            st.markdown(
                "Two fields carry their own per-row provenance, so no single "
                "layer is claimed for them:"
            )
            st.json(layers["per_row_provenance"])
        with st.expander("Every column, its layer and the reason"):
            st.dataframe(
                _frame([
                    {"column": column, **detail}
                    for column, detail in layers.get("reasons", {}).items()
                ]),
                width="stretch", hide_index=True,
            )

    with st.expander("Missingness by permitted predictor"):
        st.dataframe(
            _frame([
                {"column": k, "missing rows": v}
                for k, v in quality.get(
                    "missing_values_by_permitted_predictor", {}).items()
            ]),
            width="stretch", hide_index=True,
        )
        st.caption(quality.get("unknown_values_preserved", ""))


# ---------------------------------------------------------------------------
# 2. Model configuration
# ---------------------------------------------------------------------------


def page_model_configuration(bundle_directory: str) -> dict:
    """Build a run configuration. Returns it for the training page to use."""

    st.header("2 · Model configuration")
    defaults = load_config(
        DEFAULT_CONFIG_PATH if (REPOSITORY_ROOT / DEFAULT_CONFIG_PATH).exists() else None
    )

    st.subheader("Target")
    st.selectbox(
        "Prediction target", ["analysis_vote_share"], disabled=True,
        help="The brief names one primary target. It is shown rather than "
             "hidden so the app states what it is modelling.",
    )
    st.caption(
        "Fitted as a multiple of the contest's equal split (`share × candidates "
        "÷ 100`), then inverted. Single-member and two-member contests are "
        "otherwise on different scales."
    )

    st.subheader("Architecture")
    mode = st.radio(
        "Selection mode", ["auto", *COMPLEXITY_ORDER],
        help="`auto` runs the two gates. Naming an architecture ships it "
             "regardless — the brief's manual mode.",
        horizontal=False,
    )
    if mode != "auto":
        st.warning(
            f"Manual override. All architectures are still scored and "
            f"`architecture.json` will record `overridden: true` beside the "
            f"verdict the gates reached, so the override stays visible."
        )

    columns = st.columns(2)
    with columns[0]:
        material = st.slider(
            "Material improvement threshold", 0.0, 0.5,
            float(defaults.selection.material_improvement), 0.01,
            help="A challenger must beat the incumbent by more than this on "
                 "Reform vote-share MAE.",
        )
        adverse = st.number_input(
            "Maximum adverse development folds", 0, 4,
            int(defaults.selection.max_adverse_folds),
        )
    with columns[1]:
        seed = st.number_input(
            "Random seed", 0, 99_999_999, int(defaults.boosting_seed),
            help="Affects the gradient-boosted architecture only; A and C have "
                 "closed-form solutions.",
        )
        resamples = st.number_input(
            "Bootstrap resamples", 100, 10_000,
            int(defaults.evaluation.bootstrap_resamples), 100,
            help="Contests are resampled, never rows.",
        )

    st.subheader("Split strategy")
    st.markdown(
        "- Grouping unit **`election_id + division_id`** — a contest cannot "
        "straddle a fold, because it has one polling date.\n"
        "- 4 named development folds, 12 rolling-origin folds.\n"
        "- **Primary holdout:** everything polled 7 May 2026, as one period.\n"
        "- **Secondary holdout:** Haslemere, 7 July 2026, evaluated with and "
        "without the May results."
    )
    st.caption(
        "The split is date-bounded and is not configurable from this page. "
        "Fold boundaries are part of the study design agreed with the "
        "supervisor; making them a slider would let a run quietly change what "
        "it was testing."
    )

    st.subheader("Reform UK and UKIP")
    reform_terms = st.checkbox(
        "Reform UK interaction terms", value=defaults.features.reform_interactions,
        help="Permitted by the brief. Unchecking is the ablation control arm.",
    )
    ukip_terms = st.checkbox(
        "UKIP contextual block (labelled sensitivity option)",
        value=defaults.features.ukip_interactions,
        help="Off by default. Adds UKIP's own columns; merges nothing.",
    )
    if ukip_terms:
        st.error(
            "The UKIP block has been run and **fails the brief's condition**: "
            "Reform out-of-fold MAE goes from 10.18 to 15.10. See "
            "`docs/ukip_contextual_sensitivity.md`. Enabling it is a "
            "sensitivity run, not a candidate for shipping."
        )

    st.subheader("Leakage exclusions")
    st.markdown(
        f"**{len(PROHIBITED_FIELDS)} fields are prohibited** for the election "
        "being predicted. Nothing derived from the current result may be an "
        "input; a test fails if one reaches the design matrix."
    )
    st.dataframe(
        pd.DataFrame(sorted(PROHIBITED_FIELDS), columns=["prohibited field"]),
        width="stretch", hide_index=True, height=200,
    )
    permitted = [c for c, v in FEATURE_COLUMNS.items() if v[0] == "predictor"]
    st.caption(
        f"{len(permitted)} predictors are classified as permitted, out of "
        f"{len(FEATURE_COLUMNS)} classified columns. A run uses fewer: the "
        "four UKIP interaction columns are absent unless the sensitivity "
        "option above is on, so the shipped model has 35. An unclassified "
        "column stops the build rather than defaulting to permitted."
    )

    return {
        "mode": mode, "material_improvement": material,
        "max_adverse_folds": int(adverse), "seed": int(seed),
        "bootstrap_resamples": int(resamples),
        "reform_interactions": reform_terms, "ukip_interactions": ukip_terms,
        "output_directory": bundle_directory,
    }


# ---------------------------------------------------------------------------
# 3. Training
# ---------------------------------------------------------------------------


def _training_command(choices: dict) -> list[str]:
    """The exact CLI invocation for these choices.

    Displayed as well as run, because the app is not the only way to build a
    bundle and should not be the only place a configuration exists.
    """

    command = [
        sys.executable, "-m", "no_news_baseline.cli", "train",
        "--output", choices["output_directory"],
        "--seed", str(choices["seed"]),
        "--bootstrap-resamples", str(choices["bootstrap_resamples"]),
    ]
    if choices["mode"] != "auto":
        command += ["--architecture", choices["mode"]]
    if choices["ukip_interactions"]:
        command += ["--ukip-interactions"]
    if not choices["reform_interactions"]:
        command += ["--no-reform-interactions"]
    return command


def page_training(choices: dict, bundle_directory: str) -> None:
    st.header("3 · Training")

    command = _training_command(choices)
    st.code(
        "PYTHONPATH=surrey-election-no-news-baseline \\\n  "
        + " \\\n  ".join(command),
        language="bash",
    )
    st.caption(
        "Two selection gates and the threshold slider are not passed on the "
        "command line; adjust them in `config/baseline_model.yaml` for a run "
        "that must be reproducible from the file alone."
    )

    if st.button("Run training", type="primary"):
        # PYTHONPATH so the subprocess can import the package, inheriting the
        # rest of the environment so it finds the same interpreter and venv.
        environment = {
            **os.environ,
            "PYTHONPATH": str(REPOSITORY_ROOT / "surrey-election-no-news-baseline"),
        }
        log_area = st.empty()
        lines: list[str] = []
        with st.spinner("Training — this takes a few minutes."):
            process = subprocess.Popen(
                command, cwd=REPOSITORY_ROOT, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            # Streamed rather than captured at the end: a run whose progress is
            # only visible after it finishes is indistinguishable from a hang.
            for line in process.stdout:  # type: ignore[union-attr]
                lines.append(line.rstrip())
                log_area.code("\n".join(lines[-25:]))
            process.wait()
        if process.returncode == 0:
            st.success("Training finished.")
            st.cache_data.clear()
            st.cache_resource.clear()
        else:
            st.error(f"Training failed with exit code {process.returncode}.")

    st.divider()
    bundle = load_bundle(bundle_directory)
    if bundle is None:
        _missing_bundle(bundle_directory)
        return

    selection = bundle.architecture.get("selection", {})
    st.subheader("Selected architecture")
    _metric_row([
        ("shipped", bundle.architecture.get("selected_model_type", "—")),
        ("mode", selection.get("mode", "—")),
        ("decided on", selection.get("decision_basis", "—")),
        ("rows behind the decision", selection.get("decision_rows", "—")),
    ])
    if selection.get("overridden"):
        st.warning(
            f"Manual override: the gates would have selected "
            f"`{selection.get('gate_verdict')}`."
        )
    for reason in selection.get("reasons", []):
        st.markdown(f"- {reason}")
    if selection.get("decision_rows_note"):
        st.caption(selection["decision_rows_note"])

    st.subheader("Architecture comparison, every fold")
    comparison = load_csv(f"{bundle_directory}/architecture_comparison.csv")
    if comparison:
        table = _frame(comparison)
        for column in table.columns:
            if column not in {"split_id", "split_role", "architecture"}:
                table[column] = pd.to_numeric(table[column], errors="coerce")
        role = st.multiselect(
            "Split role", sorted(table["split_role"].unique()),
            default=[r for r in table["split_role"].unique()
                     if r == "development_fold"] or None,
        )
        if role:
            table = table[table["split_role"].isin(role)]
        st.dataframe(table, width="stretch", hide_index=True)

    st.subheader("Fold-level results for the shipped architecture")
    by_split = bundle.metrics.get("by_split", {})
    if by_split:
        st.dataframe(
            _frame([
                {"split": split, "rows": values.get("rows"),
                 "MAE": values.get("mae"),
                 "winner accuracy": values.get("winner_accuracy")}
                for split, values in by_split.items()
            ]),
            width="stretch", hide_index=True,
        )


# ---------------------------------------------------------------------------
# 4. Results
# ---------------------------------------------------------------------------


def page_results(bundle_directory: str) -> None:
    st.header("4 · Results")
    bundle = load_bundle(bundle_directory)
    if bundle is None:
        _missing_bundle(bundle_directory)
        return

    out_of_fold = bundle.metrics.get("out_of_fold", {}).get("overall", {})
    holdout = bundle.metrics.get("primary_holdout", {}).get("overall", {})

    st.subheader("Overall")
    left, right = st.columns(2)
    with left:
        st.markdown("**Out of fold** (rolling origin, pre-2026)")
        _metric_row([
            ("rows", out_of_fold.get("rows", "—")),
            ("MAE", f"{out_of_fold.get('mae', 0):.2f}"),
            ("winner", f"{100 * out_of_fold.get('winner_accuracy', 0):.1f}%"),
        ])
    with right:
        st.markdown("**Primary holdout** (7 May 2026)")
        _metric_row([
            ("rows", holdout.get("rows", "—")),
            ("MAE", f"{holdout.get('mae', 0):.2f}"),
            ("winner", f"{100 * holdout.get('winner_accuracy', 0):.1f}%"),
        ])
    st.caption(HOLDOUT_NOTE)
    st.info(
        f"**The holdout MAE of {holdout.get('mae', 0):.2f} is not better than "
        f"the out-of-fold {out_of_fold.get('mae', 0):.2f}.** Two-member wards "
        "average 9.75 per cent per candidate against 22.65 in single-member "
        "divisions; relative to their own scales they are "
        f"{holdout.get('relative_mae', 0):.2f} and "
        f"{out_of_fold.get('relative_mae', 0):.2f}."
    )

    interval = holdout.get("mae_contest_bootstrap_95", {})
    if interval.get("lower") is not None:
        st.caption(
            f"Contest-level bootstrap, holdout MAE 95% interval "
            f"{interval['lower']:.2f} – {interval['upper']:.2f} over "
            f"{interval['contests']} contests. Contests are resampled, never "
            "rows: shares within a contest sum to 100."
        )

    st.subheader("Reform UK")
    reform_oof = bundle.reform_metrics.get("out_of_fold", {}).get("reform_uk", {})
    reform_holdout = bundle.reform_metrics.get("primary_holdout", {}).get("reform_uk", {})
    _metric_row([
        ("OOF rows", reform_oof.get("rows", "—")),
        ("OOF MAE", f"{reform_oof.get('mae', 0):.2f}"),
        ("holdout rows", reform_holdout.get("rows", "—")),
        ("holdout MAE", f"{reform_holdout.get('mae', 0):.2f}"),
    ])
    if bundle.reform_metrics.get("out_of_fold", {}).get("small_sample_warning"):
        st.error(
            f"**Small sample.** The out-of-fold Reform figures rest on "
            f"{reform_oof.get('rows')} rows. They must not be quoted without it."
        )
    by_architecture = bundle.reform_metrics.get("by_architecture_primary_holdout", {})
    if by_architecture:
        st.markdown("**Every architecture's Reform figures on the holdout**")
        st.dataframe(
            _frame([
                {"architecture": name, "rows": values.get("rows"),
                 "MAE": values.get("mae"),
                 "vs equal split": values.get(
                     "equal_split_reference", {}).get(
                         "improvement_over_equal_split")}
                for name, values in by_architecture.items()
            ]),
            width="stretch", hide_index=True,
        )
        st.caption(
            "The rejected architectures stay visible. On the holdout the "
            "shipped architecture is not the best on Reform — see "
            "`docs/architecture_selection_evidence.md`."
        )

    st.subheader("By election")
    by_election = bundle.metrics.get("primary_holdout", {}).get("by_election", {})
    if by_election:
        st.dataframe(
            _frame([
                {"election": election, "rows": values.get("rows"),
                 "MAE": values.get("mae"),
                 "winner accuracy": values.get("winner_accuracy")}
                for election, values in by_election.items()
            ]),
            width="stretch", hide_index=True,
        )

    st.subheader("Seat allocation")
    seat_error = holdout.get("party_seat_total_absolute_error_by_election", {})
    if seat_error:
        st.dataframe(
            _frame([{"election": k, "party seat-total absolute error": v}
                    for k, v in seat_error.items()]),
            width="stretch", hide_index=True,
        )
        st.caption(
            f"Total {holdout.get('party_seat_total_absolute_error')}. Exact "
            f"seat sets are right in "
            f"{100 * holdout.get('seat_set_accuracy', 0):.1f}% of contests."
        )

    st.subheader("Candidate-level predictions")
    predictions = load_csv(f"{bundle_directory}/holdout_predictions.csv")
    if predictions:
        table = _frame(predictions)
        parties = sorted(table["standard_party_name"].unique())
        chosen = st.multiselect("Filter by party", parties, default=[])
        if chosen:
            table = table[table["standard_party_name"].isin(chosen)]
        if st.checkbox("Reform UK only"):
            table = table[table["is_reform_uk"].astype(str).str.lower().isin(
                {"true", "1", "yes"})]
        st.dataframe(table, width="stretch", hide_index=True, height=380)


# ---------------------------------------------------------------------------
# 5. Explainability
# ---------------------------------------------------------------------------


def page_explainability(bundle_directory: str, contract_directory: str) -> None:
    st.header("5 · Explainability")
    st.warning(
        "These are model contributions, not causal effects. They describe how "
        "this fitted model combines pre-election information. They do not "
        "establish why any voter behaved as they did."
    )

    bundle = load_bundle(bundle_directory)
    if bundle is None:
        _missing_bundle(bundle_directory)
        return
    loaded = load_model(bundle_directory)
    if loaded is None:
        st.warning("The bundle has no `model.pkl` to explain.")
        return
    model, encoder = loaded

    predictions = load_csv(f"{bundle_directory}/holdout_predictions.csv")
    if not predictions:
        st.warning("No holdout predictions to explain.")
        return

    architecture = bundle.architecture.get("selected_model_type", "")
    st.caption(f"Explaining the shipped architecture: `{architecture}`.")

    if hasattr(model, "predict") and hasattr(model, "feature_importance"):
        _explain_tree(model, encoder, contract_directory, bundle_directory)
    else:
        _explain_linear(model, encoder)


def _explain_tree(booster, encoder, contract_directory: str, bundle_directory: str) -> None:
    """Exact TreeSHAP for the boosted architecture."""

    from no_news_baseline.candidate_cohort import is_within_candidate_cohort
    from no_news_baseline.candidate_historical_strength import attach_strength_features
    from no_news_baseline.candidate_interactions import attach_interactions
    from no_news_baseline.candidate_tree_explainability import (
        global_shap_importance,
        party_shap_profile,
    )
    from no_news_baseline.candidate_splits import PRIMARY_HOLDOUT_DATE
    from no_news_baseline.election_dates import parse_election_date

    features, targets = load_contract(contract_directory)
    if not features:
        st.warning("The contract is not available, so SHAP cannot be computed.")
        return
    rows = [r for r in features if is_within_candidate_cohort(r)]
    rows = list(attach_interactions(attach_strength_features(rows, targets)))
    holdout_rows = [
        r for r in rows
        if parse_election_date(str(r["election_date"])).date() == PRIMARY_HOLDOUT_DATE
    ]
    if not holdout_rows:
        st.warning("No holdout rows found in the contract.")
        return

    with st.spinner("Computing exact TreeSHAP…"):
        importance = global_shap_importance(
            booster=booster, rows=holdout_rows, encoder=encoder)
        reform = party_shap_profile(
            booster=booster, rows=holdout_rows, encoder=encoder, reform_only=True)

    st.subheader("Global feature importance (mean |SHAP|)")
    table = _frame(list(importance)[:20])
    st.dataframe(table, width="stretch", hide_index=True)

    st.subheader("Reform UK specifically")
    st.caption(
        f"{reform.get('rows', 0)} Reform rows on the holdout. The model's base "
        f"value is {reform.get('base_value', 0):.3f} and its mean prediction "
        f"for these rows is {reform.get('mean_predicted_relative_share', 0):.3f}, "
        "both as multiples of the contest's equal split — so a mean below 1.0 "
        "means Reform is predicted below an equal share."
    )
    contributions = reform.get("importance") or ()
    if contributions:
        st.dataframe(_frame(list(contributions)[:20]), width="stretch",
                     hide_index=True)
    st.caption(reform.get("interpretation_warning", ""))


def _explain_linear(model, encoder) -> None:
    """Coefficients for the interpretable architectures."""

    coefficients = getattr(model, "coefficients", None)
    if coefficients is None:
        coefficients = getattr(model, "coef_", None)
    if coefficients is None:
        st.warning("This model exposes no coefficients to display.")
        return

    names = list(encoder.column_names)
    table = pd.DataFrame({
        "feature": names[: len(coefficients)],
        "coefficient": list(coefficients)[: len(names)],
    })
    table["magnitude"] = table["coefficient"].abs()
    table = table.sort_values("magnitude", ascending=False).drop(columns="magnitude")

    st.subheader("Coefficients, largest first")
    st.dataframe(table.head(30), width="stretch", hide_index=True)
    st.caption(
        "On the model's own scale, where 1.0 is the contest's equal split. "
        "Coefficients are on standardised inputs, so they are comparable to "
        "each other but are not percentage points."
    )

    reform_terms = table[table["feature"].str.contains("reform", case=False)]
    if not reform_terms.empty:
        st.subheader("Reform UK terms")
        st.dataframe(reform_terms, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# 6. Export
# ---------------------------------------------------------------------------


def page_export(bundle_directory: str) -> None:
    st.header("6 · Export")
    bundle = load_bundle(bundle_directory)
    if bundle is None:
        _missing_bundle(bundle_directory)
        return

    manifest = bundle.manifest
    files = manifest.get("files", {})
    st.markdown(
        f"**{len(files)} files**, built "
        f"{manifest.get('generated', 'at an unrecorded time')}, shipping "
        f"`{manifest.get('selected_architecture', '—')}`."
    )
    strays = manifest.get("files_not_written_by_this_run", [])
    if strays:
        st.warning(
            f"{len(strays)} file(s) in the directory were not written by the "
            f"last run and are excluded from the manifest: {strays}."
        )

    st.dataframe(
        _frame([{"file": name, "sha256": digest[:16] + "…"}
                for name, digest in sorted(files.items())]),
        width="stretch", hide_index=True, height=380,
    )
    st.caption(
        "Hashes let a later stage prove it loaded the bundle these metrics "
        "describe, rather than one that happened to be in the same place."
    )

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle_zip:
        for name in sorted(files):
            path = bundle.directory / name
            if path.exists():
                bundle_zip.write(path, arcname=f"{bundle.directory.name}/{name}")
    archive.seek(0)
    st.download_button(
        "Download the complete model bundle (.zip)", archive,
        file_name=f"{bundle.directory.name}.zip", mime="application/zip",
        type="primary",
    )
    st.caption(
        "Only the files in the manifest are included, so what is downloaded is "
        "exactly what the last run produced."
    )

    with st.expander("Model card"):
        st.markdown(bundle.model_card or "_No model card in this bundle._")

    with st.expander("Resolved configuration this bundle was built with"):
        st.json(bundle.training_config.get("resolved_configuration", {}))
