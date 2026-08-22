"""Build the offline viva pack: demo/viva_pack.html.

    .venv/bin/python demo/build_viva_pack.py

A viewing layer only, kept apart from the pipeline (see demo/README.md).
Every tabular number is read from the frozen report table pack
(outputs/report_tables_v1, sha256-pinned by its manifest.json), every
figure is embedded base64 from the committed outputs/report_figures_v1,
and the repository map is computed from `git ls-files` rather than typed.
Headline numbers quoted in the report are asserted against the frozen
artefacts at build time, so the pack cannot silently drift from the
evidence it presents.
"""

from __future__ import annotations

import ast
import base64
import json
import re
import subprocess
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
TABLES = REPO / "outputs" / "report_tables_v1"
FIGURES = REPO / "outputs" / "report_figures_v1"
SRC_NM = REPO / "src" / "news_modelling"
OUT = REPO / "demo" / "viva_pack.html"


# ---------------------------------------------------------------- loading

def load_table(stem: str) -> pd.DataFrame:
    return pd.read_csv(TABLES / f"{stem}.csv")


def load_manifest() -> dict:
    return json.loads((TABLES / "manifest.json").read_text(encoding="utf-8"))


def figure_b64(name: str) -> str:
    data = (FIGURES / name).read_bytes()
    return base64.b64encode(data).decode("ascii")


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
        check=True,
    )
    return out.stdout.splitlines()


# ------------------------------------------------------------- assertions

def assert_headline_numbers(t: dict[str, pd.DataFrame]) -> None:
    """Fail the build if the pack's headline numbers drift from the
    frozen artefacts. These are the numbers the abstract and Section 5
    of the report rest on."""
    v2 = t["t05"]
    row = v2[(v2.arm == "combined") & (v2.window == "90-31 days")].iloc[0]
    assert row.news_mae == 4.205, row.news_mae
    assert row.news_vs_recalibrated == 0.24, row.news_vs_recalibrated
    assert (row.ci_lower, row.ci_upper) == (0.078, 0.387)
    row = v2[(v2.arm == "national") & (v2.window == "90-31 days")].iloc[0]
    assert row.news_mae == 4.177 and row.news_vs_recalibrated == 0.268
    assert (row.ci_lower, row.ci_upper) == (0.109, 0.411)
    assert set(v2.recalibrated_mae) == {4.445}
    assert set(t["t04"].recalibrated_mae) == {4.441}
    # v1: no improvements; v2: 5 improvements, 4 CIs entirely above zero.
    assert (t["t04"].news_vs_recalibrated > 0).sum() == 0
    assert (v2.news_vs_recalibrated > 0).sum() == 5
    assert ((v2.ci_lower > 0) & (v2.ci_upper > 0)).sum() == 4
    # Untouched baseline reference numbers.
    t01 = t["t01"].set_index("metric")["value"]
    assert t01["overall MAE (share points)"] == 4.514
    assert t01["seat-call accuracy"] == 0.7188
    assert t01["Reform UK MAE (share points)"] == 3.232
    # Woking South: pre-registered pick was the worst of 18.
    ws = t["t20"]
    pick = ws[ws.combination_pick].iloc[0]
    assert pick.news_vs_baseline == ws.news_vs_baseline.min() == -3.8037
    # Election-record counts quoted in Section 2 must match the Stage 1
    # bundle's data-quality report whenever it is present locally
    # (local-by-design artefact; a fresh clone skips this check).
    quality_path = (REPO / "surrey-election-no-news-baseline" / "outputs" /
                    "model_bundle_v1" / "data_quality_report.json")
    if quality_path.exists():
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        assert (quality["elections"], quality["contests"],
                quality["rows"]) == (24, 343, 1992)
        per = quality["party_counts_by_election"]
        by_rows = sum(v["rows"] for e, v in per.items() if "by-election" in e)
        assert by_rows == 94 and quality["rows"] - by_rows == 1898
        assert sum(1 for e in per if "by-election" in e) == 19

    # Kappa evidence quoted in the pack must match the frozen LaTeX table.
    a5 = (TABLES / "latex" / "a5_llm_validation.tex").read_text("utf-8")
    for needle in ("0.742", "0.848", "0.741", "0.736", "0.705", "0.635",
                   "0.598", "0.521"):
        assert needle in a5, needle
    # Section 5's interpretation numbers must match the committed
    # exploratory artefacts they cite.
    placebos = (REPO / "news_features" / "identity_placebos_v1" /
                "identity_placebo_findings.md").read_text("utf-8")
    for needle in ("+0.8342", "+0.8504", "+0.2291",
                   "[+0.4572, +1.2504]", "[+0.1669, +0.2876]"):
        assert needle in placebos, needle
    margins = (REPO / "news_features" / "stance_volume_margins_v1" /
               "stance_volume_findings.md").read_text("utf-8")
    for needle in ("5 of 6", "+0.0993", "+0.1327", "-0.1071", "+0.3722"):
        assert needle in margins, needle


# ----------------------------------------------------------- html helpers

def esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def df_html(df: pd.DataFrame, caption: str = "", source: str = "",
            max_rows: int | None = None, prov: str | None = None) -> str:
    body = df if max_rows is None else df.head(max_rows)
    head = "".join(f"<th>{esc(c)}</th>" for c in body.columns)
    rows = []
    for _, r in body.iterrows():
        cells = "".join(
            f"<td>{'' if pd.isna(v) else esc(v)}</td>" for v in r)
        rows.append(f"<tr>{cells}</tr>")
    note = ""
    if max_rows is not None and len(df) > max_rows:
        note = (f"<p class='src'>showing {max_rows} of {len(df)} rows; "
                f"full table in the export listed in Section 8.</p>")
    cap = f"<p class='cap'>{caption}</p>" if caption else ""
    btn = prov_btn(prov) if prov else ""
    src = f"<p class='src'>source: {source}{btn}</p>" if source else ""
    return (f"{cap}<div class='tablewrap'><table><thead><tr>{head}</tr>"
            f"</thead><tbody>{''.join(rows)}</tbody></table></div>"
            f"{src}{note}")


def tex_tabular_html(path: Path, caption: str, source: str,
                     prov: str | None = None) -> str:
    """Minimal converter for the two frozen two/three-column LaTeX tables."""
    rows, header = [], None
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if "&" not in line:
            continue
        line = line.rstrip("\\").strip()
        line = line.replace(r"\allowbreak{}", "")
        line = re.sub(r"\\texttt\{([^}]*)\}", r"<code>\1</code>", line)
        # Split into cells BEFORE any replacement that emits an HTML
        # entity: entities contain "&", and splitting after inserting
        # them shears the row into phantom columns (the a13 header bug).
        cells = []
        for cell in line.split("&"):
            cell = cell.strip()
            for a, b in ((r"\_", "_"), (r"$\kappa$", "&kappa;"),
                         (r"\Delta", "&Delta;"), ("--", "&ndash;"),
                         (r"\%", "%"), (r"\times", "&times;"), ("$", "")):
                cell = cell.replace(a, b)
            cells.append(cell)
        if header is None:
            header = cells
        else:
            rows.append(cells)
    head = "".join(f"<th>{h}</th>" for h in header)
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    btn = prov_btn(prov) if prov else ""
    return (f"<p class='cap'>{caption}</p><div class='tablewrap'><table>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
            f"</div><p class='src'>source: {source}{btn}</p>")


def img(name: str, caption: str, prov: str = "figs",
        label: str = "code behind this figure") -> str:
    return (f"<figure><img src='data:image/png;base64,{figure_b64(name)}' "
            f"alt='{esc(caption)}'><figcaption>{esc(caption)} "
            f"<span class='src'>(outputs/report_figures_v1/{name})</span>"
            f"{prov_btn(prov, label)}"
            f"</figcaption></figure>")


# ------------------------------------------------------- code provenance
#
# "Click a number, see the code that produced it." Sources are read from
# the repository at build time (never typed in), so an excerpt can only
# show what the committed pipeline actually says.

_FUNC_CACHE: dict[Path, dict[str, str]] = {}


def _functions_of(path: Path) -> dict[str, str]:
    if path not in _FUNC_CACHE:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        out: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[node.name] = ast.get_source_segment(text, node) or ""
        _FUNC_CACHE[path] = out
    return _FUNC_CACHE[path]


def extract_function(path: Path, name: str) -> str:
    funcs = _functions_of(path)
    assert name in funcs, f"{name} not found in {path}"
    return funcs[name]


def module_doc(path: Path) -> tuple[str, int]:
    """First docstring paragraph and the module's line count."""
    text = path.read_text(encoding="utf-8")
    doc = ast.get_docstring(ast.parse(text)) or ""
    para = doc.split("\n\n")[0].strip()
    return para, text.count("\n") + 1


def parse_sources() -> dict[str, str]:
    """The SOURCES dict of build_report_tables.py: manifest key -> path."""
    text = (SRC_NM / "build_report_tables.py").read_text(encoding="utf-8")
    block = text.split("SOURCES = {", 1)[1].split("\n}", 1)[0]
    pairs = re.findall(r'"(\w+)":\s*Path\(\s*((?:"[^"]*"\s*)+)\)', block)
    return {k: "".join(re.findall(r'"([^"]*)"', v)) for k, v in pairs}


# For each table: the frozen inputs (manifest keys), the upstream modules
# that computed the numbers, and the exact functions worth reading.
BRT = "build_report_tables"
PROV: dict[str, dict] = {
    "t01": {"inputs": ["unblinding", "holdout"],
            "modules": [("unblind_2026",
                         ["score_specification", "_seat_accuracy"]),
                        ("descriptive_2026_targets",
                         ["load_2026_rows", "contests_fully_correct",
                          "reform_block", "deciding_margin_mae"])],
            "builders": ["t01_baseline_reference"],
            "note": "Two sources by design: the MAEs and seat-call "
                    "accuracies come from the frozen unblinding record "
                    "(same scorer as t04/t05); the margin, per-ward "
                    "correctness and Reform descriptives are recomputed "
                    "from the scored holdout file by the annex module "
                    "excerpted here."},
    "t02": {"inputs": ["holdout"],
            "modules": [("descriptive_2026_targets",
                         ["load_2026_rows", "per_party_mae"])],
            "builders": ["t02_per_party_mae"],
            "note": "Stage 1 holdout predictions come from the "
                    "surrey-election-no-news-baseline subproject's frozen "
                    "model bundle."},
    "t03": {"inputs": ["holdout"],
            "modules": [("descriptive_2026_targets",
                         ["load_2026_rows", "seat_totals"])],
            "builders": ["t03_seat_totals", "_seat_calls"]},
    "t04": {"inputs": ["unblinding"],
            "modules": [("unblind_2026",
                         ["score_specification", "_bootstrap_rows"]),
                        ("news_estimator", ["bootstrap_improvement"])],
            "builders": ["t04_confirmatory_v1", "_confirmatory_rows"]},
    "t05": {"inputs": ["unblinding"],
            "modules": [("unblind_2026",
                         ["score_specification", "_bootstrap_rows"]),
                        ("news_estimator", ["bootstrap_improvement"])],
            "builders": ["t05_confirmatory_v2", "_confirmatory_rows"]},
    "t06": {"inputs": ["unblinding"],
            "modules": [("unblind_2026", ["score_specification"])],
            "builders": ["t06_sensitivity_summary"],
            "note": "Every sensitivity cell was scored by the SAME "
                    "score_specification as the confirmatory grid, only "
                    "with with_bootstrap=False (the pre-registered rule: "
                    "sensitivity results carry no CI and can never be "
                    "promoted). The builder then computes this table's "
                    "own numbers — counts and delta ranges per family — "
                    "from those frozen per-cell deltas."},
    "t07": {"inputs": ["unblinding", "v2_predictions"],
            "modules": [("unblind_2026", ["_seat_accuracy"])],
            "builders": ["t07_seat_accuracy", "seat_accuracy_controls"]},
    "t08": {"inputs": ["v2_predictions"], "modules": [],
            "builders": ["t08_reform_seat_calls", "_seat_calls"]},
    "t09": {"inputs": ["decompositions"],
            "modules": [("exploratory_decompositions",
                         ["decomposition_one", "_score"])],
            "builders": ["t09_attribution"]},
    "t10": {"inputs": ["decompositions"],
            "modules": [("exploratory_decompositions",
                         ["_confirmatory_blocks", "_split_errors",
                          "decomposition_two"])],
            "builders": ["t10_mechanism_pooled"]},
    "t13": {"inputs": ["approaches"],
            "modules": [("compare_news_approaches",
                         ["fitting_cells", "leave_one_election_out"]),
                        ("news_estimator", ["fit"])],
            "builders": ["t13_approaches"]},
    "t14": {"inputs": ["probe"],
            "modules": [("haslemere_probe_prediction",
                         ["load_haslemere_baseline", "score"])],
            "builders": ["t14_probe"]},
    "t15": {"inputs": ["probe"],
            "modules": [("haslemere_probe_prediction",
                         ["load_haslemere_baseline", "score"])],
            "builders": ["t15_probe_reference"]},
    "t16": {"inputs": ["catalogue"], "modules": [],
            "builders": ["t16_nonnews_channels"],
            "note": "The catalogue was hand-collected under the Haslemere "
                    "probe protocol (news_collection/haslemere_probe/)."},
    "t17": {"inputs": ["release_v2", "scenarios"],
            "modules": [("news_collection/canonical_corpus_release_v2",
                         ["build_release"])],
            "builders": ["t17_corpus"],
            "note": "The corpus counts' lineage: the collection pipeline "
                    "records a keep/drop decision (with reason) for every "
                    "one of the 2,666 candidate articles in adjudication "
                    "sheets; canonical_corpus_release (v1) takes the "
                    "union of terminal INCLUDE decisions, applies date/"
                    "window/text rules and counts 1,632; the v2 wrapper "
                    "shown here merges the 627 by-election articles "
                    "(disjointness asserted) and re-counts everything to "
                    "2,259 with the by-arm and by-window tallies. Inputs "
                    "are hashed and the release carries a stable id, so "
                    "every feature builder can prove it used this exact "
                    "corpus."},
    "t18": {"inputs": ["scenarios"],
            "modules": [("synthetic_news_scenarios",
                         ["perturb_features", "fit_frozen_specification",
                          "run_scenario"])],
            "builders": ["t18_scenarios"]},
    "t19": {"inputs": ["local_rerun"],
            "modules": [("local_v3_rerun",
                         ["reference_deltas", "main"]),
                        ("unblind_2026", ["score_specification"])],
            "builders": ["t19_local_v3_rerun"]},
    "t20": {"inputs": ["ws_unseal", "ws_protocol"],
            "modules": [("woking_south_unseal",
                         ["assert_predictions_committed",
                          "read_outcomes_once", "main"]),
                        ("woking_south_blind_protocol",
                         ["committed_delta", "derive_combination"])],
            "builders": ["t20_woking_south_unseal"]},
    "t21": {"inputs": ["ws_unseal", "ws_blind_predictions"],
            "modules": [("woking_south_unseal",
                         ["read_outcomes_once", "main"])],
            "builders": ["t21_woking_south_autopsy"]},
    "t22": {"inputs": ["per_party_bootstrap"],
            "modules": [("per_party_bootstrap",
                         ["error_split", "block_analysis",
                          "_summarise_draws"])],
            "builders": ["t22_per_party_contrast"]},
    "t23": {"inputs": ["mde"],
            "modules": [("minimal_detectable_effect",
                         ["mde_from_interval", "comparisons_annex",
                          "summarise"])],
            "builders": ["t23_mde_summary"]},
    # Non-table provenance keys.
    "elecdata": {"inputs": [],
                 "modules": [("surrey-election-extractor/scripts/"
                              "generate_no_news_candidate_contests",
                              ["generate_no_news_candidate_contests"]),
                             ("surrey-election-no-news-baseline/scripts/"
                              "build_candidate_model_bundle",
                              ["_data_quality_report"]),
                             ("study_design_figure", ["_counts"])],
                 "builders": [],
                 "note": "Lineage of the counts, upstream to downstream: "
                         "(1) the extractor subproject parses each "
                         "candidate line off the official results pages "
                         "into its audited master database; "
                         "(2) the standardisation pipeline unifies party "
                         "names, recomputes vote shares against the "
                         "published totals (0.5pp tolerance), attaches a "
                         "source link and mints candidate_contest_id — "
                         "from here ONE ROW = one candidate in one "
                         "contest; (3) _data_quality_report() counts and "
                         "health-checks those rows and writes "
                         "data_quality_report.json (the counts' "
                         "authority, in the Stage 1 bundle); (4) "
                         "downstream consumers — the study-design "
                         "figure's _counts() and this pack's build — "
                         "only re-assert against that record."},
    "newsfeat": {"inputs": ["release_v2"],
                 "modules": [("news_features/build_feature_table", ["main"]),
                             ("news_features/build_feature_table_v2",
                              ["main"])],
                 "builders": [],
                 "note": "Every aggregation rule, share definition and "
                         "zero-cell policy is frozen in the v1 builder; "
                         "the v2 wrapper re-runs it byte-identical on the "
                         "enriched corpus. Output: "
                         "news_features/news_feature_table_v2.csv, the "
                         "table the frozen Stage 2 models read."},
    "identity": {"inputs": [],
                 "modules": [("identity_placebos",
                              ["tone_trajectories", "variance_split"])],
                 "builders": [],
                 "note": "Committed artefacts: news_features/"
                         "identity_placebos_v1/ (results JSON + findings). "
                         "Every arm re-runs the frozen harness; the party "
                         "dummies read no article and are window-invariant, "
                         "so their per-window direction agreement with the "
                         "frozen specification (3 of 6) follows from the "
                         "frozen row's signs."},
    "margins": {"inputs": [],
                "modules": [("stance_volume_margins",
                             ["_pearson", "volume_weighting_check"])],
                "builders": [],
                "note": "Committed artefacts: news_features/"
                        "stance_volume_margins_v1/ (margins JSON + "
                        "findings). Replaces the earlier sign count with "
                        "per-period margins at the supervisor's direction "
                        "(2026-08-05), because cumulative windows overlap "
                        "and are not independent trials."},
    "lopo": {"inputs": [],
             "modules": [("production_news_lopo", ["run_lopo"]),
                         ("run_production_news_lopo", ["main"])],
             "builders": [],
             "note": "Pre-holdout leave-one-party-out: refit Stage 2 "
                     "with one party's training cells removed, re-score "
                     "all 18 specifications. Result: removing "
                     "Conservative cells produced 6 of 18 improvements; "
                     "removing any other party, none. Recorded in the "
                     "evidence register before unblinding."},
    "a1pred": {"inputs": [],
        "modules": [("report_appendix_tables", ["predictors"])],
        "builders": [],
        "note": "The predictor list is read from the Stage 1 bundle's "
                "feature_schema.json (the shipped model's own schema); "
                "only the plain-English glosses are authored here, and "
                "an assertion fails if the gloss map and the schema "
                "ever disagree — the table cannot drift from the "
                "model."},
    "a12cum": {"inputs": ["unblinding"],
        "modules": [("unblind_2026", ["score_specification"]),
                    ("report_appendix_tables", ["cumulative_results"])],
        "builders": [],
        "note": "Cumulative-window results were computed once at "
                "unblinding by the same scorer as the confirmatory "
                "grid (score_specification, without bootstrap — "
                "sensitivity by the pre-registered rule); this builder "
                "only expands the 18 comparisons out of the frozen "
                "record."},
    "a13feat": {"inputs": [],
        "modules": [("placebo_specifications", ["run_arm"]),
                    ("report_appendix_tables", ["content_features"])],
        "builders": [],
        "note": "Underlying record: news_features/"
                "placebo_specifications_v1/placebo_results.json — each "
                "content feature added one at a time to the frozen "
                "pair by the placebo module, post-unblinding, "
                "register-recorded; the builder formats both testable "
                "windows and asserts the headline values."},
    "llmgate": {"inputs": [],
        "modules": [
            ("news_collection/compute_review_agreement", ["cohens_kappa"]),
            ("llm_extraction/compare_d4_agreement", ["judge"]),
            ("llm_extraction/stance_classification", ["validate_rules"]),
            ("llm_extraction/freeze_layer", ["verify_evidence"]),
        ],
        "builders": [],
        "note": "The gate in execution order: every extracted record "
                "first passes per-record validation (structure, verbatim "
                "evidence, status consistency; one retry then removal); "
                "agreement between the two models and against the 168 "
                "human annotations is measured by Cohen's kappa; the "
                "pre-registered judge applies kappa >= 0.60 (with a "
                "Gwet's AC1 fallback only when label skew makes kappa "
                "unstable); layers that pass are frozen, and the freeze "
                "re-verifies every evidence span verbatim so the frozen "
                "file self-certifies."},
    "pipeline": {"inputs": [],
        "modules": [
            ("surrey-election-no-news-baseline/no_news_baseline/"
             "candidate_architecture_selection", ["select_architecture"]),
            ("surrey-election-no-news-baseline/no_news_baseline/"
             "candidate_boosted_model",
             ["boosting_params", "fit_and_predict_boosted_fold"]),
            ("surrey-election-no-news-baseline/scripts/"
             "build_candidate_model_bundle", ["_fit_selected"]),
            ("blinded_2026_predictions",
             ["strip_outcome_columns", "_fit_specification",
              "predict_specification", "_normalise_contests",
              "_assign_ranks"]),
            ("blinded_2026_predictions_v2", ["aggregate_v2_residuals"]),
        ],
        "builders": [],
        "note": "The two stages in execution order: (1) architecture "
                "selection under the pre-defined Reform-focused gates; "
                "(2) the fixed LightGBM parameters; (3) the final Stage 1 "
                "fit on the 1,150 pre-2026 rows; (4) the blinding guard "
                "that strips outcome columns before the news layer may "
                "touch the holdout; (5) residuals to election-party "
                "cells; (6) the per-window ridge fit; (7) clipping and "
                "per-contest renormalisation; (8) deterministic seat "
                "ranks. The remaining orchestrators — "
                "build_v2_blinded_predictions (writes the freeze) and "
                "write_outputs (hashes every frozen file) — are one "
                "click away via 'open full file'."},
    "stage2fit": {"inputs": [], "modules": [
        ("blinded_2026_predictions_v2", ["aggregate_v2_residuals"]),
        ("news_estimator", ["fit"])], "builders": [],
        "note": "The Stage 2 fit itself: residuals aggregated per "
                "election-party cell, then the per-window ridge."},
    "combospec": {"inputs": [],
        "modules": [("combined_specification",
                     ["supported_absolute_errors", "paired_contrast"]),
                    ("placebo_specifications", ["run_arm"]),
                    ("news_estimator", ["bootstrap_improvement"])],
        "builders": [],
        "note": "Committed artefact: news_features/"
                "combined_specification_v1/ (results JSON + findings). "
                "The final cell of the identity factorial: party "
                "identity, volume and within-party centred tone in one "
                "fit on the 45 frozen cells, via the same frozen "
                "fit/predict/score chain as every placebo arm. Each "
                "ingredient's marginal is a PAIRED contest-bootstrap "
                "contrast — both arms scored inside the same draws — "
                "and the run first re-derives every comparator arm's "
                "committed identity-placebo delta to drift 0.0, "
                "aborting on mismatch. Exploratory, post-unblinding, "
                "promotes nothing."},
    "fit2017": {"inputs": ["unblinding"],
        "modules": [("blinded_2026_predictions",
                     ["_fitting_rows_for_variant", "_fit_specification"]),
                    ("unblind_2026", ["score_specification"])],
        "builders": [],
        "note": "The 2017-only replication variant: the same frozen "
                "pipeline refitted on the 2017 party rows alone "
                "(reusing the v1 experiment's own aggregator so the "
                "replication cannot drift from the protocol it "
                "replicates), predicted on the blinded 2026 rows, and "
                "scored by the same score_specification without "
                "bootstrap. Result: 0 of 18 improve — reproducing the "
                "v1 failure and showing the signal needs the enriched "
                "training sample."},
    # Per-figure provenance: the code that COMPUTES the numbers printed
    # on each figure, not the matplotlib layout that draws them.
    "fig1": {"inputs": ["unblinding"],
        "modules": [("unblind_2026",
                     ["score_specification", "_bootstrap_rows"]),
                    ("news_estimator", ["bootstrap_improvement"]),
                    ("make_report_figures", ["figure_confirmatory"])],
        "builders": [],
        "note": "Every dot on the forest plot is a news-vs-recalibrated "
                "MAE delta and every whisker a contest-bootstrap 95% "
                "interval, both computed ONCE at unblinding by "
                "score_specification and _bootstrap_rows (via the frozen "
                "bootstrap_improvement) and written to the unblinding "
                "record — the same record t04/t05 tabulate. "
                "figure_confirmatory only reads that frozen JSON and "
                "draws; it computes nothing new."},
    "fig2": {"inputs": ["holdout"],
        "modules": [("descriptive_2026_targets",
                     ["load_2026_rows", "seat_totals"]),
                    ("make_report_figures", ["figure_seats"])],
        "builders": [],
        "note": "Each bar is a count of predicted_elected / "
                "observed_elected flags per party over the 832 scored "
                "2026 rows. seat_totals() is the annex's exact per-party "
                "count (the numbers t03 tabulates: Conservative 118 vs "
                "30, Liberal Democrats 6 vs 96, Reform 0 vs 14); "
                "figure_seats() recomputes the same counts inline with "
                "one extra step — the small local parties are grouped "
                "into a single 'Residents' assocs & other local' bar "
                "(36 predicted vs 11 actual), which is why the figure "
                "shows seven bars while t03 lists every party "
                "separately."},
    "fig4": {"inputs": ["per_party_bootstrap"],
        "modules": [("per_party_bootstrap",
                     ["error_split", "block_analysis",
                      "_summarise_draws"])],
        "builders": [],
        "note": "Each bar is contrast_point: Reform's |level-error| "
                "change minus the unweighted mean of the fitted "
                "parties' changes, for one (island, arm, window) "
                "specification; each whisker is the paired "
                "contest-bootstrap interval in which Reform AND the "
                "group mean are recomputed inside every one of the "
                "2,000 draws, so the interval belongs to the difference "
                "itself. All computed by block_analysis (point "
                "estimates via error_split, intervals via "
                "_summarise_draws) and frozen in the per-party "
                "bootstrap annex; the figure module only reads that "
                "JSON. Same source as t22."},
    "fig5": {"inputs": ["mde", "per_party_bootstrap"],
        "modules": [("minimal_detectable_effect",
                     ["mde_from_interval", "comparisons_annex"]),
                    ("per_party_bootstrap", ["block_analysis"])],
        "builders": [],
        "note": "Two numbers per row: the DOT is that party's observed "
                "|level-error| change in the 31-90-day combined cell "
                "(the abs_bias_change point estimate computed by "
                "block_analysis, read out by comparisons_annex); the "
                "GREY BAR is that party's MDE80 — the smallest effect "
                "its own bootstrap interval width could certify with "
                "~80% power, derived from the interval half-width by "
                "mde_from_interval. A dot inside its bar = an effect "
                "the design cannot distinguish from resampling noise. "
                "Same records as t22 (intervals) and t23 "
                "(thresholds)."},
    "fig6": {"inputs": ["per_party_bootstrap", "unblinding"],
        "modules": [("per_party_bootstrap",
                     ["error_split", "block_analysis"]),
                    ("unblind_2026", ["score_specification"]),
                    ("news_estimator", ["bootstrap_improvement"])],
        "builders": [],
        "note": "Two layers, two frozen sources. TOP (heatmap): each "
                "cell is one party's abs_bias_change_vs_recalibrated in "
                "one window — the per-party level-error change computed "
                "by block_analysis/error_split and stored in the "
                "bootstrap annex (same numbers as t22's party rows). "
                "BOTTOM (bars): the overall MAE delta the SAME "
                "specifications produced, with contest-bootstrap "
                "whiskers — read from the unblinding record computed by "
                "score_specification (same numbers as t05's combined "
                "rows). The figure juxtaposes the two committed "
                "records; it computes neither."},
    "fig0b": {"inputs": ["release_v2"],
        "modules": [("pipeline_overview_figure", ["_candidate_counts"]),
                    ("news_collection/canonical_corpus_release_v2",
                     ["build_release"]),
                    ("corpus_funnel_figure", ["main"])],
        "builders": [],
        "note": "The three bar totals have three computed sources: "
                "2,666 assessed = _candidate_counts() summing the three "
                "disjoint adjudication sheets the v1 release hashes; "
                "1,632 usable v1 = the count the v1 release builder "
                "froze after the five screening rules; 2,259 v2 = "
                "build_release() merging the 627 by-election articles "
                "into the v1 corpus (disjointness asserted) and "
                "re-counting. corpus_funnel_figure.main() re-reads all "
                "three counts and ASSERTS them (2,666 / 1,632 / 2,259 / "
                "national 2,071) before drawing a single bar."},
    "figs": {"inputs": ["unblinding", "release_v2", "holdout"],
             "modules": [("make_report_figures", ["figure_confirmatory"]),
                         ("study_design_figure", ["_counts"]),
                         ("corpus_funnel_figure", ["main"]),
                         ("framework_figure", ["main"])], "builders": [],
             "note": "Figure code is mostly matplotlib layout, so only "
                     "two representative functions are excerpted: the "
                     "forest-plot drawer (reads the same unblinding "
                     "record as t04/t05) and the study-design counter "
                     "(every number on that figure is computed from the "
                     "committed record, never typed). The rest of each "
                     "module is one click away via 'open full file'."},
}


