"""Phase 7 / Step 2 runner: build the article time-window assignment
layer from the Step 1 alignment layer + the frozen deterministic
temporal layer.

    news_features/article_time_window_assignment.json

No LLM call, no API cost. All inputs are read-only and
hash-verified where a manifest hash exists; rebuilds are
byte-identical.

Usage:
    python3 -m src.news_features.run_time_windows build
"""

import json
import sys
from collections import Counter
from pathlib import Path

from ..llm_extraction.freeze_layer import sha256_file
from .alignment import ELECTIONS
from .time_windows import TW_VERSION, build_assignment, check_assignment

ALIGN = Path("news_features/article_entity_alignment.json")
WINDOWS_FILE = Path("llm_context/temporal_windows_deterministic.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")
OUT = Path("news_features/article_time_window_assignment.json")


def build() -> None:
    # input integrity: the deterministic layer must be the exact
    # bytes the Phase 6 freeze manifest recorded
    manifest = json.loads(MANIFEST.read_text())
    expected = manifest["input_file_hashes_sha256"][str(WINDOWS_FILE)]
    assert sha256_file(WINDOWS_FILE) == expected, \
        "deterministic temporal layer hash mismatch"

    align = json.loads(ALIGN.read_text())
    stored_windows = json.loads(WINDOWS_FILE.read_text())

    # election mapping comes from the Step 1 alignment layer (the
    # single authority for article -> election), preserved verbatim
    elections = {r["article_id"]: r["election_id"]
                 for r in align["records"]
                 if r["alignment_type"] == "election"}

    assigned, excluded, invalid = [], [], []
    for aid in sorted(elections):
        stored = stored_windows.get(aid)
        if stored is None:
            invalid.append({"article_id": aid,
                            "reason": "missing_deterministic_entry"})
            continue
        rec, exc = build_assignment(aid, elections[aid], stored)
        if exc:
            excluded.append(exc)
            continue
        errs = check_assignment(rec)
        if errs:
            invalid.append({"article_id": aid, "reason": errs})
            continue
        assigned.append(rec)

    if invalid:
        raise SystemExit("time-window build aborted: "
                         + json.dumps(invalid, indent=1))

    OUT.write_text(json.dumps(
        {"assignment_version": TW_VERSION,
         "alignment_version": align["alignment_version"],
         "deterministic_layer_sha256": expected,
         "elections": ELECTIONS,
         "assigned_count": len(assigned),
         "excluded_count": len(excluded),
         "assigned": assigned,
         "excluded_post_or_out_of_window": excluded},
        indent=1, ensure_ascii=False) + "\n")

    # ---- audit statistics -------------------------------------------
    per_election = Counter(r["election_id"] for r in assigned)
    per_window = Counter(r["individual_time_window"] for r in assigned)
    flagged = [r["article_id"] for r in assigned if r["flags"]]
    print(f"{len(assigned)} assigned, {len(excluded)} excluded "
          f"-> {OUT}")
    print("per election:", dict(sorted(per_election.items())))
    print("per window:", dict(per_window.most_common()))
    print("cumulative counts:", {
        n: sum(1 for r in assigned if r["cumulative_windows"][n])
        for n in assigned[0]["cumulative_windows"]})
    print(f"result-flagged (D3, retained+flagged): {len(flagged)}",
          flagged)
    print("exclusions:", Counter(e["exclusion_reason"]
                                 for e in excluded) or "none")


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
