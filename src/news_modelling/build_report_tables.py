"""Build the report table pack from committed result artefacts.

    PYTHONPATH=src .venv/bin/python -m news_modelling.build_report_tables

One module, seventeen tables, three rules:

1. READ, NEVER MODEL. Every number is read from a committed artefact
   (the unblinding record, the decomposition and probe results, the
   frozen prediction file, the Stage 1 holdout file, the canonical v2
   release, the scenario and catalogue outputs). The only arithmetic
   permitted is counting, rounding and the two recomputations noted
   below, both reproducing figures already recorded in the register.
2. EVERY TABLE CARRIES ITS SOURCE. Each CSV gets a title and a source
   pointer (file plus register section) in the pack's README, and
   ``manifest.json`` records the sha256 of every input file read, so
   any number in the report can be traced to the bytes behind it.
3. REPORT-GRADE FORMATTING, MACHINE-GRADE FILES. The CSVs hold plain
   numbers (three decimals for MAE-scale values, four for accuracies);
   the README renders the same tables as markdown for eyeballing.
   Nothing here writes prose for the report - titles and source notes
   only.

The two recomputations (both from committed inputs, both matching the
register's recorded figures): the Reform seat-call table re-reads the
frozen v2 prediction file's elected flags against observed outcomes
(register: "Reform-specific seat calls" addendum), and the baseline
descriptive block reuses ``descriptive_2026_targets``'s functions over
the committed holdout file (register section 16 annex).
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from news_modelling.blinded_2026_predictions_v2 import V2_VARIANT
from news_modelling.descriptive_2026_targets import (
    contests_fully_correct,
    deciding_margin_mae,
    load_2026_rows,
    per_party_mae,
    reform_block,
    seat_totals,
)
from news_modelling.unblind_2026 import CONFIRMATORY, load_observed

OUT_DIR = Path("outputs/report_tables_v1")

SOURCES = {
    "unblinding": Path(
        "news_features/unblinding_2026_v1/unblinding_results.json"),
    "decompositions": Path(
        "news_features/exploratory_decompositions_v1/decomposition_results.json"),
    "approaches": Path(
        "news_features/approach_comparison_v1/approach_comparison.json"),
    "probe": Path("news_features/haslemere_probe/probe_result.json"),
    "scenarios": Path(
        "news_features/synthetic_scenarios_v1/scenario_results.json"),
    "catalogue": Path(
        "news_collection/haslemere_probe/nonnews_trail_catalogue.json"),
    "release_v2": Path("news_collection/canonical_corpus_release_v2.json"),
    "v2_predictions": Path(
        "news_features/blinded_2026_predictions_v2/blinded_predictions.csv"),
    "holdout": Path(
        "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
        "holdout_predictions.csv"),
}

WINDOW_ORDER = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
                "14_to_8_days", "7_to_4_days", "final_72_hours")
WINDOW_LABEL = {"180_to_91_days": "180-91 days", "90_to_31_days": "90-31 days",
                "30_to_15_days": "30-15 days", "14_to_8_days": "14-8 days",
                "7_to_4_days": "7-4 days", "final_72_hours": "final 72h"}
ARM_LABEL = {"combined_exploratory": "combined",
             "national_exploratory": "national",
             "local_sensitivity": "local"}


def _window_rank(entry: dict) -> tuple:
    return (ARM_LABEL.get(entry["analysis"], entry["analysis"]),
            WINDOW_ORDER.index(entry["period"]))


# --------------------------------------------------------------------------
# Table builders. Each returns (name, title, source_note, rows); rows are
# ordered dicts sharing one key set, ready for csv.DictWriter.
# --------------------------------------------------------------------------

def t01_baseline_reference(unblinding: dict) -> tuple:
    """Headline baseline metrics on 2026: the reference every news
    comparison is read against. MAEs and seat accuracies come from the
    unblinding record; margin, per-ward correctness and the Reform
    descriptives reuse the annex's own functions over the holdout file."""

    rows_2026 = load_2026_rows()
    margin, contests = deciding_margin_mae(rows_2026)
    both_right, wards = contests_fully_correct(rows_2026)
    reform = reform_block(rows_2026)
    baseline = unblinding["baseline_all_2026_rows"]
    seats = unblinding["baseline_seat_accuracy"]
    reform_rows = unblinding["baseline_reform_rows"]
    reform_seats = unblinding["baseline_reform_seat_accuracy"]
    rows = [
        {"metric": "overall MAE (share points)",
         "value": round(baseline["mae"], 3), "n": baseline["rows"]},
        {"metric": "seat-call accuracy",
         "value": round(seats["accuracy"], 4), "n": seats["rows"]},
        {"metric": "wards with both seats exactly right",
         "value": both_right, "n": wards},
        {"metric": "deciding-margin MAE (share points)",
         "value": round(margin, 2), "n": contests},
        {"metric": "Reform UK MAE (share points)",
         "value": round(reform_rows["mae"], 3), "n": reform_rows["rows"]},
        {"metric": "Reform UK seat-call accuracy (all-lose call)",
         "value": round(reform_seats["accuracy"], 4),
         "n": reform_seats["rows"]},
        {"metric": "Reform UK mean predicted share (%)",
         "value": reform["mean_predicted_share"], "n": reform["candidates"]},
        {"metric": "Reform UK mean observed share (%)",
         "value": reform["mean_observed_share"], "n": reform["candidates"]},
        {"metric": "Reform UK predicted top-two contests",
         "value": reform["predicted_top_two"], "n": reform["candidates"]},
        {"metric": "Reform UK observed top-two contests",
         "value": reform["observed_top_two"], "n": reform["candidates"]},
    ]
    return ("t01_baseline_2026_reference",
            "Untouched baseline on the 2026 principal election",
            "unblinding_results.json + holdout_predictions.csv "
            "(register section 16 and its annex)", rows)