# Plain-language companions to the verbatim excerpts. The code itself must
# stay byte-identical to the repository (a test enforces it), so the
# explanation lives beside the code, never inside it. Keys: "module.func".
ANNOTATIONS: dict[str, dict] = {
    "descriptive_2026_targets.contests_fully_correct": {
        "problem": "Compute t01's 'wards with both seats exactly "
                   "right': in how many contests did the baseline call "
                   "the WHOLE result perfectly?",
        "how": "Group rows by contest; a contest counts as fully "
               "correct only when the SET of predicted winners equals "
               "the SET of actual winners — both seats, exactly the "
               "same two people.",
        "numbers": "18 of 81 wards — the baseline got both seats right "
                   "in under a quarter of contests.",
        "lines": [
            ("{predicted_elected} == {observed_elected} (as sets)",
             "set equality: both predicted winners must be exactly the "
             "two real winners — one wrong name fails the ward"),
        ],
    },
    "descriptive_2026_targets.reform_block": {
        "problem": "Compute t01's Reform descriptives: how the baseline "
                   "saw (and missed) the party with no history.",
        "how": "Filter to the 162 Reform rows; average predicted and "
               "observed shares; count candidates ranked top-two "
               "(elected) in prediction vs reality.",
        "numbers": "Mean predicted 9.3% vs observed 10.7%; predicted "
                   "top-two contests 0 vs observed 14 — the baseline "
                   "never put a single Reform candidate in the top "
                   "two.",
        "lines": [
            ("sum(r[\"pred\"] for r in reform) / len(reform)",
             "mean predicted share over the 162 Reform candidates"),
            ("sum(1 for r in reform if int(r[\"predicted_rank\"]) <= 2)",
             "how many Reform candidates the baseline ranked in the "
             "top two: zero"),
        ],
    },
    "descriptive_2026_targets.deciding_margin_mae": {
        "problem": "Compute t01's deciding-margin MAE: how well did the "
                   "baseline predict the GAP that decides the last "
                   "seat?",
        "how": "Per contest, sort candidates by predicted share and by "
               "observed share; the deciding margin is 2nd place minus "
               "3rd place (the gap between the last winner and the "
               "first loser in a two-seat ward); average "
               "|predicted gap − observed gap| across contests with at "
               "least three candidates.",
        "numbers": "4.31 share points over 81 contests — the closeness "
                   "of races was mispredicted by about as much as the "
                   "shares themselves.",
        "lines": [
            ("predicted_gap = by_pred[1][\"pred\"] - by_pred[2][\"pred\"]",
             "the deciding margin: 2nd (last winner) minus 3rd (first "
             "loser) in the predicted ordering"),
            ("errors.append(abs(predicted_gap - observed_gap))",
             "per-contest error of that gap; the table reports its "
             "mean"),
        ],
    },
    "descriptive_2026_targets.load_2026_rows": {
        "problem": "Load the scored 2026 holdout rows for the "
                   "descriptive baseline tables.",
        "how": "Read the Stage 1 bundle's holdout_predictions.csv, keep "
               "only 2026 rows, parse predicted and observed shares to "
               "numbers. This file is ALREADY unblinded — these tables "
               "describe the baseline after scoring; nothing here "
               "touches the news layer's frozen files.",
        "numbers": "The 832 scored rows behind t02 and t03.",
        "lines": [
            ("row[\"election_id\"].startswith(\"surrey-county-"
             "council-2026\")",
             "2026 only — the descriptive tables are about the sealed "
             "test year"),
        ],
    },
    "descriptive_2026_targets.per_party_mae": {
        "problem": "Compute t02's numbers: each party's baseline MAE on "
                   "2026.",
        "how": "Group the rows by party; per party average "
               "|predicted \u2212 observed|; sort by candidate count.",
        "numbers": "t02's whole table — Reform 3.23 over 162 "
                   "candidates, Liberal Democrats 7.54, etc.",
        "lines": [
            ("errors[party].append(abs(row[\"pred\"] - row[\"obs\"]))",
             "per-candidate absolute error, pooled per party"),
            ("sum(v) / len(v)",
             "the party's MAE is the plain average of its candidates' "
             "errors"),
        ],
    },
    "descriptive_2026_targets.seat_totals": {
        "problem": "Compute t03's numbers: predicted vs actual seat "
                   "totals per party — the realignment table.",
        "how": "Count each party's predicted-elected flags and "
               "observed-elected flags; sort by actual seats with the "
               "party name as tie-break (set iteration is "
               "hash-randomised, so without the tie-break identical "
               "rebuilds could reshuffle equal-seat parties).",
        "numbers": "t03 and fig2: Conservatives 118 predicted vs 30 "
                   "actual, Liberal Democrats 6 vs 96, Reform 0 vs "
                   "14.",
        "lines": [
            ("if row[\"predicted_elected\"] == \"True\": "
             "predicted[party] += 1",
             "predicted seats = count of predicted-elected flags per "
             "party"),
            ("key=lambda item: (-item[2], item[0])",
             "sort by actual seats, name as tie-break — deterministic "
             "output"),
        ],
    },
    "report_appendix_tables.predictors": {
        "problem": "Emit the a1 predictor dictionary — and guarantee it "
                   "can never drift from the shipped model.",
        "how": "Read the predictor names from the Stage 1 bundle's own "
               "feature_schema.json; assert the hand-written gloss map "
               "covers exactly that set (any predictor added, removed "
               "or renamed fails the build); emit one row per "
               "predictor.",
        "numbers": "All 35 rows of a1 / report Table 3.",
        "lines": [
            ("schema = json.loads(SCHEMA.read_text(...))",
             "the names come from the model bundle's schema, not from "
             "a typed list"),
            ("assert set(names) == set(PREDICTOR_GLOSSES)",
             "gloss map and schema must match exactly — the table "
             "cannot silently drift from the model"),
        ],
    },
    "report_appendix_tables.cumulative_results": {
        "problem": "Expand the 18 cumulative-window comparisons out of "
                   "the frozen unblinding record into table a12 "
                   "(report Table 10).",
        "how": "Read the unblinding JSON; keep entries whose role is "
               "cumulative sensitivity (assert exactly 18); sort by "
               "arm then window; emit news MAE, \u0394MAE and Reform "
               "\u0394 per row; spot-assert one known value "
               "(+0.6101).",
        "numbers": "Every cell of a12 — including the best cumulative "
                   "result, previous-14-days MAE 3.8353.",
        "lines": [
            ("e[\"period_role\"] == \"cumulative_sensitivity\"",
             "the family filter again: only the 18 cumulative "
             "sensitivity entries"),
            ("assert rows[2][3] == \"+0.6101\"",
             "a spot check pins the table to the frozen record"),
        ],
    },
    "report_appendix_tables.content_features": {
        "problem": "Emit the a13 seven-content-features table, both "
                   "testable windows, with the bar comparison.",
        "how": "Read the committed placebo record; assert the bar "
               "(+0.3413), the seven features, exactly one whole-CI "
               "pass (+0.5718 [+0.3864, +0.7533]), the 91\u2013180 "
               "flip (\u22120.6094) and the all-seven overfit check "
               "(\u22120.6635); emit one row per arm.",
        "numbers": "Every cell of a13 / report Table 11.",
        "lines": [
            ("clears = entry[\"ci_lower\"] > bar",
             "'whole CI above the bar' is literally: lower bound "
             "beats +0.3413"),
            ("assert above == 1",
             "exactly one feature may clear the bar — the table "
             "refuses to print otherwise"),
        ],
    },
    "news_collection/compute_review_agreement.cohens_kappa": {
        "problem": "The gate's yardstick: compute Cohen's kappa — "
                   "agreement between two raters CORRECTED for the "
                   "agreement they would reach by pure chance.",
        "how": "Step 1: count how often the two raters actually agree "
               "(po). "
               "Step 2: from each rater's label frequencies, compute "
               "how often they would agree by luck alone (pe) — two "
               "raters who both say 'neutral' 90% of the time agree "
               "constantly without meaning anything. "
               "Step 3: kappa = (po \u2212 pe) / (1 \u2212 pe): the "
               "share of the non-chance room that was actually "
               "achieved. Returns None when kappa is undefined (no "
               "pairs, or only one label ever used — nothing to "
               "explain).",
        "numbers": "Every kappa in report Table 1 / a5: 0.848 (stance, "
                   "model\u2013model), 0.741/0.736 (vs humans), 0.742 "
                   "(issue), and the failed 0.598/0.521 that excluded "
                   "two layers.",
        "lines": [
            ("po = agree / n",
             "raw agreement: how often the two raters said the same "
             "thing"),
            ("pe = sum((r1_counts[c]/n) * (r2_counts[c]/n) ...)",
             "chance agreement from the label frequencies — the part "
             "that means nothing"),
            ("kappa = (po - pe) / (1 - pe)",
             "the formula: achieved non-chance agreement over possible "
             "non-chance agreement"),
            ("if pe >= 1.0: return po, pe, None",
             "one-category degenerate case: kappa undefined, say so "
             "instead of faking a number"),
        ],
    },
    "llm_extraction/compare_d4_agreement.judge": {
        "problem": "The pre-registered verdict machine: does one "
                   "extraction field pass the agreement gate?",
        "how": "Step 1: compute percent agreement, Cohen's kappa and "
               "Gwet's AC1 for the field's label pairs. "
               "Step 2: primary route — kappa >= 0.60 passes. "
               "Step 3: fallback route — ONLY when one label dominates "
               "(skew trigger: a marginal >= the threshold), kappa "
               "becomes unstable, so AC1 >= 0.60 plus a minimum raw "
               "agreement may pass instead. "
               "Step 4: everything (both statistics, the marginals, "
               "which route fired) goes into the verdict record — the "
               "decision is auditable, not just a yes/no.",
        "numbers": "The pass/fail column of report Table 1: which "
                   "layers ran in production, which were excluded.",
        "lines": [
            ("if kappa is not None and kappa >= GATE",
             "the primary gate: kappa >= 0.60, fixed before any score "
             "was seen"),
            ("elif skewed and ac1 is not None and ac1 >= GATE and "
             "agree >= FALLBACK_AGREEMENT",
             "the fallback fires only under label skew — a "
             "pre-registered exception, not an escape hatch"),
            ("marginals.append(max(c.values()) / n)",
             "the skew detector: how dominant is the most common "
             "label"),
            ("return {\"pairs\": n, ... \"verdict\": verdict}",
             "the full evidence behind every verdict is recorded"),
        ],
    },
    "llm_extraction/stance_classification.validate_rules": {
        "problem": "Per-record quality control: refuse any stance "
                   "record that breaks the format contract — before it "
                   "can pollute the corpus.",
        "how": "Six named checks. T1: every evidence span must appear "
               "VERBATIM in the article (no paraphrased 'quotes'). "
               "T2: low-confidence rows must be flagged for review. "
               "T3: one row per entity, no duplicates. "
               "T4: a voter-switching claim must name from\u2192to. "
               "T5/T6: status consistency — an empty record cannot "
               "claim 'extracted', a 'not_attempted' record cannot "
               "carry rows. A failing record gets one retry, then "
               "removal.",
        "numbers": "No numbers of its own — it is why the stance layer "
                   "that reached kappa = 0.848 contains only records "
                   "whose evidence is literally in the text.",
        "lines": [
            ("if text and text not in haystack",
             "T1: the quoted evidence must exist verbatim in the "
             "article — hallucinated quotes are structurally "
             "impossible"),
            ("conf < LOW_CONFIDENCE and record.get(\"review_status\") "
             "!= \"flagged\"",
             "T2: uncertain answers must route to human review, not "
             "slip through"),
            ("errors.append(f\"T3: duplicate entity rows for "
             "{dupes}\")",
             "T3: one verdict per party per article"),
            ("if record.get(\"extraction_status\") == \"extracted\"",
             "T5: an empty result may not call itself a success"),
        ],
    },
    "llm_extraction/freeze_layer.verify_evidence": {
        "problem": "Freeze-time re-verification: the frozen label file "
                   "must self-certify, not rely on checks that ran "
                   "months earlier.",
        "how": "At the moment a layer is frozen, walk every evidence "
               "span in every card and re-check it still matches the "
               "article text verbatim (the same T1 check from "
               "extraction time, run once more); record spans-checked "
               "vs spans-verified in the frozen file itself.",
        "numbers": "The verification counts stored inside the frozen "
                   "label cards.",
        "lines": [
            ("ok += text in (title if from_title else body)",
             "the whole check in one line: is the span still literally "
             "there"),
            ("return {\"spans\": total, \"verified\": ok}",
             "the frozen file carries its own audit result"),
        ],
    },
    "surrey-election-no-news-baseline/no_news_baseline/candidate_architecture_selection.select_architecture": {
        "problem": "Choose Stage 1's architecture (Ridge vs partial "
                   "pooling vs LightGBM) by a rule fixed BEFORE any "
                   "score was seen — not by taste after the fact.",
        "how": "Step 1: demand all three architectures are scored on "
               "the temporal development folds — refuse to choose from "
               "an incomplete comparison. "
               "Step 2: pool each architecture's development folds on "
               "the primary criterion (Reform-focused MAE); the holdout "
               "is never a development fold, so selection cannot read "
               "it. "
               "Step 3: walk the architectures in complexity order and "
               "only let a more complex one displace a simpler one if "
               "it clears the pre-set material-improvement gate (5%) "
               "without too many adverse folds. Verdicts are recorded.",
        "numbers": "The outcome the paper reports: LightGBM cut Reform "
                   "UK MAE by 8.3% vs Ridge (> the 5% gate) and was "
                   "selected; pooled OOF MAE 9.85 / 8.97 / 8.87 across "
                   "the three candidates.",
        "lines": [
            ("if len(present) < len(COMPLEXITY_ORDER): raise",
             "no cherry-picking by omission: all three architectures "
             "must be on the table or selection refuses to run"),
            ("score.split_role == \"development_fold\"",
             "selection pools development folds only — the 2026 holdout "
             "is structurally invisible to it"),
            ("incumbent = present[0]",
             "simplest architecture is the incumbent; complexity must "
             "pay a pre-set toll (the 5% gate) to displace it"),
        ],
    },
    "surrey-election-no-news-baseline/no_news_baseline/candidate_boosted_model.boosting_params": {
        "problem": "Keep the LightGBM hyperparameters FIXED — declared "
                   "before any outer fold was scored, immune to quiet "
                   "tuning.",
        "how": "Return a fresh copy of the declared parameter dict each "
               "call; only the random seed may be overridden. A copy "
               "every time because LightGBM mutates the dict it is "
               "handed — sharing one would let a fold silently change "
               "the next fold's parameters.",
        "numbers": "No numbers of its own; it guarantees every fold and "
                   "the final model trained under identical settings.",
        "lines": [
            ("params = dict(BOOSTING_PARAMS)",
             "fresh copy per call — no fold can mutate another fold's "
             "configuration"),
            ("if seed is not None: params[\"seed\"] = int(seed)",
             "the seed is the ONLY overridable value; everything else "
             "was declared up front"),
        ],
    },
    "surrey-election-no-news-baseline/scripts/build_candidate_model_bundle._fit_selected": {
        "problem": "Fit the SELECTED architecture on the full pre-2026 "
                   "training set (1,150 rows) — the model whose "
                   "predictions get frozen.",
        "how": "One branch per architecture, each mirroring the fold "
               "code exactly so the shipped model is the same model the "
               "comparison scored. For LightGBM: encode features "
               "(unstandardised — trees split on order), build the "
               "relative-share target (share × candidate count / 100), "
               "pick the boosting-round count by inner time-ordered "
               "validation, train with the fixed parameters. Returns "
               "model + encoder + a record of every hyperparameter "
               "choice.",
        "numbers": "The 832 frozen 2026 baseline predictions and the "
                   "792 OOF rows come from models fitted through this "
                   "path; baseline MAE 4.4410 (753 rows) follows.",
        "lines": [
            ("to_relative_share(target_vector(...), [int(r[\"candidate_"
             "count_in_contest\"]) ...])",
             "the training target: share × candidate count / 100 — "
             "mean 1 per contest, comparable across contest sizes"),
            ("CandidateFeatureEncoder(standardise=False)",
             "trees need order, not scale: unscaled columns keep split "
             "thresholds readable"),
            ("choice = select_boosting_rounds(...)",
             "the one tuned quantity (number of rounds) is chosen by "
             "inner time-ordered validation, never on the holdout"),
            ("Each branch mirrors the fold code exactly",
             "(docstring) the shipped model is the same construction "
             "the selection compared — no last-minute changes"),
        ],
    },
    "surrey-election-no-news-baseline/no_news_baseline/candidate_boosted_model.fit_and_predict_boosted_fold": {
        "problem": "ONE mock exam: fit LightGBM on everything before "
                   "this fold's polling day, predict that day's "
                   "candidates — the function that generates the OOF "
                   "rows, run once per fold (16 times).",
        "how": "Step 1: pick the boosting-round count on the fold's own "
               "inner time-ordered validation split. "
               "Step 2: encode features (unstandardised) and build the "
               "relative-share target — identical construction to the "
               "final model. "
               "Step 3: train with the fixed parameters, predict the "
               "fold's test rows, convert back to vote shares. "
               "Step 4: normalise within contest and allocate seats "
               "with EXACTLY the same helpers Architectures A and C "
               "use — a fair three-way comparison requires identical "
               "contest handling.",
        "numbers": "The 792 OOF rows (16 folds: 377 + 331 + 84) — "
                   "Stage 2's raw material — and the development-fold "
                   "scores the architecture referee pooled (9.85 / 8.97 "
                   "/ 8.87).",
        "lines": [
            ("select_boosting_rounds(train_rows, targets, seed=seed)",
             "each fold tunes its one tunable quantity on its own inner "
             "past — never on the fold's test day, never on 2026"),
            ("boosting_params(seed)",
             "the fixed parameter sheet — every fold trains under "
             "identical settings"),
            ("to_vote_share(predicted_relative, test_counts)",
             "predictions converted back from the relative-share scale "
             "to real vote shares"),
            ("normalise_within_contest(payload)",
             "identical contest handling to Architectures A and C — "
             "the comparison stays about the architecture, nothing "
             "else"),
        ],
    },
    "blinded_2026_predictions.predict_specification": {
        "problem": "Where r&#770;<sub>ep</sub> meets the candidates: "
                   "apply one fitted specification to all 832 blinded "
                   "2026 rows, producing the control column and the "
                   "news column side by side.",
        "how": "Step 1: for each candidate, start from the Stage 1 "
               "baseline prediction. "
               "Step 2: if the candidate belongs to a supported party, "
               "look up that party's two 2026 news features for this "
               "window and run the frozen model — the output is "
               "r&#770;<sub>ep</sub>, the party's news adjustment; "
               "every candidate of the same party gets the same number. "
               "Step 3: unsupported minor parties get NO adjustment but "
               "stay in the contest denominator. "
               "Step 4: build both arms — control = baseline + "
               "intercept only (r&#772;, no news), news = baseline + "
               "full adjustment — then both pass through the same "
               "clip-and-renormalise door and the same seat ranker.",
        "numbers": "The recalibrated_prediction and "
                   "news_enhanced_prediction columns of every frozen "
                   "file — the two columns later measured as 4.4454 and "
                   "4.2051.",
        "lines": [
            ("row[\"news_adjustment\"] = float(model.predict(vector)[0])",
             "r&#770;<sub>ep</sub> lands here: one predicted residual "
             "per party, stamped onto each of its candidates"),
            ("row[\"raw_recalibrated\"] = ... + (model.intercept if "
             "key is not None else 0.0)",
             "the control arm: baseline plus r&#772; alone — the "
             "no-news adjustment in code"),
            ("row[\"raw_news_enhanced\"] = ... + "
             "row[\"news_adjustment\"]",
             "the news arm: baseline plus the full "
             "r&#770;<sub>ep</sub>"),
            ("clipped = {\"recalibrated\": _normalise_contests(...), "
             "\"news_enhanced\": _normalise_contests(...)}",
             "both arms go through the identical clip-and-renormalise "
             "door — the adjustment cannot change the baseline's "
             "scale"),
        ],
    },
    "blinded_2026_predictions.strip_outcome_columns": {
        "problem": "The blinding guard: the Stage 1 holdout file on "
                   "disk contains observed columns (Stage 1 scored its "
                   "own holdout when trained) — the news layer must "
                   "never see them.",
        "how": "Copy every row, dropping every column named in "
               "OUTCOME_COLUMNS. Its sibling assert_blind_fieldnames "
               "refuses to WRITE any file whose schema mentions an "
               "outcome column — blinding enforced on the way in and "
               "the way out.",
        "numbers": "No numbers — it is the reason the frozen prediction "
                   "files physically cannot contain 2026 results.",
        "lines": [
            ("if key not in OUTCOME_COLUMNS",
             "outcome columns are dropped at the door; the news layer "
             "receives predictions and features only"),
        ],
    },
    "blinded_2026_predictions._fit_specification": {
        "problem": "Fit ONE Stage 2 model: an (arm, window) ridge on "
                   "the party-mean residual cells.",
        "how": "Step 1: build the design matrix — for each fitting "
               "cell, look up its two news features for this window "
               "(structural zero when a party had no coverage). "
               "Step 2: target = the cell's mean residual. "
               "Step 3: fit ridge with the FIXED penalty (α=1.0, never "
               "tuned). "
               "Step 4: record training-row counts, the intercept (= "
               "mean training residual — the no-news control's "
               "constant) and every standardised coefficient — the "
               "record the freeze protocol stores and every later "
               "refit is asserted against.",
        "numbers": "The frozen coefficients per specification; the "
                   "intercept behind 4.4414 (v1) / 4.4454 (v2); 12 such "
                   "fits per version.",
        "lines": [
            ("RidgeModel(FIXED_RIDGE_PENALTY)",
             "α = 1.0, fixed before validation — 11 (v1) cells cannot "
             "support tuning, and a tuned penalty would leak"),
            ("\"intercept_mean_training_residual\": model.intercept",
             "the no-news control's constant is literally this model's "
             "intercept, recorded at fit time"),
            ("\"standardised_coefficients\": {...}",
             "the exact values fit_frozen_specification re-asserts to "
             "1e-9 before any scenario may run"),
        ],
    },
    "blinded_2026_predictions._normalise_contests": {
        "problem": "After adding an adjustment, predictions must stay "
                   "legal vote shares: none negative, each contest "
                   "summing to 100.",
        "how": "Group rows by contest; clip negatives to zero (counting "
               "how many); rescale each contest's shares to sum to "
               "exactly 100; refuse to proceed if a contest has no "
               "positive prediction. Applied identically to the news "
               "arm and the control, so the adjustment cannot quietly "
               "change the baseline's scale.",
        "numbers": "Every frozen prediction column passed through here; "
                   "the clipping counts per arm are recorded (e.g. the "
                   "2021 Reform 41.2% clipping discussed in §5.4).",
        "lines": [
            ("if value < 0: clipped += 1; value = 0.0",
             "negative shares are impossible — clipped and counted, "
             "not hidden"),
            ("row[output_column] = 100.0 * value / total",
             "each contest rescaled to exactly 100 — shares stay "
             "shares"),
            ("raise ProductionExperimentError(\"A contest has no "
             "positive prediction.\")",
             "a fully-zero contest is an error, never a silent output"),
        ],
    },
    "blinded_2026_predictions._assign_ranks": {
        "problem": "Turn each contest's predicted shares into "
                   "elected/not-elected calls, deterministically.",
        "how": "Group by contest; sort by predicted share descending "
               "with candidate id as tie-break (two runs can never "
               "disagree — the tie-break is recorded in the protocol); "
               "the top k are elected, k = the contest's seat count (a "
               "pre-election fact: two-member wards in 2026).",
        "numbers": "The news_predicted_elected flags that seat-call "
                   "accuracy (t07) and the scenario seat-flips (t18) "
                   "are computed from.",
        "lines": [
            ("key=lambda row: (-float(row[share_column]), "
             "str(row[\"candidate_contest_id\"]))",
             "share descending, id as tie-break: deterministic ranking"),
            ("row[\"news_predicted_elected\"] = position <= seats",
             "top-k are called elected; k is fixed before the election"),
        ],
    },
    "unblind_2026.score_specification": {
        "problem": "The study's marking machine: turn one specification's "
                   "832 frozen predictions plus the real 2026 results "
                   "into that specification's complete scorecard. Called "
                   "once per grid cell — 24 confirmatory cells (v1/v2 × "
                   "combined/national × 6 windows, with bootstrap) and "
                   "every sensitivity cell (local arm, cumulative "
                   "windows, without bootstrap) — same arithmetic "
                   "everywhere.",
        "how": "Step 1: join — look each candidate's real result up by "
               "id, so prediction and truth sit in one record. "
               "Step 2: filter — keep the 753 supported-party rows "
               "(six study parties); carve out the 162 Reform rows as a "
               "subset. "
               "Step 3: score — for each of the three prediction columns "
               "(raw baseline / no-news control / news model), take "
               "|prediction − observed| per candidate and average: "
               "that is the MAE. "
               "Step 4: subtract — ΔMAE = control MAE − news MAE; "
               "positive means news reduced error. "
               "Step 5: repeat steps 3–4 on the Reform subset via the "
               "SAME inner function scope() — identical arithmetic, "
               "smaller crowd — giving the Reform Δ. "
               "Step 6: only if this cell is confirmatory, bootstrap the "
               "overall difference (2,000 contest resamples) for the CI.",
        "numbers": "Per cell: control MAE → t04/t05 'recalibrated_mae' "
                   "(4.445 at the headline cell); news MAE → 'news_mae' "
                   "(4.205); their difference → 'news_vs_recalibrated' "
                   "(+0.240); Reform's own MAE and Δ → the two Reform "
                   "columns (−0.688); seat-call accuracy → t07; the "
                   "resample distribution → CI [+0.078, +0.387].",
        "lines": [
            ("observed[row[\"candidate_contest_id\"]]",
             "the join: fetch this candidate's real result by id — "
             "prediction and truth now share a row"),
            ("row[\"included_in_reported_metrics\"] == \"True\"",
             "CSV stores booleans as text, so equality against the "
             "string converts it back — a detail examiners like to ask "
             "about"),
            ("supported = [...]",
             "832 → 753: only supported-party rows enter reported "
             "metrics; the unsupported rows still exist for seat calls"),
            ("reform = [row for row in supported ...]",
             "Reform is a SUBSET of supported (162 rows) — it will be "
             "scored by the same arithmetic, not by separate code"),
            ("def scope(rows):",
             "defined once, called twice: scope(supported) for the "
             "overall scorecard, scope(reform) for Reform's — one "
             "scorer, two crowds"),
            ("recalibrated.get(\"mae\", 0) - news.get(\"mae\", 0)",
             "THE number: ΔMAE = control error − news error; positive "
             "means news helps (4.445 − 4.205 = +0.240)"),
            ("\"reform_uk\": scope(reform)",
             "Reform's Δ (−0.688) comes from this call — same formula, "
             "162 rows"),
            ("_seat_accuracy(joined, ...)",
             "seat calls use all 832 joined rows, not just supported — "
             "elected/not-elected is judged for everyone"),
            ("if with_bootstrap:",
             "the only fork between confirmatory and sensitivity cells: "
             "True → CI computed; False → identical scorecard, no "
             "interval, never promotable"),
            ("_bootstrap_rows(supported, ...)",
             "CI is computed for the overall result only — passing "
             "`supported`, not `reform`, is why Reform's Δ carries no "
             "interval"),
        ],
    },
    "news_estimator.bootstrap_improvement": {
        "problem": "The actual CI machine: turn the prepared error pairs "
                   "into the 95% interval.",
        "how": "Step 1: group the error pairs by contest using the ids "
               "_bootstrap_rows kept. "
               "Step 2: 2,000 times, draw contests WITH replacement "
               "(81 draws from 81 contests; repeats allowed) and pool "
               "their candidates. "
               "Step 3: in each draw compute control MAE, news MAE and "
               "their difference — one resampled ΔMAE per draw. "
               "Step 4: sort the 2,000 ΔMAEs and take the 2.5th and "
               "97.5th percentiles: the middle 95% is the interval. "
               "A fixed random seed makes all 2,000 draws exactly "
               "reproducible.",
        "numbers": "ci_lower/ci_upper in every confirmatory row — "
                   "[+0.078, +0.387] at the headline cell — plus the "
                   "share of draws favouring news.",
        "lines": [
            ("by_contest.setdefault((r[\"election_id\"], "
             "r[\"area_id\"]), []).append(r)",
             "group by contest — the unit of independence"),
            ("rng = np.random.default_rng(seed)",
             "fixed seed: the 'random' interval is bit-for-bit "
             "reproducible"),
            ("picked = rng.integers(0, len(contests), size=len(contests))",
             "with replacement: 81 draws from 81 contests, repeats "
             "allowed — one bootstrap resample"),
            ("draws.append(base - news)",
             "one resampled ΔMAE per draw; 2,000 of these"),
            ("np.percentile(draws, 2.5)",
             "middle 95% of the 2,000 values = the interval"),
        ],
    },
    "unblind_2026._bootstrap_rows": {
        "problem": "Prepare the raw material the confidence interval is "
                   "built from — the CI machinery cannot eat full "
                   "candidate records, it needs one error pair per row, "
                   "grouped by contest.",
        "how": "Step 1: for each candidate compute |control prediction − "
               "observed share| (the control's error on this person). "
               "Step 2: compute |news prediction − observed share| (the "
               "news model's error). "
               "Step 3: keep the election and contest ids alongside the "
               "two errors and drop everything else. "
               "Downstream, 2,000 resamples draw whole CONTESTS from "
               "this material and recompute ΔMAE each time; the middle "
               "95% of those 2,000 values is the interval.",
        "numbers": "Feeds the CI [+0.078, +0.387] on the headline card "
                   "and every ci_lower/ci_upper cell in t04/t05.",
        "lines": [
            ("\"area_id\": row[\"division_id\"]",
             "kept because resampling draws whole contests: within a "
             "contest candidates' errors are linked (shares sum to 100), "
             "so the contest — not the candidate — is the independent "
             "unit"),
            ("abs(row[comparator_key] - row[\"observed_vote_share\"])",
             "absolute error per candidate; MAE is the mean of these. "
             "comparator_key lets the same code serve both comparisons "
             "(vs control, vs raw baseline)"),
        ],
    },
    "build_report_tables._confirmatory_rows": {
        "problem": "Convert the sealed unblinding JSON into the 12 tidy "
                   "rows of Table t04/t05 — formatting with one crucial "
                   "act of gatekeeping.",
        "how": "Step 1: filter — of everything the unblinding record "
               "holds, admit only entries whose family is "
               "'confirmatory' (the 12 pre-registered comparisons for "
               "this version); cumulative and local sensitivity entries "
               "in the same JSON are not let through. "
               "Step 2: sort windows in time order (180-91 first, final "
               "72h last). "
               "Step 3: rename internal labels to display labels. "
               "Step 4: round every value to 3 decimals and emit one row "
               "per comparison.",
        "numbers": "Every cell of t04/t05 — 4.445 (control), 4.205 "
                   "(news), +0.240 (ΔMAE), both CI columns, and the two "
                   "Reform columns (−0.688 at the headline cell).",
        "lines": [
            ("e[\"family\"] == \"confirmatory\"",
             "the confirmatory/exploratory boundary as one line of code: "
             "sensitivity results cannot leak into the confirmatory "
             "table"),
            ("sorted(entries, key=_window_rank)",
             "windows appear in campaign-time order, not alphabetical"),
            ("ARM_LABEL[entry[\"analysis\"]]",
             "internal name → display name: 'combined_exploratory' "
             "becomes 'combined'"),
            ("round(..., 3)",
             "the table pack keeps 3 decimals — why the paper says "
             "4.4454 but the CSV says 4.445 (same number, two "
             "roundings)"),
        ],
    },
    "unblind_2026._seat_accuracy": {
        "problem": "Score the secondary outcome: of all elected / "
                   "not-elected calls the news model made, what share "
                   "was right?",
        "how": "Step 1: for each candidate compare the model's "
               "predicted-elected flag with what actually happened. "
               "Step 2: count matches. "
               "Step 3: divide by the number of rows — one number per "
               "specification. Note it runs on all 832 joined rows: "
               "elected/not-elected is judged for every candidate, not "
               "just supported parties.",
        "numbers": "The seat-call accuracy column of t07 (e.g. 0.8317 at "
                   "91–180 days, 0.7909 at 31–90) — compared there "
                   "against the 0.8053 elect-nobody floor, which no "
                   "confirmed-MAE specification beats.",
        "lines": [
            ("str(row[flag_key]) == str(row[\"observed_elected\"])",
             "string-compare both flags (CSV text again): did the "
             "predicted call match reality for this candidate?"),
            ("round(correct / len(rows), 4)",
             "accuracy = correct calls ÷ all calls"),
        ],
    },
    "build_report_tables._seat_calls": {
        "problem": "Turn a column of predicted vote shares into seat "
                   "calls, exactly as the frozen ranker did — so control "
                   "arms can be scored on seats too.",
        "how": "Step 1: group candidates by contest. "
               "Step 2: within each contest sort by predicted share, "
               "highest first, breaking ties on candidate id so two runs "
               "can never disagree. "
               "Step 3: elect the top k, where k is the contest's seat "
               "count (two in every 2026 ward). "
               "Step 4: return an elected/not-elected flag per "
               "candidate.",
        "numbers": "t03's seat totals (baseline: Conservatives 118 "
                   "predicted vs 30 actual, Reform 0 vs 14) and t08's "
                   "Reform seat calls (0 in every specification).",
        "lines": [
            ("sorted(contest_rows, key=lambda r: (-float(r[share_column]), "
             "str(r[\"candidate_contest_id\"])))",
             "rank by share descending; the id tie-break makes the "
             "allocation deterministic"),
            ("position <= seats",
             "top-k are elected; k = the contest's seat count"),
        ],
    },
    "build_report_tables.seat_accuracy_controls": {
        "problem": "The frozen record scored news seat calls against the "
                   "RAW baseline only — the recalibrated control (the "
                   "comparator every MAE delta uses) was never given a "
                   "seat allocation. This builds the missing comparator, "
                   "plus the metric's trivial floor.",
        "how": "Step 1: read the committed v2 prediction file. "
               "Step 2: for each specification, allocate seats from the "
               "CONTROL's predicted shares using the same deterministic "
               "ranker, and score those calls. "
               "Step 3: compute the elect-nobody floor — every 2026 ward "
               "elects 2 from a longer field, so most rows are "
               "not-elected, and a model that elects nobody is right "
               "about all of them.",
        "numbers": "t07's 'vs control' column and the 0.8053 floor — the "
                   "context showing seat-call accuracy below the floor "
                   "is worse than refusing to answer.",
        "lines": [
            ("calls = _seat_calls(spec_rows, \"recalibrated_prediction\")",
             "the control gets its seat allocation from the same ranker "
             "the news arm used — like for like"),
            ("[\"observed_elected\"]) == \"False\"",
             "the floor counts how often 'nobody wins' is right — "
             "0.8053 of all calls"),
        ],
    },
    "synthetic_news_scenarios.perturb_features": {
        "problem": "Answer 'what if n more articles about party P with "
                   "tone T had been collected?' — at the feature level, "
                   "changing exactly the numbers those articles would "
                   "have changed.",
        "how": "Step 1: copy the frozen feature table (originals "
               "untouched). "
               "Step 2: find the 2026 cells for the chosen window; raise "
               "the window's article total by n and P's article count "
               "by n. "
               "Step 3: if the tone is favourable/unfavourable, raise "
               "that count too and recompute P's net portrayal = "
               "(favourable − unfavourable) ÷ P's articles; a neutral "
               "story moves volume but not tone. "
               "Step 4: the denominator grew for everyone — recompute "
               "EVERY party's article share under the new total "
               "(injected Reform coverage dilutes everyone else's share; "
               "arithmetic, not a modelling choice).",
        "numbers": "The perturbed inputs behind every t18 row and every "
                   "live run in the Streamlit scenario page.",
        "lines": [
            ("if tone not in (\"favourable\", \"unfavourable\", "
             "\"neither\")",
             "three tones only; 'neither' is the volume-without-tone "
             "contrast"),
            ("new_total = old_total + articles",
             "the window's denominator grows by exactly n"),
            ("f\"{(favourable - unfavourable) / party_count:.6f}\"",
             "net portrayal recomputed for the target party only"),
            ("cell[columns[\"share\"]] = ... count / new_total",
             "every party's share recomputed — the dilution effect"),
        ],
    },
    "synthetic_news_scenarios.fit_frozen_specification": {
        "problem": "Guarantee scenarios run on the FROZEN model — a "
                   "drifted input must fail loudly, never produce "
                   "quietly different what-ifs.",
        "how": "Step 1: load the frozen protocol's record for this "
               "(arm, window). "
               "Step 2: rebuild the training rows from the same Stage 1 "
               "bundle the freeze used (the fit is deterministic). "
               "Step 3: refit the ridge. "
               "Step 4: compare every standardised coefficient with the "
               "protocol's recorded value; any difference beyond 1e-9 "
               "raises an error and no scenario runs.",
        "numbers": "No numbers of its own — it is the integrity gate "
                   "both t18 and the Streamlit app pass through before "
                   "anything is predicted.",
        "lines": [
            ("if abs(refit_value - frozen_value) > 1e-9",
             "the assertion: refit must reproduce the frozen "
             "coefficients to nine decimal places"),
            ("raise ProductionExperimentError(...no scenario may run "
             "against an unfrozen model\")",
             "failure is loud and total — there is no 'run anyway'"),
        ],
    },
    "synthetic_news_scenarios.run_scenario": {
        "problem": "Turn one perturbed feature table into 'what moved' — "
                   "the before/after comparison that is a scenario's "
                   "entire output.",
        "how": "Step 1: predict 2026 with the frozen model on UNTOUCHED "
               "features (the reference). "
               "Step 2: predict again on the perturbed features — same "
               "model, same clipping at zero, same renormalisation to "
               "100 per contest. "
               "Step 3: subtract per candidate, average per party. "
               "Step 4: record which elected/not-elected calls flipped. "
               "Step 5: record how many articles the cell held before "
               "injection — ten articles are a ripple on 300 and a flood "
               "on 10, so no delta is read without its denominator.",
        "numbers": "t18's Δ column (favourable Reform story +1.00pp vs "
                   "unfavourable −2.00pp; final-72h story −0.82pp with 8 "
                   "seat flips), the seat-flip count, and the "
                   "cell-context columns.",
        "lines": [
            ("reference, _ = predict_specification(...)",
             "the before-picture: frozen model on unperturbed features"),
            ("perturbed_features = perturb_features(...)",
             "the injection happens here, between the two predictions"),
            ("row[\"news_enhanced_prediction\"] - "
             "before[\"news_enhanced_prediction\"]",
             "per-candidate delta; averaged per party for the report"),
            ("window_articles_before_injection",
             "the denominator context recorded with every scenario"),
        ],
    },
    "news_features/build_feature_table_v2.main": {
        "problem": "The v2 wrapper: rebuild the feature table on the "
                   "enriched corpus WITHOUT touching a single "
                   "aggregation rule — its main() is one line, "
                   "delegating to the frozen v1 builder.",
        "how": "The module overrides exactly three globals before "
               "delegating: the output paths (news_feature_table_v2.*), "
               "the corpus source (release v2 instead of v1), and the "
               "election grid (adding the eight by-elections). It also "
               "names three tranches extracted AFTER this table was "
               "written (haslemere1, e5local1, wokingsouth1 — 321 "
               "articles belonging to other lineages, one of which "
               "failed its own kappa gate at 0.476) and excludes them, "
               "which restores the property that the rebuild is "
               "byte-identical to the committed CSV.",
        "numbers": "news_feature_table_v2.csv — 864 rows, the table the "
                   "frozen Stage 2 models read.",
        "lines": [
            ("def main(): frozen.main()",
             "the whole wrapper: every rule runs from the v1 builder, "
             "unchanged"),
            ("frozen.GRID_ELECTIONS = ... | {SCC-2013..., ESWS-2026...}",
             "(module level) the grid gains the eight enrichment "
             "by-elections"),
            ("frozen.EXCLUDED_TRANCHES = {haslemere1, e5local1, "
             "wokingsouth1}",
             "(module level) three later tranches from other lineages "
             "are named and excluded — with this line the rebuild is "
             "byte-identical to the committed CSV; without it the table "
             "cannot be rebuilt at all"),
        ],
    },
    "news_features/build_feature_table.main": {
        "problem": "THE feature factory: turn labelled articles into "
                   "the election\u00d7party\u00d7period feature table "
                   "\u2014 the two formulas that define 'party article "
                   "share' and 'net portrayal' live here (and only "
                   "here; every later use is frozen re-use).",
        "how": "Step 1: load the labelled article records and sum "
               "counts per (election, party, window) and per arm. "
               "Step 2: walk the FULL election\u00d7party\u00d7period "
               "grid \u2014 including cells where a completed search "
               "found zero articles; dropping them would turn a real "
               "zero into a missing observation. "
               "Step 3: per cell compute the two features \u2014 "
               "share = party articles \u00f7 window total; net "
               "portrayal = (favourable \u2212 unfavourable) \u00f7 "
               "party articles. Counts are genuine zeroes, but a share "
               "whose DENOMINATOR is zero stays blank: 0/0 is not 'a "
               "share of zero', it is undefined, and the model gets an "
               "explicit missing-value policy instead of a fabricated "
               "proportion. "
               "Step 4: emit the same pair separately for the local and "
               "national arms (the columns the "
               "baseline/local/national/combined comparison needs).",
        "numbers": "Every news number the frozen models ever see: the "
                   "party_article_share and net_portrayal_share columns "
                   "of the feature table (288 rows v1, 864 rows v2) "
                   "\u2014 the x\u2091\u209a\u2c7c in the \u00a74.3 "
                   "equation.",
        "lines": [
            ("\"party_article_share\": round(p[\"party_article_count\"] "
             "/ total, 6) if total else \"\"",
             "feature 1, visibility: the party's articles over the "
             "window total \u2014 blank (not zero) when the window has "
             "no articles at all"),
            ("\"net_portrayal_share\": round((fav - unfav) / "
             "p[\"party_article_count\"], 6) if "
             "p[\"party_article_count\"] else \"\"",
             "feature 2, tone: (favourable \u2212 unfavourable) over "
             "the party's articles; neutral sits in the denominator "
             "only"),
            ("zero_article_cells.append({...})",
             "a completed search that found nothing is kept and "
             "logged, never silently dropped \u2014 a real zero is "
             "data"),
            ("for arm, arm_party in by_arm.items():",
             "the same two formulas emitted per collection arm "
             "(local_/national_ prefixes) \u2014 three arms, three "
             "copies of the pair"),
        ],
    },
    "news_collection/canonical_corpus_release_v2.build_release": {
        "problem": "THE corpus-counting code: produce the authoritative "
                   "article counts — 2,259 total, 188 local / 2,071 "
                   "national, and the per-window tallies (1,840 / 314 / "
                   "41 / 36 / 11 / ...) — as a hashed, id-stamped "
                   "release.",
        "how": "Step 1: take the v1 release (the 1,632 usable "
               "principal-election articles, themselves the terminal "
               "INCLUDE decisions filtered by date, window and text "
               "rules). "
               "Step 2: load the 627 by-election articles and ASSERT the "
               "two families share no article id. "
               "Step 3: merge, then count with Counter(): per arm, per "
               "election, per window, per election-and-arm — plain "
               "tallying of labelled articles. "
               "Step 4: hash the input sheets and stamp a release id "
               "derived from those hashes, so any consumer can prove it "
               "used exactly this corpus.",
        "numbers": "Everything in canonical_corpus_release_v2.json: the "
                   "2,259 / 188 / 2,071 on the funnel and in t17, and "
                   "the per-window numbers behind the far-window-skew "
                   "caveat.",
        "lines": [
            ("principal_report, principal = v1.build_release()",
             "v2 stands on v1: the 1,632 usable principal-election "
             "articles come from the v1 rules unchanged"),
            ("assert not overlap",
             "the by-election family may not share a single article id "
             "with the principal family — double counting is impossible"),
            ("by_window = Counter(a[\"window\"] for a in "
             "articles.values())",
             "the per-window tallies are a plain Counter over each "
             "article's window label — 1,840 in 91-180 days etc."),
            ("release_id = \"canonical-news-v2-\" + hashlib.sha256(...)",
             "the release id is derived from the input hashes: same "
             "inputs, same id; changed inputs, new id"),
        ],
    },
    "surrey-election-extractor/scripts/generate_no_news_candidate_contests.generate_no_news_candidate_contests": {
        "problem": "The ROW FACTORY: this is where the 1,992 candidate "
                   "rows are manufactured — the release every Stage 1 "
                   "count, model and report number ultimately stands on.",
        "how": "Step 1: load the audited elections — the extractor's "
               "master database built from the official results pages, "
               "with reviewed geographic mappings and reviewed "
               "historical-reference decisions. "
               "Step 2: build one record per candidate per contest, "
               "attaching continuity evidence (did this candidate stand "
               "before?). "
               "Step 3: write PREDICTORS and OUTCOMES to two separate "
               "files, joined only by candidate_contest_id — model code "
               "physically cannot stumble on an outcome column while "
               "selecting features (a leakage guard built into the file "
               "layout). "
               "Step 4: write a coverage audit alongside. Deterministic: "
               "same inputs, byte-identical output.",
        "numbers": "The 1,992 rows themselves (features + targets "
                   "files), which _data_quality_report() then counts "
                   "into 24 / 343 / 1,992.",
        "lines": [
            ("elections = load_audited_elections()",
             "input = the audited master database from the official "
             "pages — not raw scraping"),
            ("features, targets, coverage = "
             "build_no_news_candidate_contests(payload)",
             "the moment the rows are born: one candidate in one "
             "contest per row"),
            ("write_text(...features...) / write_text(...targets...)",
             "predictors and outcomes land in SEPARATE files — the "
             "anti-leakage file layout"),
            ("\"this file can never disagree with the master database\"",
             "same reviewed inputs as every other release: one source "
             "of truth for what comparisons are permitted"),
        ],
    },
    "surrey-election-no-news-baseline/scripts/build_candidate_model_bundle._data_quality_report": {
        "problem": "THE counting code: turn the standardised candidate "
                   "tables into the headline counts (24 / 343 / 1,992, "
                   "rows per election) — and health-check the data while "
                   "counting.",
        "how": "Step 1: rows — every candidate occupies exactly one row, "
               "so the total is len(features) = 1,992. "
               "Step 2: contests — group rows by (election_id, "
               "division_id) and count the groups: 343. "
               "Step 3: elections — deduplicate election_id: 24. "
               "Step 4: rows per election — sweep the table once, "
               "incrementing that election's counter per row (the "
               "358/377/331/379/453 and the 94 by-election rows come "
               "from summing these). "
               "Step 5: while counting, health-check — every contest's "
               "shares must sum to ~100 (with a stated tolerance), no "
               "share outside 0–100, no duplicate ids, features and "
               "targets must match one-to-one.",
        "numbers": "Everything in data_quality_report.json: 1,992 rows, "
                   "343 contests, 24 elections, per-election row counts "
                   "(hence the 1,898-vs-94 principal/by-election split), "
                   "plus the validation verdicts.",
        "lines": [
            ("\"rows\": len(features)",
             "1,992 is literally the number of rows — one candidate, "
             "one row"),
            ("contests = group_by_contest(features) ... len(contests)",
             "343 = number of (election, division) groups"),
            ("len({str(row[\"election_id\"]) for row in features})",
             "24 = distinct election ids after deduplication"),
            ("by_election[str(row[\"election_id\"])][\"rows\"] += 1",
             "the per-election tallies: sweep once, +1 to the owning "
             "election — source of 358/377/331/379/453 and the 94"),
            ("100 - tolerance <= total <= 100 + tolerance",
             "health check during counting: every contest's shares must "
             "reconcile to ~100"),
            ("len(ids) - len(set(ids))",
             "duplicate-id check: must be zero or the report exposes "
             "it"),
        ],
    },
    "combined_specification.supported_absolute_errors": {
        "problem": "Produce one arm's per-candidate error list, keyed "
                   "by candidate id, so two arms can later be compared "
                   "on IDENTICAL rows.",
        "how": "Step 1: fit the arm's ridge on the 45 frozen cells and "
               "predict the blinded 2026 rows — same frozen calls as "
               "run_arm, so an arm's errors here and its delta there "
               "come from identical predictions. "
               "Step 2: per supported candidate, store |prediction − "
               "observed| along with the contest ids the bootstrap "
               "needs.",
        "numbers": "The raw material of every cell in the marginals "
                   "table (753 error pairs per contrast).",
        "lines": [
            ("errors[row[\"candidate_contest_id\"]] = {...}",
             "keyed by candidate id — the pairing handle: the same "
             "person's error under two arms"),
        ],
    },
    "combined_specification.paired_contrast": {
        "problem": "Compute one ingredient's marginal: does the full "
                   "three-ingredient arm beat the nested arm missing "
                   "that ingredient — with an interval on the "
                   "DIFFERENCE?",
        "how": "Step 1: join the two arms' error lists by candidate id "
               "into one row per person (comparator error, full "
               "error). "
               "Step 2: point estimate = comparator MAE − full MAE "
               "(positive = the full arm is better, i.e. the "
               "ingredient adds value). "
               "Step 3: reuse the FROZEN bootstrap (same resampler, "
               "same seed): each draw picks contests once and scores "
               "both arms on that draw, so the interval belongs to "
               "the difference, not to two overlapping marginals.",
        "numbers": "Every cell of the paired-marginals table, "
                   "including tone's marginal at 31-90d: −0.1229 "
                   "[−0.1595, −0.0879] — centred tone SUBTRACTS "
                   "out-of-sample value once identity and volume are "
                   "known.",
        "lines": [
            ("\"baseline_absolute_error\": entry[\"absolute_error\"], "
             "\"news_absolute_error\": full_errors[key][...]",
             "the pairing: one row = one candidate under both arms — "
             "the same trick as the headline CI"),
            ("interval = bootstrap_improvement(rows)",
             "the same frozen CI machine, re-aimed at an arm-vs-arm "
             "difference"),
        ],
    },
    "placebo_specifications.run_arm": {
        "problem": "Run one content-feature placebo specification "
                   "through the FROZEN pipeline: the frozen pair plus "
                   "one extra content feature, scored exactly like the "
                   "real thing.",
        "how": "Step 1: fit the frozen per-window ridge with the "
               "augmented column list on the same 45 cells. "
               "Step 2: predict the blinded 2026 rows with the frozen "
               "applier (clipping and renormalisation included). "
               "Step 3: rank seats deterministically, then hand the "
               "predictions to score_specification WITH bootstrap. "
               "Post-unblinding and register-recorded — these CIs "
               "diagnose, they cannot promote.",
        "numbers": "Every delta and CI in a13 — e.g. positive_share "
                   "at 31-90d +0.5718 [+0.3864, +0.7533], the only "
                   "whole-CI pass; the all-seven bundle −0.6635.",
        "lines": [
            ("model, record = _fit_specification(cells, feature_index, "
             "period=window, feature_columns=columns)",
             "same frozen fit, one extra column — the ONLY thing that "
             "changes per placebo arm"),
            ("metrics = score_specification(predictions, observed, "
             "with_bootstrap=True)",
             "same marking machine as the confirmatory grid, so a13's "
             "numbers are comparable by construction"),
        ],
    },
    "woking_south_blind_protocol.committed_delta": {
        "problem": "Look up one arm×window's committed 2026 delta — "
                   "the raw material for the blind test's arm-picking "
                   "rule.",
        "how": "Local deltas come from the v3 re-run record; combined "
               "and national from the frozen unblinding record's "
               "confirmatory entries. Read, never recomputed.",
        "numbers": "The 18 deltas in t20's derivation table.",
        "lines": [
            ("if (entry[\"family\"] == \"confirmatory\" ...",
             "only committed, pre-existing numbers may steer the "
             "blind pick"),
        ],
    },
    "woking_south_blind_protocol.derive_combination": {
        "problem": "Freeze the blind test's arm-picking rule as code: "
                   "which arm serves each window, decided BEFORE the "
                   "Woking South result exists.",
        "how": "Step 1: per window, look up the three arms' committed "
               "2026 deltas. "
               "Step 2: the window goes to the arm with the largest "
               "delta; ties at 4 dp fall to alphabetical order — even "
               "the tie-break is frozen. "
               "Step 3: return the full delta table beside the "
               "winners, so the derivation is visible, not just its "
               "result.",
        "numbers": "t20's combination_pick column — including the "
                   "pre-registered pick (local, 91-180d) that turned "
                   "out worst of 18.",
        "lines": [
            ("winner = max(sorted(deltas), key=lambda arm: deltas[arm])",
             "the whole rule in one line: largest committed delta "
             "wins, sorted() fixes the tie-break"),
        ],
    },
    "run_production_news_lopo.main": {
        "problem": "The LOPO runner: wire the committed inputs into "
                   "run_lopo and print the verdict.",
        "how": "Calls run_lopo on the frozen feature table, audit, "
               "OOF file and primary results; writes the record and "
               "prints the counts — including the explicit '2026 "
               "holdout read: no'.",
        "numbers": "The printed summary of the LOPO record.",
        "lines": [
            ("print(\"2026 holdout read       : no\")",
             "the check is pre-holdout by construction and says so"),
        ],
    },
    "blinded_2026_predictions._fitting_rows_for_variant": {
        "problem": "Serve the training cells for whichever declared "
                   "fit variant is being run — the main pooled fit or "
                   "the 2017-only replication.",
        "how": "Step 1: 'pooled_2017_2021' → the standard pooled "
               "residual cells (the production v1 fit). "
               "Step 2: 'fit_2017_only' → ONLY the 2017 party rows, "
               "produced by the v1 experiment's own aggregator, so the "
               "replication variant cannot drift from the protocol it "
               "replicates. "
               "Step 3: any other name raises — variants must be "
               "declared, not improvised.",
        "numbers": "The training cells behind the 2017-only "
                   "sensitivity family in t06 (0 of 18 improve).",
        "lines": [
            ("if variant == \"fit_2017_only\":",
             "the replication fork: same pipeline, smaller declared "
             "training set"),
            ("raise ProductionExperimentError(f\"Unknown fitting "
             "variant: {variant!r}\")",
             "no undeclared variants can ever run"),
        ],
    },
    "build_report_tables.t06_sensitivity_summary": {
        "problem": "Compute t06's numbers: per (version, family), how "
                   "many sensitivity comparisons ran, how many improved, "
                   "and the best/worst delta — a summary instead of 84 "
                   "rows of non-promotable detail.",
        "how": "Step 1: walk the frozen unblinding record and keep only "
               "entries whose family is 'sensitivity' (the mirror image "
               "of t04/t05's confirmatory filter). "
               "Step 2: bucket the deltas by (version, analysis group). "
               "Step 3: per bucket, count the comparisons, count deltas "
               "> 0, and take max and min.",
        "numbers": "All of t06 — e.g. v2 local_sensitivity: 12 "
                   "comparisons, 8 improved, best +0.508, worst −0.833.",
        "lines": [
            ("if entry[\"family\"] != \"sensitivity\": continue",
             "only sensitivity cells enter — the same one-line boundary "
             "that keeps them OUT of t04/t05"),
            ("\"improved\": sum(1 for d in deltas if d > 0)",
             "the improved count: how many of the bucket's deltas are "
             "positive"),
            ("\"best_delta\": round(max(deltas), 3)",
             "best and worst delta bracket the family's range — the "
             "table's last two columns"),
        ],
    },
    "exploratory_decompositions._score": {
        "problem": "Score one refitted specification the same way the "
                   "official scorer would: supported-row MAE for news "
                   "and control, and their difference.",
        "how": "Step 1: skip rows without a party key (unsupported). "
               "Step 2: per row take |prediction − observed| for the "
               "news and the recalibrated columns. "
               "Step 3: average each and subtract — the same ΔMAE "
               "definition as score_specification, reimplemented "
               "minimally for refit experiments.",
        "numbers": "t09's no_reform_delta column: each refit's ΔMAE on "
                   "the same 753-row scoring population.",
        "lines": [
            ("if row[\"party_key\"] is None: continue",
             "same 832→753 gate as the official scorer, expressed via "
             "the party key"),
            ("float(np.mean(recal) - np.mean(news))",
             "ΔMAE = control error − news error, identical convention "
             "to t04/t05"),
        ],
    },
    "exploratory_decompositions.decomposition_one": {
        "problem": "Compute t09: is the headline improvement carried by "
                   "the seven Reform-era training cells? Refit every "
                   "confirmatory specification WITHOUT them and compare "
                   "deltas.",
        "how": "Step 1: rebuild the 45 v2 fitting cells, then drop the "
               "Reform ones (45 → 38). "
               "Step 2: for each of the 12 confirmatory (arm, window) "
               "specifications, refit the frozen ridge on the reduced "
               "cells and re-predict the blinded 2026 rows with the "
               "frozen applier. "
               "Step 3: score each refit (_score) and set it beside the "
               "full fit's frozen delta — read from the unblinding "
               "record, never recomputed, so the reference cannot "
               "drift. "
               "Step 4: verdict per row — improvement survives or "
               "collapses without the Reform cells.",
        "numbers": "All of t09: e.g. combined 31-90d +0.2404 → +0.0773 "
                   "(survives, shrunken); national 31-90d +0.2683 → "
                   "−0.0015 (collapses); 3 survive, 2 collapse.",
        "lines": [
            ("no_reform = [c for c in full_cells if c[\"party_key\"] != "
             "\"reform_uk\"]",
             "the intervention: the same fit minus the 7 Reform-era "
             "cells"),
            ("full_delta = {... for e in unblinding[\"files\"][\"v2\"] "
             "if e[\"family\"] == \"confirmatory\"}",
             "the comparison column comes from the frozen record — this "
             "table can never disagree with section 16"),
            ("entry[\"verdict\"] = \"improvement collapses without "
             "Reform cells\"",
             "the plain-language verdict printed in t09's last column"),
        ],
    },
    "exploratory_decompositions._confirmatory_blocks": {
        "problem": "Prepare the raw material for the mechanism "
                   "decompositions: per (arm, window), each party's "
                   "(prediction, observed) pairs for both the news and "
                   "the baseline predictions.",
        "how": "Step 1: read the frozen v2 prediction file once. "
               "Step 2: keep only confirmed-window, reported-metric "
               "rows of the v2 variant. "
               "Step 3: file each row's (news prediction, observed) "
               "pair under its party and under 'all', and the same "
               "row's (baseline prediction, observed) pair under a "
               "'baseline|' prefix — one read serves both sides of "
               "every comparison.",
        "numbers": "The input pairs behind every cell of t10 (pooled) "
                   "and t11/t12 (per-party).",
        "lines": [
            ("if row[\"included_in_reported_metrics\"] != \"True\": "
             "continue",
             "same 753 scoring population as everywhere else"),
            ("blocks[key][\"baseline|\" + row[\"party_key\"]].append(...)",
             "news and baseline pairs travel together, so each party's "
             "before/after split uses identical rows"),
        ],
    },
    "exploratory_decompositions._split_errors": {
        "problem": "The mechanism lens: split a set of signed errors "
                   "into LEVEL (bias) and SPREAD (dispersion).",
        "how": "Step 1: errors = prediction − observed (signed). "
               "Step 2: bias = their mean; |bias| is the level error. "
               "Step 3: dispersion = mean |error − bias| — what remains "
               "after the level is removed. A broadcast party-level "
               "adjustment can only move the bias term, so this split "
               "is exactly the test of the tide-gauge reading.",
        "numbers": "Every bias/dispersion cell in t10-t12 (and the "
                   "same split, byte-compatible, underlies t22).",
        "lines": [
            ("bias = float(np.mean(errors))",
             "the level: the party's average signed miss"),
            ("\"dispersion_mae\": ... np.mean(np.abs(errors - bias))",
             "the spread news cannot touch: ward-to-ward variation "
             "after removing the level"),
        ],
    },
    "exploratory_decompositions.decomposition_two": {
        "problem": "Compute t10: pooled over all parties, did news move "
                   "the bias term or the dispersion term?",
        "how": "Step 1: per (arm, window), pool every supported row's "
               "pairs. "
               "Step 2: _split_errors on the news pairs and on the "
               "baseline pairs. "
               "Step 3: report the change in each component. Pooled "
               "bias is pinned near zero by contest normalisation "
               "(shares in a contest sum to 100), so the informative "
               "pooled column is DISPERSION — which falls exactly in "
               "the improving windows.",
        "numbers": "All of t10: baseline vs news dispersion and its "
                   "change, per confirmatory specification.",
        "lines": [
            ("news_all = split(parties[\"all\"])",
             "the pooled split: all 753 rows as one crowd"),
            ("\"dispersion_change\": round(news_all[\"dispersion_mae\"] "
             "- base_all[\"dispersion_mae\"], 4)",
             "t10's key column: negative = news tightened the "
             "ward-to-ward spread"),
        ],
    },
    "compare_news_approaches.fitting_cells": {
        "problem": "Build the training cells for the A-vs-B design "
                   "comparison, keeping the observed and baseline means "
                   "separate (the joint approach needs both).",
        "how": "Step 1: walk the OOF rows of the fitting elections. "
               "Step 2: group by (election, party) — the same "
               "anti-pseudo-replication grain as every production fit. "
               "Step 3: per cell store mean observed share and mean "
               "baseline prediction (their difference is the residual "
               "approach's target).",
        "numbers": "The cells both approaches in t13 train on.",
        "lines": [
            ("sums[(election, key)]",
             "one cell per election×party — news is party-level, so "
             "the fit must be too"),
            ("\"mean_observed\": ... \"mean_baseline\": ...",
             "kept separate: A models observed−baseline; B models "
             "observed with baseline as a feature"),
        ],
    },
    "compare_news_approaches.leave_one_election_out": {
        "problem": "Compute t13's numbers: with the tiny v1 sample, "
                   "which design wins — residual correction (A) or "
                   "joint model (B)?",
        "how": "Step 1: hold out one fitting election at a time. "
               "Step 2: approach A — fit the ridge on news features "
               "only, target = observed − baseline; predict the "
               "held-out cells' adjustment; error = |baseline + "
               "adjustment − observed|. "
               "Step 3: approach B — fit the same ridge but with the "
               "baseline as an extra feature the model may re-weight; "
               "target = observed itself. "
               "Step 4: baseline-only reference: |baseline − observed| "
               "untouched. Pool the held-out errors per approach.",
        "numbers": "t13's three MAE columns per window — the record "
                   "behind choosing the residual design (Approach A) "
                   "for the frozen pipeline.",
        "lines": [
            ("target_a = ... cell[\"mean_observed\"] - "
             "cell[\"mean_baseline\"]",
             "A's target is the residual: what history got wrong"),
            ("design_b ... with_baseline=True",
             "B lets the ridge re-weight the baseline itself — riskier "
             "with 11 cells, and it showed"),
            ("errors[\"baseline_only\"].append(...)",
             "the do-nothing reference both approaches must beat"),
        ],
    },
    "haslemere_probe_prediction.load_haslemere_baseline": {
        "problem": "Assemble the Haslemere by-election's five candidate "
                   "rows exactly as the frozen pipeline would see a "
                   "holdout contest: baseline prediction, recalibrated "
                   "control, blinded fields.",
        "how": "Step 1: read the Stage 1 bundle's rows for the sealed "
               "Haslemere contest. "
               "Step 2: build the same blinded row shape the 2026 "
               "holdout used (outcome columns stripped). "
               "Step 3: return the observed results separately, for "
               "scoring only.",
        "numbers": "The five-row contest behind every t14/t15 cell.",
        "lines": [
            ("sanitise_holdout_rows(...)",
             "the same blinding guard as the 2026 holdout — the probe "
             "predicts first, looks second"),
        ],
    },
    "haslemere_probe_prediction.score": {
        "problem": "Compute t14/t15's numbers for one specification on "
                   "the Haslemere contest: MAE, per-party signed "
                   "errors, and the winner call — for all three "
                   "prediction columns.",
        "how": "Step 1: define one inner scorer and run it three times "
               "(news / recalibrated / baseline) — same "
               "one-scorer-many-crowds pattern as score_specification. "
               "Step 2: per candidate, error = prediction − observed "
               "share; MAE = mean |error|. "
               "Step 3: the predicted winner is the highest predicted "
               "share; compare against the real winner.",
        "numbers": "Every t14 row (3 of 12 specifications beat the "
                   "control; window ordering 31-90 best / 91-180 worst "
                   "replicates) and t15's reference columns.",
        "lines": [
            ("def one(column: str) -> dict:",
             "defined once, called for news, control and baseline — "
             "identical arithmetic per column"),
            ("\"winner_correct\": top_party == winner_observed",
             "the seat-level call for this one-seat contest"),
        ],
    },
    "local_v3_rerun.reference_deltas": {
        "problem": "Pin the committed numbers the v3 re-run is read "
                   "against: the frozen v2 local-sensitivity and "
                   "confirmatory deltas per window.",
        "how": "Read the unblinding record and index the relevant "
               "deltas by window — read, not recomputed, so the "
               "comparison column of t19 cannot drift from section "
               "16.",
        "numbers": "t19's reference columns (the frozen v2 deltas each "
                   "v3 window is compared to).",
        "lines": [
            ("if entry[\"analysis\"] == \"local_sensitivity\"",
             "the v2 local arm is the direct predecessor the re-run "
             "must be read against"),
        ],
    },
    "local_v3_rerun.main": {
        "problem": "Compute t19: re-run the local arm on the "
                   "gate-passing v3 feature lineage and score it with "
                   "the production machinery.",
        "how": "Step 1: assert the licence — every v3 column must "
               "carry a 'usable' verdict in the committed metadata; a "
               "failed gate raises instead of silently serving. "
               "Step 2: rebuild the 45 v2 cells, fit the frozen ridge "
               "per window on the v3 features, predict the blinded "
               "2026 rows. "
               "Step 3: score each window with score_specification "
               "(with bootstrap) — the SAME scorer as the confirmatory "
               "grid. "
               "Step 4: write results beside the frozen reference "
               "deltas.",
        "numbers": "All of t19: 4 of 6 windows improve, with a sign "
                   "inversion at 180-91 days.",
        "lines": [
            ("if verdicts[column][\"verdict\"] != \"usable\": raise "
             "RuntimeError(...)",
             "the kappa-gate crossing is asserted, not assumed — a "
             "stale table cannot serve"),
            ("metrics = score_specification(predictions, observed, "
             "with_bootstrap=True)",
             "same marking machine as t04/t05 — comparable numbers by "
             "construction"),
        ],
    },
    "woking_south_unseal.assert_predictions_committed": {
        "problem": "Enforce the blind test's order of events in code: "
                   "predictions must be committed to git BEFORE any "
                   "result is read.",
        "how": "Step 1: hash the predictions file on disk (git "
               "hash-object). "
               "Step 2: ask git for the blob id of the same path in "
               "HEAD. "
               "Step 3: refuse to unseal unless both exist and are "
               "identical — the commit is the timestamped proof the "
               "predictions predate the look.",
        "numbers": "No numbers — it produces the LICENCE for every "
                   "number in t20/t21.",
        "lines": [
            ("if in_head.returncode != 0: raise RuntimeError(\"UNSEAL "
             "REFUSED: ... Commit the predictions first",
             "not committed → no unsealing, full stop"),
            ("if in_head.stdout.strip() != on_disk:",
             "committed but edited since → also refused; what is "
             "scored is exactly what was committed"),
        ],
    },
    "woking_south_unseal.read_outcomes_once": {
        "problem": "The single point where the blind test touches "
                   "reality: read the five observed results, once.",
        "how": "Scan the master OOF file for the Woking South "
               "election's five rows and return share + elected flag "
               "per candidate; assert exactly five rows came back.",
        "numbers": "The observed shares every t20/t21 error is "
                   "measured against.",
        "lines": [
            ("if len(outcomes) != 5: raise RuntimeError(...)",
             "five candidates expected; anything else aborts the "
             "unsealing"),
        ],
    },
    "woking_south_unseal.main": {
        "problem": "Compute every number in t20 and t21: score all 18 "
                   "sealed specifications against the just-read "
                   "outcomes.",
        "how": "Step 1: verify the git lock, then read the outcomes "
               "once. "
               "Step 2: group the sealed predictions by (arm, window). "
               "Step 3: per specification — MAE for news / control / "
               "baseline via one inner mae() helper; the winner call "
               "(highest news prediction vs the real winner); Reform's "
               "signed error. "
               "Step 4: write the results JSON and findings table, "
               "flagging the pre-registered pick.",
        "numbers": "All of t20 (the pick — local 91-180d — was the "
                   "worst of 18) and t21's per-party autopsy "
                   "(adjustment worsened all five parties; the LD "
                   "landslide 64.0% was encoded nowhere).",
        "lines": [
            ("blob = assert_predictions_committed()",
             "scoring cannot start before the git lock passes"),
            ("def mae(column: str) -> float:",
             "one scorer, three prediction columns — the pattern "
             "again"),
            ("\"reform_signed_error\": ...",
             "t21's key column: signed, so direction of the miss is "
             "visible"),
        ],
    },
    "production_news_lopo.run_lopo": {
        "problem": "Compute the LOPO stability check: remove one "
                   "party's training cells at a time and re-score all "
                   "18 pre-holdout comparisons — does the conclusion "
                   "depend on any single party?",
        "how": "Step 1: audit the inputs (holdout untouched, same "
               "corpus release, same training parties as the primary "
               "run) — any mismatch raises. "
               "Step 2: for each of the five parties, drop its cells "
               "and refit every (arm, window) specification with the "
               "production machinery, no bootstrap. "
               "Step 3: set each omitted delta beside the primary "
               "run's frozen delta and record the change, coefficient "
               "sign flips, and whether the omission CREATED an "
               "improvement.",
        "numbers": "The LOPO record: removing Conservative cells "
                   "produced 6 of 18 improvements; removing any other "
                   "party, none.",
        "lines": [
            ("if primary.get(\"stage1_holdout_file_read\") is not "
             "False: raise LopoAuditError(...)",
             "the check runs pre-holdout by construction — it audits "
             "that the primary run never read the holdout"),
            ("reduced = {party: row ... if party != omitted_party}",
             "the intervention: one party's cells removed, everything "
             "else frozen"),
            ("\"creates_overall_improvement\": omitted_delta > 0",
             "the question the check answers, one boolean per "
             "comparison"),
        ],
    },
    "identity_placebos.tone_trajectories": {
        "problem": "Build the trajectory placebo: does the DIRECTION "
                   "of tone over the campaign (softening vs hardening) "
                   "predict anything?",
        "how": "Step 1: per (election, party), collect (time-to-poll "
               "midpoint, tone) points — windows with no articles are "
               "SKIPPED, not read as zero, so thin coverage cannot "
               "manufacture a fake swing to neutrality. "
               "Step 2: fit a least-squares slope per cell (needs ≥2 "
               "covered windows; otherwise the feature says nothing). "
               "Step 3: scale to tone change per 100 days so the "
               "coefficient is readable beside [-1,1] features.",
        "numbers": "The trajectory arm of the identity-placebo record "
                   "(part of the 'what carries the signal' battery).",
        "lines": [
            ("if count in (\"\", \"0\") ... continue",
             "no articles → no point; zero coverage is missing data, "
             "not neutral tone"),
            ("slopes[key] = covariance / spread * 100",
             "the least-squares slope, rescaled per 100 days"),
        ],
    },
    "identity_placebos.variance_split": {
        "problem": "Answer 'is the news signal mostly WHO you are "
                   "(party identity) or HOW you are covered?': split "
                   "each feature's variance into between-party and "
                   "within-party shares.",
        "how": "Step 1: per window and feature, group the fitting "
               "cells' values by party. "
               "Step 2: between = variance of party means around the "
               "grand mean (weighted by group size); within = variance "
               "around each party's own mean. "
               "Step 3: report each as a share of the total, plus the "
               "party means themselves.",
        "numbers": "The variance-split table in the identity-placebo "
                   "record — how much of each feature a party dummy "
                   "could mimic.",
        "lines": [
            ("between = sum(len(g) * (sum(g) / len(g) - grand) ** 2 ...",
             "the between-party component: what a party dummy can "
             "capture"),
            ("within = sum(sum((v - sum(g) / len(g)) ** 2 ...",
             "the within-party component: what only actual coverage "
             "differences can supply"),
        ],
    },
    "stance_volume_margins._pearson": {
        "problem": "One small dependency-free correlation: Pearson r "
                   "between two lists, None when n < 3 or a spread is "
                   "zero.",
        "how": "Covariance divided by the product of the two standard "
               "deviations, computed longhand.",
        "numbers": "The r values in the volume-proxy check.",
        "lines": [
            ("if n < 3 or n != len(ys): return None",
             "too few points → no correlation claimed, rather than a "
             "meaningless one"),
        ],
    },
    "stance_volume_margins.volume_weighting_check": {
        "problem": "Check whether tone is secretly a volume proxy: per "
                   "window, how correlated are net portrayal and "
                   "article count over the covered fitting cells?",
        "how": "Step 1: per window, collect (article count, net tone) "
               "pairs for fitting cells with coverage. "
               "Step 2: Pearson r and r² per window. High |r| would "
               "mean the two features carry one signal, not two.",
        "numbers": "The per-window r/r² table in the margins record "
                   "(supervisor-directed replacement for the earlier "
                   "sign count).",
        "lines": [
            ("if count_str in (\"\", \"0\") or tone_str == \"\": "
             "continue",
             "only covered cells enter — zeros are absence, not data"),
            ("\"r_squared\": round(r ** 2, 4)",
             "shared-variance share: how much of tone volume already "
             "explains"),
        ],
    },
    "make_report_figures.figure_confirmatory": {
        "problem": "Draw the report's headline figure — the forest plot "
                   "of all 24 confirmatory comparisons (paper Figure 4, "
                   "pack fig1), v1 and v2 side by side.",
        "how": "Step 1: read the same frozen unblinding record t04/t05 "
               "are built from. "
               "Step 2: loop over the two versions — left panel v1, "
               "right panel v2 — and within each over both arms and all "
               "six windows. "
               "Step 3: draw one dot per comparison at its ΔMAE with "
               "whiskers at the CI ends, and a dashed line at zero. "
               "Right of the line = news better; a whisker crossing the "
               "line = CI includes zero.",
        "numbers": "Every dot and whisker in fig1 — the same +0.240 "
                   "[+0.078, +0.387] you can read in t05, drawn instead "
                   "of tabulated.",
        "lines": [
            ("for ax, version, title in ((axes[0], \"v1\", \"(a) v1\"), "
             "(axes[1], \"v2\", \"(b) v2\"))",
             "the v1/v2 comparison is the figure's structure: one panel "
             "per version, same axes"),
            ("if e[\"family\"] == \"confirmatory\"",
             "same gate as the tables: only the 24 pre-registered "
             "comparisons are drawn"),
            ("delta = metrics[\"news_vs_recalibrated_mae\"]",
             "each dot IS the table's ΔMAE — no re-computation, same "
             "JSON field"),
            ("ax.errorbar(delta, y, xerr=[[delta - low], [high - delta]]",
             "whiskers span the bootstrap CI; crossing the dashed zero "
             "line = not confirmed"),
            ("ax.axvline(0, ...)",
             "the zero line: the visual form of 'does the CI exclude "
             "zero'"),
        ],
    },
    "make_report_figures.figure_seats": {
        "problem": "Compute and draw fig2's seat totals: how many seats "
                   "the history-only baseline gave each party versus how "
                   "many the party actually won.",
        "how": "Step 1: read the scored 2026 holdout rows (same file as "
               "t01-t03). "
               "Step 2: for each row add 1 to the party's predicted "
               "counter if predicted_elected is True, and 1 to its "
               "actual counter if observed_elected is True — parties "
               "outside the six main ones are pooled into one "
               "'Residents' assocs & other local' group. "
               "Step 3: draw one hatched bar (predicted) and one solid "
               "bar (actual) per party, labelled with the exact "
               "counts.",
        "numbers": "Every number printed on fig2: Conservative 118 vs "
                   "30, Liberal Democrats 6 vs 96, Reform UK 0 vs 14, "
                   "Residents' assocs & other local 36 vs 11, Green 0 "
                   "vs 8, Independent 0 vs 3, Labour 2 vs 0.",
        "lines": [
            ("predicted[group] += row[\"predicted_elected\"] == \"True\"",
             "the predicted seat count: True adds 1, False adds 0 — a "
             "party's bar is just how many of its rows carry the "
             "predicted-winner flag"),
            ("actual[group] += row[\"observed_elected\"] == \"True\"",
             "the actual seat count, same rule on the observed flag"),
            ("group = party if party in main else \"Residents' assocs "
             "& other local\"",
             "small local parties are pooled into one bar — the only "
             "difference from t03's exact per-party list"),
        ],
    },
    "per_party_bootstrap.error_split": {
        "problem": "Split one party's signed errors into the two "
                   "components the whole per-party story is told in: "
                   "LEVEL (bias — is the party as a whole over- or "
                   "under-predicted?) and DISPERSION (spread around "
                   "that level).",
        "how": "Step 1: bias = the plain mean of the signed errors "
               "(predicted − observed, so positive = overpredicted). "
               "Step 2: dispersion = mean |error − bias|, the spread "
               "left after removing the level. "
               "Step 3: total MAE = mean |error| for reference. All "
               "rounded to 4 dp.",
        "numbers": "Every level number on fig4/fig6 and in t22 starts "
                   "here: e.g. Reform 2021 bias +12.21 under the "
                   "baseline vs +3.07 under news; Reform 2026 bias "
                   "−1.33 vs −3.16.",
        "lines": [
            ("bias = float(errors.mean())",
             "the LEVEL: the party's average signed miss — the "
             "quantity the news adjustment moves"),
            ("\"dispersion_mae\": ... np.abs(errors - bias).mean()",
             "the SPREAD after removing the level — t10-t12 show news "
             "moves levels, not spread"),
            ("\"abs_bias\": round(abs(bias), 4)",
             "|bias| is what the change columns compare: did news "
             "bring the party's level closer to zero?"),
        ],
    },
    "per_party_bootstrap.block_analysis": {
        "problem": "Compute, for ONE (island, arm, window) "
                   "specification, every per-party number and interval "
                   "on fig4, fig5 (dots), fig6 (heatmap) and t22: each "
                   "party's level change under news, the fitted-group "
                   "mean, the Reform-minus-group contrast, and paired "
                   "bootstrap intervals for all of them.",
        "how": "Step 1: build each model's signed-error vector "
               "(prediction − observed) for baseline, recalibrated "
               "control and news. "
               "Step 2: point estimates — per party, error_split each "
               "model's errors and take abs_bias_change = news |bias| "
               "− control |bias| (negative = news improved that "
               "party's level); the group value is the unweighted MEAN "
               "over the non-Reform parties (party-level mean, so an "
               "81-row Conservative slate cannot outvote a 36-row "
               "Green one); the contrast is Reform minus that mean. "
               "Step 3: intervals — 2,000 paired draws: resample the "
               "CONTESTS with replacement, and inside each draw "
               "recompute every party's change, the group mean AND the "
               "contrast from the same resampled contests, so the "
               "contrast's interval belongs to the difference itself. "
               "Step 4: summarise each quantity's draws into a 95% "
               "percentile interval.",
        "numbers": "All of t22; every bar and whisker on fig4; every "
                   "heatmap cell on fig6's top panel (e.g. Liberal "
                   "Democrat −4.84 and Green +5.06 at 91-180 days); "
                   "every dot on fig5.",
        "lines": [
            ("errors = {model: np.array([r[model] for r in rows]) - "
             "observed for model in (\"baseline\", \"recalibrated\", "
             "\"news\")}",
             "three error vectors over the same candidates — every "
             "comparison is three readings of one exam"),
            ("entry[f\"abs_bias_change_vs_{control}\"] = ... "
             "models[\"news\"][\"abs_bias\"] - models[control][\"abs_bias\"]",
             "the heatmap/dot quantity: negative = news moved the "
             "party's level closer to zero"),
            ("group_point[q] = ... np.mean([point[p][q] for p in "
             "group_present])",
             "group = unweighted mean over fitted parties, one vote "
             "per party"),
            ("contrast_point[q] = point[study_party][q] - group_point[q]",
             "fig4's bar: Reform's change minus the group's — did "
             "news treat Reform worse than the parties it was fitted "
             "on?"),
            ("picked = rng.integers(0, len(contests), size=len(contests))",
             "the paired draw: resample whole contests, recompute "
             "everything inside — same bootstrap unit as the headline "
             "CI"),
            ("draws[q][\"contrast\"][d] = per_party[study_party][q] - "
             "group_value",
             "the contrast recomputed inside every draw — that is what "
             "makes its interval 'paired'"),
        ],
    },
    "per_party_bootstrap._summarise_draws": {
        "problem": "Turn 2,000 bootstrap draws of one quantity into "
                   "the interval printed on fig4's whiskers and t22's "
                   "CI columns.",
        "how": "Step 1: drop NaN draws (a party absent from a "
               "resample). "
               "Step 2: take the 2.5th and 97.5th percentiles — the "
               "middle 95% of the draws. "
               "Step 3: also record the share of draws below and above "
               "zero, because structural-zero windows produce draws "
               "exactly at zero which one share alone would misread.",
        "numbers": "Every ci_lower/ci_upper on fig4, t22 and (via "
                   "comparisons_annex) the fig5 blind-zone bars.",
        "lines": [
            ("np.percentile(valid, 2.5) ... np.percentile(valid, 97.5)",
             "same percentile rule as the headline +0.240 CI — one "
             "convention across the whole project"),
            ("\"share_draws_negative\": ... (valid < 0).mean()",
             "negative draws favour news (an error component "
             "falling); reported alongside the interval"),
        ],
    },
    "minimal_detectable_effect.mde_from_interval": {
        "problem": "Compute the ruler-resolution numbers on fig5 and "
                   "t23: from one bootstrap interval, how small an "
                   "effect could this cell have certified at all?",
        "how": "Step 1: half-width = (upper − lower) / 2; a zero "
               "half-width marks a structural-zero cell (no in-window "
               "articles, nothing was ever measured). "
               "Step 2: SE ≈ half-width / 1.96 (normal "
               "approximation). "
               "Step 3: MDE50 = the half-width itself (an effect this "
               "size is detected ~50% of the time); MDE80 = half-width "
               "× 1.4294 — the (z95 + z80)/z95 factor — the smallest "
               "effect detected with ~80% power.",
        "numbers": "Every grey bar on fig5 and every mde_80_power in "
                   "t23 — e.g. the v2 combined 31-90d overall MDE80 ≈ "
                   "0.216, which the observed +0.240 clears.",
        "lines": [
            ("half = (upper - lower) / 2",
             "the interval's half-width is the design's noise level — "
             "everything else is derived from it"),
            ("\"mde_80_power\": round(half * MDE80_FACTOR, 3)",
             "MDE80 = half-width × 1.4294: the smallest effect this "
             "cell would flag in ~80% of resamples"),
            ("if half <= 0: return {\"status\": \"structural_zero\" ...",
             "zero-width intervals are labelled structural zeros, not "
             "treated as infinitely precise"),
        ],
    },
    "minimal_detectable_effect.comparisons_annex": {
        "problem": "Build fig5's rows: pair each party's OBSERVED "
                   "level change with that party's OWN detection "
                   "threshold, one row per (island, arm, window, "
                   "party).",
        "how": "Step 1: walk every specification in the per-party "
               "bootstrap annex. "
               "Step 2: per party, read the observed "
               "abs_bias_change_vs_recalibrated point estimate (the "
               "dot) and its bootstrap interval, and derive the MDE "
               "numbers from that interval's width (the grey bar) via "
               "mde_from_interval. "
               "Step 3: keep the Reform-vs-group contrast as its own "
               "row — it is a difference with its own paired interval, "
               "not any single party's. "
               "Step 4: mark duplicate prediction vectors (combined = "
               "local + national, so where one component is empty two "
               "arms coincide) so identical vectors are never counted "
               "as two independent looks.",
        "numbers": "Every (dot, bar) pair on fig5 — e.g. Green's wide "
                   "blind zone on the 2026 panel comes from its "
                   "interval width, not its sample size.",
        "lines": [
            ("observed = spec[\"parties\"][unit][quantity]",
             "the dot: that party's observed level change, straight "
             "from the annex's point estimate"),
            ("**mde_from_interval(interval[\"ci_lower\"], "
             "interval[\"ci_upper\"])",
             "the bar: the threshold is derived from THAT party's own "
             "interval width — thresholds are not shared"),
            ("units.append((\"reform_vs_group_contrast\", \"contrast\"))",
             "the contrast keeps its own row with its own paired "
             "interval"),
        ],
    },
    "minimal_detectable_effect.summarise": {
        "problem": "Compress the comparison rows into t23: median and "
                   "range of MDE80 per island × scope × party.",
        "how": "Step 1: group rows by (island, scope, party) — party "
               "stays in the key because per-party resolutions differ "
               "by more than an order of magnitude, so a pooled median "
               "would be quotable but wrong for every party in it. "
               "Step 2: per group, count estimable vs structural-zero "
               "cells and deduplicate shared prediction vectors. "
               "Step 3: report median, min and max MDE80 over the "
               "estimable cells.",
        "numbers": "Every row of t23, including the v2 overall median "
                   "MDE80 ≈ 0.216 quoted against the observed +0.240.",
        "lines": [
            ("grouped[(row[\"island\"], row[\"scope\"], "
             "row.get(\"party\", \"\"))].append(row)",
             "party is part of the grouping key — no pooling across "
             "parties"),
            ("\"median_mde_80\": round(median(estimable), 3)",
             "the summary number the report quotes per island/scope"),
            ("distinct = len({m.get(\"vector_owner\") ...",
             "identical prediction vectors are counted once — the "
             "claimed number of independent looks is honest"),
        ],
    },
    "pipeline_overview_figure._candidate_counts": {
        "problem": "Compute the 2,666 at the top of the corpus funnel: "
                   "how many candidate articles the screening pipeline "
                   "actually assessed.",
        "how": "Step 1: read the three adjudication sheets the frozen "
               "v1 release hashes — the main E4/E5 decision table plus "
               "the pilot and validation batches. "
               "Step 2: the three are confirmed disjoint (zero shared "
               "article ids), so summing their row counts is exact, "
               "not an approximation of a union. "
               "Step 3: count per arm (local / national) for the "
               "funnel's colour split.",
        "numbers": "fig0b's top bar: 2,666 candidate articles "
                   "assessed, split into the local and national arms.",
        "lines": [
            ("all_rows = rows(DECISIONS) + rows(PILOT_SHEET) + "
             "rows(VALIDATION_SHEET)",
             "the three sheets the release hashes — the same files "
             "the 2,666 count is frozen from"),
            ("counts = Counter(r.get(\"arm\", \"unknown\") for r in "
             "all_rows)",
             "per-arm counts feed the funnel's local/national colour "
             "split"),
        ],
    },
    "study_design_figure._counts": {
        "problem": "Prove the study-design figure's numbers are computed, "
                   "not decorative: every count on fig0 is read from "
                   "committed records and asserted before drawing.",
        "how": "Step 1: read the Stage 1 bundle's data-quality report "
               "(the authority for 24 / 343 / 1,992). "
               "Step 2: split the 24 event ids into 5 principals and 19 "
               "by-elections by name; split the by-elections into "
               "news-enriched (8), Stage-1-only (8), sealed-holdout (2, "
               "polled on/after 7 May 2026) and the blind case (Woking "
               "South). "
               "Step 3: assert every one of those counts, plus the "
               "11/45 fitting-cell split and the 832 blinded rows, "
               "before a single box is drawn.",
        "numbers": "All counts on fig0: 24 events, 343 contests, 1,992 "
                   "rows, 5+19 split, 17/8/8/2 by-election roles, 832 "
                   "sealed candidates.",
        "lines": [
            ("by_elections = [e for e in election_ids if \"by-election\" "
             "in e]",
             "the 5-vs-19 split comes from the event ids themselves"),
            ("sealed = {e ... if date.fromisoformat(e[-10:]) >= "
             "HOLDOUT_BOUNDARY}",
             "the two sealed by-elections are defined by polling date "
             "(on/after 7 May 2026), not hand-picked"),
            ("assert quality[\"elections\"] == 24 and "
             "quality[\"rows\"] == 1992",
             "the figure refuses to draw if the committed record "
             "disagrees with its labels"),
            ("assert len(enriched) == 8 and len(sealed) == 2",
             "the by-election role split (8 enriched / 8 Stage-1-only / "
             "2 sealed / 1 blind) is checked, not assumed"),
        ],
    },
    "corpus_funnel_figure.main": {
        "problem": "Draw the corpus construction as a proportional "
                   "funnel: how 2,666 candidate articles became the "
                   "1,632-article v1 corpus and the 2,259-article v2 "
                   "corpus, and how small the local arm is throughout.",
        "how": "Step 1: read the candidate-article counts from the "
               "hashed adjudication sheets and the two committed corpus "
               "releases (v1, v2). "
               "Step 2: assert the headline counts (2,666 / 1,632 / "
               "2,259 / national 2,071). "
               "Step 3: draw three horizontal bars whose LENGTHS are the "
               "counts, each split into local (orange) and national "
               "(blue), with the screened-out remainder in grey — "
               "proportions visible at a glance, unlike a box "
               "flowchart.",
        "numbers": "fig0b's three bars: 2,666 assessed; 1,632 usable v1 "
                   "(188 local / 1,444 national); 2,259 v2 (+627 "
                   "by-election articles, national arm only).",
        "lines": [
            ("assert cand[\"total\"] == 2666 and v1[\"articles\"] == "
             "1632",
             "the funnel refuses to draw if the committed releases "
             "disagree with its labels"),
            ("assert v2[\"articles\"] == 2259 and "
             "v2[\"by_arm\"][\"national\"] == 2071",
             "v2's growth is checked to be in the national arm — the "
             "figure's own caption claim"),
            ("ax.barh(y, local, ...); ax.barh(y, national, left=local, "
             "...)",
             "bar length = article count: the 'proportional, not "
             "flowchart' promise in code"),
            ("cand[\"total\"] - v1[\"articles\"]",
             "the grey segment: 1,034 articles excluded at screening, "
             "shown rather than hidden"),
        ],
    },
    "framework_figure.main": {
        "problem": "Draw the two-stage framework (pack fig0c / report "
                   "Figure 1): the Stage 1 chain, the Stage 2 chain, the "
                   "three comparators, and the freeze line — with every "
                   "number on the figure asserted first.",
        "how": "Step 1: read the enrichment record, the frozen protocol, "
               "the Stage 1 training table and the OOF file, plus both "
               "corpus releases. "
               "Step 2: assert the numbers the boxes will display — "
               "1,150 training records, 792 OOF rows, 11 v1 cells / 45 "
               "v2 cells, 832 blinded rows, corpora 1,632 / 2,259. "
               "Step 3: draw left chain (history → LightGBM → baseline), "
               "right chain (news features → per-window ridge → "
               "adjustment), the three comparator boxes, then the orange "
               "dashed FREEZE LINE with the sealed evaluation box below "
               "it.",
        "numbers": "Every figure label: 1,150 / 792 / 11-vs-45 / 832 / "
                   "1,632-vs-2,259, and the ΔMAE definition printed in "
                   "the sealed box.",
        "lines": [
            ("assert training_rows == 1150 ... assert oof_rows == 792",
             "box labels are counted from the committed files, then "
             "asserted — never typed"),
            ("\"election × party cells · v1: 11, v2: 45\"",
             "the v1/v2 split is printed on the Stage 2 box itself"),
            ("ax.plot([0.3, 11.2], [2.35, 2.35], color=ORANGE, ... "
             "linestyle=(0, (6, 4)))",
             "the freeze line: everything above it existed before the "
             "2026 results were read"),
            ("\"$\\Delta$MAE = MAE$_{\\mathrm{recalibrated}}$ − "
             "MAE$_{\\mathrm{news}}$\"",
             "the sealed box carries the exact ΔMAE definition the "
             "scoring code implements"),
        ],
    },
    "news_estimator.fit": {
        "problem": "The mathematical heart of Stage 2: RidgeModel.fit "
                   "implements the report's &sect;4.3 equation line by "
                   "line — r&#770; = r&#772; + &Sigma; &beta;\u00b7"
                   "(x\u2212x&#772;)/s.",
        "how": "Step 1: standardise each feature column — subtract its "
               "training mean, divide by its training standard deviation "
               "(the (x\u2212x&#772;)/s part); a zero-variance column "
               "is scaled by one so it contributes nothing instead of "
               "producing NaNs. "
               "Step 2: centre the target on its mean and remember that "
               "mean — it becomes the intercept r&#772;, deliberately "
               "OUTSIDE the penalised system, so the penalty never "
               "shrinks it. "
               "Step 3: solve the ridge normal equations (X'X + "
               "&lambda;I)w = X'y as a linear system (numerically safer "
               "than inverting a collinear matrix) — the solution is the "
               "two &beta;s. "
               "&lambda; is the fixed penalty &alpha;=1.0 passed in by "
               "_fit_specification.",
        "numbers": "The frozen &beta;s of all 12 specifications and the "
                   "intercept r&#772; behind 4.4414 / 4.4454 — every "
                   "number in the &sect;4.3 equation.",
        "lines": [
            ("standardised = (design - means) / scales",
             "the (x \u2212 x&#772;)/s in the formula: both features "
             "forced onto one scale so the penalty treats them equally"),
            ("scales = np.where(scales > 0, scales, 1.0)",
             "a constant column would divide by zero; scale it by one "
             "and let it contribute nothing"),
            ("centred_target = target - target_mean",
             "centre y; the removed mean IS r&#772; — kept aside, "
             "unpenalised"),
            ("gram = standardised.T @ standardised + self._l2 * "
             "np.eye(n_features)",
             "the (X'X + &lambda;I) of ridge; _l2 is the fixed "
             "&alpha;=1.0"),
            ("np.linalg.solve(gram, standardised.T @ centred_target)",
             "solve for the &beta;s as a linear system — no explicit "
             "matrix inversion on collinear data"),
            ("self._intercept = target_mean",
             "the intercept is literally the mean training residual — "
             "the no-news control's whole model"),
        ],
    },
    "blinded_2026_predictions_v2.aggregate_v2_residuals": {
        "problem": "Build Stage 2's training data out of Stage 1's "
                   "honest mistakes — one row per election×party cell, "
                   "never per candidate.",
        "how": "Step 1: take the 792 out-of-fold rows (each predicted by "
               "a model that never saw it) and compute residual = "
               "observed − predicted. "
               "Step 2: group by (election, party) and average — the "
               "anti-pseudo-replication rule: news exists per "
               "election×party, so the fit sees one mean residual per "
               "cell. "
               "Step 3: guard the enrichment's promises — Reform must "
               "be absent from 2017 (it did not exist) and present in "
               "at least one by-election cell; otherwise raise.",
        "numbers": "The 45 v2 training cells (11 in v1) — including the "
                   "seven Reform cells behind the t09 attribution — and "
                   "the training mean that becomes the no-news control's "
                   "intercept.",
        "lines": [
            ("float(row[\"observed_vote_share\"]) - "
             "float(row[\"predicted_vote_share\"])",
             "the residual: how wrong Stage 1 was on a row it had never "
             "seen"),
            ("residuals[(election, key)].append(...)",
             "grouped per election×party cell — one training row per "
             "cell, not per candidate"),
            ("raise ProductionExperimentError(\"Unexpected Reform row in "
             "2017 fitting data.\")",
             "guard: Reform did not exist in 2017; its presence would "
             "mean corrupted inputs"),
            ("if not reform_byelection_cells: raise",
             "guard: without Reform by-election cells the fit would "
             "silently revert to the v1 design"),
        ],
    },
}

