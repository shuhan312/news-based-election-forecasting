"""Filter the Guardian download down to plausibly relevant articles.

Two things happen here:
  1. drop sections that cannot contain Surrey local politics
     (sport, culture, Australian edition, ...)
  2. print a random sample of the surviving titles, to count by hand
     how many are genuinely about Surrey local politics

Writes the filtered table to data/processed/guardian_articles_filtered.csv.

Usage:  python src/filter_articles.py
"""

import pandas as pd

IN_PATH = "data/processed/guardian_articles.csv"
OUT_PATH = "data/processed/guardian_articles_filtered.csv"

# Sections that showed up in the download but are clearly not about
# UK local politics. Everything not listed here survives, so a new
# section appearing later is kept by default and reviewed by eye.
DROP_SECTIONS = [
    "Sport", "Football", "Cricket",
    "Australia news", "US news", "World news",
    "Life and style", "Culture", "Music", "Film", "Books", "Stage",
    "Television & radio", "Art and design", "Games",
    "Food", "Travel", "Fashion",
    "From the Observer", "Obituaries", "Crosswords",
]

SAMPLE_SIZE = 40
SEED = 42  # fixed so the sample is the same on every run


def main():
    df = pd.read_csv(IN_PATH)
    print(f"loaded: {len(df)} articles")

    kept = df[~df["section"].isin(DROP_SECTIONS)].copy()
    print(f"after section filter: {len(kept)} articles "
          f"({len(df) - len(kept)} dropped)\n")

    print("Articles per year (filtered):")
    print(kept["published_at"].str[:4].value_counts().sort_index().to_string())

    print("\nRemaining sections:")
    print(kept["section"].value_counts().to_string())

    # Relevance ladder, strictest test last. Naming a council in full
    # ("Woking Borough Council") is the best proxy we have for an
    # article genuinely being about Surrey local politics.
    text = kept["title"].fillna("") + " " + kept["body_text"].fillna("")
    titles = kept["title"].fillna("")

    named_council = text.str.contains(
        "Surrey County Council|Woking Borough Council|Guildford Borough Council"
        "|Elmbridge Borough Council|Spelthorne Borough Council"
        "|Runnymede Borough Council|Tandridge District Council"
        "|Waverley Borough Council|Surrey Heath Borough Council"
        "|Mole Valley District Council|Reigate and Banstead|Epsom and Ewell",
        case=False)
    surrey_and_council = (text.str.contains("Surrey", case=False)
                          & text.str.contains("council", case=False))
    title_local = titles.str.contains(
        "Surrey|Woking|Guildford|Elmbridge|Spelthorne|Runnymede"
        "|Tandridge|Waverley", case=False)

    print("\nRelevance ladder (loosest to strictest):")
    print(f"  mention Surrey AND council anywhere: {surrey_and_council.sum()}")
    print(f"  title mentions Surrey or a borough:  {title_local.sum()}")
    print(f"  name a specific Surrey council:      {named_council.sum()}")

    print("\nArticles naming a specific Surrey council, per year:")
    print(kept[named_council]["published_at"].str[:4]
          .value_counts().sort_index().to_string())

    kept.to_csv(OUT_PATH, index=False)
    print(f"\nsaved -> {OUT_PATH}")

    # Sample for the manual relevance count. Read each title and ask:
    # is this about Surrey local politics? Tally yes/no.
    sample = kept.sample(min(SAMPLE_SIZE, len(kept)), random_state=SEED)
    print(f"\n--- random sample of {len(sample)} titles ---")
    for _, row in sample.sort_values("published_at").iterrows():
        print(f"{row['published_at'][:10]}  [{row['section']}]  {row['title']}")


if __name__ == "__main__":
    main()