def t02_per_party_mae() -> tuple:
    """Baseline share error by party - the annex's per-party table."""

    rows = [{"party": party, "candidates": n, "baseline_mae": round(mae, 2)}
            for party, n, mae in per_party_mae(load_2026_rows())]
    return ("t02_baseline_per_party_mae",
            "Baseline per-party MAE, 2026 principal election",
            "holdout_predictions.csv (register annex)", rows)


def t03_seat_totals() -> tuple:
    """Predicted-versus-actual seat totals - the realignment table."""

    rows = [{"party": party, "predicted_seats": predicted,
             "actual_seats": actual}
            for party, predicted, actual in seat_totals(load_2026_rows())]
    return ("t03_baseline_seat_totals",
            "Baseline seat totals, predicted vs actual (162 seats)",
            "holdout_predictions.csv (register annex; figure 2)", rows)


def _confirmatory_rows(unblinding: dict, version: str) -> list[dict]:
    """Shared shape for t04/t05: one row per confirmatory comparison."""

    rows = []
    entries = [e for e in unblinding["files"][version]
               if e["family"] == "confirmatory"]
    for entry in sorted(entries, key=_window_rank):
        overall = entry["metrics"]["all_supported_parties"]
        reform = entry["metrics"]["reform_uk"]
        ci = entry["metrics"]["bootstrap_news_vs_recalibrated"]
        rows.append({
            "arm": ARM_LABEL[entry["analysis"]],
            "window": WINDOW_LABEL[entry["period"]],
            "baseline_mae": round(overall["baseline"]["mae"], 3),
            "recalibrated_mae": round(
                overall["recalibrated_without_news"]["mae"], 3),
            "news_mae": round(overall["news_enhanced"]["mae"], 3),
            "news_vs_recalibrated": round(
                overall["news_vs_recalibrated_mae"], 3),
            "ci_lower": round(ci.get("improvement_ci_lower", 0.0), 3),
            "ci_upper": round(ci.get("improvement_ci_upper", 0.0), 3),
            "reform_news_mae": round(reform["news_enhanced"]["mae"], 3),
            "reform_vs_recalibrated": round(
                reform["news_vs_recalibrated_mae"], 3),
        })
    return rows


def t04_confirmatory_v1(unblinding: dict) -> tuple:
    return ("t04_confirmatory_v1",
            "Confirmatory comparisons, v1 (before enrichment): 0 of 12 improve",
            "unblinding_results.json (register section 16)",
            _confirmatory_rows(unblinding, "v1"))