BUILDER_DEFAULT_ANN = {
    "problem": "Formatting only — no new numbers are computed here.",
    "how": "Reads the frozen record shown above, renames labels, rounds "
           "to 3 decimals and writes this table's CSV.",
    "numbers": "Every cell of the table this modal belongs to.",
    "lines": [],
}


def annotation_html(ann: dict) -> str:
    lines_html = ""
    if ann.get("lines"):
        rows = "".join(
            f"<tr><td><code>{esc(frag)}</code></td><td>{esc(note)}</td>"
            f"</tr>" for frag, note in ann["lines"])
        lines_html = (f"<table class='annlines'><thead><tr><th>key line"
                      f"</th><th>what it means</th></tr></thead>"
                      f"<tbody>{rows}</tbody></table>")
    return (f"<div class='ann'>"
            f"<p><b>Problem it solves:</b> {esc(ann['problem'])}</p>"
            f"<p><b>How:</b> {esc(ann['how'])}</p>"
            f"<p><b>Numbers it produces:</b> {esc(ann['numbers'])}</p>"
            f"{lines_html}</div>")


def code_details(label: str, source: str, ann: dict | None = None) -> str:
    ann_html = annotation_html(ann) if ann else ""
    return (f"<details><summary><code>{esc(label)}</code></summary>"
            f"{ann_html}<pre><code>{esc(source)}</code></pre></details>")


