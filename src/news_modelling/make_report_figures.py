"""Generate the report's six core figures from the archived results.

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

Figure 1 - the confirmatory answer, as a forest plot. Points are the
news-versus-recalibrated MAE delta for all 24 confirmatory cells,
v1 in the left panel and v2 in the right, sharing one x-axis so neither
panel is rescaled to look better than the other. Combined and national
news are offset within each window (circle vs square) rather than
listed as separate rows, and whiskers are the same contest-bootstrap
95% intervals as before. v1 has no window where both arms clear zero;
v2's 31-90-day window is the only one where both do.

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

Figure 5 - each party against its own detection threshold. Per-party
level changes in the headline window beside that party's MDE80, so a
cell reads as "cleared its threshold" or "sits inside the blind zone".
The thresholds are not interchangeable: |bias| has a corner at zero,
so an already well-calibrated party (Green) has a blind zone an order
of magnitude wider than a party of the same size.

Figure 6 - mechanism against outcome. Per-party level corrections for
every window (diverging heatmap) above the overall MAE delta the same
specifications produced: the loudest per-party corrections sit in the
window with the worst overall outcome, because the same adjustment
throws Green and Reform the wrong way. A mechanism that demonstrably
works is not the same thing as an accuracy gain.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

UNBLINDING = Path("news_features/unblinding_2026_v1/unblinding_results.json")
RELEASE = Path("news_collection/canonical_corpus_release_v2.json")
BOOTSTRAP = Path(
    "news_features/per_party_bootstrap_v1/per_party_bootstrap_results.json")
MDE = Path("news_features/minimal_detectable_effect_v1/mde_results.json")
HOLDOUT = Path(
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "holdout_predictions.csv")
OUTPUT = Path("outputs/report_figures_v1")

BLUE, ORANGE, RED = "#2a78d6", "#eb6834", "#e34948"
INK, MUTED, GRID = "#333333", "#666666", "#e5e5e5"

WINDOW_ORDER = ["180_to_91_days", "90_to_31_days", "30_to_15_days",
                "14_to_8_days", "7_to_4_days", "final_72_hours"]
WINDOW_LABEL = {"180_to_91_days": "91–180 days", "90_to_31_days": "31–90 days",
                "30_to_15_days": "15–30 days", "14_to_8_days": "8–14 days",
                "7_to_4_days": "4–7 days", "final_72_hours": "1–3 days"}


def _style(ax) -> None:
    """Recessive axes: no top/right spine, light grid behind the marks."""

    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.set_axisbelow(True)


def figure_confirmatory() -> None:
    """Forest plot: all 24 frozen confirmatory MAE deltas, v1 vs v2,
    combined/national offset within each window, one shared x-axis.
    """

    results = json.loads(UNBLINDING.read_text(encoding="utf-8"))
    markers = {"combined_exploratory": "o", "national_exploratory": "s"}
    colours = {"combined_exploratory": BLUE, "national_exploratory": ORANGE}
    tags = {"combined_exploratory": "Combined", "national_exploratory": "National"}
    offsets = {"combined_exploratory": 0.13, "national_exploratory": -0.13}

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.6), sharex=True, sharey=True)

    for ax, version, title in ((axes[0], "v1", "(a) v1"),
                               (axes[1], "v2", "(b) v2")):
        cells = [e for e in results["files"][version]
                 if e["family"] == "confirmatory"]
        y_base = {window: i for i, window in enumerate(reversed(WINDOW_ORDER))}
        for arm in ("combined_exploratory", "national_exploratory"):
            for window in WINDOW_ORDER:
                entry = next(e for e in cells
                             if e["period"] == window and e["analysis"] == arm)
                metrics = entry["metrics"]["all_supported_parties"]
                ci = entry["metrics"]["bootstrap_news_vs_recalibrated"]
                delta = metrics["news_vs_recalibrated_mae"]
                low, high = ci.get("improvement_ci_lower", 0), ci.get("improvement_ci_upper", 0)
                y = y_base[window] + offsets[arm]
                ax.errorbar(delta, y, xerr=[[delta - low], [high - delta]],
                            fmt=markers[arm], color=colours[arm],
                            ecolor=colours[arm], elinewidth=1.3, capsize=3,
                            markersize=6, markeredgecolor="white",
                            markeredgewidth=0.6, linewidth=0, zorder=3)
                anchor, align = (high, "left") if delta >= 0 else (low, "right")
                ax.annotate(f"{delta:+.2f}", xy=(anchor, y),
                            xytext=(7 if delta >= 0 else -7, 0),
                            textcoords="offset points", va="center", ha=align,
                            fontsize=6.8, color=INK)
        ax.axvline(0, color=MUTED, linewidth=1, linestyle="--")
        ax.set_yticks(list(y_base.values()))
        ax.set_yticklabels([WINDOW_LABEL[w] for w in reversed(WINDOW_ORDER)],
                           fontsize=8, color=INK)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.grid(False)
        _style(ax)

    axes[0].set_xlabel("news vs recalibrated control, MAE delta "
                       "(right of zero = news better)", fontsize=9, color=MUTED)
    axes[1].set_xlabel("news vs recalibrated control, MAE delta "
                       "(right of zero = news better)", fontsize=9, color=MUTED)

    handles = [Line2D([0], [0], marker="o", color=BLUE, linestyle="",
                      markersize=6, markeredgecolor="white", label="Combined"),
              Line2D([0], [0], marker="s", color=ORANGE, linestyle="",
                      markersize=6, markeredgecolor="white", label="National")]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False,
              fontsize=9, bbox_to_anchor=(0.5, 1.02))
    fig.text(0.01, 0.005,
             "Whiskers: contest-bootstrap 95% intervals (2,000 resamples). "
             "Source: unblinding record, register section 16.",
             fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
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
             "Source: canonical-news-v2-81000bf38785; register section 15.\n"
             "Near-polling windows hold tens of articles, not thousands - "
             "the qualifier on every late-window conclusion.",
             fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
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


def figure_party_resolution() -> None:
    """Figure 5: each party's effect against its OWN detection threshold.

    The grey bar is that party's blind zone - every effect smaller than
    its MDE80 is indistinguishable from resampling noise - and the dot
    is the level change actually observed, blue where news improved the
    party's level and red where it worsened it. A dot inside the grey
    bar is a cell the design could not certify in either direction.

    Thresholds are per party for a reason: |bias| has a corner at zero,
    so a party already well calibrated (Green) has resampled biases
    folded across that corner and a much wider blind zone than a party
    of similar size. Panels do not share an x-axis - the 2021 island is
    an order of magnitude coarser - so the two are read separately.
    """

    mde = json.loads(MDE.read_text(encoding="utf-8"))
    rows = [r for r in mde["comparisons"]
            if r["scope"] == "party_level" and r["window"] == "90_to_31_days"
            and r["arm"] == "combined_exploratory" and r["status"] == "ok"]

    panels = (("validation_2021",
               "2021 validation - fit: five 2017 party rows, ZERO Reform"),
              ("holdout_2026_v2",
               "2026 holdout v2 - fit: 45 cells, seven Reform-era"))
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    for ax, (island, subtitle) in zip(axes, panels):
        members = sorted((r for r in rows if r["island"] == island),
                         key=lambda r: -abs(r["observed_delta"]))
        y = range(len(members), 0, -1)
        for position, row in zip(y, members):
            threshold = row["mde_80_power"]
            effect = abs(row["observed_delta"])
            improved = row["observed_delta"] < 0
            ax.barh(position, threshold, height=0.62, color=GRID, zorder=2)
            ax.scatter([effect], [position], s=46, zorder=4,
                       color=BLUE if improved else RED,
                       edgecolor="white", linewidth=0.8)
            inside = effect < threshold
            # Inside the blind zone the dot sits left of the bar's end,
            # so the value goes ABOVE it and the verdict to the bar's
            # right - otherwise the two labels land on the same spot.
            ax.annotate(f"{row['observed_delta']:+.2f}",
                        xy=(effect, position),
                        xytext=(0, 9) if inside else (7, 0),
                        textcoords="offset points",
                        va="center", ha="center" if inside else "left",
                        fontsize=7.5, color=INK)
            if inside:
                # Name the verdict in text: colour alone must not carry it.
                ax.annotate("not detectable", xy=(threshold, position),
                            xytext=(7, 0), textcoords="offset points",
                            va="center", fontsize=7, color=MUTED)
        ax.set_yticks(list(y))
        ax.set_yticklabels([r["party"].replace("_", " ") for r in members],
                           fontsize=8.5, color=INK)
        ax.set_xlim(0, max(max(abs(r["observed_delta"]), r["mde_80_power"])
                           for r in members) * 1.35)
        ax.set_title(subtitle, fontsize=9.5, color=INK, loc="left")
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        _style(ax)
    # Proxy handles: the per-row artists only carry one colour each, so
    # a legend built from them would silently drop whichever verdict the
    # top row does not happen to be.
    handles = [
        Patch(facecolor=GRID, label="blind zone (effect below MDE80)"),
        Line2D([], [], marker="o", linestyle="none", color=BLUE,
               markeredgecolor="white", label="news improved the level"),
        Line2D([], [], marker="o", linestyle="none", color=RED,
               markeredgecolor="white", label="news worsened the level"),
    ]
    fig.legend(handles=handles, frameon=False, fontsize=8, ncol=3,
               loc="lower left", bbox_to_anchor=(0.01, 0.085))
    axes[0].set_xlabel("share points (note: panels use different scales)",
                       fontsize=9, color=MUTED)
    fig.suptitle("Every party judged against its own detection threshold "
                 "(combined arm, 90-31 days)",
                 fontsize=12, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.005,
             "Dot: |change in the party's election-wide level error|. Bar: "
             "MDE80, the smallest change that party's contest count and "
             "error stability could detect in ~80% of samples.\nGreen's "
             "wide blind zone is the |bias| corner at zero, not a small "
             "sample. Source: design-resolution annex; exploratory.",
             fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.16, 1, 0.93))
    fig.savefig(OUTPUT / "fig5_party_resolution.png", dpi=200)
    plt.close(fig)


def figure_mechanism_vs_outcome() -> None:
    """Figure 6: why big per-party corrections do not buy accuracy.

    Top - the mechanism layer: each party's election-wide level error
    change, every window, as a diverging heatmap (blue = news reduced
    that party's level error, red = increased it). Bottom - the outcome
    layer: the overall MAE delta the same specifications produced, with
    contest-bootstrap intervals.

    The two layers use OPPOSITE sign conventions because they measure
    opposite-facing quantities - a level ERROR falling is negative, an
    accuracy GAIN is positive - so each panel states its own, and
    colour is harmonised instead: blue means news helped in both.

    Reading it: at 180-91 days the mechanism layer is at its loudest
    (Liberal Democrat -4.84, Conservative -1.78) and the outcome layer
    is at its worst (-0.575), because the same adjustment threw Green
    +5.06 and Reform +4.63 the wrong way. At 90-31 days every party
    moves less and the outcome turns positive. The panels are NOT an
    arithmetic decomposition of each other - MAE is over absolute
    errors and also carries dispersion - so this is a juxtaposition,
    not a budget.
    """

    annex = json.loads(BOOTSTRAP.read_text(encoding="utf-8"))
    unblinding = json.loads(UNBLINDING.read_text(encoding="utf-8"))
    arm = "combined_exploratory"
    quantity = "abs_bias_change_vs_recalibrated"
    parties = ["conservative", "liberal_democrat", "labour",
               "green", "reform_uk"]

    grid = []
    for party in parties:
        row = []
        for window in WINDOW_ORDER:
            spec = next(s for s in annex["specifications"]
                        if s["island"] == "holdout_2026_v2"
                        and s["analysis"] == arm and s["period"] == window)
            row.append(spec["parties"][party][quantity])
        grid.append(row)
    matrix = np.array(grid)

    outcome, lows, highs = [], [], []
    for window in WINDOW_ORDER:
        entry = next(e for e in unblinding["files"]["v2"]
                     if e["family"] == "confirmatory"
                     and e["analysis"] == arm and e["period"] == window)
        ci = entry["metrics"]["bootstrap_news_vs_recalibrated"]
        outcome.append(entry["metrics"]["all_supported_parties"]
                       ["news_vs_recalibrated_mae"])
        lows.append(ci.get("improvement_ci_lower", 0.0))
        highs.append(ci.get("improvement_ci_upper", 0.0))

    # Diverging ramp: two hues around a neutral midpoint, never a hue
    # at zero. Symmetric limits so equal magnitudes read equally.
    ramp = LinearSegmentedColormap.from_list(
        "helped_harmed", [BLUE, "#f2f2f0", RED])
    limit = float(np.abs(matrix).max())

    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(10.5, 6.6), sharex=True,
        gridspec_kw={"height_ratios": [5, 2.4], "hspace": 0.12})

    top.imshow(matrix, cmap=ramp, vmin=-limit, vmax=limit, aspect="auto")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            # Ink on pale cells, white on saturated ones, so the value
            # is legible without depending on the fill's hue.
            shade = INK if abs(value) < limit * 0.55 else "white"
            top.text(j, i, f"{value:+.2f}", ha="center", va="center",
                     fontsize=8.5, color=shade)
    top.set_yticks(range(len(parties)))
    top.set_yticklabels([p.replace("_", " ") for p in parties],
                        fontsize=9, color=INK)
    top.set_xticks(range(len(WINDOW_ORDER)))
    top.tick_params(colors=MUTED, labelsize=9, length=0)
    for side in top.spines.values():
        side.set_visible(False)
    top.set_title("Mechanism layer - change in each party's election-wide "
                  "level error (negative = news reduced it)",
                  fontsize=10, color=INK, loc="left", pad=8)

    for position, (value, low, high) in enumerate(zip(outcome, lows, highs)):
        bottom.bar(position, value, width=0.6, zorder=3,
                   color=BLUE if value > 0 else RED)
        bottom.plot([position, position], [low, high],
                    color=INK, linewidth=1, zorder=4)
        straddles = low <= 0 <= high
        bottom.annotate(f"{value:+.3f}" + (" ns" if straddles else ""),
                        xy=(position, high if value >= 0 else low),
                        xytext=(0, 4 if value >= 0 else -12),
                        textcoords="offset points", ha="center",
                        fontsize=8, color=INK)
    bottom.axhline(0, color=MUTED, linewidth=1)
    # Value labels hang past the whisker ends, so the y-range needs
    # headroom or the lowest one lands on the x tick labels.
    bottom.set_ylim(min(lows) * 1.45, max(highs) * 1.30)
    bottom.set_xticks(range(len(WINDOW_ORDER)))
    bottom.set_xticklabels([WINDOW_LABEL[w] for w in WINDOW_ORDER],
                           fontsize=9, color=INK)
    bottom.set_ylabel("MAE gain", fontsize=9, color=MUTED)
    bottom.grid(axis="y", color=GRID, linewidth=0.8)
    bottom.set_title("Outcome layer - overall MAE against the recalibrated "
                     "control (positive = news better; ns = interval "
                     "includes zero)",
                     fontsize=10, color=INK, loc="left", pad=6)
    _style(bottom)

    fig.suptitle("A mechanism that works is not an accuracy gain: "
                 "2026 holdout, combined arm",
                 fontsize=12, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.005,
             "Blue = news helped in both panels; the two panels state "
             "opposite sign conventions because an error falling is "
             "negative and a gain is positive.\nThey are a juxtaposition, "
             "not a decomposition - MAE is over absolute errors and also "
             "carries dispersion. Sources: per-party bootstrap annex and "
             "the unblinding record; exploratory.",
             fontsize=7.5, color=MUTED)
    # Explicit margins, not tight_layout: an imshow axes is not
    # compatible with it and the call warns that results may be wrong.
    fig.subplots_adjust(left=0.145, right=0.99, top=0.885, bottom=0.135)
    fig.savefig(OUTPUT / "fig6_mechanism_vs_outcome.png", dpi=200)
    plt.close(fig)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figure_confirmatory()
    figure_seats()
    figure_corpus()
    figure_island_contrast()
    figure_party_resolution()
    figure_mechanism_vs_outcome()
    for name in ("fig1_confirmatory_deltas", "fig2_seat_totals",
                 "fig3_corpus_windows", "fig4_island_contrast",
                 "fig5_party_resolution", "fig6_mechanism_vs_outcome"):
        print(f"-> {OUTPUT / name}.png")


if __name__ == "__main__":
    main()