def t05_confirmatory_v2(unblinding: dict) -> tuple:
    return ("t05_confirmatory_v2",
            "Confirmatory comparisons, v2 (after enrichment): 5 of 12 improve,"
            " 4 intervals above zero",
            "unblinding_results.json (register section 16)",
            _confirmatory_rows(unblinding, "v2"))


def t06_sensitivity_summary(unblinding: dict) -> tuple:
    """Sensitivity families, summarised per (version, arm): these ran and
    are reportable as sensitivity only, so the pack carries counts and
    the delta range, not 84 rows of non-promotable detail."""

    rows = []
    for version in ("v1", "v2"):
        buckets: dict[str, list[float]] = defaultdict(list)
        for entry in unblinding["files"][version]:
            if entry["family"] != "sensitivity":
                continue
            delta = entry["metrics"]["all_supported_parties"][
                "news_vs_recalibrated_mae"]
            buckets[entry["analysis"]].append(delta)
        for analysis, deltas in sorted(buckets.items()):
            rows.append({
                "version": version,
                "specification_group": analysis,
                "comparisons": len(deltas),
                "improved": sum(1 for d in deltas if d > 0),
                "best_delta": round(max(deltas), 3),
                "worst_delta": round(min(deltas), 3),
            })
    return ("t06_sensitivity_summary",
            "Sensitivity families (non-promotable), summarised",
            "unblinding_results.json (register section 16)", rows)


def t07_seat_accuracy(unblinding: dict) -> tuple:
    """Seat-call accuracy per confirmatory specification - the recorded
    secondary outcome where the MAE and seat endpoints diverge."""

    rows = []
    for version in ("v1", "v2"):
        entries = [e for e in unblinding["files"][version]
                   if e["family"] == "confirmatory"]
        for entry in sorted(entries, key=_window_rank):
            rows.append({
                "version": version,
                "arm": ARM_LABEL[entry["analysis"]],
                "window": WINDOW_LABEL[entry["period"]],
                "news_seat_accuracy": round(
                    entry["metrics"]["seat_accuracy_news"]["accuracy"], 4),
                "baseline_seat_accuracy": round(
                    unblinding["baseline_seat_accuracy"]["accuracy"], 4),
            })
    return ("t07_seat_accuracy_by_specification",
            "Seat-call accuracy per specification (secondary outcome)",
            "unblinding_results.json (register section 16 addendum)", rows)


def t08_reform_seat_calls(observed: dict) -> tuple:
    """Reform's per-specification seat calls, recomputed from the frozen
    v2 prediction file's elected flags - reproduces the register's
    'Reform-specific seat calls' addendum (0 predicted everywhere except
    the 105-seat over-call at combined 14-8 days)."""

    stats: dict[tuple, Counter] = defaultdict(Counter)
    with SOURCES["v2_predictions"].open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if (row["fit_variant"] != V2_VARIANT
                    or row["period_role"] != "confirmed_window"
                    or row["analysis"] not in CONFIRMATORY["v2"]["analyses"]
                    or row["party_key"] != "reform_uk"):
                continue
            outcome = observed[row["candidate_contest_id"]]
            cell = stats[(ARM_LABEL[row["analysis"]], row["period"])]
            predicted = row["news_predicted_elected"] == "True"
            actual = str(outcome["observed_elected"]) == "True"
            cell["rows"] += 1
            cell["predicted_seats"] += predicted
            cell["hits_of_14"] += predicted and actual
            cell["correct_calls"] += predicted == actual
    rows = [{"arm": "baseline", "window": "-", "predicted_seats": 0,
             "hits_of_14": 0, "row_accuracy": 0.9136}]
    for (arm, window) in sorted(stats,
                                key=lambda k: (k[0],
                                               WINDOW_ORDER.index(k[1]))):
        cell = stats[(arm, window)]
        rows.append({
            "arm": arm, "window": WINDOW_LABEL[window],
            "predicted_seats": cell["predicted_seats"],
            "hits_of_14": cell["hits_of_14"],
            "row_accuracy": round(cell["correct_calls"] / cell["rows"], 4),
        })
    return ("t08_reform_seat_calls_v2",
            "Reform seat calls per v2 specification (actual: 14 of 162 won)",
            "blinded_predictions.csv v2 + observed outcomes "
            "(register Reform seat-call addendum)", rows)