def provenance_html(key: str, manifest: dict) -> str:
    """The full number-to-code chain for one provenance key."""
    spec = PROV[key]
    sources = parse_sources()
    parts: list[str] = []
    if spec["inputs"]:
        rows = []
        for k in spec["inputs"]:
            sha = manifest["input_sha256"].get(k, "")
            rows.append(f"<li><code>{esc(sources.get(k, k))}</code>"
                        f"<br><span class='src'>sha256 pinned in "
                        f"manifest.json: <code>{esc(sha[:20])}&hellip;"
                        f"</code></span></li>")
        parts.append("<p><strong>1&nbsp;&middot;&nbsp;Frozen input "
                     f"artefact(s)</strong></p><ul>{''.join(rows)}</ul>")
    if spec["modules"]:
        mods = []
        for name, funcs in spec["modules"]:
            # A slash routes to another package under src/ (e.g.
            # "news_features/build_feature_table"); if that does not
            # exist, the name is taken from the repository root (e.g.
            # the Stage 1 subproject's scripts).
            if "/" in name:
                rel = f"src/{name}.py"
                if not (REPO / rel).exists():
                    rel = f"{name}.py"
            else:
                rel = f"src/news_modelling/{name}.py"
            path = REPO / rel
            para, n = module_doc(path)
            mods.append(f"<li><code>{rel}</code> ({n} lines) "
                        f"<button class='openfile' data-path='{rel}'>open "
                        f"full file</button><br>"
                        f"<span class='src'>{esc(para)}</span>" + "".join(
                            code_details(f"{name}.{f}()",
                                         extract_function(path, f),
                                         ANNOTATIONS.get(f"{name}.{f}"))
                            for f in funcs) + "</li>")
        parts.append("<p><strong>2&nbsp;&middot;&nbsp;Computed by</strong>"
                     f"</p><ul>{''.join(mods)}</ul>")
    if spec["builders"]:
        brt_path = SRC_NM / f"{BRT}.py"
        funcs = "".join(
            code_details(f"{BRT}.{f}()", extract_function(brt_path, f),
                         ANNOTATIONS.get(f"{BRT}.{f}",
                                         BUILDER_DEFAULT_ANN))
            for f in spec["builders"])
        parts.append("<p><strong>3&nbsp;&middot;&nbsp;CSV written by</strong>"
                     f" <code>src/news_modelling/{BRT}.py</code> "
                     f"<button class='openfile' data-path='src/"
                     f"news_modelling/{BRT}.py'>open full file</button>"
                     f"</p>{funcs}")
    if spec.get("note"):
        parts.append(f"<p class='src'>{esc(spec['note'])}</p>")
    parts.append("<p class='src'>4&nbsp;&middot;&nbsp;This pack re-reads "
                 "the committed CSV and asserts the headline values at "
                 "build time (demo/build_viva_pack.py, "
                 "assert_headline_numbers). All excerpts above are "
                 "extracted from the repository at build time, never "
                 "copied by hand.</p>")
    return "".join(parts)


