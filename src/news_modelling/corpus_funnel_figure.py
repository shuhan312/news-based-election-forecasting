"""Draw the corpus construction as a proportional funnel, not a flowchart.

    PYTHONPATH=src .venv/bin/python -m news_modelling.corpus_funnel_figure

Three horizontal bars whose lengths are article counts: the candidate
articles the eligibility pipeline assessed, the usable v1 corpus, and
the v2 corpus after by-election enrichment. Each bar splits into its
local and national arms, so the figure shows at once what a box
flowchart hides: the scale of the reduction, how small the local arm is
at every stage, and that enrichment grew the national arm only. Layer
coverage and feature-table shapes ride as a footnote because they are
different units (records and rows, not articles).

Every count is read from committed evidence:

- candidate articles: the three disjoint adjudication sheets hashed by
  the v1 release (via the pipeline-overview module's counter);
- v1 corpus and arms: ``canonical_corpus_release_v1.json``;
- v2 corpus and arms: ``canonical_corpus_release_v2.json``;
- extraction coverage: the production tranches, deduplicated the way
  ``build_feature_table.load_records()`` does (same helper).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from news_modelling.pipeline_overview_figure import (_candidate_counts,
                                                     _extraction_completion)

V1 = Path("news_collection/canonical_corpus_release_v1.json")
V2 = Path("news_collection/canonical_corpus_release_v2.json")
OUTPUT = Path("outputs/report_figures_v1")

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, DROP = "#333333", "#666666", "#d9dde2"


def main() -> None:
    cand = _candidate_counts()
    v1 = json.loads(V1.read_text())["usable_feature_corpus"]
    v2 = json.loads(V2.read_text())["usable_feature_corpus"]
    layers = _extraction_completion()

    assert cand["total"] == 2666 and v1["articles"] == 1632
    assert v2["articles"] == 2259 and v2["by_arm"]["national"] == 2071

    bars = [
        ("Candidate articles assessed", cand["local"], cand["national"], 0),
        ("Usable corpus, v1 (principal elections)",
         v1["by_arm"]["local"], v1["by_arm"]["national"],
         cand["total"] - v1["articles"]),
        ("Corpus v2 (+627 by-election articles, national arm)",
         v2["by_arm"]["local"], v2["by_arm"]["national"], 0),
    ]

    fig, ax = plt.subplots(figsize=(9.6, 3.4))
    for i, (label, local, national, dropped) in enumerate(bars):
        y = -i
        ax.barh(y, local, left=0, height=0.52, color=ORANGE, zorder=3)
        ax.barh(y, national, left=local, height=0.52, color=BLUE, zorder=3)
        if dropped:
            ax.barh(y, dropped, left=local + national, height=0.52,
                    color=DROP, zorder=3)
            ax.annotate(f"{dropped:,} excluded",
                        (local + national + dropped / 2 + 90, y),
                        ha="center", va="center", fontsize=8.5, color=MUTED)
        ax.annotate(f"{local}", (local / 2, y), ha="center", va="center",
                    fontsize=8.5, color="white", weight="bold")
        ax.annotate(f"{national:,}", (local + national / 2, y),
                    ha="center", va="center", fontsize=9.5, color="white",
                    weight="bold")
        total = local + national
        ax.annotate(f"{total:,}", (local + national + 30, y),
                    ha="left", va="center", fontsize=10.5, color=INK,
                    weight="bold", zorder=4)
        ax.text(0, y + 0.44, label, ha="left", va="bottom", fontsize=10,
                color=INK)

    ax.set_xlim(0, 2980)
    ax.set_ylim(-2.55, 0.95)
    ax.axis("off")
    ax.legend(handles=[Patch(color=ORANGE, label="local arm"),
                       Patch(color=BLUE, label="national arm"),
                       Patch(color=DROP, label="excluded at screening")],
              loc="lower right", frameon=False, fontsize=9,
              bbox_to_anchor=(1.0, -0.16), ncol=3, columnspacing=1.1)
    fig.text(0.005, 0.015,
             f"Extraction coverage on v1: issues {layers['issues']:,} / "
             f"stance {layers['stance_revised']:,} / framing "
             f"{layers['framing_revised']:,} of 1,632 articles; feature "
             "tables: 288 rows (v1), 864 rows (v2).",
             fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT / "fig0b_corpus_funnel.png", dpi=200)
    plt.close(fig)
    print("wrote", OUTPUT / "fig0b_corpus_funnel.png")


if __name__ == "__main__":
    main()
