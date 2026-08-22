"""Draw the study design as a tree: how the 24 election events are used.

    PYTHONPATH=src .venv/bin/python -m news_modelling.study_design_figure

One source box (the county-level election record) splits into the five
principal elections and the nineteen by-elections, and every leaf states
one role: training history, Stage 2 residual fit (v1 and v2), or sealed
evaluation. The figure replaces the report's prose accounting of the
by-elections (19 = 17 into Stage 1, of which 8 news-enriched and one
pre-registered blind case, plus 2 held out in the 2026 holdout period)
with a shape a reader can check at a glance. It shares the visual
language of the corpus pipeline figure - rounded boxes, one headline
per box, blue for fitted data and orange for sealed tests - so the two
diagrams read as a pair.

The figure draws; it computes nothing new. Every count is read from
committed evidence and asserted before drawing:

- events, contests and candidate rows: the shipped Stage 1 bundle's
  ``data_quality_report.json`` (24 / 343 / 1,992 and the 24 election
  identifiers with their polling dates);
- the eight news-enriched by-elections and the 11 / 34 / 45 fitting-cell
  split: ``news_features/byelection_enrichment_v1/byelection_enrichment.json``;
- the sealed scope: ``news_features/blinded_2026_predictions_v2/
  frozen_protocol.json`` (832 blinded candidate rows, 45 fitting rows,
  seven Reform-era cells); the two holdout-period by-elections are the
  ones polled on or after 7 May 2026, the primary-holdout boundary of
  the Stage 1 technical report;
- the blind case: ``woking-south-2025-07-10``, the contest of the
  pre-registered protocol in ``news_features/woking_south_blind_v1/``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

QUALITY = Path(
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "data_quality_report.json")
ENRICHMENT = Path(
    "news_features/byelection_enrichment_v1/byelection_enrichment.json")
PROTOCOL = Path(
    "news_features/blinded_2026_predictions_v2/frozen_protocol.json")
OUTPUT = Path("outputs/report_figures_v1")

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED = "#333333", "#666666"
BLUE_FACE, ORANGE_FACE = "#eaf1fb", "#fdeee2"

HOLDOUT_BOUNDARY = date(2026, 5, 7)
BLIND_CASE = "surrey-county-council-by-election-woking-south-2025-07-10"


def _counts() -> dict:
    quality = json.loads(QUALITY.read_text(encoding="utf-8"))
    enrichment = json.loads(ENRICHMENT.read_text(encoding="utf-8"))
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))

    election_ids = sorted(quality["party_counts_by_election"])
    by_elections = [e for e in election_ids if "by-election" in e]
    principals = [e for e in election_ids if "by-election" not in e]
    sealed = {e for e in by_elections
              if date.fromisoformat(e[-10:]) >= HOLDOUT_BOUNDARY}
    enriched = set(enrichment["by_election_event_ids"])
    stage1_only = set(by_elections) - enriched - sealed - {BLIND_CASE}

    assert quality["elections"] == 24 and quality["rows"] == 1992
    assert quality["contests"] == 343
    assert len(principals) == 5 and len(by_elections) == 19
    assert len(enriched) == 8 and len(sealed) == 2 and len(stage1_only) == 8
    assert enrichment["general_election_cells"] == 11
    assert enrichment["total_cells"] == 45
    assert protocol["blinded_candidate_rows"] == 832
    reform_cells = [c for c in protocol["reform_fitting_cells"]
                    if "by-election" in c["election_id"]]
    return {"reform_era_cells": len(reform_cells) + 1,
            "blinded_rows": protocol["blinded_candidate_rows"]}


def _box(ax, xy, width, height, title, subtitle="", sealed=False,
         subtitle_size=9.5, title_frac=0.66, subtitle_frac=0.30):
    x, y = xy
    edge, face = ((ORANGE, ORANGE_FACE) if sealed else (BLUE, BLUE_FACE))
    ax.add_patch(FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.5, edgecolor=edge, facecolor=face, zorder=3))
    if subtitle:
        ax.text(x + width / 2, y + height * title_frac, title, ha="center",
                va="center", fontsize=11.5, color=INK, weight="bold",
                zorder=4)
        ax.text(x + width / 2, y + height * subtitle_frac, subtitle,
                ha="center", va="center", fontsize=subtitle_size,
                color=MUTED, zorder=4, linespacing=1.35)
    else:
        ax.text(x + width / 2, y + height / 2, title, ha="center",
                va="center", fontsize=11.5, color=INK, weight="bold",
                zorder=4)


def _drop(ax, x_from, y_from, x_to, y_to):
    """Elbow connector: down from the parent, across, into the child."""
    y_mid = (y_from + y_to) / 2
    ax.plot([x_from, x_from, x_to], [y_from, y_mid, y_mid],
            color=MUTED, linewidth=1.4, zorder=2)
    ax.add_patch(FancyArrowPatch((x_to, y_mid), (x_to, y_to),
                                 arrowstyle="-|>", mutation_scale=13,
                                 linewidth=1.4, color=MUTED, zorder=2))


def _spine(ax, x, y_from, children):
    """File-tree spine: one vertical line with a stub into each child."""
    lowest = min(y for y, _ in children)
    ax.plot([x, x], [y_from, lowest], color=MUTED, linewidth=1.4, zorder=2)
    for y, x_child in children:
        ax.add_patch(FancyArrowPatch((x, y), (x_child, y),
                                     arrowstyle="-|>", mutation_scale=13,
                                     linewidth=1.4, color=MUTED, zorder=2))


def main() -> None:
    counts = _counts()

    fig, ax = plt.subplots(figsize=(11.0, 7.8))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 9.3)
    ax.axis("off")

    _box(ax, (2.5, 8.15), 6.0, 1.0,
         "Surrey county-level election record, 2013\u20132026",
         "24 events \u00b7 343 contests \u00b7 1,992 candidate rows")

    # Split into the two families.
    _drop(ax, 4.4, 8.15, 2.55, 6.85)
    _drop(ax, 6.6, 8.15, 8.35, 6.85)
    _box(ax, (0.45, 5.95), 4.2, 0.9, "5 principal elections",
         "2013 \u00b7 2017 \u00b7 2021 \u00b7 2026 East + West")
    _box(ax, (6.25, 5.95), 4.3, 0.9, "19 by-elections", "2015\u20132026")

    # Principal-election roles.
    _spine(ax, 0.85, 5.95, [(5.05, 1.15), (3.75, 1.15), (2.45, 1.15)])
    _box(ax, (1.15, 4.65), 3.5, 0.8, "2013",
         "start of the training history")
    _box(ax, (1.15, 3.35), 3.5, 0.8, "2017 + 2021",
         "successive validation")
    _box(ax, (1.15, 2.05), 3.5, 0.8, "2026 East + West Surrey",
         f"sealed final test \u00b7 {counts['blinded_rows']} candidates, "
         "frozen", sealed=True)

    # By-election roles.
    _spine(ax, 6.65, 5.95, [(5.05, 6.95), (0.65, 6.75)])
    _box(ax, (6.95, 4.65), 3.6, 0.8, "17 enter the Stage 1 baseline")
    _spine(ax, 7.25, 4.65, [(3.75, 7.55), (2.75, 7.55), (1.83, 7.30)])
    _box(ax, (7.55, 3.35), 3.15, 0.8,
         "8 also enter the\nnews analysis")
    _box(ax, (7.55, 2.45), 3.15, 0.6, "8 Stage 1 only")
    _box(ax, (7.30, 1.42), 3.55, 0.82, "Woking South (2025)",
         "Tests whether the method transfers\nto a different election",
         sealed=True, subtitle_size=8.7, title_frac=0.74,
         subtitle_frac=0.34)
    _box(ax, (6.75, 0.05), 4.10, 1.20, "2 sealed 2026 by-elections",
         "Haslemere (7 Jul): Tests whether the results\n"
         "replicate on another election\n"
         "Warlingham (7 May): Kept unused —\n"
         "saved for a future test",
         sealed=True, subtitle_size=8.7, title_frac=0.84,
         subtitle_frac=0.38)

    ax.text(0.45, 0.45, "blue = enters fitting", fontsize=9.5, color=BLUE)
    ax.text(0.45, 0.12, "orange = sealed / blind evaluation only",
            fontsize=9.5, color=ORANGE)
    fig.tight_layout()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT / "fig0_study_design.png", dpi=200)
    plt.close(fig)
    print("wrote", OUTPUT / "fig0_study_design.png")


if __name__ == "__main__":
    main()
