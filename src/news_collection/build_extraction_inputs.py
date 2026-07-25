"""Step 1 of the Context Extraction stage: freeze WHICH articles are
extracted and WHICH body text each one gets.

Two hard rules, both enforced structurally rather than by promise:

1. **Eligibility is read, never re-judged.** The eligible set is the
   union of already-frozen decisions - the full-corpus decisions table
   plus the pilot and validation sheets' human roll-ups. This module
   contains no eligibility logic at all; if an article's status ever
   needs to change, that happens upstream in the eligibility stage and
   this sheet is simply rebuilt.

2. **A snippet must never impersonate a full article.** Every row
   states exactly which text source was chosen and how complete it is
   (full_text / partial_text / snippet_only / missing_text), and
   carries a sha256 of the chosen text bytes. The extractor later
   hashes what it actually sends to the model; any mismatch means the
   input drifted after this freeze and the run refuses that row.

Text-source preference order (most faithful first):

    api_full_body    - full body text delivered by a publisher API
                       (Guardian Content API bodyText); no scraping
                       ambiguity, machine-clean.
    publisher_page   - text extracted from the live publisher page our
                       own fetcher saved (site_search / serper /
                       serpapi / google_cse routes).
    wayback_capture  - text extracted from an archived capture
                       (robots-restricted publishers, dead URLs).
    api_snippet      - only a search-API snippet/extract survives.
                       NEVER counted as full text.
    none             - no usable text stored at all.

The stored record already collapses sources 1-4 into one extracted
text file (content.text_path) written at collection time; what this
module adds is the *label* of where that text came from (from the
retrieval adapter + access route, recorded at fetch time) and the
honest completeness class, so the extraction stage can weigh or
exclude thin inputs explicitly instead of discovering the problem
mid-run.

Completeness classes (thresholds shared with the eligibility stage's
text_completeness() so the two stages never disagree about what
"full" means):

    full_text     - has_full_text and word_count >= 100
    partial_text  - has_full_text but word_count < 100 (a stub page,
                    a truncated capture)
    snippet_only  - no stored full text; only the search snippet /
                    API extract exists
    missing_text  - nothing usable at all

Usage:
    python3 -m src.news_collection.build_extraction_inputs
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

DECISIONS = Path("news_collection/corpus_eligibility_decisions.csv")
PILOT = Path("news_collection/manual_review_sample.csv")
VALIDATION = Path("news_collection/llm_validation_sample.csv")
RECORDS = Path("data/raw/news/records")
OUT = Path("news_collection/extraction_inputs.csv")

# Same boundary the eligibility stage used to call a text "full"
# (build_manual_review_sample.text_completeness). Kept as a named
# constant so a future change is one edit, visible in review.
FULL_TEXT_MIN_WORDS = 100

FIELDS = [
    "article_id", "election_id", "arm", "eligibility_source",
    "text_source", "text_status", "word_count",
    "text_path", "text_sha256",
]


def load_eligible():
    """The frozen eligible set, with WHERE each decision came from.

    Precedence if an article somehow appears in more than one place
    (it should not): the human sheets win over the corpus table,
    because their decisions were made first and are the more directly
    human-audited record.
    """
    eligible = {}
    for r in csv.DictReader(DECISIONS.open()):
        if r["overall_decision"] == "include":
            eligible[r["article_id"]] = {
                "election_id": r["election_id"], "arm": r["arm"],
                "eligibility_source": "corpus_decisions",
            }
    for path, label in ((PILOT, "pilot_manual"), (VALIDATION, "validation_manual")):
        for r in csv.DictReader(path.open()):
            if r.get("review_round") not in ("initial", "llm_validation"):
                continue
            final = r.get("final_reviewed_decision") or r.get("original_manual_decision")
            if final == "include":
                eligible[r["article_id"]] = {
                    "election_id": r["election_id"], "arm": r["arm"],
                    "eligibility_source": label,
                }
    return eligible


def classify_text(rec):
    """Return (text_source, text_status, word_count, text_path, sha256).

    Decides nothing about eligibility and never mutates the record -
    it only *describes* what was stored at collection time.
    """
    content = rec.get("content") or {}
    retrieval = rec.get("retrieval") or {}
    adapter = retrieval.get("adapter") or ""
    text_path = content.get("text_path") or ""
    has_full = bool(content.get("has_full_text"))
    wc = int(content.get("word_count") or 0)

    # Which route produced the stored text file, per the adapter that
    # fetched it. Labels, not judgements: guardian's API body and a
    # scraped page are both "the text", but downstream may trust or
    # weight them differently and must be able to see the difference.
    if adapter == "guardian":
        source = "api_full_body"
    elif adapter == "wayback":
        source = "wayback_capture"
    elif adapter in ("site_search", "serper", "serpapi", "google_cse",
                     "manual_import", "pilot"):
        source = "publisher_page"
    else:
        source = adapter or "unknown"

    text = ""
    if text_path and Path(text_path).exists():
        text = Path(text_path).read_text(errors="replace")

    if text and has_full and wc >= FULL_TEXT_MIN_WORDS:
        status = "full_text"
    elif text and has_full:
        status = "partial_text"
    elif text or content.get("extract"):
        # Something survives but it was never marked as full text -
        # that is a snippet and is labelled as such, per the rule that
        # a snippet must never impersonate an article.
        source = "api_snippet" if not text else source
        status = "snippet_only"
        text = text or content.get("extract") or ""
    else:
        source, status = "none", "missing_text"

    sha = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
    return source, status, wc, text_path if text else "", sha


def main():
    eligible = load_eligible()
    rows, stats = [], Counter()
    for aid in sorted(eligible):
        meta = eligible[aid]
        rec_path = RECORDS / f"{aid}.json"
        rec = json.loads(rec_path.read_text()) if rec_path.exists() else {}
        source, status, wc, tpath, sha = classify_text(rec)
        stats[status] += 1
        rows.append({
            "article_id": aid, **meta,
            "text_source": source, "text_status": status,
            "word_count": wc, "text_path": tpath, "text_sha256": sha,
        })

    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} eligible articles -> {OUT}")
    print("by text_status:", dict(stats))
    print("by text_source:", dict(Counter(r['text_source'] for r in rows)))
    print("by eligibility_source:",
          dict(Counter(r['eligibility_source'] for r in rows)))
    print("\nsnippet_only and missing_text rows are visible, not hidden: "
          "the extraction stage must decide their treatment explicitly "
          "(exclude, or extract with a partial-input flag) - never "
          "silently extract them as if they were full articles.")


if __name__ == "__main__":
    main()
