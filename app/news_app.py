"""Streamlit interface for the news layer: status, results, scenarios.

    PYTHONPATH=src .venv/bin/python -m streamlit run app/news_app.py

The design's news application, delivered as a thin viewing-and-scenario
layer over the artefacts the pipeline already produces. Three pages
instead of the guide's eleven, and the reduction is deliberate: every
processing step (upload, extraction, review, training, export) already
ran through the auditable CLI pipeline and its outputs are frozen, so
pages that would re-drive processing would either duplicate the CLI or
invite mutation of frozen evidence. What a reader still needs
interactively is exactly three things - what state is the news layer
in, what did the one-time unblinding find, and how does the frozen
model respond to a hypothetical story - and that is what these pages
do. The baseline's own six-page application is untouched.

Every page carries the statistical interpretation warning the design
requires on results surfaces, and the scenario page re-verifies the
frozen model's coefficients before running anything - the same
assertion the CLI scenario tool makes, so the app cannot quietly serve
an unfrozen model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from news_modelling.production_news_experiment import _read_csv  # noqa: E402
from news_modelling.stage1_bundle import load_stage1_bundle  # noqa: E402
from news_modelling.synthetic_news_scenarios import (  # noqa: E402
    ARM_COLUMNS,
    DISCLAIMER,
    PARTIES,
    fit_frozen_specification,
    run_scenario,
)
from news_modelling.blinded_2026_predictions import (  # noqa: E402
    sanitise_holdout_rows,
)

WARNING = ("The models estimate statistical associations. Nothing on this "
           "page establishes how voters responded to news, and no scenario "
           "output is a real-world claim.")

WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")


@st.cache_data
def load_json(path: str) -> dict:
    return json.loads((REPO / path).read_text(encoding="utf-8"))


@st.cache_resource
def bundle_summary() -> dict:
    """Hash-verified Stage 1 bundle summary; cached because verification
    re-hashes every bundle file."""

    return load_stage1_bundle(
        REPO / "surrey-election-no-news-baseline/outputs/model_bundle_v1"
    ).summary()


@st.cache_resource
def scenario_model(arm: str, window: str):
    """The frozen specification for one (arm, window), coefficient-checked
    against the v2 protocol before anything runs."""

    features = _read_csv(REPO / "news_features/news_feature_table_v2.csv")
    model, columns, bundle = fit_frozen_specification(
        features, arm=arm, window=window)
    blinded = sanitise_holdout_rows([dict(r) for r in bundle.holdout])
    return features, model, columns, blinded


def page_status() -> None:
    st.header("News layer status")
    st.caption(WARNING)

    st.subheader("Frozen Stage 1 baseline")
    summary = bundle_summary()
    left, mid, right = st.columns(3)
    left.metric("architecture", summary["selected_architecture"])
    mid.metric("out-of-fold rows", summary["baseline_out_of_fold_rows"])
    right.metric("Reform OOF rows", summary["reform_out_of_fold_rows"])
    st.caption(f"bundle {summary['bundle_version']}, trained "
               f"{summary['training_date']}; holdout elections: "
               f"{', '.join(summary['holdout_elections'])}")

    st.subheader("Canonical news corpus v2")
    release = load_json("news_collection/canonical_corpus_release_v2.json")
    corpus = release["usable_feature_corpus"]
    left, mid, right = st.columns(3)
    left.metric("articles", corpus["articles"])
    mid.metric("local / national",
               f"{corpus['by_arm'].get('local', 0)} / "
               f"{corpus['by_arm'].get('national', 0)}")
    right.metric("release", release["release_id"].rsplit("-", 1)[-1])
    st.bar_chart({"articles": {w: corpus["by_window"].get(w, 0)
                               for w in WINDOWS}})

    st.subheader("Frozen prediction files")
    for version in ("v1", "v2"):
        manifest = load_json(
            f"news_features/blinded_2026_predictions_{version}/"
            "sha256_manifest.json")
        st.code(f"{version}: {manifest['prediction_rows']} rows  "
                f"sha256 {manifest['blinded_predictions.csv'][:16]}…",
                language=None)
    st.caption("Full provenance: news_features/"
               "PRODUCTION_NEWS_EVIDENCE_REGISTER.md, sections 13-18.")


def page_results() -> None:
    st.header("The one-time 2026 unblinding")
    st.caption(WARNING)
    results = load_json(
        "news_features/unblinding_2026_v1/unblinding_results.json")

    baseline = results["baseline_all_2026_rows"]
    reform = results["baseline_reform_rows"]
    left, mid, right = st.columns(3)
    left.metric("baseline MAE", f"{baseline['mae']:.2f}")
    mid.metric("baseline seat accuracy",
               f"{results['baseline_seat_accuracy']['accuracy']:.1%}")
    right.metric("baseline Reform MAE", f"{reform['mae']:.2f}")

    for version, label in (("v1", "v1 - before enrichment"),
                           ("v2", "v2 - after enrichment")):
        st.subheader(label)
        rows = []
        for entry in results["files"][version]:
            if entry["family"] != "confirmatory":
                continue
            overall = entry["metrics"]["all_supported_parties"]
            ci = entry["metrics"]["bootstrap_news_vs_recalibrated"]
            rows.append({
                "arm": entry["analysis"].replace("_exploratory", ""),
                "window": entry["period"],
                "news MAE": round(overall["news_enhanced"]["mae"], 3),
                "vs control": round(overall["news_vs_recalibrated_mae"], 3),
                "95% CI": f"[{ci.get('improvement_ci_lower', 0):+.3f}, "
                          f"{ci.get('improvement_ci_upper', 0):+.3f}]",
            })
        improved = sum(1 for r in rows if r["vs control"] > 0)
        st.caption(f"{improved} of {len(rows)} confirmatory comparisons "
                   "improve on the recalibrated control.")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.info("No specification, window, arm or variant may be selected or "
            "promoted because of these numbers (pre-declared rule; "
            "register section 16). Seat-level and arm-level detail: "
            "unblinding_2026_v1/descriptive_targets_annex.md.")


def page_scenarios() -> None:
    st.header("Synthetic news scenario laboratory")
    st.warning(DISCLAIMER)

    left, right = st.columns(2)
    party = left.selectbox("Party the story is about", PARTIES,
                           index=PARTIES.index("reform_uk"))
    tone = left.selectbox("Tone", ("favourable", "unfavourable", "neither"))
    arm = right.selectbox("Collection arm", tuple(ARM_COLUMNS),
                          help="local is a sensitivity-only arm with thin "
                               "cells; expect outsized, fragile responses")
    window = right.selectbox("Window before polling day", WINDOWS, index=1)
    articles = st.slider("Hypothetical articles injected", 1, 50, 10)

    if st.button("Run scenario against the frozen v2 model"):
        with st.spinner("verifying frozen coefficients and predicting…"):
            features, model, columns, blinded = scenario_model(arm, window)
            outcome = run_scenario(
                features, blinded, model, columns, window=window,
                scenario={"party": party, "arm": arm,
                          "articles": articles, "tone": tone})
        context = outcome["injection_context"]
        st.caption(
            f"The cell held {context['window_articles_before_injection']} "
            f"articles ({context['party_articles_before_injection']} naming "
            f"{party}) before injection - read the deltas against that "
            "base.")
        st.subheader("Mean predicted-share change by party (points)")
        st.dataframe(
            [{"party": p, "delta": d}
             for p, d in outcome["mean_share_delta_by_party"].items()],
            use_container_width=True, hide_index=True)
        st.metric("seat calls changed", outcome["seat_flip_count"])
        if outcome["seat_flips"]:
            st.dataframe(outcome["seat_flips"][:20],
                         use_container_width=True, hide_index=True)


def page_epilogue() -> None:
    """The exploratory epilogue: what happened after the unblinding.
    Every table reads committed artefacts; the no-promotion rule
    applies to every number shown."""

    st.header("Exploratory epilogue")
    st.caption(WARNING)

    st.subheader("The local arm, re-run on the v3 lineage (exploratory)")
    rerun = load_json("news_features/local_v3_rerun_v1/rerun_results.json")
    rows = []
    for entry in rerun["windows"]:
        overall = entry["metrics"]["all_supported_parties"]
        ci = entry["metrics"].get("bootstrap_news_vs_recalibrated", {})
        ref = rerun["reference_deltas"][entry["window"]]
        rows.append({
            "window": entry["window"],
            "local v3 delta": round(overall["news_vs_recalibrated_mae"], 3),
            "95% CI": f"[{ci.get('improvement_ci_lower', 0):+.3f}, "
                      f"{ci.get('improvement_ci_upper', 0):+.3f}]",
            "combined (conf)": ref.get("combined_confirmatory"),
            "national (conf)": ref.get("national_confirmatory"),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption("4 of 6 windows improve; the sign inversion at 180-91 days "
               "(local helps where both confirmatory arms harmed) motivated "
               "the pre-registered combination tested below.")

    st.subheader("Woking South: the pre-registered blind test")
    unseal = load_json(
        "news_features/woking_south_blind_v1/unseal_results.json")
    st.caption(unseal["status"])
    st.dataframe([{
        "window": spec["window"], "arm": spec["arm"],
        "pick": "PICK" if spec["combination_pick"] else "",
        "news MAE": spec["news_mae"],
        "baseline MAE": spec["baseline_mae"],
        "delta": spec["news_vs_baseline"],
        "Reform err": spec["reform_signed_error"],
        "winner": "yes" if spec["winner_correct"] else "NO",
    } for spec in unseal["specifications"]],
        use_container_width=True, hide_index=True)
    st.error("The pick (local at 180-91 days) scored worst of all 18 "
             "specifications: the 2026-derived window-arm advantage did "
             "not transfer. Predictions were committed to git before the "
             "outcome was read; the register carries the full autopsy.")

    st.subheader("Per-party bootstrap annex: the sign flip between islands")
    annex = load_json("news_features/per_party_bootstrap_v1/"
                      "per_party_bootstrap_results.json")
    quantity = "abs_bias_change_vs_recalibrated"
    island_label = {"validation_2021": "2021 validation",
                    "holdout_2026_v2": "2026 holdout (v2)"}
    st.dataframe([{
        "island": island_label[spec["island"]],
        "arm": spec["analysis"].replace("_exploratory", "")
                               .replace("_sensitivity", ""),
        "window": spec["period"],
        "Reform level change": spec["parties"]["reform_uk"][quantity],
        "fitted-group change": spec["group_point"][quantity],
        "contrast": spec["contrast_point"][quantity],
        "95% CI": (lambda ci: f"[{ci.get('ci_lower', 0):+.2f}, "
                              f"{ci.get('ci_upper', 0):+.2f}]")(
            spec["bootstrap"]["units"]["contrast"][quantity]),
    } for spec in annex["specifications"]],
        use_container_width=True, hide_index=True)
    st.info("Paired contest-bootstrap intervals (2,000 resamples) on the "
            "Reform-minus-group level contrast, versus the recalibrated "
            "control. The contrast sits below zero through most 2021 "
            "windows (the borrowed adjustment flattered Reform - zero "
            "Reform fitting rows there) and above zero through most 2026 "
            "ones: the direction of the news layer's Reform correction "
            "does not survive the change of island. Exploratory; the "
            "register's bootstrap-annex addendum carries the census and "
            "footnotes.")

    st.subheader("Design resolution: minimal detectable effects")
    mde = load_json("news_features/minimal_detectable_effect_v1/"
                    "mde_results.json")
    st.dataframe([{
        "island": entry["island"], "scope": entry["scope"],
        "comparisons": entry["comparisons"],
        "estimable": entry["estimable"],
        "median MDE80": entry.get("median_mde_80"),
        "range": (f"[{entry['min_mde_80']}, {entry['max_mde_80']}]"
                  if entry.get("median_mde_80") is not None else "-"),
    } for entry in mde["summary"]],
        use_container_width=True, hide_index=True)
    st.caption("MDE80 = the smallest true effect this design detects in "
               "~80% of repeated samples, derived from committed interval "
               "widths only (observed deltas never enter). 2021 resolves "
               "overall effects no finer than ~1 share point and "
               "Reform-specific effects no finer than ~2.6; the 2026 v2 "
               "island resolves to ~0.2 - which is why the small legacy "
               "level corrections could be certified only there. Single-"
               "contest case studies (Haslemere, Woking South) admit no "
               "interval at all.")


def main() -> None:
    st.set_page_config(page_title="Surrey news layer", page_icon="📰",
                       layout="wide")
    st.sidebar.title("Surrey news layer")
    st.sidebar.caption("Read-only views over frozen, hash-anchored "
                       "artefacts; the scenario page runs the frozen model "
                       "and retrains nothing.")
    page = st.sidebar.radio("Page", ("News layer status",
                                     "Unblinding results",
                                     "Scenario laboratory",
                                     "Exploratory epilogue"),
                            label_visibility="collapsed")
    if page == "News layer status":
        page_status()
    elif page == "Unblinding results":
        page_results()
    elif page == "Scenario laboratory":
        page_scenarios()
    else:
        page_epilogue()


if __name__ == "__main__":
    main()