COMBINED_SPEC = REPO / ("news_features/combined_specification_v1/"
                        "combined_specification_results.json")


def combined_factorial_html() -> str:
    """The identity factorial and its paired marginals, read at build
    time from the committed combined-specification record. The headline
    marginal (centred tone after identity+volume, 31-90d) is asserted
    against the value quoted in the interpretation bullet."""

    payload = json.loads(COMBINED_SPEC.read_text(encoding="utf-8"))
    windows = ["180_to_91_days", "90_to_31_days", "30_to_15_days",
               "14_to_8_days", "7_to_4_days", "final_72_hours"]
    wlabel = {"180_to_91_days": "91–180d", "90_to_31_days": "31–90d",
              "30_to_15_days": "15–30d", "14_to_8_days": "8–14d",
              "7_to_4_days": "4–7d", "final_72_hours": "1–3d"}
    arm_label = [
        ("frozen", "frozen news pair (share + tone)"),
        ("placebo_party_dummies", "party identity alone (6 dummies)"),
        ("party_dummies_plus_share", "identity + volume"),
        ("party_dummies_plus_tone_within", "identity + centred tone"),
        ("tone_within_party", "share + centred tone"),
        ("party_dummies_plus_volume_and_tone_within",
         "identity + volume + centred tone (full)"),
    ]
    arms = {name: {r["window"]: r["delta_vs_recalibrated"]
                   for r in payload["arms"][name]}
            for name, _ in arm_label}
    tone_marginal = payload["paired_marginals"]["90_to_31_days"][
        "vs_party_dummies_plus_share"]
    assert round(tone_marginal["full_minus_comparator_mae_gain"], 4) == -0.1229
    assert round(tone_marginal["ci_lower"], 4) == -0.1595
    assert round(tone_marginal["ci_upper"], 4) == -0.0879

    head = "".join(f"<th>{wlabel[w]}</th>" for w in windows)
    body = []
    for name, label in arm_label:
        cells = "".join(f"<td>{arms[name][w]:+.4f}</td>" for w in windows)
        body.append(f"<tr><td>{label}</td>{cells}</tr>")
    factorial = (f"<div class='tablewrap'><table><thead><tr>"
                 f"<th>arm (ΔMAE vs recalibrated control)</th>{head}"
                 f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>")

    contrast_label = [
        ("vs_placebo_party_dummies", "full vs identity alone"),
        ("vs_party_dummies_plus_share",
         "full vs identity+volume (tone's marginal)"),
        ("vs_party_dummies_plus_tone_within",
         "full vs identity+tone (volume's marginal)"),
        ("vs_tone_within_party",
         "full vs tone alone (identity's marginal)"),
    ]
    rows = []
    for w in windows:
        cells = []
        for key, _ in contrast_label:
            m = payload["paired_marginals"][w][key]
            point = m["full_minus_comparator_mae_gain"]
            starred = m["ci_lower"] > 0 or m["ci_upper"] < 0
            text = (f"{point:+.4f} [{m['ci_lower']:+.3f}, "
                    f"{m['ci_upper']:+.3f}]")
            cells.append(f"<td>{'<strong>' + text + '</strong>' if starred else text}</td>")
        rows.append(f"<tr><td>{wlabel[w]}</td>{''.join(cells)}</tr>")
    chead = "".join(f"<th>{label}</th>" for _, label in contrast_label)
    marginals = (f"<div class='tablewrap'><table><thead><tr><th>window</th>"
                 f"{chead}</tr></thead><tbody>{''.join(rows)}</tbody>"
                 f"</table></div>")

    return (
        "<h3>The identity factorial in one table (exploratory, "
        "post-unblinding)</h3>"
        f"{factorial}"
        "<p class='src'>Every arm: same 45 frozen fitting cells, frozen "
        "prediction and scoring code; only feature_columns differ. "
        "Positive = better than the recalibrated control. The dummies "
        "row repeats +0.8342 across windows because party identity "
        "reads no article and cannot vary by window.</p>"
        f"{marginals}"
        "<p class='src'>Paired contest-bootstrap contrasts (bold = "
        "interval excludes zero): positive = the full three-ingredient "
        "specification beats the nested arm. Identity's marginal is "
        "the only consistently positive column; tone's marginal at "
        "31–90d is the quoted −0.1229 [−0.1595, −0.0879]. source: "
        "news_features/combined_specification_v1/"
        "combined_specification_results.json"
        f"{prov_btn('combospec', 'code behind these numbers')}</p>")


def prov_btn(key: str, label: str = "code behind these numbers") -> str:
    if key is None:
        return ""
    assert key in PROV, key
    return (f" <button class='prov' data-prov='{key}'>&#9656; {label}"
            f"</button>")


# ---------------------------------------------------------- code navigator

CODE_PREFIXES = ("src/", "app/", "tests/", "demo/")


def code_index(files: list[str]) -> list[dict]:
    """Every tracked Python file with its def/class names, for the
    searchable in-page code navigator."""
    entries = []
    for rel in files:
        if not rel.endswith(".py") or not rel.startswith(CODE_PREFIXES):
            continue
        text = (REPO / rel).read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
            defs = [n.name for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef))]
        except SyntaxError:
            defs = []
        entries.append({"p": rel, "d": sorted(set(defs)), "s": text})
    return sorted(entries, key=lambda e: e["p"])