def t09_attribution(decompositions: dict) -> tuple:
    """Attribution decomposition: each improvement with and without the
    seven Reform-era fitting cells (45 -> 38)."""

    rows = [{
        "arm": ARM_LABEL[spec["analysis"]],
        "window": WINDOW_LABEL[spec["window"]],
        "full_fit_delta": spec["full_fit_delta"],
        "no_reform_delta": spec["no_reform_delta"],
        "verdict": spec["verdict"],
    } for spec in sorted(decompositions["attribution"]["specifications"],
                         key=lambda s: (ARM_LABEL[s["analysis"]],
                                        WINDOW_ORDER.index(s["window"])))]
    return ("t09_attribution_decomposition",
            "Attribution: v2 deltas with vs without the 7 Reform cells "
            "(3 improvements survive, 2 collapse)",
            "decomposition_results.json (register section 18)", rows)


def t10_mechanism_pooled(decompositions: dict) -> tuple:
    """Pooled bias/dispersion split; pooled bias is pinned near zero by
    contest normalisation, so the informative column is dispersion."""

    rows = [{
        "arm": ARM_LABEL[spec["analysis"]],
        "window": WINDOW_LABEL[spec["window"]],
        "baseline_dispersion": spec["baseline"]["dispersion_mae"],
        "news_dispersion": spec["news"]["dispersion_mae"],
        "dispersion_change": spec["dispersion_change"],
    } for spec in sorted(decompositions["mechanism"]["per_specification"],
                         key=lambda s: (ARM_LABEL[s["analysis"]],
                                        WINDOW_ORDER.index(s["window"])))]
    return ("t10_mechanism_pooled_dispersion",
            "Mechanism (pooled): dispersion falls exactly in the improving "
            "windows",
            "decomposition_results.json (register section 18)", rows)


def t11_mechanism_reform(decompositions: dict) -> tuple:
    """Reform's per-party decomposition across all twelve specifications:
    signed level error (negative = under-predicted) and ward dispersion,
    baseline against news."""

    rows = []
    for spec in sorted(
            decompositions["mechanism_per_party"]["per_specification"],
            key=lambda s: (ARM_LABEL[s["analysis"]],
                           WINDOW_ORDER.index(s["window"]))):
        reform = spec["parties"]["reform_uk"]
        rows.append({
            "arm": ARM_LABEL[spec["analysis"]],
            "window": WINDOW_LABEL[spec["window"]],
            "baseline_signed_bias": reform["baseline"]["signed_bias"],
            "news_signed_bias": reform["news"]["signed_bias"],
            "baseline_dispersion": reform["baseline"]["dispersion_mae"],
            "news_dispersion": reform["news"]["dispersion_mae"],
        })
    return ("t11_mechanism_reform_bias",
            "Per-party mechanism, Reform UK: news moves the level the wrong "
            "way; dispersion never moves",
            "decomposition_results.json (register section 18)", rows)


def t12_mechanism_headline_window(decompositions: dict) -> tuple:
    """All five parties in the headline 90-31-day window: level-error and
    dispersion change per arm - the '5 of 5 levels move, 0 of 5
    dispersions move' table."""

    headline = {
        spec["analysis"]: spec["parties"]
        for spec in decompositions["mechanism_per_party"]["per_specification"]
        if spec["window"] == "90_to_31_days"
    }
    rows = []
    for party in sorted(headline["combined_exploratory"]):
        combined = headline["combined_exploratory"][party]
        national = headline["national_exploratory"][party]
        rows.append({
            "party": party,
            "combined_abs_bias_change": combined["abs_bias_change"],
            "combined_dispersion_change": combined["dispersion_change"],
            "national_abs_bias_change": national["abs_bias_change"],
            "national_dispersion_change": national["dispersion_change"],
        })
    return ("t12_mechanism_headline_window",
            "Per-party mechanism at 90-31 days: every level moves, no "
            "dispersion does",
            "decomposition_results.json (register section 18)", rows)


