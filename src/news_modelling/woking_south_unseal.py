"""Unseal Woking South: the protocol's ONLY reader of this outcome.

    PYTHONPATH=src .venv/bin/python -m news_modelling.woking_south_unseal

Machine-locked as the frozen protocol demands, and the lock is git
itself: before reading anything, this script computes the blob id of
``blind_predictions.csv`` as committed at HEAD and compares it to the
bytes on disk - if the file is uncommitted, missing from HEAD, or
differs by one byte from what was committed, the unseal refuses to
run. Predictions first, in history, then answers; never the reverse.

Scoring follows the frozen protocol's endpoints exactly: for every one
of the 18 arm x window specifications - none selected, the derived
combination marked by its pick flag - the contest MAE of the news
prediction against the untouched baseline and the recalibrated
control, the winner call, and per-party signed errors with Reform UK
explicit. One contest, five candidates: a case study, whatever it
says. Output: unseal_results.json and unseal_findings.md beside the
predictions, and the result is read exactly once, here.
"""

from __future__ import annotations

import csv
import json
import subprocess
from collections import defaultdict
from pathlib import Path

PRED = Path("news_features/woking_south_blind_v1/blind_predictions.csv")
PROTOCOL = Path("news_features/woking_south_blind_v1/protocol.json")
OOF = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1/"
           "out_of_fold_predictions.csv")
OUT_JSON = Path("news_features/woking_south_blind_v1/unseal_results.json")
OUT_MD = Path("news_features/woking_south_blind_v1/unseal_findings.md")

WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")


def assert_predictions_committed() -> str:
    """The git lock: HEAD's blob of the predictions file must equal the
    bytes on disk. Returns the blob id for the record."""

    on_disk = subprocess.run(
        ["git", "hash-object", str(PRED)],
        capture_output=True, text=True, check=True).stdout.strip()
    in_head = subprocess.run(
        ["git", "rev-parse", f"HEAD:{PRED.as_posix()}"],
        capture_output=True, text=True)
    if in_head.returncode != 0:
        raise RuntimeError(
            "UNSEAL REFUSED: blind_predictions.csv is not in the current "
            "HEAD commit. Commit the predictions first - that order is "
            "the whole point.")
    if in_head.stdout.strip() != on_disk:
        raise RuntimeError(
            "UNSEAL REFUSED: the file on disk differs from the committed "
            "version. Commit exactly what will be scored.")
    return on_disk


def read_outcomes_once(election: str) -> dict[str, dict]:
    """THE read. The only place in the blind test that touches results."""

    outcomes = {}
    with OOF.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["election_id"] == election:
                outcomes[row["candidate_contest_id"]] = {
                    "observed_share": float(row["observed_vote_share"]),
                    "observed_elected": row["observed_elected"] == "True",
                }
    if len(outcomes) != 5:
        raise RuntimeError(f"expected 5 outcome rows, got {len(outcomes)}")
    return outcomes


def main() -> None:
    blob = assert_predictions_committed()
    protocol = json.loads(PROTOCOL.read_text())
    outcomes = read_outcomes_once(protocol["election"])

    specs: dict[tuple, list[dict]] = defaultdict(list)
    with PRED.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            specs[(row["arm"], row["window"])].append(row)

    results = []
    for (arm, window), rows in sorted(
            specs.items(), key=lambda k: (WINDOWS.index(k[0][1]), k[0][0])):
        def mae(column: str) -> float:
            return round(sum(
                abs(float(r[column])
                    - outcomes[r["candidate_contest_id"]]["observed_share"])
                for r in rows) / len(rows), 4)
        winner_row = max(rows,
                         key=lambda r: float(r["news_enhanced_prediction"]))
        winner_ok = outcomes[winner_row["candidate_contest_id"]][
            "observed_elected"]
        reform = next(r for r in rows if r["party_key"] == "reform_uk")
        results.append({
            "arm": arm, "window": window,
            "combination_pick": rows[0]["combination_pick"] == "True",
            "news_mae": mae("news_enhanced_prediction"),
            "recalibrated_mae": mae("recalibrated_prediction"),
            "baseline_mae": mae("baseline_prediction"),
            "news_vs_baseline": round(
                mae("baseline_prediction")
                - mae("news_enhanced_prediction"), 4),
            "reform_signed_error": round(
                float(reform["news_enhanced_prediction"])
                - outcomes[reform["candidate_contest_id"]]["observed_share"],
                4),
            "winner_correct": winner_ok,
        })

    payload = {
        "status": ("UNSEALED once, against the committed predictions "
                   f"(blob {blob[:16]}). Case study: one contest, five "
                   "candidates; no promotion of any arm or combination."),
        "election": protocol["election"],
        "specifications": results,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n",
                        encoding="utf-8")

    picks = [r for r in results if r["combination_pick"]]
    lines = [
        "# Woking South unsealed", "", f"**{payload['status']}**", "",
        "| window | arm | pick | news MAE | baseline MAE | delta "
        "(news better >0) | Reform signed err | winner |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r['window']} | {r['arm']} | "
            f"{'**PICK**' if r['combination_pick'] else ''} | "
            f"{r['news_mae']:.3f} | {r['baseline_mae']:.3f} | "
            f"{r['news_vs_baseline']:+.3f} | "
            f"{r['reform_signed_error']:+.2f} | "
            f"{'yes' if r['winner_correct'] else 'NO'} |")
    improved_picks = sum(1 for r in picks if r["news_vs_baseline"] > 0)
    lines += [
        "",
        f"Combination picks beating the untouched baseline: "
        f"**{improved_picks} of {len(picks)}** windows (near windows are "
        "structural-zero controls per the pre-outcome census; the "
        "informative panel is 180-91 days).", "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
