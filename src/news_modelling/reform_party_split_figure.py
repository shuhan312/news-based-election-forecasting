"""Reform vs non-Reform per-party delta-MAE by window (frozen combined arm).

Draws the "helps others, hurts Reform" split as a clean grouped bar chart,
replacing the a19 table. Data source: reform_decomposition.json (frozen arm).
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "news_features" / "reform_decomposition_v1" / "reform_decomposition.json"
OUT = ROOT / "report" / "figures" / "fig8_reform_party_split.png"
OUT2 = ROOT / "outputs" / "report_figures_v1" / "fig8_reform_party_split.png"

WINDOW_LABELS = {
    "180_to_91_days": "180-91 d",
    "90_to_31_days": "90-31 d",
    "30_to_15_days": "30-15 d",
    "14_to_8_days": "14-8 d",
    "7_to_4_days": "7-4 d",
    "final_72_hours": "final 72h",
}


def main():
    data = json.loads(SRC.read_text())
    frozen = data["arms"]["frozen"]

    windows = [WINDOW_LABELS[item["window"]] for item in frozen]
    non_reform = [item["non_reform"]["delta"] for item in frozen]
    reform = [item["reform"]["delta"] for item in frozen]
    overall = [item["all"]["delta"] for item in frozen]
    n_nr = frozen[0]["non_reform"]["n"]
    n_rf = frozen[0]["reform"]["n"]
    n_all = frozen[0]["all"]["n"]

    x = np.arange(len(windows))
    w = 0.27

    fig, ax = plt.subplots(figsize=(11.5, 5.8))
    ax.bar(x - w, non_reform, w, label=f"Non-Reform (n={n_nr})", color="#2166ac")
    ax.bar(x, overall, w, label=f"Overall (n={n_all})", color="#9e9e9e")
    ax.bar(x + w, reform, w, label=f"Reform UK (n={n_rf})", color="#b2182b")

    ax.axhline(0, color="black", linewidth=0.8)

    # label every bar at its tip: positive above, negative below
    def label_bars(vals, xpos):
        for xi, v in zip(xpos, vals):
            above = v >= 0
            ax.annotate(f"{v:+.2f}", (xi, v),
                        textcoords="offset points",
                        xytext=(0, 3 if above else -11),
                        ha="center", va="bottom" if above else "top",
                        fontsize=7)

    label_bars(non_reform, x - w)
    label_bars(overall, x)
    label_bars(reform, x + w)

    allvals = reform + non_reform + overall
    lo, hi = min(allvals), max(allvals)
    ax.set_ylim(lo - 0.45, hi + 0.35)

    ax.set_xticks(x)
    ax.set_xticklabels(windows)
    ax.set_ylabel(r"$\Delta$MAE  (positive = news lowered error)")
    ax.set_title("News lowered error for non-Reform candidates but raised "
                 "it for Reform UK",
                 fontsize=12, weight="bold")
    # legend outside the plot area (right), never overlaps bars
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)

    ax.grid(axis="y", linestyle=":", alpha=0.4)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT2.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=200, bbox_inches="tight")
    fig.savefig(OUT2, dpi=200, bbox_inches="tight")
    print(f"saved: {OUT}")
    print(f"saved: {OUT2}")


if __name__ == "__main__":
    main()