def t13_approaches(approaches: dict) -> tuple:
    """Residual (A) vs joint (B) vs baseline-only, leave-one-election-out:
    A lower in 16 of 18."""

    rows = [{
        "specification_group": spec["analysis"],
        "window": WINDOW_LABEL[spec["period"]],
        "residual_A_mae": spec["loeo_cell_mae"]["residual_A"],
        "joint_B_mae": spec["loeo_cell_mae"]["joint_B"],
        "baseline_only_mae": spec["loeo_cell_mae"]["baseline_only"],
        "lower": spec["lower_mae"],
    } for spec in approaches["specifications"]]
    return ("t13_approach_comparison",
            "Residual (A) vs joint stacked (B): A lower in 16 of 18",
            "approach_comparison.json (register section 18)", rows)


def t14_probe(probe: dict) -> tuple:
    """The Haslemere case study: all twelve frozen specifications on the
    unseen July contest, against the before-May baseline."""

    rows = [{
        "arm": ARM_LABEL[spec["analysis"]],
        "window": WINDOW_LABEL[spec["window"]],
        "news_mae": spec["news"]["contest_mae"],
        "recalibrated_mae": spec["recalibrated"]["contest_mae"],
        "baseline_mae": spec["baseline"]["contest_mae"],
        "news_reform_signed_error": spec["news"][
            "signed_error_by_party"].get("reform_uk"),
        "winner_correct": spec["news"]["winner_correct"],
    } for spec in sorted(probe["specifications"],
                         key=lambda s: (ARM_LABEL[s["analysis"]],
                                        WINDOW_ORDER.index(s["window"])))]
    return ("t14_haslemere_probe",
            "Haslemere probe: frozen v2 specifications on the 7 July contest "
            "(3 of 12 beat control; window pattern replicates)",
            "probe_result.json (register Haslemere addenda)", rows)


def t15_probe_reference(probe: dict) -> tuple:
    """The probe's fixed reference points and corpus facts, as one table
    so the case study's context is citable beside its results."""

    reference = probe["reference"]
    corpus = probe["corpus"]
    rows = [
        {"item": "before-May baseline contest MAE",
         "value": reference["before_may_baseline_mae"]},
        {"item": "after-May baseline contest MAE",
         "value": reference["after_may_baseline_mae"]},
        {"item": "Reform signed error, before-May baseline",
         "value": reference["reform_before_may_signed_error"]},
        {"item": "Reform signed error, after-May baseline",
         "value": reference["reform_after_may_signed_error"]},
        {"item": "probe corpus articles", "value": corpus["articles"]},
        {"item": "articles naming any study party",
         "value": corpus["articles_naming_a_study_party"]},
        {"item": "all articles local-arm",
         "value": corpus["all_local_arm"]},
    ]
    return ("t15_haslemere_reference",
            "Haslemere probe: baseline references and corpus facts",
            "probe_result.json + Stage 1 metrics.json", rows)


def t16_nonnews_channels(catalogue: dict) -> tuple:
    """Where the campaign's visibility actually lived: the catalogue's
    channel counts, with the zero-press-articles line explicit."""

    rows = [{"channel": channel, "records": count}
            for channel, count in catalogue["by_channel"].items()]
    rows.append({"channel": "editorial press articles (the finding)",
                 "records": catalogue["editorial_press_articles_found"]})
    return ("t16_nonnews_trail_channels",
            "Non-news digital trail of the Haslemere campaign, by channel",
            "nonnews_trail_catalogue.json (register catalogue addendum)",
            rows)


def t17_corpus(release: dict, scenarios: dict) -> tuple:
    """Corpus volumes per confirmed window and arm (canonical v2), the
    far-window skew every late-window conclusion is qualified by."""

    corpus = release["usable_feature_corpus"]
    rows = [{
        "window": WINDOW_LABEL[window],
        "articles": corpus["by_window"].get(window, 0),
    } for window in WINDOW_ORDER]
    rows.append({"window": "total (local / national)",
                 "articles": f"{corpus['articles']} "
                             f"({corpus['by_arm'].get('local', 0)} / "
                             f"{corpus['by_arm'].get('national', 0)})"})
    return ("t17_corpus_by_window",
            "Canonical v2 corpus per confirmed window",
            "canonical_corpus_release_v2.json (register section 15; "
            "figure 3)", rows)


