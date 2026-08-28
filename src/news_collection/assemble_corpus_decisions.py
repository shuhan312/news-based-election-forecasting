"""Assemble the remaining corpus's final eligibility decisions from
their two provenance streams, under §8.5 + §9 of
eligibility_manual_review_methodology.md. Section 9 was adopted provisionally
on 2026-07-24 and used in the final assembly; no separate later ratification
record is retained, so the per-decision source fields preserve the reversible
audit boundary.

The population may arrive in two disjoint review sheets: the original
2,370-row corpus sheet and the later local-extension sheet. Their LLM outputs
remain separate for audit, then are unioned here by article id. Duplicate ids
across either pair are fatal because they would make provenance ambiguous.

Per-rule sources:

| Rule | arm=national | arm=local |
|---|---|---|
| E4, E8 | frozen v2 (validated §8.5)   | frozen v2 (validated §8.5) |
| E6     | frozen v2 (Reform-flagged only; else not_applicable) | same |
| E5     | frozen v2 (§9 arm split) | HUMAN, from full_corpus_review.csv |

A third stream sits above both: second_review_queue.csv carries the
human adjudications of every needs_second_review flag and of the 20
articles the LLM failed twice (all four rules judged by hand there,
with E6 auto-filled not_applicable on non-Reform-flagged rows). A
queue cell whose ``*_source`` is ``human`` or ``auto`` overrides the
base streams - that is the queue's whole purpose, and the pre-sync
backups of the queue preserve the pre-adjudication state.

Every output row records, per rule, which stream the decision came
from (``llm_v2`` / ``human`` / ``auto`` / empty when unresolved).
Reversing §9 therefore requires no data surgery: filter e5_source and
re-derive.

A row's overall decision is computed by the same
``derive_overall_decision`` used everywhere else, and ONLY when all
four rules are present. Rows blocked on the LLM retry (non-ok status)
or on human E5 coding are reported as pending, never guessed.

The extension sheet may still contain blank human E5 cells. Those rows are
emitted as pending rather than guessed, so assembly can be rerun safely after
each review tranche.

Usage:
    python3 -m src.news_collection.assemble_corpus_decisions
"""

import csv
from collections import Counter
from pathlib import Path

from .manual_review_schema import RULES, derive_overall_decision

SHEETS = (
    Path("news_collection/full_corpus_review.csv"),
    Path("news_collection/e5_local_review_queue_round2.csv"),
)
LLM_OUTPUTS = (
    Path("news_collection/manual_review_llm_v2_corpus.csv"),
    Path("news_collection/manual_review_llm_v2_local_extension.csv"),
)
QUEUE = Path("news_collection/second_review_queue.csv")
OUT = Path("news_collection/corpus_eligibility_decisions.csv")

FIELDS = (
    ["article_id", "election_id", "arm", "needs_reform_disambiguation"]
    + [f"{r.lower()}_{s}" for r in RULES
       for s in ("decision", "reason_code", "source")]
    + ["overall_decision", "resolution_status"]
)


def load_disjoint_rows(paths: tuple[Path, ...], *, label: str) -> dict[str, dict]:
    """Load every existing stream and reject overlapping article identities.

    The local extension is a continuation of the corpus, not a replacement for
    the original 2,370 rows. A duplicate across streams would make provenance
    ambiguous, so assembly fails rather than silently taking the later file.
    """

    rows: dict[str, dict] = {}
    available = [path for path in paths if path.exists()]
    if not available:
        raise RuntimeError(f"no {label} files exist: {list(paths)}")
    for path in available:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                article_id = row["article_id"]
                if article_id in rows:
                    raise RuntimeError(
                        f"{article_id} appears in multiple {label} files; "
                        f"latest conflict is {path}")
                rows[article_id] = row
    return rows


def main() -> None:
    sheet = load_disjoint_rows(SHEETS, label="review-sheet")
    llm = load_disjoint_rows(LLM_OUTPUTS, label="LLM-output")

    # Adjudication layer: cells a human resolved (or the flag-derived E6
    # not_applicable) in the second-review queue outrank both base streams.
    overrides: dict[str, dict[str, tuple[str, str, str]]] = {}
    if QUEUE.exists():
        for q in csv.DictReader(QUEUE.open()):
            for rule in RULES:
                f = rule.lower()
                if q.get(f"{f}_source") in ("human", "auto") and q.get(
                        f"{f}_decision"):
                    overrides.setdefault(q["article_id"], {})[rule] = (
                        q[f"{f}_decision"], q[f"{f}_reason_code"],
                        q[f"{f}_source"])

    rows, statuses = [], Counter()
    n_overridden = 0
    for aid, s in sorted(sheet.items()):
        m = llm.get(aid, {})
        llm_ok = m.get("status") == "ok"
        out = {
            "article_id": aid, "election_id": s["election_id"],
            "arm": s["arm"],
            "needs_reform_disambiguation": s["needs_reform_disambiguation"],
        }
        blockers = []
        for rule in RULES:
            f = rule.lower()
            decision = source = reason = ""
            override = overrides.get(aid, {}).get(rule)
            if override:
                decision, reason, source = override
                n_overridden += 1
            elif rule == "E5" and s["arm"] == "local":
                # §9: local relevance stays a human judgement.
                decision = s.get("e5_decision", "")
                reason = s.get("e5_reason_code", "")
                source = "human" if decision else ""
                if not decision:
                    blockers.append("awaiting_human_e5")
            elif llm_ok:
                decision = m.get(f"{f}_decision", "")
                reason = m.get(f"{f}_reason_code", "")
                source = "llm_v2" if decision else ""
                if not decision:
                    blockers.append(f"llm_missing_{f}")
            else:
                blockers.append("awaiting_llm_retry")
            out[f"{f}_decision"] = decision
            out[f"{f}_reason_code"] = reason
            out[f"{f}_source"] = source

        if blockers:
            out["overall_decision"] = ""
            out["resolution_status"] = ";".join(sorted(set(blockers)))
        else:
            out["overall_decision"] = derive_overall_decision(
                out["e4_decision"], out["e5_decision"],
                out["e6_decision"], out["e8_decision"])
            out["resolution_status"] = "resolved"
        statuses[out["resolution_status"].split(";")[0]] += 1
        rows.append(out)

    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} rows -> {OUT}")
    print(f"queue-adjudicated rule cells applied: {n_overridden}")
    print("resolution:", dict(statuses))
    resolved = [r for r in rows if r["resolution_status"] == "resolved"]
    print("overall (resolved only):",
          dict(Counter(r["overall_decision"] for r in resolved)))
    print("\nRe-run this script whenever the human E5 sheet or the LLM "
          "corpus CSV changes - it derives, never stores judgement.")


if __name__ == "__main__":
    main()
