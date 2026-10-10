"""Examples, reference labels and the dev/test split.

A reference label is only as good as the process that made it, so every
example records where its label came from (`provenance`) and which labelling
batch it belongs to (`origin`). The audit stage reads both.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

PROVENANCES = ("human", "ai_assisted", "model")


@dataclass(frozen=True)
class Example:
    id: str
    label: int                      # 1 = positive class, 0 = negative
    provenance: str                 # how the reference label was made
    origin: str                     # which labelling batch it came from
    reason: str = ""                # the label's reason code, if recorded
    group: dict = field(default_factory=dict)   # subgroup fields, e.g. source

    def __post_init__(self):
        if self.label not in (0, 1):
            raise ValueError(f"{self.id}: label must be 0 or 1")
        if self.provenance not in PROVENANCES:
            raise ValueError(f"{self.id}: unknown provenance {self.provenance!r}")


def load_labels(path: str | Path, *, origin: str, provenance: str,
                id_col: str, label_col: str, positive: str, negative: str,
                reason_col: str | None = None,
                group_cols: tuple[str, ...] = (),
                where: dict | None = None) -> list[Example]:
    """Read one labelling batch from CSV.

    Only rows whose label is exactly `positive` or `negative` are kept.
    Anything else (unresolved, needs second review, blank) is not a
    reference label and is dropped rather than guessed. `where` keeps only
    rows whose columns equal the given values, e.g. {"arm": "local"}.
    """
    where = where or {}
    out = []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if any(row.get(k) != v for k, v in where.items()):
                continue
            value = row[label_col]
            if value not in (positive, negative):
                continue
            out.append(Example(
                id=row[id_col], label=int(value == positive),
                provenance=provenance, origin=origin,
                reason=row.get(reason_col, "") if reason_col else "",
                group={c: row.get(c, "") for c in group_cols}))
    return out


def hash_split(examples: list[Example], *, salt: str,
               force_dev_origins: tuple[str, ...] = ()) -> dict[str, str]:
    """Deterministic, label-stratified 50/50 dev/test split.

    Within each label, examples are ordered by sha256(salt:id) and the first
    half goes to test. Only the id decides the order, so no property of an
    article can steer it, and the same ids always land in the same split.
    Examples from `force_dev_origins` (already-seen data) always go to dev.
    """
    split = {e.id: "dev" for e in examples if e.origin in force_dev_origins}
    pool = [e for e in examples if e.origin not in force_dev_origins]
    for label in (1, 0):
        group = sorted((e for e in pool if e.label == label),
                       key=lambda e: hashlib.sha256(
                           f"{salt}:{e.id}".encode()).hexdigest())
        half = len(group) // 2
        for i, e in enumerate(group):
            split[e.id] = "test" if i < half else "dev"
    return split


def load_split_file(path: str | Path) -> dict[str, str]:
    """A previously committed split (columns: article_id, split)."""
    with open(path, encoding="utf-8", newline="") as handle:
        return {r["article_id"]: r["split"] for r in csv.DictReader(handle)}