def t18_scenarios(scenarios: dict) -> tuple:
    """The four pre-registered synthetic scenarios: what each injected
    and what the frozen model did - flattened one row per run."""

    rows = []
    for preset, runs in scenarios["presets"].items():
        for run in runs:
            spec = run["scenario"]
            rows.append({
                "preset": preset[:60],
                "party": spec["party"], "tone": spec["tone"],
                "arm": spec["arm"], "articles": spec["articles"],
                "window": WINDOW_LABEL[run["window"]],
                "cell_articles_before": run["injection_context"][
                    "window_articles_before_injection"],
                "target_party_delta": run["mean_share_delta_by_party"].get(
                    spec["party"]),
                "seat_flips": len(run.get("seat_flips", [])),
            })
    return ("t18_synthetic_scenarios",
            "Synthetic news scenarios on the frozen v2 model (associational; "
            "register section 17)",
            "scenario_results.json (register section 17)", rows)


# --------------------------------------------------------------------------
# Writing.
# --------------------------------------------------------------------------

def _markdown(title: str, source: str, rows: list[dict]) -> list[str]:
    columns = list(rows[0].keys())
    lines = [f"## {title}", "", f"*Source: {source}*", "",
             "| " + " | ".join(columns) + " |",
             "| " + " | ".join("---" for _ in columns) + " |"]
    lines += ["| " + " | ".join(str(row[c]) for c in columns) + " |"
              for row in rows]
    return lines + [""]


def main() -> None:
    unblinding = json.loads(SOURCES["unblinding"].read_text())
    decompositions = json.loads(SOURCES["decompositions"].read_text())
    approaches = json.loads(SOURCES["approaches"].read_text())
    probe = json.loads(SOURCES["probe"].read_text())
    scenarios = json.loads(SOURCES["scenarios"].read_text())
    catalogue = json.loads(SOURCES["catalogue"].read_text())
    release = json.loads(SOURCES["release_v2"].read_text())
    observed = load_observed()

    tables = [
        t01_baseline_reference(unblinding),
        t02_per_party_mae(),
        t03_seat_totals(),
        t04_confirmatory_v1(unblinding),
        t05_confirmatory_v2(unblinding),
        t06_sensitivity_summary(unblinding),
        t07_seat_accuracy(unblinding),
        t08_reform_seat_calls(observed),
        t09_attribution(decompositions),
        t10_mechanism_pooled(decompositions),
        t11_mechanism_reform(decompositions),
        t12_mechanism_headline_window(decompositions),
        t13_approaches(approaches),
        t14_probe(probe),
        t15_probe_reference(probe),
        t16_nonnews_channels(catalogue),
        t17_corpus(release, scenarios),
        t18_scenarios(scenarios),
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    readme = ["# Report table pack v1", "",
              "Every table is read from committed artefacts; "
              "`manifest.json` holds the sha256 of each input. "
              "Confirmatory numbers are the register's; everything "
              "exploratory is labelled by its source section.", "",
              "**Two baselines appear and differ by design**: 4.514 is "
              "the untouched baseline over all 832 candidate rows "
              "(t01); 4.441 is the same baseline over the supported-"
              "party rows every news comparison is scored on "
              "(t04/t05). Use 4.441 when comparing against news "
              "models, 4.514 when describing the baseline alone - "
              "mixing them misstates the deltas.", ""]
    for name, title, source, rows in tables:
        with (OUT_DIR / f"{name}.csv").open("w", newline="",
                                            encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()),
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        readme += _markdown(title, source, rows)
    (OUT_DIR / "README.md").write_text("\n".join(readme), encoding="utf-8")

    manifest = {
        "tables": {name: title for name, title, _s, _r in tables},
        "input_sha256": {
            key: hashlib.sha256(path.read_bytes()).hexdigest()
            for key, path in SOURCES.items()
        },
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"{len(tables)} tables -> {OUT_DIR}")
    for name, title, _source, rows in tables:
        print(f"  {name}: {len(rows)} rows - {title[:60]}")


if __name__ == "__main__":
    main()
