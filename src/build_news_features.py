"""Turn the filtered Guardian articles into monthly time-series features.

For each month from Jan 2021 to May 2026 this counts:
  - how many articles mention each of the five parties
  - how many articles fall under each theme (elections, council finance,
    housing, energy), read off the queries that matched the article
  - total article volume

Output:
  data/processed/news_features_monthly.csv   the feature table
  data/processed/figures/party_mentions.png  party lines + election months
  data/processed/figures/topic_volume.png    theme lines + election months

These monthly series are the first news features (X) to set against the
ward results (y). Sentiment and LLM-based categories can be added to the
same table later.

Usage:  python src/build_news_features.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

IN_PATH = "data/processed/guardian_articles_filtered.csv"
OUT_CSV = Path("data/processed/news_features_monthly.csv")
FIG_DIR = Path("data/processed/figures")

# what to look for in the text; \b stops "Tory" matching "history"
PARTY_PATTERNS = {
    "conservative": r"\bConservative|\bTory\b|\bTories\b",
    "labour": r"\bLabour\b",
    "libdem": r"Liberal Democrat|\bLib Dem",
    "green": r"Green Party",
    "reform": r"Reform UK",
}

# themes come from which fetch query matched the article
TOPIC_MARKERS = {
    "elections": "local election",
    "council_finance": "council tax",
    "housing": "housing",
    "energy": "energy bills",
}

# conventional party colours, taken from a CVD-validated palette
PARTY_COLOURS = {
    "conservative": "#2a78d6",
    "labour": "#e34948",
    "libdem": "#eda100",
    "green": "#008300",
    "reform": "#1baf7a",
}
TOPIC_COLOURS = ["#2a78d6", "#1baf7a", "#eda100", "#4a3aa7"]

# vertical markers for the local election months in the study period
ELECTIONS = ["2021-05", "2022-05", "2023-05", "2024-05", "2026-05"]


def monthly_counts(df):
    text = df["title"].fillna("") + " " + df["body_text"].fillna("")
    out = pd.DataFrame({"month": df["published_at"].str[:7]})

    for party, pattern in PARTY_PATTERNS.items():
        out[party] = text.str.contains(pattern, regex=True).astype(int)
    for topic, marker in TOPIC_MARKERS.items():
        out[topic] = df["matched_query"].fillna("").str.contains(marker).astype(int)
    out["articles_total"] = 1

    return out.groupby("month").sum().reset_index()


def plot_lines(features, columns, colours, title, path):
    fig, ax = plt.subplots(figsize=(11, 5))
    x = range(len(features))

    for month in ELECTIONS:
        if month in set(features["month"]):
            pos = features.index[features["month"] == month][0]
            ax.axvline(pos, color="#c3c2b7", linestyle="--", linewidth=1, zorder=1)
            ax.text(pos, ax.get_ylim()[1], " elections", color="#6b6b66",
                    fontsize=8, va="top", rotation=90)

    for col, colour in zip(columns, colours):
        ax.plot(x, features[col], color=colour, linewidth=2, label=col, zorder=2)
        # label the line at its right end so the legend isn't doing all the work
        ax.annotate(col, (x[-1], features[col].iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", color=colour, fontsize=9, va="center")

    ticks = [i for i, m in enumerate(features["month"]) if m.endswith(("-01", "-07"))]
    ax.set_xticks(ticks)
    ax.set_xticklabels(features["month"].iloc[ticks], rotation=45, fontsize=8)
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("articles per month", fontsize=9)
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#eeeeea", linewidth=0.8)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"figure -> {path}")


def main():
    df = pd.read_csv(IN_PATH)
    features = monthly_counts(df)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(OUT_CSV, index=False)
    print(f"{len(features)} months -> {OUT_CSV}")

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plot_lines(features, list(PARTY_PATTERNS), list(PARTY_COLOURS.values()),
               "Guardian articles mentioning each party (monthly)",
               FIG_DIR / "party_mentions.png")
    plot_lines(features, list(TOPIC_MARKERS), TOPIC_COLOURS,
               "Guardian article volume by theme (monthly)",
               FIG_DIR / "topic_volume.png")

    # quick sanity read-out: busiest months overall, all columns shown,
    # so the terminal output actually matches what gets written to CSV
    top = features.nlargest(5, "articles_total")
    print("\nBusiest months overall (all columns):")
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()
