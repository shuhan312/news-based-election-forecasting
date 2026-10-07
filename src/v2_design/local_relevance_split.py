"""Fix the dev/test split for the local relevance classifier, before any run.

Human reference: V1's fully manual local E5 decisions
(news_collection/full_corpus_review.csv, arm=local, e5_decision in
include/exclude). The 52-row local slice of V1's validation sample, where
the frozen v2 classifier scored kappa 0.165, is already-seen data and goes to
dev. The test half is drawn by a salted hash within each label, so the split
cannot depend on anything but the article id.

No classifier output is read here.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

CORPUS = Path("news_collection/full_corpus_review.csv")
VALIDATION = Path("news_collection/llm_validation_sample.csv")
OUT = Path("v2_design/local_relevance_v1/split.csv")
SALT = "v2-local-relevance-2026-10-07"
LABELS = ("include", "exclude")


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [r for r in csv.DictReader(handle)
                if r["arm"] == "local" and r["e5_decision"] in LABELS]


def _rank(article_id: str) -> str:
    return hashlib.sha256(f"{SALT}:{article_id}".encode()).hexdigest()


def main() -> None:
    out = []
    corpus = _rows(CORPUS)
    for label in LABELS:
        group = sorted((r for r in corpus if r["e5_decision"] == label),
                       key=lambda r: _rank(r["article_id"]))
        half = len(group) // 2
        for i, r in enumerate(group):
            out.append((r, "test" if i < half else "dev", "corpus_manual"))
    for r in _rows(VALIDATION):
        out.append((r, "dev", "v1_validation_seen"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["article_id", "election_id", "source_id", "origin",
                         "split"])
        for r, split, origin in sorted(out, key=lambda x: x[0]["article_id"]):
            writer.writerow([r["article_id"], r["election_id"], r["source_id"],
                             origin, split])
    counts = {}
    for r, split, _ in out:
        key = (split, r["e5_decision"])
        counts[key] = counts.get(key, 0) + 1
    print(f"-> {OUT}", dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
