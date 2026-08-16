"""Emit the report's appendix tables as LaTeX, from the committed table pack.

    PYTHONPATH=src .venv/bin/python -m news_modelling.report_appendix_tables

Every table body is derived from an already-committed artefact - the
``outputs/report_tables_v1`` pack (whose ``manifest.json`` hashes its own
inputs), the evidence register's LLM-validation table, and the shipped
Stage 1 bundle's feature schema. The module formats; it computes nothing
new, so any number in the appendix can be traced back through the pack's
README to its register section. Output is one ``.tex`` file per table
under ``outputs/report_tables_v1/latex/``, each containing a bare
``tabular`` environment (booktabs rules) for the report to ``\\input``
inside its own ``table`` float with its own caption.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

PACK = Path("outputs/report_tables_v1")
REGISTER = Path("news_features/PRODUCTION_NEWS_EVIDENCE_REGISTER.md")
SCHEMA = Path(
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "feature_schema.json")
OUT = PACK / "latex"


def _escape(text: str) -> str:
    return (text.replace("\\", r"\textbackslash{}").replace("&", r"\&")
            .replace("%", r"\%").replace("#", r"\#").replace("_", r"\_"))


def _read(name: str) -> list[dict[str, str]]:
    with (PACK / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write(name: str, colspec: str, header: list[str],
           rows: list[list[str]]) -> None:
    lines = [f"\\begin{{tabular}}{{{colspec}}}", "\\toprule",
             " & ".join(header) + r" \\", "\\midrule"]
    lines += [" & ".join(row) + r" \\" for row in rows]
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    (OUT / name).write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT / name)


WINDOW_TEXT = {"180-91 days": "91--180 days", "90-31 days": "31--90 days",
               "30-15 days": "15--30 days", "14-8 days": "8--14 days",
               "7-4 days": "4--7 days", "final 72h": "1--3 days"}


def _window(name: str) -> str:
    return WINDOW_TEXT.get(name, _escape(name))


def _ci(row: dict[str, str]) -> str:
    return f"[{float(row['ci_lower']):+.3f}, {float(row['ci_upper']):+.3f}]"


def confirmatory(version: str, source: str, name: str) -> None:
    rows = []
    for row in _read(source):
        rows.append([
            _escape(row["arm"]), _window(row["window"]),
            f"{float(row['recalibrated_mae']):.3f}",
            f"{float(row['news_mae']):.3f}",
            f"{float(row['news_vs_recalibrated']):+.3f}", _ci(row),
            f"{float(row['reform_vs_recalibrated']):+.3f}",
        ])
    _write(name, "llrrrcr",
           ["arm", "window", "control MAE", "news MAE",
            r"$\Delta$MAE", r"95\% CI", r"Reform $\Delta$"], rows)


UNBLINDING = Path("news_features/unblinding_2026_v1/unblinding_results.json")


def sensitivity_summary() -> None:
    """Sensitivity families split by fitting variant.

    Same frozen unblinding record as the pack's t06, regrouped so the
    2017-only replication is visible as its own rows instead of being
    pooled into the v1 family totals.
    """
    family_names = {"combined_exploratory": "combined news",
                    "national_exploratory": "national news",
                    "local_sensitivity": "local news"}
    fit_names = {"fit_2017_only": "2017 only",
                 "pooled_2017_2021": "2017 + 2021",
                 "pooled_2017_2021_byelections": "2017 + 2021 + by-elections"}
    data = json.loads(UNBLINDING.read_text(encoding="utf-8"))
    groups: dict[tuple, list[float]] = {}
    for version in ("v1", "v2"):
        for entry in data["files"][version]:
            if entry.get("family") == "confirmatory":
                continue
            delta = entry["metrics"]["all_supported_parties"][
                "news_vs_recalibrated_mae"]
            key = (version, entry["fit_variant"], entry["analysis"],
                   entry["period_role"])
            groups.setdefault(key, []).append(delta)
    role_names = {"confirmed_window": "confirmed",
                  "cumulative_sensitivity": "cumulative"}
    rows = []
    for (version, fit, family, role), deltas in sorted(groups.items()):
        rows.append([
            version, fit_names[fit], family_names[family], role_names[role],
            str(len(deltas)), str(sum(1 for d in deltas if d > 0)),
            f"{max(deltas):+.3f}", f"{min(deltas):+.3f}",
        ])
    assert sum(int(r[4]) for r in rows) == 84
    _write("a3_sensitivity_summary.tex", "llllrrrr",
           ["version", "fitted on", "news arm", "windows", "n",
            "improved", r"best $\Delta$", r"worst $\Delta$"], rows)


def seat_accuracy() -> None:
    rows = []
    for row in _read("t07_seat_accuracy_by_specification.csv"):
        if row["version"] != "v2":
            continue
        delta = row["news_vs_recalibrated_control"]
        rows.append([
            _escape(row["arm"]), _window(row["window"]),
            f"{float(row['news_seat_accuracy']):.4f}",
            f"{float(delta):+.4f}" if delta not in ("", "None") else "--",
            "yes" if row["beats_elect_nobody_floor"] == "True" else "no",
        ])
    _write("a4_seat_accuracy_v2.tex", "llrrc",
           ["arm", "window", "seat-call accuracy (news)",
            "vs control", r"beats 0.8053 floor"], rows)


def llm_validation() -> None:
    """Report-facing restatement of the register's section-4 table.

    The register records its evidence in internal shorthand ("n=55",
    "both arms", "frozen kappa"). The appendix restates the same facts
    in plain wording; every kappa value emitted here is asserted to
    appear verbatim in the register section, so the two cannot drift.
    The deterministic Reform-mention pattern is omitted - it is not an
    LLM extraction layer.
    """
    section = REGISTER.read_text(encoding="utf-8")
    match = re.search(r"## 4\. LLM extraction.*?\n\n## 5\.", section,
                      flags=re.S)
    assert match, "register section 4 not found"
    register_text = match.group(0)
    rows = [
        ("Issue classification",
         "$\\kappa$ = 0.742 between the two models; 0.616 against human "
         "labels (Sonnet, 53 articles)",
         "passed; run with Sonnet 5"),
        ("Stance (revised three-level)",
         "$\\kappa$ = 0.848 between the two models (92 articles); 0.741 "
         "(Haiku) and 0.736 (Sonnet) against human labels (71 articles)",
         "passed; run with Haiku 4.5"),
        ("Framing: incumbent judgement",
         "$\\kappa$ = 0.705 between the two models",
         "passed, limited evidence"),
        ("Framing: local impact",
         "$\\kappa$ = 0.635 between the two models",
         "passed, limited evidence"),
        ("Framing: challenger emergence and voter discontent",
         "only 2--6 and 4--5 positive articles among the 55 validation "
         "articles: too few to measure agreement",
         "not assessable; exploratory use only"),
        ("Expected impact",
         "$\\kappa$ = 0.598 for both models after redesign (60 articles)",
         "excluded, below 0.60"),
        ("Credit--blame",
         "$\\kappa$ = 0.521 / 0.516 against human labels (57 articles); "
         "a redesign did not improve it",
         "excluded"),
    ]
    for _, evidence, _ in rows:
        for value in re.findall(r"0\.\d{3}", evidence):
            assert value in register_text, (
                f"{value} not found in register section 4")
    _write("a5_llm_validation.tex",
           r"p{0.26\linewidth}p{0.42\linewidth}p{0.23\linewidth}",
           ["extraction layer", "validation evidence", "decision"],
           [list(r) for r in rows])


def approach_comparison() -> None:
    """Residual (A) vs joint (B) design, restated in plain wording."""
    arm_names = {"combined_exploratory": "combined",
                 "national_exploratory": "national",
                 "local_sensitivity": "local"}
    rows = []
    for row in _read("t13_approach_comparison.csv"):
        rows.append([
            arm_names[row["specification_group"]], _window(row["window"]),
            f"{float(row['residual_A_mae']):.3f}",
            f"{float(row['joint_B_mae']):.3f}",
            f"{float(row['baseline_only_mae']):.3f}",
            "residual" if row["lower"] == "A" else "joint",
        ])
    _write("a8_approach_comparison.tex", "llrrrc",
           ["news arm", "window", "residual design MAE",
            "joint design MAE", "baseline-only MAE", "better design"],
           rows)


def woking_south() -> None:
    rows = []
    for row in _read("t20_woking_south_blind_test.csv"):
        rows.append([
            _window(row["window"]), _escape(row["arm"]),
            "yes" if row["combination_pick"] == "True" else "",
            f"{float(row['news_mae']):.3f}",
            f"{float(row['news_vs_baseline']):+.3f}",
            f"{float(row['reform_signed_error']):+.2f}",
        ])
    _write("a6_woking_south_blind.tex", "llcrrr",
           ["window", "arm", "pick", "news MAE",
            r"$\Delta$ vs baseline", "Reform signed error"], rows)


def haslemere_probe() -> None:
    """The frozen v2 specifications replayed on the July 2026 by-election."""
    rows = []
    for row in _read("t14_haslemere_probe.csv"):
        news = float(row["news_mae"])
        control = float(row["recalibrated_mae"])
        rows.append([
            _escape(row["arm"]), _window(row["window"]),
            f"{news:.3f}", f"{control:.3f}", f"{control - news:+.3f}",
            f"{float(row['news_reform_signed_error']):+.2f}",
        ])
    _write("a9_haslemere_probe.tex", "llrrrr",
           ["arm", "window", "news MAE", "control MAE",
            r"$\Delta$ vs control", "Reform signed error"], rows)


def blind_tests() -> None:
    """Both blind tests side by side, one row per specification.

    Rows are the 18 arm-window specifications of the Woking South
    protocol; the Haslemere probe replayed only the two confirmatory
    arms, so its cells are dashed for the local arm. The two tests score
    against different constant references (Woking South: the no-news
    baseline, 10.085; Haslemere: the recalibrated control, 4.491), which
    the caption states instead of a column. A starred arm marks the
    combination the pre-registered rule picked.
    """
    ws = {(r["window"], r["arm"]): r
          for r in _read("t20_woking_south_blind_test.csv")}
    has = {(r["window"], r["arm"]): r
           for r in _read("t14_haslemere_probe.csv")}
    window_order = ["180-91 days", "90-31 days", "30-15 days",
                    "14-8 days", "7-4 days", "final 72h"]
    rows = []
    for window in window_order:
        for arm in ("combined", "local", "national"):
            w = ws[(window, arm)]
            arm_label = _escape(arm)
            if w["combination_pick"] == "True":
                arm_label += "$^{*}$"
            row = [_window(window), arm_label,
                   f"{float(w['news_mae']):.3f}",
                   f"{float(w['news_vs_baseline']):+.3f}"]
            h = has.get((window, arm))
            if h:
                control = float(h["recalibrated_mae"])
                news = float(h["news_mae"])
                row += [f"{news:.3f}", f"{control - news:+.3f}"]
            else:
                row += ["--", "--"]
            rows.append(row)
    lines = ["\\begin{tabular}{llrrrr}", "\\toprule",
             " &  & \\multicolumn{2}{c}{Woking South} & "
             "\\multicolumn{2}{c}{Haslemere} \\\\",
             "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}",
             "window & arm & news MAE & $\\Delta$ & news MAE & "
             "$\\Delta$ \\\\", "\\midrule"]
    lines += [" & ".join(r) + " \\\\" for r in rows]
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    (OUT / "a10_blind_tests.tex").write_text("\n".join(lines),
                                             encoding="utf-8")
    print("wrote", OUT / "a10_blind_tests.tex")


def mde_summary() -> None:
    rows = []
    for row in _read("t23_mde_summary.csv"):
        if row["scope"] not in ("overall MAE delta", "Reform MAE delta",
                                "Reform-vs-group contrast"):
            continue
        rows.append([
            _escape(row["island"]), _escape(row["scope"]),
            row["estimable"], f"{float(row['median_mde80']):.3f}",
            f"{float(row['min_mde80']):.3f}",
            f"{float(row['max_mde80']):.3f}",
        ])
    _write("a7_mde_summary.tex", "llrrrr",
           ["evaluation island", "scope", "estimable",
            "median MDE80", "min", "max"], rows)


PREDICTOR_GLOSSES = {
    "analysis_number_of_seats": "seats contested in the area",
    "analysis_previous_turnout": "turnout at the previous comparable election",
    "area_parties_in_previous_contest":
        "parties standing in the area's previous contest",
    "authority": "council holding the election",
    "candidate_count_in_contest": "candidates standing in the contest",
    "candidate_previously_stood": "candidate stood in an earlier election",
    "contest_structure": "single- or two-member contest",
    "election_date": "polling date",
    "election_type": "scheduled election or by-election",
    "election_year": "election year",
    "first_appearance_of_party_in_area":
        "party standing in this area for the first time",
    "geographic_reference_eligibility":
        "area has an approved exact-boundary historical reference",
    "historical_predictor_availability":
        "lagged predictors exist for this row",
    "incumbent_candidate_yes_no": "candidate holds the seat",
    "incumbent_party_yes_no": "party holds the seat",
    "is_reform_uk": "Reform UK indicator",
    "is_ukip": "UKIP indicator",
    "party_candidate_count_in_contest":
        "candidates the party fields in the contest",
    "party_category": "established, emerging, local or independent",
    "party_contest_rate_previous":
        "share of areas the party contested previously",
    "party_contests_fought_previous":
        "contests the party fought at the previous election",
    "party_count_in_contest": "parties standing in the contest",
    "party_county_strength_previous":
        "party's county-wide vote share at the previous election",
    "party_county_strength_trend":
        "change in county-wide vote share between elections",
    "party_previously_contested": "party stood in this area before",
    "party_was_previous_winner": "party won this area last time",
    "previous_electorate": "registered electors at the previous election",
    "previous_party_vote_share":
        "party's vote share in this area last time",
    "previous_winning_party": "party that won this area last time",
    "reform_x_party_contest_rate_previous":
        "Reform indicator x previous contest rate",
    "reform_x_party_county_strength_previous":
        "Reform indicator x previous county strength",
    "reform_x_party_county_strength_trend":
        "Reform indicator x county strength trend",
    "reform_x_previous_party_vote_share":
        "Reform indicator x previous area vote share",
    "standard_party_name": "standardised party label",
    "years_since_previous_comparable_election":
        "years since the previous comparable election",
}


def predictors() -> None:
    """One row per predictor with a plain-English gloss.

    The gloss map must cover the shipped feature schema exactly - the
    assertion below fails on any predictor added, removed or renamed,
    so this table cannot silently drift from the model bundle.
    """
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    names = sorted(schema["source_predictors"])
    assert set(names) == set(PREDICTOR_GLOSSES), (
        set(names) ^ set(PREDICTOR_GLOSSES))
    # Underscores are the only legal break points in a predictor name;
    # without \allowbreak the longest names overrun their p-column.
    rows = [["\\texttt{"
             + _escape(name).replace(r"\_", r"\_\allowbreak{}") + "}",
             _escape(PREDICTOR_GLOSSES[name])] for name in names]
    _write("a1_stage1_predictors.tex",
           r"p{0.42\linewidth}p{0.50\linewidth}",
           ["predictor", "meaning"], rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    predictors()
    confirmatory("v1", "t04_confirmatory_v1.csv", "a2a_confirmatory_v1.tex")
    confirmatory("v2", "t05_confirmatory_v2.csv", "a2b_confirmatory_v2.tex")
    sensitivity_summary()
    seat_accuracy()
    llm_validation()
    approach_comparison()
    woking_south()
    haslemere_probe()
    blind_tests()
    mde_summary()


if __name__ == "__main__":
    main()
