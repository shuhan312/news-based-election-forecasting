"""Freeze the Woking South blind-test protocol (runs before ANY contact).

    PYTHONPATH=src .venv/bin/python -m news_modelling.woking_south_blind_protocol

Order is the discipline. This module is executed and committed BEFORE
one article is collected for the Woking South 10 July 2025 by-election,
and it pins every choice the test involves, so that nothing chosen
after news contact can steer the result:

1. THE COMBINATION RULE IS DERIVED, NOT TYPED. The window-weighted
   combination assigns each window to one arm; the assignment is
   computed here as "the arm with the largest committed 2026
   news-vs-recalibrated delta in that window" - combined and national
   read from the unblinding record, local from the v3 re-run record.
   Both files are committed; their sha256 digests are pinned in the
   protocol so the derivation can be re-checked forever.
2. EVERY INPUT IS PINNED BY HASH. The v2 and v3exp feature tables (the
   fitting tables for the arms), the Stage 1 bundle's out-of-fold file
   (the baseline rows for the contest) and the two result records are
   hashed into the protocol; the runner will refuse a changed file.
3. ENDPOINTS ARE PRE-DECLARED. Primary: contest MAE of the combination
   against the untouched baseline. Reference: each single arm's contest
   MAE. Secondary: winner call and per-party signed errors. One
   contest, five candidates: the protocol says in advance that this is
   a case study and no promotion of any arm can follow from it.
4. THE STOP-LOSS IS PRE-SET. If the collection funnel ends with fewer
   than 15 usable articles, the test aborts and the shortfall is
   recorded as the finding.
5. THE UNSEAL IS MACHINE-LOCKED. Observed outcomes for this contest
   already sit in the committed baseline files, so "not looking" is
   the entire blindness; the protocol names one future script as the
   only permitted reader of those columns and requires, before it
   runs, that a predictions file exists AND that its exact bytes are
   already in git history. No committed predictions, no unseal.

Evidence tier, stated in the protocol itself: news-blind and
analyst-blind (no news artefact and no person in this analysis has
read the outcome), baseline-informed (the result sat inside Stage 1's
rolling-origin training), single contest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ELECTION = "surrey-county-council-by-election-woking-south-2025-07-10"
POLLING_DAY = "2025-07-10"

OUT_DIR = Path("news_features/woking_south_blind_v1")

# Committed sources the combination rule is derived from, and the
# frozen artefacts every later stage will fit or predict with.
PINNED_INPUTS = {
    "unblinding_record":
        Path("news_features/unblinding_2026_v1/unblinding_results.json"),
    "local_v3_rerun_record":
        Path("news_features/local_v3_rerun_v1/rerun_results.json"),
    "feature_table_v2": Path("news_features/news_feature_table_v2.csv"),
    "feature_table_v3exp":
        Path("news_features/news_feature_table_v3exp.csv"),
    "estimability_audit":
        Path("news_features/production_estimability_v1/estimability_report.json"),
    "baseline_out_of_fold":
        Path("surrey-election-no-news-baseline/outputs/model_bundle_v1/"
             "out_of_fold_predictions.csv"),
}

WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")

# Which fitting table each arm's specification is refitted on: the two
# frozen arms fit on the v2 table exactly as at unblinding; local fits
# on v3exp, the lineage that made its columns reportable.
ARM_TABLE = {"combined": "feature_table_v2",
             "national": "feature_table_v2",
             "local": "feature_table_v3exp"}


def committed_delta(record: dict, analysis: str, window: str) -> float:
    """news-vs-recalibrated delta for one arm x window, from its record."""

    if analysis == "local":
        for entry in record["windows"]:
            if entry["window"] == window:
                return entry["metrics"]["all_supported_parties"][
                    "news_vs_recalibrated_mae"]
        raise KeyError(window)
    wanted = f"{analysis}_exploratory"
    for entry in record["files"]["v2"]:
        if (entry["family"] == "confirmatory"
                and entry["analysis"] == wanted
                and entry["period"] == window):
            return entry["metrics"]["all_supported_parties"][
                "news_vs_recalibrated_mae"]
    raise KeyError((analysis, window))


def derive_combination(unblinding: dict, rerun: dict) -> dict:
    """The mechanical rule: each window goes to the arm with the largest
    committed 2026 delta there. Ties (to 4 dp) would fall to the arm
    name's alphabetical order - stated so even the tie-break is frozen -
    and the full delta table is returned beside the winners so the
    derivation is visible, not just its result."""

    assignment, table = {}, {}
    for window in WINDOWS:
        deltas = {
            "combined": round(committed_delta(unblinding, "combined", window), 4),
            "local": round(committed_delta(rerun, "local", window), 4),
            "national": round(committed_delta(unblinding, "national", window), 4),
        }
        winner = max(sorted(deltas), key=lambda arm: deltas[arm])
        assignment[window] = winner
        table[window] = deltas
    return {"window_to_arm": assignment, "derivation_deltas": table}


def main() -> None:
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name, path in PINNED_INPUTS.items()}
    unblinding = json.loads(PINNED_INPUTS["unblinding_record"].read_text())
    rerun = json.loads(PINNED_INPUTS["local_v3_rerun_record"].read_text())
    combination = derive_combination(unblinding, rerun)

    protocol = {
        "protocol": "woking-south-blind-test-v1",
        "election": ELECTION,
        "polling_day": POLLING_DAY,
        "evidence_tier": (
            "news-blind and analyst-blind; baseline-informed (the outcome "
            "sat inside Stage 1's rolling-origin training); single contest "
            "- a case study, whatever the result"),
        "pinned_input_sha256": hashes,
        "combination_rule": (
            "each window is served by the arm with the largest committed "
            "2026 news-vs-recalibrated delta in that window; ties at 4 dp "
            "fall to alphabetical arm order"),
        **combination,
        "arm_fitting_tables": ARM_TABLE,
        "specifications": (
            "each arm uses its frozen two-column feature set from the "
            "estimability audit; ridge penalty and all fitting, "
            "prediction, contest-normalisation and seat-allocation code "
            "are the frozen modules already in the repository"),
        "baseline_rows": (
            f"the Stage 1 out-of-fold rows for {ELECTION} "
            "(split rolling_2025-07-10, 5 candidates), outcome columns "
            "stripped at load by strip_outcome_columns"),
        "collection": {
            "window": "2025-01-11 to 2025-07-10 (180 days, historical)",
            "method": ("the by-election collection pipeline unchanged: "
                       "registry sources, the standard query template, "
                       "CDX and dated-search routes"),
            "funnel": ("frozen eligibility rules; LLM E4/E8 batch with "
                       "the production models; human E5 for local rows; "
                       "frozen extraction, model assignment unchanged"),
        },
        "stop_loss": {
            "rule": ("if the assembled corpus holds fewer than "
                     "MIN_USABLE_ARTICLES usable articles, the test "
                     "aborts and the shortfall is recorded as the "
                     "finding"),
            "min_usable_articles": 15,
        },
        "endpoints": {
            "primary": ("contest MAE of the window-weighted combination "
                        "against the untouched baseline"),
            "reference": "contest MAE of each single arm",
            "secondary": ("winner call; per-party signed errors, Reform "
                          "UK reported explicitly"),
            "reading_rules": (
                "one contest, five candidates: illustrative evidence "
                "only; no arm or combination may be promoted from this "
                "result; every specification's number is reported, none "
                "selected"),
        },
        "unseal": {
            "only_reader": "src/news_modelling/woking_south_unseal.py "
                           "(to be written; the ONLY code permitted to "
                           "read observed columns for this election)",
            "preconditions": (
                "a predictions file exists under "
                "news_features/woking_south_blind_v1/ AND its exact "
                "bytes are reachable in git history (verified with "
                "git cat-file); otherwise the unseal refuses to run"),
            "prohibition": (
                "until the unseal runs, no code or person in this "
                "analysis reads observed_vote_share, observed_rank, "
                "observed_elected, error or any outcome column for "
                f"{ELECTION} from any file"),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "protocol.json").write_text(
        json.dumps(protocol, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Woking South blind test - frozen protocol v1", "",
        f"Election: {ELECTION}, polling day {POLLING_DAY}.",
        f"Evidence tier: {protocol['evidence_tier']}.", "",
        "## The derived window-to-arm assignment", "",
        "| window | combined | local | national | -> serves the window |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for window in WINDOWS:
        deltas = combination["derivation_deltas"][window]
        lines.append(
            f"| {window} | {deltas['combined']:+.4f} | "
            f"{deltas['local']:+.4f} | {deltas['national']:+.4f} | "
            f"**{combination['window_to_arm'][window]}** |")
    lines += [
        "", "Derivation rule: largest committed 2026 delta per window; "
        "ties at 4 dp fall to alphabetical order. Sources and every "
        "other pinned choice: protocol.json (input hashes included).",
        "", "Stop-loss: abort and record if usable articles < 15. "
        "Unseal: only by the named script, only after a predictions "
        "file is committed.", "",
    ]
    (OUT_DIR / "protocol.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"-> {OUT_DIR}")


if __name__ == "__main__":
    main()