# Live-demo inputs: verified present at build time so the pack can state
# honestly whether the Streamlit scenario app is runnable on this machine.
LIVE_APP_INPUTS = (
    "app/news_app.py",
    "news_features/news_feature_table_v2.csv",
    "news_features/blinded_2026_predictions_v2/frozen_protocol.json",
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "bundle_manifest.json",
)


def viva_box(say: list[str], qa: list[tuple[str, str]]) -> str:
    say_html = "".join(f"<li>{s}</li>" for s in say)
    qa_html = "".join(
        f"<details><summary>{esc(q)}</summary><p>{a}</p></details>"
        for q, a in qa)
    return (f"<details class='viva'><summary>Viva guidance for this section"
            f"</summary><p><strong>What to say (&asymp;30&ndash;60s):</strong>"
            f"</p><ul>{say_html}</ul>"
            f"<p><strong>Likely questions:</strong></p>{qa_html}</details>")


# ------------------------------------------------------------ repo map

REPO_MAP = [
    ("src/news_collection", "News collection: SerpAPI / publisher / Wayback "
     "adapters, eligibility and leakage screening, decision audit trails"),
    ("src/news_store + src/dedup + src/normalisation", "Article store, exact/"
     "near-duplicate handling, character and name normalisation"),
    ("src/llm_extraction", "Claude-based extraction layers (issue, stance, "
     "framing, and the excluded layers), validation runs, freeze layer"),
    ("src/news_features", "Article-level outputs to election-party-window "
     "feature tables (v1/v2), leakage audits"),
    ("src/news_modelling", "Stage 2 estimator, blinded 2026 predictions "
     "v1/v2, unblinding, decompositions, blind tests, report tables and "
     "figures with build-time assertions"),
    ("src (top level)", "Election results collection, validation and dataset "
     "build: official SCC sources, standardisation, calendar, audits"),
    ("surrey-election-no-news-baseline", "Stage 1 subproject: LightGBM "
     "history-only baseline, model selection, out-of-fold residuals, its own "
     "app and docs"),
    ("surrey-election-extractor", "Results-extraction subproject used to "
     "convert official election pages into structured records"),
    ("app", "Streamlit viewing/scenario layer over the frozen artefacts"),
    ("tests", "Pytest suite guarding the pipeline, blinding, artefact "
     "citations and frozen predictions"),
    ("outputs/report_tables_v1 + report_figures_v1", "The frozen, "
     "sha256-pinned evidence pack this demonstrator reads"),
    ("report", "LaTeX report source and figures; logbook/ and deliverables/ "
     "track process"),
]


def repo_map_html(files: list[str]) -> str:
    def count(prefixes: tuple[str, ...]) -> int:
        return sum(f.endswith(".py") and f.startswith(prefixes)
                   for f in files)

    counts = {
        "src/news_collection": ("src/news_collection/",),
        "src/news_store + src/dedup + src/normalisation":
            ("src/news_store/", "src/dedup/", "src/normalisation/"),
        "src/llm_extraction": ("src/llm_extraction/",),
        "src/news_features": ("src/news_features/",),
        "src/news_modelling": ("src/news_modelling/",),
        "surrey-election-no-news-baseline":
            ("surrey-election-no-news-baseline/",),
        "surrey-election-extractor": ("surrey-election-extractor/",),
        "app": ("app/",),
        "tests": ("tests/",),
    }
    counts["src (top level)"] = None  # computed below
    top_level = sum("/" not in f[4:] and f.endswith(".py")
                    for f in files if f.startswith("src/"))
    rows = []
    for name, purpose in REPO_MAP:
        if name in counts and counts[name] is not None:
            n = count(counts[name])
            n_txt = f"{n} .py"
        elif name == "src (top level)":
            n_txt = f"{top_level} .py"
        else:
            n_txt = "&ndash;"
        rows.append(f"<tr><td><code>{esc(name)}</code></td>"
                    f"<td>{esc(purpose)}</td><td>{n_txt}</td></tr>")
    return ("<div class='tablewrap'><table><thead><tr><th>where</th>"
            "<th>what it does</th><th>tracked code</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>"
            "<p class='src'>source: computed from <code>git ls-files</code> "
            "at build time.</p>")


# ----------------------------------------------------------------- style

CSS = """
:root { --bg:#ffffff; --fg:#1a1c20; --mut:#5b6270; --line:#e3e6eb;
        --card:#f6f7f9; --acc:#1f5fbf; --good:#0b7a4b; --bad:#b03030;
        --warn:#8a5a00; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14161a; --fg:#e8eaee; --mut:#9aa2b1; --line:#2a2e36;
          --card:#1c1f25; --acc:#7aa7e8; --good:#5fd39a; --bad:#e88;
          --warn:#e2b35c; }
}
* { box-sizing:border-box; }
body { margin:0; font:15px/1.55 -apple-system,'Segoe UI',Roboto,Helvetica,
       Arial,sans-serif; color:var(--fg); background:var(--bg); }
nav { position:fixed; top:0; left:0; bottom:0; width:230px; padding:18px;
      border-right:1px solid var(--line); overflow-y:auto; background:var(--bg); }
nav h1 { font-size:14px; margin:0 0 10px; }
nav a { display:block; padding:5px 8px; border-radius:6px; color:var(--fg);
        text-decoration:none; font-size:13.5px; }
nav a:hover { background:var(--card); }
main { margin-left:230px; padding:28px 40px 80px; max-width:1000px; }
@media (max-width:860px){ nav{position:static;width:auto;border:none;}
                          main{margin:0;padding:16px;} }
section { margin-bottom:44px; scroll-margin-top:12px; }
h2 { border-bottom:2px solid var(--line); padding-bottom:6px; }
h3 { margin-top:26px; }
.cap { font-weight:600; margin:14px 0 4px; }
.src { color:var(--mut); font-size:12.5px; margin:4px 0 0; }
.tablewrap { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:13.5px; }
th,td { border:1px solid var(--line); padding:4px 8px; text-align:left;
        white-space:nowrap; }
th { background:var(--card); }
td { font-variant-numeric:tabular-nums; }
figure { margin:18px 0; }
figure img { max-width:100%; border:1px solid var(--line); border-radius:8px;
             background:#fff; }
figcaption { color:var(--mut); font-size:13px; margin-top:6px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
         gap:12px; margin:14px 0; }
.card { background:var(--card); border:1px solid var(--line);
        border-radius:10px; padding:12px 14px; }
.card b { font-size:22px; display:block; }
.card span { color:var(--mut); font-size:12.5px; }
.good { color:var(--good); } .bad { color:var(--bad); }
.warnbox { border-left:4px solid var(--warn); background:var(--card);
           padding:10px 14px; border-radius:0 8px 8px 0; margin:14px 0; }
details.viva { border:1px dashed var(--acc); border-radius:10px;
               padding:10px 14px; margin:18px 0; }
details.viva > summary { color:var(--acc); font-weight:600; cursor:pointer; }
details.viva details { margin:6px 0 6px 10px; }
details.viva summary { cursor:pointer; }
.explorer { background:var(--card); border:1px solid var(--line);
            border-radius:10px; padding:14px; margin:14px 0; }
.explorer select { font:inherit; padding:4px 6px; margin-right:10px;
                   background:var(--bg); color:var(--fg);
                   border:1px solid var(--line); border-radius:6px; }
.explorer .out { margin-top:10px; }
code { background:var(--card); padding:1px 5px; border-radius:5px;
       font-size:13px; }
.twocol { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
@media (max-width:860px){ .twocol{grid-template-columns:1fr;} }
kbd { border:1px solid var(--line); border-bottom-width:2px; padding:0 5px;
      border-radius:4px; font-size:12px; }
button.prov { font:12px inherit; color:var(--acc); background:none;
              border:1px solid var(--acc); border-radius:12px;
              padding:1px 9px; cursor:pointer; margin-left:6px; }
button.prov:hover { background:var(--card); }
#modal { position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:50;
         display:flex; align-items:center; justify-content:center; }
#modal[hidden] { display:none; }
#modal-box { background:var(--bg); color:var(--fg); max-width:860px;
             width:92%; max-height:86vh; overflow-y:auto; border-radius:12px;
             border:1px solid var(--line); padding:20px 24px;
             position:relative; }
#modal-close { position:sticky; top:0; float:right; font:16px inherit;
               background:var(--card); color:var(--fg); cursor:pointer;
               border:1px solid var(--line); border-radius:8px;
               padding:2px 10px; }
#modal-box pre { background:var(--card); border:1px solid var(--line);
                 border-radius:8px; padding:10px 12px; overflow-x:auto;
                 font-size:12px; line-height:1.45; }
#modal-box details { margin:8px 0; }
#modal-box summary { cursor:pointer; color:var(--acc); }
.provsrc { display:none; }
ol.spine { counter-reset: sp; list-style:none; padding-left:0; }
ol.spine li { counter-increment: sp; margin:7px 0; padding:8px 12px;
  background:var(--card); border:1px solid var(--line); border-radius:8px; }
ol.spine li::before { content: counter(sp); display:inline-block;
  width:22px; height:22px; line-height:22px; text-align:center;
  border-radius:50%; background:var(--acc); color:#fff; font-size:12px;
  font-weight:600; margin-right:9px; }
ol.spine a { color:var(--fg); text-decoration:none; }
ol.spine a b { color:var(--acc); }
.ann { background:var(--card); border-left:3px solid var(--acc);
       border-radius:0 8px 8px 0; padding:8px 12px; margin:8px 0;
       font-size:13px; }
.ann p { margin:4px 0; }
.annlines { margin-top:6px; font-size:12.5px; }
.annlines td, .annlines th { white-space:normal; }
button.openfile { font:11.5px inherit; color:var(--mut); background:none;
                  border:1px solid var(--line); border-radius:10px;
                  padding:0 8px; cursor:pointer; margin-left:6px; }
button.openfile:hover { color:var(--acc); border-color:var(--acc); }
#code-list { max-height:300px; overflow-y:auto; margin-top:8px; }
#code-list .cfile { padding:3px 8px; border-radius:6px; cursor:pointer;
                    font:13px ui-monospace,SFMono-Regular,Menlo,monospace; }
#code-list .cfile:hover { background:var(--bg); }
#code-list .cfile .defs { color:var(--mut); font-size:11.5px; }
#code-view { margin-top:14px; }
#code-view pre { background:var(--card); border:1px solid var(--line);
                 border-radius:8px; padding:10px 12px; overflow-x:auto;
                 font-size:12px; line-height:1.45; max-height:70vh;
                 overflow-y:auto; }
"""

# ------------------------------------------------------------------- JS

JS = """
function fmt(x, dp){ if(x===null||x===undefined||x==='') return '–';
  var v = Number(x); return (v>0?'+':'') + v.toFixed(dp===undefined?3:dp); }
function confUpdate(){
  var v=document.getElementById('c-ver').value,
      a=document.getElementById('c-arm').value,
      w=document.getElementById('c-win').value,
      d=CONF[v].find(function(r){return r.arm===a && r.window===w;}),
      o=document.getElementById('c-out');
  if(!d){ o.innerHTML='no such specification'; return; }
  var pos = d.news_vs_recalibrated>0, ciPos = d.ci_lower>0 && d.ci_upper>0;
  var verdict = pos ? (ciPos ? 'news better; 95% CI entirely above zero'
                             : 'news better; CI crosses zero')
                    : 'no improvement over the no-news control';
  o.innerHTML =
   '<div class="cards">'+
   '<div class="card"><b>'+d.recalibrated_mae.toFixed(3)+'</b>'+
     '<span>no-news control MAE (pp)</span></div>'+
   '<div class="card"><b>'+d.news_mae.toFixed(3)+'</b>'+
     '<span>news MAE (pp)</span></div>'+
   '<div class="card"><b class="'+(pos?'good':'bad')+'">'+
     fmt(d.news_vs_recalibrated)+'</b><span>ΔMAE, + = news better</span></div>'+
   '<div class="card"><b>['+fmt(d.ci_lower)+', '+fmt(d.ci_upper)+']</b>'+
     '<span>95% contest-bootstrap CI (2,000 resamples)</span></div>'+
   '<div class="card"><b class="'+(d.reform_vs_recalibrated>0?'good':'bad')+'">'+
     fmt(d.reform_vs_recalibrated)+'</b><span>Reform UK ΔMAE</span></div>'+
   '</div><p><strong>'+verdict+'</strong></p>';
}
function scenUpdate(){
  var p=document.getElementById('s-preset').value,
      rows=SCEN.filter(function(r){return r.preset===p;}),
      o=document.getElementById('s-out'), h;
  h='<div class="tablewrap"><table><thead><tr><th>party</th><th>tone</th>'+
    '<th>arm</th><th>articles added</th><th>window</th>'+
    '<th>articles already in cell</th><th>Δ target-party share (pp)</th>'+
    '<th>seat flips</th></tr></thead><tbody>';
  rows.forEach(function(r){
    h+='<tr><td>'+r.party+'</td><td>'+r.tone+'</td><td>'+r.arm+'</td>'+
       '<td>'+r.articles+'</td><td>'+r.window+'</td>'+
       '<td>'+r.cell_articles_before+'</td>'+
       '<td class="'+(r.target_party_delta>0?'good':'bad')+'">'+
       fmt(r.target_party_delta,4)+'</td><td>'+r.seat_flips+'</td></tr>';
  });
  o.innerHTML=h+'</tbody></table></div>';
}
function openProv(key){
  var src=document.getElementById('prov-'+key); if(!src) return;
  document.getElementById('modal-title').textContent =
    'From number to code — ' + key;
  document.getElementById('modal-body').innerHTML = src.innerHTML;
  document.getElementById('modal').hidden = false;
}
function closeProv(){ document.getElementById('modal').hidden = true; }
function renderCodeList(entries, q){
  var list=document.getElementById('code-list'), h='';
  entries.forEach(function(e){
    var defs=e.d.slice(0,8).join(', ');
    h+='<div class="cfile" data-path="'+e.p+'">'+e.p+
       (defs?' <span class="defs">'+defs+(e.d.length>8?', …':'')+
       '</span>':'')+'</div>';
  });
  list.innerHTML=h;
  document.getElementById('code-count').textContent =
    entries.length+' of '+CODE.length+' files'+(q?' match "'+q+'"':'');
}
function codeSearch(){
  var q=document.getElementById('code-q').value.trim().toLowerCase();
  if(!q){ renderCodeList(CODE,''); return; }
  renderCodeList(CODE.filter(function(e){
    return e.p.toLowerCase().indexOf(q)>=0 ||
           e.d.some(function(d){return d.toLowerCase().indexOf(q)>=0;}) ||
           e.s.toLowerCase().indexOf(q)>=0;
  }), q);
}
function openFile(path){
  var e=CODE.find(function(x){return x.p===path;}); if(!e) return;
  var lines=e.s.split('\\n'), w=String(lines.length).length, out=[];
  for(var i=0;i<lines.length;i++)
    out.push(String(i+1).padStart(w,' ')+'  '+lines[i]);
  var view=document.getElementById('code-view');
  view.innerHTML='<p class="cap"><code>'+path+'</code> ('+lines.length+
                 ' lines, verbatim at build time)</p><pre></pre>';
  view.querySelector('pre').textContent=out.join('\\n');
  document.getElementById('s9').scrollIntoView();
}
window.addEventListener('DOMContentLoaded',function(){
  confUpdate(); scenUpdate(); renderCodeList(CODE,'');
  document.body.addEventListener('click',function(e){
    var f=e.target.closest('#code-list .cfile');
    if(f){ openFile(f.dataset.path); return; }
    var o=e.target.closest('button.openfile');
    if(o){ closeProv(); openFile(o.dataset.path); return; }
    var b=e.target.closest('button.prov');
    if(b){ openProv(b.dataset.prov); return; }
    if(e.target.id==='modal'||e.target.id==='modal-close') closeProv();
  });
  window.addEventListener('keydown',function(e){
    if(e.key==='Escape') closeProv();
  });
});
"""


# ---------------------------------------------------------------- build

