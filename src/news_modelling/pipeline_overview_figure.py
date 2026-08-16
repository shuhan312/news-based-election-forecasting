"""Draw the news data and corpus construction pipeline, end to end.

    PYTHONPATH=src .venv/bin/python -m news_modelling.pipeline_overview_figure

A deliberately minimal version: one short title and one headline number per
box, arrows carry a two-or-three-word label, and the D4 validation-gate
detail (six kappa values, three excluded layers) is compressed to a single
footnote rather than its own box. The exact numbers belong in the report
text and in ``news_layer_capability_findings.md`` / the D4 files; this
figure's job is to show the shape of the pipeline at a glance.

Every count is still read from committed evidence, not typed in by hand -
and every one of them is now traceable to a file that
``canonical_corpus_release_v1.json`` itself hashes into its own
``source_sha256`` block, not to a live directory scan:

- candidate-article counts: the union of
  ``news_collection/corpus_eligibility_decisions.csv`` (the main E4/E5
  decision table, 2,370 rows for the four principal elections),
  ``manual_review_sample.csv`` (168 rows, the human pilot batch) and
  ``llm_validation_sample.csv`` (128 rows, the model validation batch).
  These three sheets do not overlap (verified: 0 shared ``article_id``
  values), so their row counts sum cleanly to the union. An earlier version
  of this figure instead grep-counted every file in
  ``data/raw/news/records/`` tagged to the four principal elections
  (15,899) - that count is real, but it is a *live snapshot of the raw
  retrieval directory as it stands today*, which now holds ~4,100 records
  collected after ``effective_dates_v2.csv`` (the date/window input the
  frozen v1 release actually used) was last generated. Those later records
  were never assessed by the pipeline that produced the 1,632-article
  release, so citing 15,899 as "what fed the corpus" is not defensible;
  the three adjudication sheets are;
- canonical corpus counts: ``news_collection/canonical_corpus_release_v1.json``'s
  own ``usable_feature_corpus`` block;
- extraction completion counts: the union of
  ``llm_context/corpus_extraction_outputs_{narrow,far,far2,far3,all}.json``,
  deduplicated exactly the way ``build_feature_table.load_records()`` does
  (oldest-to-newest tranche order, ``superseded_layers`` honoured, a record
  only counts if it has no ``validation_errors``);
- feature table shape: ``news_features/news_feature_table_v1_metadata.json``.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from matplotlib.patches import FancyBboxPatch

DECISIONS = Path("news_collection/corpus_eligibility_decisions.csv")
PILOT_SHEET = Path("news_collection/manual_review_sample.csv")
VALIDATION_SHEET = Path("news_collection/llm_validation_sample.csv")
CANONICAL_RELEASE = Path("news_collection/canonical_corpus_release_v1.json")
EXTRACTION_OUTPUTS = [
    Path(f"llm_context/corpus_extraction_outputs_{tranche}.json")
    for tranche in ("narrow", "far", "far2", "far3", "all")
]
FEATURE_METADATA = Path("news_features/news_feature_table_v1_metadata.json")
OUTPUT = Path("news_features/pipeline_overview_v1")

BLUE, INK, MUTED = "#2a78d6", "#333333", "#666666"
BOX_FACE = "#eaf1fb"


def _candidate_counts() -> dict[str, int]:
    """Unique candidate articles across the three sheets the frozen v1
    release actually hashes: the main E4/E5 decision table plus the pilot
    and validation batches. Confirmed disjoint (zero shared article_id
    values), so counting rows per sheet and summing is exact, not an
    approximation of a true union.
    """

    def rows(path: Path) -> list[dict]:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    all_rows = rows(DECISIONS) + rows(PILOT_SHEET) + rows(VALIDATION_SHEET)
    counts = Counter(r.get("arm", "unknown") for r in all_rows)
    return {"local": counts["local"], "national": counts["national"],
            "total": len(all_rows)}


def _canonical_counts() -> dict[str, int]:
    release = json.loads(CANONICAL_RELEASE.read_text(encoding="utf-8"))
    return {"total": release["usable_feature_corpus"]["articles"]}


def _extraction_completion() -> dict[str, int]:
    """Exact replica of ``build_feature_table.load_records()``'s dedup rule."""

    layer_names = ("issues", "stance_revised", "framing_revised")
    order = {"narrow": 0, "far": 1, "far2": 2, "far3": 3, "all": 9}
    accepted: dict[str, dict[str, dict]] = {name: {} for name in layer_names}

    ordered_paths = sorted(
        (p for p in EXTRACTION_OUTPUTS if p.exists()),
        key=lambda p: order.get(p.stem.replace("corpus_extraction_outputs_", ""), 5),
    )
    for path in ordered_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        superseded = set(payload.get("superseded_layers") or ())
        layers = payload.get("layers", {})
        for layer_name in layer_names:
            if layer_name in superseded:
                continue
            for entry in layers.get(layer_name, []):
                if entry.get("record") is None or entry.get("validation_errors"):
                    continue
                accepted[layer_name][entry["article_id"]] = entry
    return {name: len(ids) for name, ids in accepted.items()}


