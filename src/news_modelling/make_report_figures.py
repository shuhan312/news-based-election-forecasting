"""Generate the report's four core figures from the archived results.

    PYTHONPATH=src .venv/bin/python -m news_modelling.make_report_figures

Everything drawn here is read from committed evidence - the unblinding
record, the canonical v2 release and the Stage 1 holdout file - so each
figure can be regenerated with one command and every plotted number can
be traced to its register section. The module draws; it computes nothing
new. Colours are the validated defaults (blue #2a78d6 / orange #eb6834
categorical pair; blue/red as the diverging improvement/harm pair; both
pairs pass the palette validator's CVD and contrast checks), marks are
thin, axes recessive, and values are labelled directly so no figure
depends on colour alone.

Figure 1 - the confirmatory answer. Diverging horizontal bars of the
news-versus-recalibrated MAE delta for all 24 confirmatory cells,
v1 beside v2, with contest-bootstrap 95% whiskers. Blue = news better,
red = news worse; the v1 panel being all red and the v2 panel splitting
by window IS the project's headline, visible in one glance.

Figure 2 - the seat-level reversal. Predicted against actual seat
totals per party under the history-only baseline: the Conservative 118
against 30 and Liberal Democrat 6 against 96 bars are the realignment
the baseline could not see.

Figure 3 - the corpus by window. Article counts per confirmed window in
canonical release v2; the far-window skew that qualifies every
near-polling-day conclusion.

Figure 4 - the transfer failure in one picture. The bootstrap annex's
Reform-minus-fitted-group level contrast for every specification on
both evaluation islands, with its paired contest-bootstrap interval:
the 2021 panel sits almost entirely left of zero (the borrowed
adjustment flattered Reform) and the 2026 panel almost entirely right
(it hurt Reform) - the sign flip that is the register's third
statement of the transfer failure.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

UNBLINDING = Path("news_features/unblinding_2026_v1/unblinding_results.json")
RELEASE = Path("news_collection/canonical_corpus_release_v2.json")
BOOTSTRAP = Path(
    "news_features/per_party_bootstrap_v1/per_party_bootstrap_results.json")
HOLDOUT = Path(
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "holdout_predictions.csv")
OUTPUT = Path("outputs/report_figures_v1")

BLUE, ORANGE, RED = "#2a78d6", "#eb6834", "#e34948"
INK, MUTED, GRID = "#333333", "#666666", "#e5e5e5"

WINDOW_ORDER = ["180_to_91_days", "90_to_31_days", "30_to_15_days",
                "14_to_8_days", "7_to_4_days", "final_72_hours"]
WINDOW_LABEL = {"180_to_91_days": "180-91 days", "90_to_31_days": "90-31 days",
                "30_to_15_days": "30-15 days", "14_to_8_days": "14-8 days",
                "7_to_4_days": "7-4 days", "final_72_hours": "final 72h"}


def _style(ax) -> None:
    """Recessive axes: no top/right spine, light grid behind the marks."""

    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.set_axisbelow(True)


def figure_confirmatory() -> None:
    results = json.loads(UNBLINDING.read_text(encoding="utf-8"))
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), sharex=True)

    for ax, version, title in (
            (axes[0], "v1", "v1 - before enrichment (0 of 12 improved)"),
            (axes[1], "v2", "v2 - after enrichment (5 of 12 improved)")):
        cells = [e for e in results["files"][version]
                 if e["family"] == "confirmatory"]
        rows = []
        for window in WINDOW_ORDER:
            for arm, tag in (("combined_exploratory", "combined"),
                             ("national_exploratory", "national")):
                entry = next(e for e in cells
                             if e["period"] == window and e["analysis"] == arm)
                metrics = entry["metrics"]
                ci = metrics["bootstrap_news_vs_recalibrated"]
                rows.append((
                    f"{WINDOW_LABEL[window]}  ({tag})",
                    metrics["all_supported_parties"]["news_vs_recalibrated_mae"],
                    ci.get("improvement_ci_lower", 0),
                    ci.get("improvement_ci_upper", 0),
                ))
        y = range(len(rows), 0, -1)
        for position, (label, delta, low, high) in zip(y, rows):
            colour = BLUE if delta > 0 else RED
            ax.barh(position, delta, height=0.55, color=colour, zorder=3)
            ax.plot([low, high], [position, position],
                    color=INK, linewidth=1, zorder=4)
            # Anchor the label outside the whisker's far end, not the bar
            # tip, so the interval line never strikes through the number.
            anchor = max(high, delta) if delta >= 0 else min(low, delta)
            ax.annotate(f"{delta:+.2f}",
                        xy=(anchor, position),
                        xytext=(4 if delta >= 0 else -4, 0),
                        textcoords="offset points",
                        va="center", ha="left" if delta >= 0 else "right",
                        fontsize=7.5, color=INK)
        ax.axvline(0, color=MUTED, linewidth=1)
        ax.set_yticks(list(y))
        ax.set_yticklabels([r[0] for r in rows], fontsize=8, color=INK)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        _style(ax)

    axes[0].set_xlabel("news vs recalibrated control, MAE delta "
                       "(right of zero = news better)", fontsize=9,
                       color=MUTED)
    fig.suptitle("Did news improve 2026 vote-share prediction? "
                 "The 24 pre-registered comparisons",
                 fontsize=12, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.005,
             "Whiskers: contest-bootstrap 95% intervals (2,000 resamples). "
             "Source: unblinding record, register section 16.",
             fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(OUTPUT / "fig1_confirmatory_deltas.png", dpi=200)
    plt.close(fig)


def figure_seats() -> None:
    with HOLDOUT.open(encoding="utf-8", newline="") as handle:
        rows = [r for r in csv.DictReader(handle)
                if r["election_id"].startswith("surrey-county-council-2026")]
    predicted, actual = Counter(), Counter()
    main = {"Liberal Democrats", "Conservative", "Reform UK",
            "The Green Party", "Independent", "Labour"}
    for row in rows:
        party = row["standard_party_name"]
        group = party if party in main else "Residents' assocs & other local"
        predicted[group] += row["predicted_elected"] == "True"
        actual[group] += row["observed_elected"] == "True"

    order = sorted(actual, key=lambda party: -actual[party])
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    positions = range(len(order), 0, -1)
    for position, party in zip(positions, order):
        # 2px-equivalent gap between the pair; hatch doubles as the
        # print/CVD secondary encoding for "predicted".
        ax.barh(position + 0.19, predicted[party], height=0.34, color=BLUE,
                hatch="//", edgecolor="white", linewidth=0.5, zorder=3,
                label="predicted" if position == len(order) else None)
        ax.barh(position - 0.19, actual[party], height=0.34, color=ORANGE,
                zorder=3, label="actual" if position == len(order) else None)
        ax.annotate(str(predicted[party]),
                    xy=(predicted[party], position + 0.19),
                    xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=8, color=INK)
        ax.annotate(str(actual[party]),
                    xy=(actual[party], position - 0.19),
                    xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=8, color=INK)
    ax.set_yticks(list(positions))
    ax.set_yticklabels(order, fontsize=9, color=INK)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.set_xlabel("seats (162 available across 81 two-member wards)",
                  fontsize=9, color=MUTED)
    ax.set_title("Baseline seat totals, predicted vs actual:\n"
                 "the realignment election history could not see",
                 fontsize=11, color=INK, loc="left")
    _style(ax)
    fig.text(0.01, 0.005,
             "Source: Stage 1 holdout predictions vs observed results; "
             "register section 16 addendum.", fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUTPUT / "fig2_seat_totals.png", dpi=200)
    plt.close(fig)


def figure_corpus() -> None:
    release = json.loads(RELEASE.read_text(encoding="utf-8"))
    counts = release["usable_feature_corpus"]["by_window"]
    values = [counts.get(window, 0) for window in WINDOW_ORDER]

    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    x = range(len(WINDOW_ORDER))
    ax.bar(x, values, width=0.62, color=BLUE, zorder=3)
    for position, value in zip(x, values):
        ax.annotate(f"{value:,}", xy=(position, value), xytext=(0, 3),
                    textcoords="offset points", ha="center",
                    fontsize=8.5, color=INK)
    ax.set_xticks(list(x))
    ax.set_xticklabels([WINDOW_LABEL[w] for w in WINDOW_ORDER],
                       fontsize=9, color=INK)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_ylabel("articles", fontsize=9, color=MUTED)
    ax.set_title("The corpus is far-window heavy: canonical v2 articles "
                 "per confirmed window (2,259 total)",
                 fontsize=11, color=INK, loc="left")
    _style(ax)
    fig.text(0.01, 0.005,
             "Source: canonical-news-v2-81000bf38785; register section 15. "
             "Near-polling windows hold tens of articles, not thousands - "
             "the qualifier on every late-window conclusion.",
             fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(OUTPUT / "fig3_corpus_windows.png", dpi=200)
    plt.close(fig)


def figure_island_contrast() -> None:
    """Figure 4: the Reform-versus-group contrast on both islands.

    One horizontal bar per specification, whiskered with the annex's
    paired interval - the interval belongs to the difference itself,
    because Reform and the group mean are recomputed inside every
    draw. Red = Reform's level handled worse than the fitted parties',
    blue = better, grey = structural-zero windows (no in-window
    signal, so news equals the recalibrated control exactly).
    """

    annex = json.loads(BOOTSTRAP.read_text(encoding="utf-8"))
    quantity = "abs_bias_change_vs_recalibrated"
    islands = (
        ("validation_2021", "2021 validation - fit: five 2017 party rows, "
                            "ZERO Reform rows",
         (("combined_exploratory", "combined"),
          ("national_exploratory", "national"),
          ("local_sensitivity", "local"))),
        ("holdout_2026_v2", "2026 holdout v2 - fit: 45 cells, seven "
                            "Reform-era",
         (("combined_exploratory", "combined"),
          ("national_exploratory", "national"))),
    )
    by_key = {(s["island"], s["analysis"], s["period"]): s
              for s in annex["specifications"]}

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 6.0), sharex=True)
    # Value labels hang outside the whisker's far end, so the shared
    # x-range needs headroom beyond the widest interval on either side
    # or the leftmost label collides with the y-axis tick text.
    all_bounds = [spec["bootstrap"]["units"]["contrast"][quantity].get(k, 0.0)
                  for spec in annex["specifications"]
                  for k in ("ci_lower", "ci_upper")]
    axes[0].set_xlim(min(all_bounds) - 5.5, max(all_bounds) + 5.5)
    for ax, (island, subtitle, arms) in zip(axes, islands):
        rows = []
        for window in WINDOW_ORDER:
            for arm, tag in arms:
                spec = by_key[(island, arm, window)]
                interval = spec["bootstrap"]["units"]["contrast"][quantity]
                rows.append((f"{WINDOW_LABEL[window]}  ({tag})",
                             spec["contrast_point"][quantity],
                             interval.get("ci_lower", 0.0),
                             interval.get("ci_upper", 0.0)))
        starred_neg = sum(1 for _l, _d, low, high in rows if high < 0)
        starred_pos = sum(1 for _l, _d, low, high in rows if low > 0)
        y = range(len(rows), 0, -1)
        for position, (label, delta, low, high) in zip(y, rows):
            colour = (MUTED if low == high == delta == 0
                      else RED if delta > 0 else BLUE)
            ax.barh(position, delta, height=0.55, color=colour, zorder=3)
            ax.plot([low, high], [position, position],
                    color=INK, linewidth=1, zorder=4)
            anchor = max(high, delta) if delta >= 0 else min(low, delta)
            ax.annotate(f"{delta:+.1f}", xy=(anchor, position),
                        xytext=(4 if delta >= 0 else -4, 0),
                        textcoords="offset points", va="center",
                        ha="left" if delta >= 0 else "right",
                        fontsize=7.5, color=INK)
        ax.axvline(0, color=MUTED, linewidth=1)
        ax.set_yticks(list(y))
        ax.set_yticklabels([r[0] for r in rows], fontsize=8, color=INK)
        ax.set_title(f"{subtitle}\n({starred_neg} starred negative, "
                     f"{starred_pos} starred positive)",
                     fontsize=10, color=INK, loc="left")
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        _style(ax)

    axes[0].set_xlabel("Reform |level-error| change minus fitted-party "
                       "mean (left of zero = Reform handled better)",
                       fontsize=9, color=MUTED)
    fig.suptitle("The transfer failure in one picture: the Reform "
                 "contrast flips sign between evaluation islands",
                 fontsize=12, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.005,
             "Whiskers: paired contest-bootstrap 95% intervals (2,000 "
             "resamples; Reform and the group mean recomputed in the same "
             "draws). Grey bars: structural-zero windows.\nVersus the "
             "recalibrated control. Source: per-party bootstrap annex "
             "(register addendum); exploratory, promotes nothing.",
             fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.055, 1, 0.94))
    fig.savefig(OUTPUT / "fig4_island_contrast.png", dpi=200)
    plt.close(fig)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figure_confirmatory()
    figure_seats()
    figure_corpus()
    figure_island_contrast()
    for name in ("fig1_confirmatory_deltas", "fig2_seat_totals",
                 "fig3_corpus_windows", "fig4_island_contrast"):
        print(f"-> {OUTPUT / name}.png")


if __name__ == "__main__":
    main()