def build() -> str:
    stems = {
        "t01": "t01_baseline_2026_reference",
        "t02": "t02_baseline_per_party_mae",
        "t03": "t03_baseline_seat_totals",
        "t04": "t04_confirmatory_v1",
        "t05": "t05_confirmatory_v2",
        "t06": "t06_sensitivity_summary",
        "t07": "t07_seat_accuracy_by_specification",
        "t08": "t08_reform_seat_calls_v2",
        "t09": "t09_attribution_decomposition",
        "t10": "t10_mechanism_pooled_dispersion",
        "t13": "t13_approach_comparison",
        "t14": "t14_haslemere_probe",
        "t15": "t15_haslemere_reference",
        "t16": "t16_nonnews_trail_channels",
        "t17": "t17_corpus_by_window",
        "t18": "t18_synthetic_scenarios",
        "t19": "t19_local_v3_rerun",
        "t20": "t20_woking_south_blind_test",
        "t21": "t21_woking_south_autopsy",
        "t22": "t22_per_party_contrast",
        "t23": "t23_mde_summary",
    }
    t = {k: load_table(v) for k, v in stems.items()}
    manifest = load_manifest()
    files = tracked_files()
    assert_headline_numbers(t)

    conf_json = json.dumps({
        "v1": t["t04"].to_dict("records"),
        "v2": t["t05"].to_dict("records"),
    }).replace("<", "\\u003c")
    scen = t["t18"].copy()
    scen_json = json.dumps(scen.to_dict("records")).replace("<", "\\u003c")
    presets = list(dict.fromkeys(scen.preset))
    preset_opts = "".join(
        f"<option value=\"{esc(p)}\">{esc(p)}</option>" for p in presets)
    n_tests = sum(f.startswith("tests/test_") for f in files)
    n_py = sum(f.endswith(".py") for f in files)

    v2 = t["t05"]
    head = v2[(v2.arm == "combined") & (v2.window == "90-31 days")].iloc[0]
    nat = v2[(v2.arm == "national") & (v2.window == "90-31 days")].iloc[0]

    missing_live = [p for p in LIVE_APP_INPUTS if not (REPO / p).exists()]
    if missing_live:
        live_status = ("<strong>Build-time check:</strong> not runnable on "
                       "this machine &mdash; missing: "
                       + ", ".join(f"<code>{esc(p)}</code>"
                                   for p in missing_live)
                       + " (regenerate per the repository README).")
    else:
        live_status = ("<strong>Build-time check:</strong> all inputs the "
                       "live app needs (frozen protocol, v2 feature table, "
                       "Stage 1 bundle) were present on this machine when "
                       "this pack was built.")

    sections: list[str] = []

    # -- 1 research overview -------------------------------------------
    sections.append(f"""
<section id="s1"><h2>1&nbsp;&middot;&nbsp;Research overview</h2>
<p><strong>Research question.</strong> Does pre-election news add predictive
value for local-election vote shares <em>beyond</em> an adjusted
history-only baseline? Case study: the 2026 Surrey County Council
elections, with particular attention to Reform UK, a party with little
electoral history.</p>
<p><strong>Design in one sentence.</strong> Stage&nbsp;1 predicts candidate
vote share from historical election data alone (LightGBM); Stage&nbsp;2
models the remaining Stage&nbsp;1 errors with LLM-extracted news features
(per-window Ridge); predictions were <strong>frozen before the 2026
results were read</strong>, and news is scored against a recalibrated
no-news control, not against the raw baseline.</p>
<div class="cards">
<div class="card"><b>{head.recalibrated_mae:.3f} &rarr; {head.news_mae:.3f}</b>
<span>candidate vote-share MAE (pp), no-news control vs combined news,
31&ndash;90 days (v2)</span></div>
<div class="card"><b class="good">+{head.news_vs_recalibrated:.3f}</b>
<span>&Delta;MAE, combined news, 95% CI [{head.ci_lower:+.3f},
{head.ci_upper:+.3f}]</span></div>
<div class="card"><b class="good">+{nat.news_vs_recalibrated:.3f}</b>
<span>&Delta;MAE, national news, 95% CI [{nat.ci_lower:+.3f},
{nat.ci_upper:+.3f}]</span></div>
<div class="card"><b>5 / 12</b><span>v2 specifications with lower MAE than
the control; 4 with CIs entirely above zero (v1: 0 / 12)</span></div>
</div>
<p class="src">source: t05_confirmatory_v2.csv (frozen, register-backed);
asserted at build time.{prov_btn("t05")}</p>
<p><strong>Contributions.</strong> (1) an adjusted history-only baseline for
a realignment election; (2) a sealed, pre-registered test of the
incremental value of news; (3) diagnostics showing <em>when</em> and
<em>through what</em> news helps &mdash; timing (31&ndash;90 days), training
composition (the seven Reform UK cells), and channel (volume vs stance vs
party identity).</p>
{viva_box(
  ["One-line claim: news adds a small, confirmable improvement over a "
   "recalibrated no-news control, but only under the enriched training set "
   "(v2) and clearest at 31&ndash;90 days before polling day.",
   "Stress the blinding: v1/v2 predictions frozen before the 2026 results "
   "were read; the confirmatory grid (24 comparisons) was predefined.",
   "Frame Reform UK as the hard case that motivates the design."],
  [("Why a two-stage design rather than one model with all features?",
    "If news entered one joint model, its contribution would be confounded "
    "with history. Stage 2 models only what Stage 1 cannot explain, so the "
    "test is directly about incremental value. The exploratory check "
    "(Appendix B, t13) found the residual design lower in 16 of 18 "
    "specifications."),
   ("Is +0.24pp meaningful?",
    "It is small but resolvable: the v2 design's 80%-power minimal "
    "detectable effect for overall ΔMAE has median ≈0.216pp (t23), "
    "so the observed +0.240 sits above design resolution, and both "
    "31–90-day CIs exclude zero. I claim conditional evidence, not a "
    "large effect.")])}
</section>""")

    # -- 2 data and code ------------------------------------------------
    sections.append(f"""
<section id="s2"><h2>2&nbsp;&middot;&nbsp;Data and code</h2>
<p class="src">Chain steps 1&ndash;2: the ground truth and the raw signal.</p>
<h3 id='p-elections'>Election data</h3>
<p>Surrey county-level record 2013&ndash;2026: <strong>24 events, 343
contests, 1,992 candidate rows</strong> from official Surrey Council
sources (borough/district context from Wikipedia; not used in training).
Rolling design: 2013 starts the training history, 2017+2021 validate,
the 2026 East+West elections (832 candidates, 81 two-seat wards) are the
sealed holdout. 19 by-elections 2015&ndash;2026; Woking South is a
pre-registered blind case, Warlingham stayed sealed, Haslemere was the
replication probe. Validation: recomputed vote totals/shares/turnout
against published pages (0.5pp tolerance); direct source links for 1,971
of 1,992 rows, archive listings for the remaining 21.</p>
<p class="cap">Where the headline counts come from, and how they split
{prov_btn("elecdata", "how these counts are produced")}</p>
<div class="tablewrap"><table><thead><tr><th></th><th>events</th>
<th>contests</th><th>candidate rows</th><th>row share</th></tr></thead>
<tbody>
<tr><td>principal elections (2013 / 2017 / 2021 / 2026 East / 2026 West)</td>
<td>5</td><td>324</td><td>1,898 (358 / 377 / 331 / 379 / 453)</td>
<td>95.3%</td></tr>
<tr><td>by-elections (one contest each)</td><td>19</td><td>19</td>
<td>94</td><td>4.7%</td></tr>
<tr><td><strong>total</strong></td><td><strong>24</strong></td>
<td><strong>343</strong></td><td><strong>1,992</strong></td><td></td></tr>
</tbody></table></div>
<p class="src">source: data_quality_report.json (Stage 1 bundle); asserted
at build time when the bundle is present. The by-elections are 4.7% of
the rows yet supply 34 of the 45 v2 fitting cells including all seven
Reform cells &mdash; the enrichment is about the right rows, not more
rows.</p>
{img("fig0_study_design.png", "Role assignment of the 24 election events "
     "(blue = enters fitting, orange = sealed/blind evaluation only).",
     prov="elecdata", label="code behind the counts on this figure")}
<h3 id='p-corpus'>News corpus</h3>
<p>Local (SurreyLive, BBC Surrey, Guardian Surrey; search APIs, publisher
search, web archives) and national (Guardian Open Platform) collected
separately. Screening for date, language, editorial content, political
relevance and <strong>result leakage</strong> (any article carrying
same-election results excluded regardless of date). v1: 2,666 candidates
&rarr; 1,632 usable (188 local, 1,444 national); v2 adds 627 by-election
articles &rarr; 2,259. Six non-overlapping windows (1&ndash;3 &hellip;
91&ndash;180 days) plus six cumulative windows.</p>
{img("fig0b_corpus_funnel.png", "Corpus construction funnel: 2,666 "
     "candidate articles to 1,632 usable (v1).", prov="fig0b",
     label="code behind the counts on this figure")}
{df_html(t["t17"], "Canonical v2 corpus per confirmed window",
         "t17_corpus_by_window.csv", prov="t17")}
<h3>Stage&nbsp;1 predictor dictionary (35 predictors &rarr; 127 encoded)</h3>
{tex_tabular_html(TABLES / "latex" / "a1_stage1_predictors.tex",
                  "Stage 1 predictors (from the published feature schema)",
                  "latex/a1_stage1_predictors.tex (report Table 3)",
                  prov="a1pred")}
<h3>Repository map &mdash; what was actually built</h3>
<p>{n_py} tracked Python files; {n_tests} test modules.</p>
{repo_map_html(files)}
{viva_box(
  ["Emphasise verifiability: every candidate row carries a source link; "
   "every screening decision and reason is recorded.",
   "The repo is a pipeline, not a notebook: collection → screening "
   "→ extraction → features → modelling → frozen "
   "artefacts, each stage tested.",
   "Local and national news were collected and kept separate by design."],
  [("How did you prevent result leakage from news articles?",
    "Predefined eligibility rules: exclusion of polling-day articles "
    "(publication times unavailable), original publication dates for "
    "archived copies, and exclusion of any article containing results from "
    "the same election even if dated before polling day. Tone never "
    "affected eligibility. 5% of eligibility decisions were randomly "
    "re-reviewed (≥30 articles per election)."),
   ("Why only 17 local search areas?",
    "Pre-registered selection over four electoral-structure categories "
    "(safe, marginal, changed-winner, strongest Reform share), fixed "
    "before any news content was seen — report Appendix H.")])}
</section>""")

    # -- 3 methodology --------------------------------------------------
    sections.append(f"""
<section id="s3"><h2>3&nbsp;&middot;&nbsp;Methodology</h2>
<p class="src">Chain steps 3&ndash;7: Stage 1 from the election record; the news branch (labels &rarr; features); Stage 2 joins the two; then the freeze.</p>
{img("fig0c_framework.png", "Two-stage prediction framework; everything "
     "above the dashed line was frozen before the 2026 results were read.",
     prov="pipeline", label="code of every Stage 1 + Stage 2 step")}
<h3 id='p-stage1'>Stage&nbsp;1 &mdash; history-only baseline</h3>
<p>Candidate-level target = vote share &times; candidate count / 100 (mean
1 per contest), 35 predictors &rarr; 127 inputs, preprocessing learned
inside each fold. Model selection across Ridge, partial pooling and
LightGBM on four temporal folds with a predefined Reform-focused rule:
LightGBM cut Reform UK MAE 8.3% vs Ridge (&gt;5% threshold) and was
selected. Out-of-fold predictions for 792 candidate records over 16
time-based folds &mdash; one per pre-2026 polling day with earlier
history to train on (2017, 2021, and 14 by-election days; same-day
by-elections share a fold; 2013 has no earlier history and is training
fuel only) &mdash; provide Stage&nbsp;2 residual targets; the final
model trains on 1,150 records before 7 May 2026.</p>
<h3 id='p-llm'>LLM extraction and validation gate</h3>
<p>Claude Sonnet 5 and Haiku 4.5 compared against a Cohen's
&kappa;&nbsp;&ge;&nbsp;0.60 gate (model&ndash;model and against 168 human
annotations); failed layers were redesigned once or excluded. Format
checks, evidence matched to source text, one retry then removal.
{prov_btn("llmgate", "code of the extraction gate")}</p>
{tex_tabular_html(TABLES / "latex" / "a5_llm_validation.tex",
                  "Final validation evidence per extraction layer "
                  "(threshold κ ≥ 0.60)",
                  "latex/a5_llm_validation.tex (report Table 1)",
                  prov="llmgate")}
<h3 id='p-signal'>What the news signal actually is &mdash; from article to number</h3>
<p>Each usable article carries LLM labels: which study parties it
mentions and, per party, a three-level <strong>stance</strong>
(favourable / neutral / unfavourable &mdash; "how does this article
portray this party"), plus issue and framing labels. Per
election&ndash;party&ndash;window&ndash;arm cell, the labels collapse
into exactly <strong>two numbers</strong>, the only news inputs the
frozen models ever see:</p>
<ul>
<li><strong>Party article share</strong> = P's articles &divide; all
articles in the window. <em>Visibility:</em> how much of the
conversation is about this party.</li>
<li><strong>Net portrayal (stance balance)</strong> = (favourable
&minus; unfavourable) &divide; P's articles &mdash; neutral counts in
the denominator only. <em>Tone direction:</em> is coverage leaning for
or against, on a scale from &minus;1 (all hostile) to +1 (all
friendly).</li>
</ul>
<p><strong>Worked example.</strong> A window holds 20 articles; 10
mention Reform UK: 2 favourable, 5 unfavourable, 3 neutral. Then
Reform's article share = 10/20 = <strong>0.50</strong> (half the
conversation) and net portrayal = (2&minus;5)/10 =
<strong>&minus;0.30</strong> (leaning against). A neutral story added
to the pile raises share but leaves the numerator of portrayal
untouched &mdash; volume and tone are deliberately separable, which is
what &sect;5.3's volume-vs-stance decomposition exploits. The three
arms (combined / national / local) count their own copies of both
numbers.{prov_btn("newsfeat", "code of the feature construction")}</p>
<p class="warnbox">Why only these two? The issue and framing labels
exist per article, but aggregated to cells they cleared the ten-value
training-variation bar in too few windows &mdash; so the frozen signal
is <em>visibility + tone direction</em>, and issue/framing stayed
exploratory (Appendix a13). "News signal" in every headline number
means exactly these two standardised features entering a per-window
ridge.</p>
<h3 id='p-stage2'>Stage&nbsp;2 &mdash; incremental news layer</h3>
<p>Residuals averaged per election&ndash;party cell; one Ridge
(&alpha;=1.0, fixed before validation) per window on two standardised
predictors: <em>party article share</em> and <em>stance balance</em>
(favourable&minus;unfavourable over the party's articles; neutral in the
denominator). v1 trains on 11 cells (2017+2021); v2 adds eight
by-elections &rarr; 45 cells including the first seven Reform UK cells.
Adjustments are added to Stage&nbsp;1, clipped at zero, renormalised to
100 per contest, and scored as &Delta;MAE against a recalibrated no-news
control (mean training residual as intercept) &mdash; so simple
recalibration cannot masquerade as news value.{prov_btn("stage2fit",
"code of the Stage 2 fit")}</p>
<p class="cap">The Stage 2 equation (report &sect;4.3), term by term</p>
<p style="font-size:17px;text-align:center">
<i>r&#770;<sub>ep</sub></i> = <i>r&#772;</i> +
<span style="font-size:22px">&Sigma;</span><sub>j=1..2</sub>
&nbsp;<i>&beta;<sub>j</sub></i> &middot;
(<i>x<sub>epj</sub></i> &minus; <i>x&#772;<sub>j</sub></i>) / <i>s<sub>j</sub></i>
</p>
<div class="tablewrap"><table><thead><tr><th>symbol</th><th>meaning</th>
<th>where it lives in the code</th></tr></thead><tbody>
<tr><td><i>r&#770;<sub>ep</sub></i></td><td>predicted residual for election
<i>e</i>, party <i>p</i> &mdash; "how far off we expect Stage 1 to be for
this party"</td><td>output of <code>RidgeModel.predict</code>; becomes the
per-party news adjustment</td></tr>
<tr><td><i>r&#772;</i></td><td>mean training residual (average of the
fitting cells) &mdash; the intercept, and by itself the no-news control's
constant</td><td><code>self._intercept = target_mean</code>; recorded as
<code>intercept_mean_training_residual</code></td></tr>
<tr><td><i>&beta;<sub>j</sub></i></td><td>standardised coefficient of news
feature <i>j</i> &mdash; how strongly that feature moves the predicted
residual</td><td><code>np.linalg.solve(gram, ...)</code>; recorded as
<code>standardised_coefficients</code> and re-asserted to 1e-9 by every
later refit</td></tr>
<tr><td><i>x<sub>epj</sub></i></td><td>the cell's news feature <i>j</i>:
j=1 party article share (visibility), j=2 net portrayal (tone)</td>
<td>the design-matrix columns built in
<code>_fit_specification</code></td></tr>
<tr><td>(<i>x</i> &minus; <i>x&#772;<sub>j</sub></i>) / <i>s<sub>j</sub></i></td>
<td>standardisation: subtract the training mean, divide by the training
standard deviation &mdash; both features forced onto the same scale</td>
<td><code>standardised = (design - means) / scales</code></td></tr>
</tbody></table></div>
<p><strong>Why this exact form?</strong> Three deliberate choices, each
visible in the implementation:</p>
<ul>
<li><strong>Standardise the features</strong> ((<i>x</i>&minus;<i>x&#772;</i>)/<i>s</i>):
article shares and portrayal scores live on different scales; an
unstandardised ridge penalty would silently punish one column hundreds of
times harder than the other &mdash; a modelling decision nobody made.</li>
<li><strong>Centre the target, keep the intercept unshrunk</strong>: the
penalty applies only to the two &beta;s, never to <i>r&#772;</i> &mdash;
so the intercept is exactly the mean training residual, which is what
lets the no-news control be defined as "baseline + <i>r&#772;</i>
alone".</li>
<li><strong>Only two terms in the sum</strong>: the frozen news signal is
exactly two features (visibility + tone); nothing else cleared the
pre-registered reporting bar.</li>
</ul>
<h3 id='p-freeze'>Blinding, leakage control and reproducibility</h3>
<ul>
<li>Strict time order; features and outcomes kept in separate files.</li>
<li>v1+v2 prediction files (832 candidates) frozen before unblinding; the
blind procedure applies to the frozen news-layer comparison.</li>
<li>Pre-declared rule: sensitivity and post-unblinding diagnostics are
never promoted to confirmatory findings.</li>
<li>Frozen artefacts carry a sha256 manifest; report tables/figures are
rebuilt from them with build-time assertions; {n_tests} test modules
guard the pipeline (including <code>test_artefact_citations.py</code>,
which fails if a cited artefact is not committed).</li>
</ul>
{viva_box(
  ["Walk the figure left to right: history → residuals → news "
   "adjustment → sealed evaluation.",
   "Name the three defences: recalibrated control, frozen predictions, "
   "pre-declared confirmatory/exploratory boundary.",
   "The κ gate is the reason stance is three-level and two layers "
   "were excluded — validation drove the design, not convenience."],
  [("Why Ridge with α fixed at 1.0 in Stage 2?",
    "Eleven (v1) training cells cannot support tuning; a fixed, "
    "pre-declared α avoids leaking validation information and keeps "
    "the news test honest (Mellon & Prosser 2025 on regularisation "
    "pitfalls)."),
   ("Two different LLMs — why?",
    "Per-layer selection under the same gate: Sonnet 5 won issue "
    "classification, Haiku 4.5 matched it on stance/framing at κ = "
    "0.848 model–model and 0.741 vs humans, so the cheaper model ran "
    "the bulk task. Cross-model agreement doubles as a robustness check."),
   ("What stopped you tuning on the 2026 holdout?",
    "Stage 1 metrics on 2026 had been viewed during development, but 2026 "
    "outcomes never entered training or model selection; the news-layer "
    "comparison itself was fully frozen before unblinding, and the "
    "register records the sequence.")])}
</section>""")

    # -- 4 technical results --------------------------------------------
    sections.append(f"""
<section id="s4"><h2>4&nbsp;&middot;&nbsp;Technical results</h2>
<p class="src">Chain steps 8&ndash;10: unblind, diagnose, stress-test.</p>
<h3>4.1 The baseline and the realignment it could not see</h3>
{df_html(t["t01"], "Untouched Stage 1 baseline on the 2026 principal "
         "election", "t01_baseline_2026_reference.csv", prov="t01")}
{df_html(t["t02"], "Per-party baseline MAE",
         "t02_baseline_per_party_mae.csv", max_rows=8, prov="t02")}
{img("fig2_seat_totals.png", "Predicted vs actual seat totals: the "
     "history-only baseline predicted Conservatives 118 (actual 30), "
     "Liberal Democrats 6 (actual 96), Reform UK 0 (actual 14).",
     prov="fig2", label="code behind the numbers on this figure")}
<p class="warnbox">Two baselines appear across tables by design: 4.514 is
the untouched baseline over all 832 rows; 4.441/4.445 is the same
baseline restricted to the 753 supported-party rows on which every news
comparison is scored. Mixing them misstates the deltas.</p>
<h3 id='p-unblind'>4.2 Confirmatory comparisons (frozen, 24 tests)</h3>
{img("fig1_confirmatory_deltas.png", "Forest plot of the 24 confirmatory "
     "comparisons (right of zero = news better).", prov="fig1",
     label="code behind the numbers on this figure")}
{df_html(t["t05"], "v2 confirmatory results (5 of 12 improve; 4 CIs above "
         "zero)", "t05_confirmatory_v2.csv", prov="t05")}
<p>v1 (t04): 0 of 12 improved &mdash; the same news features, with only 11
training cells, made predictions worse. The interactive explorer in
Section 6 covers every specification.</p>
<h3>4.3 Sensitivity and further checks (not promotable)</h3>
{df_html(t["t06"], "Sensitivity families summarised",
         "t06_sensitivity_summary.csv", prov="t06")}
<p class="src">What each row's <em>comparisons</em> count is made of
(a cell is sensitivity if ANY switch is off: local arm, cumulative
window, or 2017-only training variant):
v1&nbsp;combined&nbsp;18 = 6 cumulative + 12 fit_2017_only (6 confirmed
+ 6 cumulative); v1&nbsp;national&nbsp;18 = same structure;
v1&nbsp;local&nbsp;24 = 12 main-variant (6 confirmed + 6 cumulative)
+ 12 fit_2017_only; v2&nbsp;combined&nbsp;6 and
v2&nbsp;national&nbsp;6 = the 6 cumulative windows only (their 6
confirmed windows are the confirmatory cells in t05);
v2&nbsp;local&nbsp;12 = 6 confirmed + 6 cumulative (the local arm is
sensitivity throughout; v2 has no 2017-only variant). Total 60 + 24 =
84 sensitivity comparisons beside the 24 confirmatory ones.</p>
<ul>
<li><strong>Local news</strong> (v2, 31&ndash;90d): MAE 4.4454 &rarr;
4.2571 (+0.1884); positive at 8&ndash;14d and 91&ndash;180d too.
{prov_btn("t06", "code of the scoring (same marker, no CI)")}</li>
<li><strong>Cumulative windows</strong>: combined news improves all five
windows up to 90 days; best previous-14-days, MAE 3.8353 (full 18-row
table below).{prov_btn("a12cum", "code behind the cumulative results")}</li>
<li><strong>2017-only training</strong>: 0 of 18 improve &mdash;
reproduces the v1 failure; the signal needs the enriched sample.
{prov_btn("fit2017", "code of the 2017-only variant")}</li>
<li><strong>LOPO (pre-holdout)</strong>: removing Conservatives from
training produced 6/18 improvements; removing any other party, none
&mdash; training composition matters.{prov_btn("lopo",
"code of the LOPO check")}</li>
<li><strong>Local v3 re-run</strong> (t19): 4 of 6 windows improve with a
sign inversion at 180&ndash;91d (table below).
{prov_btn("t19", "code of the re-run")}</li>
</ul>
{tex_tabular_html(TABLES / "latex" / "a12_cumulative_results.tex",
                  "Cumulative-window results, all 18 comparisons (report "
                  "Table 10); sensitivity by the pre-declared rule — no "
                  "bootstrap CIs, never promoted",
                  "latex/a12_cumulative_results.tex (from the frozen "
                  "unblinding record)", prov="a12cum")}
{df_html(t["t19"], "Exploratory local re-run on the v3 lineage",
         "t19_local_v3_rerun.csv", prov="t19")}
<h3 id='p-diagnose'>4.4 Error analysis: where the gain lives</h3>
{df_html(t["t09"], "Attribution: v2 deltas with vs without the 7 Reform "
         "training cells", "t09_attribution_decomposition.csv", prov="t09")}
{img("fig4_island_contrast.png", "Reform vs non-Reform: the overall delta "
     "hides opposite movements.", prov="fig4",
     label="code behind the numbers on this figure")}
<p>Gains sit mainly with non-Reform candidates (combined-news &Delta;
&asymp; +0.49) while Reform's own &Delta; is &minus;0.6877; yet removing
the seven Reform <em>training</em> cells cuts the combined gain from
+0.2404 to +0.0773 and the national gain to &minus;0.0015. The signed
story (t22): the same downward news adjustment corrected Reform's 2021
overprediction (+12.21 &rarr; +3.07) but deepened its 2026
underprediction (&minus;1.33 &rarr; &minus;3.16).</p>
{img("fig6_mechanism_vs_outcome.png", "Mechanism vs outcome: pooled "
     "dispersion falls exactly in the improving windows (t10); per-party "
     "levels move while dispersion does not (t11/t12).", prov="fig6",
     label="code behind the numbers on this figure")}
<h3>4.5 Seat calls (secondary outcome)</h3>
{df_html(t["t07"][t["t07"].version == "v2"], "Seat-call accuracy per v2 "
         "specification vs the 0.8053 elect-nobody floor",
         "t07_seat_accuracy_by_specification.csv", prov="t07")}
<p>No confirmed-MAE specification beats the elect-nobody floor; every
specification still calls 0 Reform seats (t08, actual 14). Vote-share
error and seat calls respond to news differently.</p>
<h3 id='p-transfer'>4.6 Blind transfer and replication</h3>
{df_html(t["t20"], "Woking South pre-registered blind test: the "
         "pre-registered pick (local, 91–180d) was the worst of 18",
         "t20_woking_south_blind_test.csv", max_rows=6, prov="t20")}
{df_html(t["t21"], "Woking South autopsy: the adjustment worsened all "
         "five parties; the LD landslide (64.0%) was encoded nowhere",
         "t21_woking_south_autopsy.csv", prov="t21")}
{df_html(t["t14"], "Haslemere probe: 3 of 12 frozen specifications beat "
         "the control; the window ordering (31–90 best, 91–180 "
         "worst) replicates", "t14_haslemere_probe.csv", max_rows=6, prov="t14")}
<h3>4.7 Design resolution and uncertainty</h3>
{df_html(t["t23"], "80%-power minimal detectable effects (share points)",
         "t23_mde_summary.csv", max_rows=8, prov="t23")}
{viva_box(
  ["Lead with the honest headline: v1 failed everywhere; v2 succeeded in "
   "specific, predefined places; the difference is the training sample.",
   "Show the seat-totals figure for the realignment story — it "
   "explains why history alone was never going to be enough in 2026.",
   "Own the Woking South failure before anyone asks: a pre-registered "
   "transfer rule that did not survive contact, reported in full."],
  [("Isn't 5 of 12 just multiple testing?",
    "Possibly for any single window — the report says so and cites "
    "Liu & Shiraito. But the 24 comparisons were predefined, both arms "
    "agree at 31–90 days with CIs above zero, cumulative windows "
    "and local news repeat the pattern, and Haslemere reproduces the "
    "window ordering out of sample. The claim is deliberately "
    "conditional."),
   ("Why does news help others more than Reform itself?",
    "News moves party-level *levels*; Reform's baseline was already "
    "under-predicting in 2026, so the downward stance adjustment went the "
    "wrong way (t22 sign flip), while renormalisation and the corrected "
    "residual structure helped the other parties. Stage 2 learns from "
    "past residuals, not the target election's error."),
   ("Why report a blind test that failed?",
    "It was pre-registered, so it is reported; it is also informative: "
    "it bounds where the approach transfers (a single by-election with a "
    "landslide encoded in no channel the corpus covers).")])}
</section>""")

    # -- 5 interpretation -----------------------------------------------
    sections.append(f"""
<section id="s5"><h2>5&nbsp;&middot;&nbsp;Research interpretation</h2>
<p class="src">This section mirrors report &sect;5.3 ("Alternative
Explanations for the News Signal") and &sect;6.1&ndash;6.2: the left
column is what the frozen analysis established, the right column is the
&sect;5.3 diagnostic story, bullet for bullet.</p>
<div class="twocol">
<div><h3>Evidence (confirmatory / frozen)</h3><ul>
<li>News reduced MAE beyond a recalibrated no-news control in the v2
31&ndash;90-day window: combined +0.240 [0.078, 0.387], national +0.268
[0.109, 0.411] pp.</li>
<li>All confirmatory improvements occurred under v2; v1 produced
none.</li>
<li>91&ndash;180 days worsened both arms; seat calls never beat the
elect-nobody floor.</li></ul></div>
<div><h3>Interpretation (exploratory / post-unblinding)</h3><ul>
<li><strong>Primary: party identity.</strong> Party indicators alone
improve MAE by +0.8342 pp (vs +0.2404 for the frozen news
specification): the original baseline was under-specified, and party
identity accounts for the majority of the predictive improvement.</li>
<li><strong>News on top of party dummies is marginal in size</strong>
(+0.8342 &rarr; +0.8504 [0.4572, 1.2504]) but the news component is the
more consistent across windows: within-party tone agrees with the frozen
specification's direction in 5 of 6 non-overlapping windows (the sixth
is exactly zero), while the party dummies &mdash; window-invariant at
+0.8342 &mdash; agree in only 3 of 6.{prov_btn("identity")}</li>
<li><strong>Secondary: within-party centred tone</strong> (+0.2291
[0.1669, 0.2876]) &mdash; presented <em>not</em> as a separate
predictive gain but as evidence that the news signal is not merely a
proxy for party identity.</li>
<li><strong>The combined check was run:</strong> with party identity,
volume and centred tone in one specification, centred tone adds no
further out-of-sample value (&Delta;MAE &minus;0.1229 [&minus;0.1595,
&minus;0.0879]).</li>
<li>Volume alone +0.2247; volume+stance +0.3413 [0.2023, 0.4680]. On
per-window margins (not sign counts), stance leads volume in 5 of 6
non-overlapping windows with mean margin +0.0993 pp &mdash; but stance
and volume are strongly collinear (r&nbsp;=&nbsp;&minus;0.778,
r&sup2;&nbsp;&asymp;&nbsp;0.61 across the 19 covered fitting cells), so
do not overstate "stance beats volume".{prov_btn("margins")}</li>
<li>Incumbent-judgement framing +0.5718 pp, but only two windows had
enough training variation &mdash; exploratory only.</li></ul>
<p class="src">sources: report &sect;5.3&ndash;&sect;6.2;
news_features/identity_placebos_v1/ and stance_volume_margins_v1/
(committed exploratory artefacts); framing agreed at supervision
meeting, 14 Aug 2026, and now stated in report &sect;5.3 together with
the per-window margins (mean +0.0993) and the seven-content-feature
appendix table. Note: &sect;5.3 contains two different five-of-six
statements &mdash; stance-vs-volume margins, and the 5/6-vs-3/6
direction agreement with the frozen effect &mdash; keep them apart when
presenting.</p></div>
</div>
{combined_factorial_html()}
{tex_tabular_html(TABLES / "latex" / "a13_content_features.tex",
                  "The seven pre-declared content features, both testable "
                  "windows (report Appendix Table a13)",
                  "latex/a13_content_features.tex; underlying record: "
                  "news_features/placebo_specifications_v1/",
                  prov="a13feat")}
<p><strong>Agreed headline framing.</strong> Party identity explains most
of the predictive improvement; on top of it there is a smaller and
potentially more stable within-party news-tone signal that is not
explained by fixed party identity or by volume of coverage.</p>
<p><strong>Domain meaning.</strong> For local-election forecasting this
says: pre-election coverage contains real, timely information about a
realignment &mdash; but it complements rather than replaces electoral
history, its value peaks at 31&ndash;90 days (early enough to differ from
polls-eve wisdom, late enough to reflect the campaign), and much of what
"news" measures is <em>who is being covered how much</em>, with tone
adding a genuine but overlapping signal. Consistent with the mixed prior
literature (B&eacute;langer &amp; Soroka 2012 vs UMEDA 2023): both are
right, conditionally.</p>
{viva_box(
  ["Lead with the agreed framing: party identity is the primary finding "
   "(+0.8342, an under-specified baseline); within-party tone is the "
   "secondary signal whose job is to show news is not a proxy for party "
   "identity.",
   "Keep the two columns apart explicitly — examiners reward the "
   "discipline of not promoting exploratory results.",
   "If pressed on stance vs volume, concede the overlap first "
   "(r = −0.778), then point to the within-party CI excluding zero."],
  [("So is the mechanism just ‘Reform gets covered a lot’?",
    "Mostly party identity and volume, and I say so — party dummies "
    "alone beat the frozen news specification. The within-party centred "
    "tone result (+0.2291, CI excluding zero) is there to show the news "
    "signal is not solely a party-identity proxy, not to claim a "
    "separate gain; once party and volume are controlled, tone adds "
    "nothing further out of sample (−0.1229)."),
   ("Why report the frozen +0.2404 as the confirmatory headline if "
    "party dummies do better?",
    "Because only the news specification was frozen and pre-registered; "
    "party indicators were a post-unblinding diagnostic. The "
    "confirmatory claim and the interpretive story are kept separate "
    "deliberately."),
   ("Would you now use this operationally?",
    "As a complement: run the history baseline, add the news layer only "
    "in the 31–90-day window, and only where training cells cover "
    "the relevant parties. The MDE table (t23) says when the design can "
    "even detect an effect — that discipline transfers.")])}
</section>""")

    # -- 6 interactive demonstration ------------------------------------
    sections.append(f"""
<section id="s6"><h2>6&nbsp;&middot;&nbsp;Interactive demonstration</h2>
<p class="warnbox"><strong>Responsible-use notice.</strong> The models
estimate statistical associations. Nothing here establishes how voters
responded to news, and no scenario output is a real-world claim. Live
inference is deliberately not performed in this pack: it shows the
<em>committed, frozen</em> outputs (register section 17), so what you see
is exactly what was archived.</p>
<h3>6.1 Confirmatory-result explorer</h3>
<div class="explorer">
<label>version <select id="c-ver" onchange="confUpdate()">
<option value="v2">v2 (enriched training)</option>
<option value="v1">v1 (principal elections only)</option></select></label>
<label>news arm <select id="c-arm" onchange="confUpdate()">
<option>combined</option><option>national</option></select></label>
<label>window <select id="c-win" onchange="confUpdate()">
<option>180-91 days</option><option selected>90-31 days</option>
<option>30-15 days</option><option>14-8 days</option>
<option>7-4 days</option><option>final 72h</option></select></label>
<div class="out" id="c-out"></div>
<p class="src">data embedded verbatim from t04_confirmatory_v1.csv /
t05_confirmatory_v2.csv.{prov_btn("t05")}</p></div>
<h3>6.2 Synthetic what-if news scenarios on the frozen v2 model</h3>
<p>The design's final stage: clearly-labelled hypothetical news stories
are injected into the 2026 feature cells and the frozen enrichment model
re-predicts the election, so the sensitivity of the predictions to
<strong>tone, timing, target party and collection arm</strong> can be
read off. Outputs were computed once by the pipeline
(<code>src/news_modelling/synthetic_news_scenarios.py</code>) and
committed; the pack replays them.</p>
<p><strong>What a scenario is, mechanically.</strong> "Inject <em>n</em>
articles about party P with tone T into window W through arm A" changes
exactly the numbers those articles would have changed had they been
collected: the window's article total rises by <em>n</em>, P's article
and tone counts rise by <em>n</em>, and every party's share features are
recomputed under the enlarged denominator (an injected Reform story
dilutes everyone else's coverage share &mdash; how shares work, not a
modelling choice). The frozen ridge specification for (A,&nbsp;W) turns
the perturbed features into per-candidate adjustments, contests are
renormalised exactly as in the freeze, and the report shows what moved.
Before any scenario runs, every standardised coefficient is asserted
equal to the value recorded in the frozen protocol &mdash; a drifted
input fails loudly rather than producing quietly different what-ifs.
{prov_btn("t18", "code of the scenario engine")}</p>
<p class="warnbox"><strong>Boundary, stated in the code itself:</strong>
the issue axis ("a new story focused on crime") cannot flow through this
model &mdash; the frozen specifications carry volume and portrayal only,
because issue-level features never cleared the ten-cell reporting
threshold. That limit is recorded in the output rather than approximated
around.</p>
<div class="explorer">
<label>scenario preset <select id="s-preset" onchange="scenUpdate()">
{preset_opts}</select></label>
<div class="out" id="s-out"></div>
<p class="src">data embedded verbatim from t18_synthetic_scenarios.csv
(associational; register section 17).{prov_btn("t18")}</p></div>
<p>Reading the presets: tone flips the sign of the response
(favourable +1.00pp vs unfavourable &minus;2.00pp for the same Reform
story); timing changes magnitude and seat sensitivity (the same story is
worth &minus;2.00pp a month out but &minus;0.82pp with 8 seat flips in the
final 72h, where the cell holds only 4 real articles); a saturated cell
dampens response; the national arm reacts more strongly than local for
the same story.</p>
<h3>6.3 Live model demonstration (Streamlit)</h3>
<p>The live half of the demonstration: the repository's Streamlit app
takes <strong>inputs &mdash; party, tone, collection arm, number of
articles, pre-election window &mdash; and runs the frozen model on
them</strong>, through exactly the code shown in the provenance modal
above (<code>perturb_features</code> &rarr;
<code>fit_frozen_specification</code> &rarr; <code>run_scenario</code>).
Before any scenario runs it re-asserts every standardised coefficient
against the frozen protocol, so it cannot quietly serve an unfrozen
model. Launch:</p>
<p><code>PYTHONPATH=src .venv/bin/python -m streamlit run
app/news_app.py</code></p>
<p>{live_status}</p>
<p>The static pack and the live app split the job deliberately: the pack
carries the frozen evidence and its code trail; the app answers "what
does the model do with an input the examiner chooses" without touching
the evidence chain.</p>
{viva_box(
  ["Drive 6.1 yourself: start at v2/combined/90–31 (the headline), "
   "flip to v1 to show the same cell failing, then to 91–180 days "
   "to show you report the harm too.",
   "In 6.2, run the tone pair first — it is the cleanest visual that "
   "the model responds to stance direction, not just volume."],
  [("Why not let the examiner type in an arbitrary scenario?",
    "Two reasons: the demonstrator must stay outside the evidence chain "
    "(frozen outputs only, per the supervisor's separation requirement), "
    "and arbitrary inputs invite over-reading an associational model. "
    "The Streamlit app exists for controlled live runs against the "
    "verified frozen coefficients.")])}
</section>""")

    # -- 7 limitations ---------------------------------------------------
    sections.append(f"""
<section id="s7"><h2>7&nbsp;&middot;&nbsp;Limitations and responsible
use</h2>
<h3>Scope and data limitations</h3>
<ul>
<li><strong>Geography.</strong> Only 68 of 1,632 articles could be tied to
a single Surrey division, so features are election&ndash;party&ndash;window
level; division-level news prediction remains untested.</li>
<li><strong>Training variation.</strong> Issue and framing features had
four distinct election-level values &mdash; enough to fit, too few to
report confirmatorily; their positive results stay exploratory.</li>
<li><strong>Multiplicity.</strong> 24 confirmatory comparisons without
correction; individual positives may be chance, which is why the claim
rests on the convergent 31&ndash;90-day pattern.</li>
<li><strong>Training composition.</strong> Gains depend on the enriched
v2 sample and substantially on seven Reform cells (t09); the added
by-election cells have low individual reliability (0.2253 vs 0.9375).</li>
<li><strong>Transfer.</strong> Woking South refuted the pre-registered
transfer rule; Haslemere replicated only the window ordering. One county,
one election cycle: external validity is an open question.</li>
<li><strong>Sealed data.</strong> The May 2026 Warlingham by-election
remains sealed and unused.</li>
</ul>
<h3>What this work cannot do</h3>
<ul>
<li>No causal claims: it never establishes that coverage <em>changed</em>
votes, only that pre-election coverage carries predictive signal.</li>
<li>No voter-level inference; all quantities are party-within-election
aggregates.</li>
<li>Not a seat forecaster: no specification beat the elect-nobody
floor.</li>
<li>Not transferable as-is to other counties, national elections or other
media environments without new validation.</li>
<li>LLM labels are validated against a &kappa; gate, not ground truth of
meaning; excluded layers (expected impact, credit&ndash;blame) mark the
current reliability boundary.</li>
</ul>
{viva_box(
  ["Volunteer the limitations before being asked; each one is already "
   "documented in a frozen artefact, which is itself a strength.",
   "Distinguish limitation-of-evidence (multiplicity, transfer) from "
   "limitation-of-scope (geography, one county)."],
  [("What would you do with six more months?",
    "Broader local coverage and finer geography (the 68/1,632 problem), "
    "more comparable election–party cells so issue/framing can be "
    "tested confirmatorily, and replication in a second county; the MDE "
    "framework (t23) sets the sample sizes that would make those tests "
    "decisive.")])}
</section>""")

    # -- 8 exports -------------------------------------------------------
    export_rows = "".join(
        f"<tr><td><code>outputs/report_tables_v1/{esc(stem)}.csv</code></td>"
        f"<td>{esc(desc)}</td></tr>"
        for stem, desc in manifest["tables"].items())
    sha_rows = "".join(
        f"<tr><td>{esc(k)}</td><td><code>{esc(v[:16])}&hellip;</code></td>"
        f"</tr>" for k, v in manifest["input_sha256"].items())
    sections.append(f"""
<section id="s8"><h2>8&nbsp;&middot;&nbsp;Exports and provenance</h2>
<p>Everything shown above is a view of committed artefacts. The full
export set:</p>
{img("fig5_party_resolution.png", "Per-party design resolution (from the "
     "committed figure pack; further figures: fig3_corpus_windows.png, "
     "fig4_island_contrast.png, fig6_mechanism_vs_outcome.png).",
     prov="fig5", label="code behind the numbers on this figure")}
<div class="tablewrap"><table><thead><tr><th>artefact</th><th>contents</th>
</tr></thead><tbody>{export_rows}</tbody></table></div>
<p>LaTeX versions of the appendix tables live in
<code>outputs/report_tables_v1/latex/</code>; the report source in
<code>report/</code>.</p>
<h3>Integrity</h3>
<p><code>outputs/report_tables_v1/manifest.json</code> pins the sha256 of
every upstream input the table pack was built from:</p>
<div class="tablewrap"><table><thead><tr><th>input</th><th>sha256
(first 16)</th></tr></thead><tbody>{sha_rows}</tbody></table></div>
<h3>Regeneration</h3>
<ul>
<li>Table pack: <code>PYTHONPATH=src .venv/bin/python -m
news_modelling.build_report_tables</code></li>
<li>Figures: <code>PYTHONPATH=src .venv/bin/python -m
news_modelling.make_report_figures</code></li>
<li>This pack: <code>.venv/bin/python demo/build_viva_pack.py</code>
(build fails if any headline number drifts from the artefacts)</li>
<li>Tests: <code>.venv/bin/python -m pytest tests demo -q</code></li>
</ul>
<p class="src">Demonstrator separation: this pack lives in
<code>demo/</code>, is generated (git-ignored), reads frozen artefacts
only, and is not part of the work the reported results rest on.</p>
</section>""")

    # -- 9 code navigator ------------------------------------------------
    code = code_index(files)
    # No "<" may survive inside the inline <script> block: the HTML
    # tokenizer knows nothing about JSON string boundaries, so embedded
    # "</script>", "<script" or "<!--" sequences (this very file's source
    # contains all three) would derail it. The \\u003c escape is valid
    # JSON for "<" and neutral to JavaScript.
    code_json = json.dumps(code).replace("<", "\\u003c")
    n_code_lines = sum(e["s"].count("\n") + 1 for e in code)
    sections.append(f"""
<section id="s9"><h2>9&nbsp;&middot;&nbsp;Code navigator</h2>
<p>Every tracked Python file in <code>src/</code>, <code>app/</code>,
<code>tests/</code> and <code>demo/</code> &mdash; {len(code)} files,
{n_code_lines:,} lines &mdash; embedded verbatim at build time. Search by
file name, function/class name, or any text in the code; click a file to
read it with line numbers. This is the "show me the exact line" tool for
examiner questions; the <em>open full file</em> buttons inside every
provenance modal land here.</p>
<div class="explorer">
<input id="code-q" type="search" oninput="codeSearch()"
 placeholder="search: file, function or text — e.g. bootstrap, perturb_features, ridge"
 style="width:100%;font:inherit;padding:6px 10px;border:1px solid
 var(--line);border-radius:8px;background:var(--bg);color:var(--fg)">
<p class="src" id="code-count"></p>
<div id="code-list"></div>
</div>
<div id="code-view"></div>
{viva_box(
  ["If an examiner asks 'where is X computed', type the term here and "
   "open the file — do not paraphrase from memory.",
   "Rehearse the five files questions will hit most: unblind_2026.py, "
   "blinded_2026_predictions_v2.py, news_estimator.py, "
   "synthetic_news_scenarios.py, build_report_tables.py."],
  [("How do I know this listing matches the repository?",
    "It is generated from git ls-files at build time and the sources are "
    "embedded verbatim; the test suite spot-checks embedded excerpts "
    "against the working tree.")])}
</section>""")

    # -- viva run order (top) -------------------------------------------
    runorder = """
<section id="s0"><h2>The project as one chain</h2>
<p>Everything in this pack hangs off a single pipeline. Each step links
to the section that details it; presenting = walking this chain and
clicking into detail on demand.</p>
<ol class="spine">
<li><a href="#p-elections"><b>Election record</b></a> &mdash; 24 events,
343 contests, 1,992 candidate rows from official sources, validated
row by row. <span class="src">the ground truth</span></li>
<li><a href="#p-corpus"><b>News corpus</b></a> &mdash; collect and
screen: 2,666 candidate articles &rarr; 1,632 usable (v1); +627
by-election articles &rarr; 2,259 (v2). <span class="src">the raw
signal</span></li>
<li><a href="#p-stage1"><b>Stage 1: history-only baseline</b></a>
&mdash; LightGBM on 35 predictors; also produces 792 out-of-fold
residuals &mdash; Stage 2's training targets. <span class="src">2026:
MAE 4.514, seats 118-vs-30 wrong</span></li>
<li><a href="#p-llm"><b>LLM labels through a validation gate</b></a>
&mdash; issue / stance / framing per article; every layer must clear
&kappa; &ge; 0.60 or is excluded. <span class="src">stance
&kappa; = 0.848</span></li>
<li><a href="#p-signal"><b>Labels &rarr; two numbers per cell</b></a>
&mdash; article share (visibility) and net portrayal (tone direction):
the entire news signal. <span class="src">the features</span></li>
<li><a href="#p-stage2"><b>Stage 2: news layer on the residuals</b></a>
&mdash; per-window ridge on the two features; 11 cells (v1) &rarr; 45
cells (v2). <span class="src">the model under test</span></li>
<li><a href="#p-freeze"><b>Freeze</b></a> &mdash; 832 predictions per
specification written and hashed before any 2026 result was read.
<span class="src">sha256-sealed</span></li>
<li><a href="#p-unblind"><b>Unblind once: 24 comparisons</b></a>
&mdash; news vs recalibrated no-news control, contest-bootstrap CIs.
<span class="src">v2 31&ndash;90d: +0.240 and +0.268, both CIs &gt; 0;
v1: nothing</span></li>
<li><a href="#p-diagnose"><b>Diagnose the signal</b></a> &mdash; party
identity is the primary driver (+0.834); within-party tone is the
smaller, steadier component that proves news is not just a party label
(+0.229); Reform's sign flip explains who gains.
<span class="src">report &sect;5.3&ndash;5.4</span></li>
<li><a href="#p-transfer"><b>Stress-test out of sample</b></a> &mdash;
Woking South blind test refutes the transfer rule; Haslemere replays
the window pattern. <span class="src">honest failures</span></li>
<li><a href="#s7"><b>Limits</b></a> &mdash; what the design can
resolve (MDE), what it cannot claim, where it does not transfer.
<span class="src">the boundary</span></li>
</ol>
</section>
<section id="s0b"><h2>Suggested viva run order (&asymp;12 min)</h2>
<ol>
<li><strong>1 min</strong> &mdash; Section 1: question, one-sentence
design, the two headline cards.</li>
<li><strong>2 min</strong> &mdash; Section 2: study-design figure, corpus
funnel, one sentence on verifiability.</li>
<li><strong>3 min</strong> &mdash; Section 3: framework figure end-to-end;
&kappa; gate; the three blinding defences.</li>
<li><strong>3 min</strong> &mdash; Section 4: seat-totals figure (why
history fails), forest plot (v1 vs v2), then the Reform decomposition.</li>
<li><strong>1 min</strong> &mdash; Section 6: live-click the confirmatory
explorer and one scenario pair.</li>
<li><strong>2 min</strong> &mdash; Sections 5+7: evidence vs
interpretation, then volunteer two limitations.</li>
</ol>
<p>Navigation: sidebar links; every claim carries its artefact source
line. Open any <span style="color:var(--acc)">Viva guidance</span> box
for speaking notes and anticipated questions.</p>
</section>"""

    nav = """
<nav><h1>Viva pack &mdash; Context to Consequence</h1>
<a href="#s0">The chain</a>
<a href="#s0b">Run order</a>
<a href="#s1">1 &middot; Research overview</a>
<a href="#s2">2 &middot; Data and code</a>
<a href="#s3">3 &middot; Methodology</a>
<a href="#s4">4 &middot; Technical results</a>
<a href="#s5">5 &middot; Interpretation</a>
<a href="#s6">6 &middot; Interactive demo</a>
<a href="#s7">7 &middot; Limitations</a>
<a href="#s8">8 &middot; Exports</a>
<a href="#s9">9 &middot; Code navigator</a>
</nav>"""

    header = """
<header style="margin-bottom:26px">
<h1 style="margin-bottom:2px">Context to Consequence &mdash; AI-Driven News
Categorisation and Event Prediction</h1>
<p class="src">Viva demonstrator &middot; Shuhan Liu &middot; MSc ACSE,
Imperial College London &middot; 2026 Surrey local elections &middot;
generated from frozen artefacts; offline; no live inference.</p>
</header>"""

    prov_divs = "".join(
        f"<div class='provsrc' id='prov-{key}'>{provenance_html(key, manifest)}"
        f"</div>" for key in PROV)
    modal = ("<div id='modal' hidden><div id='modal-box'>"
             "<button id='modal-close'>close &times;</button>"
             "<h3 id='modal-title'></h3><div id='modal-body'></div>"
             "</div></div>")

    return ("<!-- generated by demo/build_viva_pack.py; do not edit -->\n"
            "<meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,"
            "initial-scale=1'>"
            "<title>Viva pack — Context to Consequence</title>"
            f"<style>{CSS}</style>"
            f"{nav}<main>{header}{runorder}{''.join(sections)}</main>"
            f"{prov_divs}{modal}"
            f"<script>var CONF={conf_json};var SCEN={scen_json};"
            f"var CODE={code_json};"
            f"{JS}</script>\n")


def main() -> None:
    html = build()
    OUT.write_text(html, encoding="utf-8")
    size = OUT.stat().st_size / 1e6
    print(f"wrote {OUT.relative_to(REPO)} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