def _feature_table_shape() -> dict[str, int]:
    meta = json.loads(FEATURE_METADATA.read_text(encoding="utf-8"))
    return {"rows": meta.get("expected_rows") or meta.get("rows")}


def _box(ax, xy, width, height, title, subtitle=""):
    x, y = xy
    ax.add_patch(FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.1",
        linewidth=1.5, edgecolor=BLUE, facecolor=BOX_FACE, zorder=3,
    ))
    if subtitle:
        ax.text(x + width / 2, y + height * 0.62, title, ha="center", va="center",
                 fontsize=12.5, color=INK, weight="bold", zorder=4)
        ax.text(x + width / 2, y + height * 0.28, subtitle, ha="center", va="center",
                 fontsize=10, color=MUTED, zorder=4)
    else:
        ax.text(x + width / 2, y + height / 2, title, ha="center", va="center",
                 fontsize=12.5, color=INK, weight="bold", zorder=4)


def _arrow(ax, x, y_top, y_bottom, label=""):
    ax.add_patch(FancyArrowPatch((x, y_top), (x, y_bottom),
                                  arrowstyle="-|>", mutation_scale=16,
                                  linewidth=1.5, color=MUTED, zorder=2))
    if label:
        ax.text(x + 0.2, (y_top + y_bottom) / 2, label, ha="left", va="center",
                 fontsize=10, color=MUTED)


def draw() -> None:
    cand = _candidate_counts()
    canon = _canonical_counts()
    extraction = _extraction_completion()
    shape = _feature_table_shape()
    n = canon["total"]

    fig, ax = plt.subplots(figsize=(8, 11))
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 13.2)
    ax.axis("off")

    # 1. sources
    _box(ax, (0.3, 11.9), 3.3, 1.0, "Local news", f"{cand['local']:,} candidates")
    _box(ax, (4.4, 11.9), 3.3, 1.0, "National news", f"{cand['national']:,} candidates")
    ax.plot([1.95, 1.95, 4.0], [11.9, 11.55, 11.55], color=MUTED, linewidth=1.3)
    ax.plot([6.05, 6.05, 4.0], [11.9, 11.55, 11.55], color=MUTED, linewidth=1.3)
    _arrow(ax, 4.0, 11.55, 10.6)

    # 2. candidate total
    _box(ax, (2.3, 9.75), 3.4, 0.85, f"{cand['total']:,} candidate articles")
    _arrow(ax, 4.0, 9.75, 8.5, "Eligibility &\nleakage screening")

    # 3. canonical corpus
    _box(ax, (2.3, 7.65), 3.4, 0.85, f"{n:,} usable articles")
    _arrow(ax, 4.0, 7.65, 6.4, "LLM\nextraction")

    # 4. three extraction layers
    for i, (label, count) in enumerate([
        ("Issue", extraction["issues"]),
        ("Stance", extraction["stance_revised"]),
        ("Framing", extraction["framing_revised"]),
    ]):
        x0 = 0.3 + i * 2.55
        _box(ax, (x0, 5.2), 2.2, 1.05, label, f"{count/n:.0%} of articles")
    ax.text(4.0, 5.02, "(3 further layers tested and excluded — see §3.2.3)",
            ha="center", va="center", fontsize=8.5, color=MUTED, style="italic")
    _arrow(ax, 4.0, 4.82, 3.55, "Feature\nconstruction")

    # 5. feature table
    _box(ax, (1.6, 2.3), 4.8, 0.9, "News feature table",
         f"{shape['rows']} rows: one per election \u00d7 party \u00d7 window")
    _arrow(ax, 4.0, 2.3, 1.05, "Join to\nbaseline")

    # 6. Stage 2 input
    _box(ax, (1.0, 0.15), 6.0, 0.75, "Stage 2 modelling input")

    fig.tight_layout()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT / "pipeline_overview.png"
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"wrote {out_path}")
    print("candidates:", cand, "canonical:", canon,
          "extraction:", extraction, "feature table:", shape)


if __name__ == "__main__":
    draw()
