"""Draw the two-stage framework: model chain, three comparators, freeze line.

    PYTHONPATH=src .venv/bin/python -m news_modelling.framework_figure

One diagram for the Methodology chapter: the Stage 1 chain (history ->
LightGBM -> baseline predictions and out-of-fold residuals), the Stage 2
chain (residual cells x news features -> Ridge per window -> news
adjustment), the three prediction objects the evaluation compares
(Stage 1 baseline, no-news recalibrated control, news-enhanced), and the
dashed freeze boundary below which the sealed 2026 results are first
read. The Delta-MAE definition rides inside the sealed-evaluation box so
the figure answers the two questions readers stumble on in prose: what
exactly is the recalibrated control, and what was frozen when.

Counts are read from committed evidence and asserted before drawing:
``blinded_predictions_v2/frozen_protocol.json`` (832 blinded rows, 45
fitting cells), ``byelection_enrichment.json`` (11 v1 cells) and the
Stage 1 bundle's ``training_rows.csv`` (1,150 training records).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

from news_modelling.study_design_figure import (BLUE, ORANGE, INK, MUTED,
                                                _box)

ENRICHMENT = Path(
    "news_features/byelection_enrichment_v1/byelection_enrichment.json")
PROTOCOL = Path(
    "news_features/blinded_2026_predictions_v2/frozen_protocol.json")
TRAINING = Path(
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "training_rows.csv")
OOF = Path(
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "out_of_fold_predictions.csv")
CORPUS_V1 = Path("news_features/news_feature_table_v1_metadata.json")
CORPUS_V2 = Path("news_features/news_feature_table_v2_metadata.json")
OUTPUT = Path("outputs/report_figures_v1")


def _arrow(ax, start, end, label="", label_dx=0.12):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>",
                                 mutation_scale=13, linewidth=1.4,
                                 color=MUTED, zorder=2))
    if label:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        ax.text(mx + label_dx, my, label, ha="left", va="center",
                fontsize=8.5, color=MUTED)


def main() -> None:
    enrichment = json.loads(ENRICHMENT.read_text(encoding="utf-8"))
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    with TRAINING.open(encoding="utf-8-sig") as handle:
        training_rows = sum(1 for _ in csv.DictReader(handle))

    with OOF.open(encoding="utf-8-sig") as handle:
        oof_rows = sum(1 for _ in csv.DictReader(handle))
    corpus_v1 = json.loads(CORPUS_V1.read_text(encoding="utf-8"))
    corpus_v2 = json.loads(CORPUS_V2.read_text(encoding="utf-8"))

    assert enrichment["general_election_cells"] == 11
    assert protocol["fitting_rows"] == 45
    assert protocol["blinded_candidate_rows"] == 832
    assert training_rows == 1150
    assert oof_rows == 792
    assert corpus_v1["corpus_size"] == 1632
    assert corpus_v2["corpus_size"] == 2259

    fig, ax = plt.subplots(figsize=(11.5, 8.2))
    ax.set_xlim(0, 11.5)
    ax.set_ylim(0, 9.2)
    ax.axis("off")

    # --- Stage 1 chain (left) -------------------------------------------
    _box(ax, (0.5, 7.9), 3.4, 0.95, "Historical election data",
         f"Section 3.1 · {training_rows:,} training records")
    _box(ax, (0.5, 6.3), 3.4, 0.95, "Stage 1: LightGBM",
         "candidate-level vote share")
    _box(ax, (0.5, 4.7), 3.4, 0.95, "2026 baseline predictions",
         "clipped, rescaled to 100")
    _arrow(ax, (2.2, 7.9), (2.2, 7.25))
    _arrow(ax, (2.2, 6.3), (2.2, 5.65))

    _box(ax, (4.6, 6.3), 2.9, 0.95, "Out-of-fold residuals",
         "observed − predicted · 792 rows")
    _arrow(ax, (3.9, 6.775), (4.6, 6.775))

    # --- Stage 2 chain (right) ------------------------------------------
    _box(ax, (7.9, 7.85), 3.1, 1.0, "News features",
         "party article share · net portrayal share\n"
         "v1: 1,632 · v2: 2,259 articles")
    _box(ax, (7.9, 6.3), 3.1, 0.95, "Stage 2: Ridge per window",
         "election × party cells · v1: 11, v2: 45")
    _box(ax, (7.9, 4.7), 3.1, 0.95, "News adjustment",
         "per party × window")
    _arrow(ax, (9.45, 7.9), (9.45, 7.25))
    _arrow(ax, (7.5, 6.775), (7.9, 6.775))
    _arrow(ax, (9.45, 6.3), (9.45, 5.65))

    # --- Three comparison objects ---------------------------------------
    _box(ax, (0.5, 2.9), 3.15, 1.0, "Stage 1 baseline",
         "no adjustment")
    _box(ax, (4.05, 2.9), 3.3, 1.0, "Recalibrated control",
         "baseline + intercept only\n(no news)")
    _box(ax, (7.9, 2.9), 3.1, 1.0, "News-enhanced",
         "baseline + news adjustment")
    _arrow(ax, (2.2, 4.7), (2.2, 3.9))
    ax.plot([2.2, 5.7], [4.35, 4.35], color=MUTED, linewidth=1.4, zorder=2)
    _arrow(ax, (5.7, 4.35), (5.7, 3.9))
    _arrow(ax, (9.45, 4.7), (9.45, 3.9))

    # --- Freeze line and sealed evaluation ------------------------------
    ax.plot([0.3, 11.2], [2.35, 2.35], color=ORANGE, linewidth=1.6,
            linestyle=(0, (6, 4)), zorder=2)
    ax.text(11.15, 2.08, "predictions frozen above this line\n"
            "before the 2026 results were read",
            fontsize=9, color=ORANGE, style="italic", ha="right", va="top")
    _box(ax, (2.9, 0.45), 5.7, 1.1, "Sealed 2026 evaluation",
         "East + West Surrey · 832 candidates\n"
         "$\\Delta$MAE = MAE$_{\\mathrm{recalibrated}}$ − "
         "MAE$_{\\mathrm{news}}$ · paired contest bootstrap",
         sealed=True)
    _arrow(ax, (2.07, 2.9), (4.2, 1.55))
    _arrow(ax, (5.7, 2.9), (5.75, 1.55))
    _arrow(ax, (9.45, 2.9), (7.3, 1.55))

    fig.tight_layout()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT / "fig0c_framework.png", dpi=200)
    plt.close(fig)
    print("wrote", OUTPUT / "fig0c_framework.png")


if __name__ == "__main__":
    main()
