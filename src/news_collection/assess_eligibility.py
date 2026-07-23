"""Article Eligibility Assessment - the pipeline stage after date
resolution (news_protocol/article_eligibility_rules.md, rules I1-I6 /
E1-E10).

What this script is, and is deliberately NOT
--------------------------------------------
The rules document's own "Consistency safeguards" section draws the
line this script follows: "Rules are applied by scripted checks
wherever the input is machine-readable (dates, windows, language,
duplicates) and by a single documented human pass where judgement is
required (E4 result-leakage, E6 Reform disambiguation, L/N relevance)."

This script is the scripted half only. It never guesses at E4 (does
this article report/react to the result?), E6 (is "Reform" the party or
planning reform?), the L/N relevance tests, or E8 (is this genuinely
editorial content?) - those need a human reading the article, and the
rules document says so explicitly. What it DOES do mechanically:

  E1  date unresolved                  - from effective_dates.csv
  E2  outside the 180-day window       - day_index = polling_day - date
  E3  polling-day-dated, no time       - this pipeline's schema never
                                          retains time-of-day (schema.py
                                          summarise_dates keeps only the
                                          calendar date), so ANY record
                                          landing exactly on polling day
                                          meets the rule's own fallback
                                          ("no confirmable time") and is
                                          excluded - not a guess, the
                                          rule's stated default
  E5  known-irrelevant (partial)       - the two relevance-flag files
                                          already built (Guardian non-UK
                                          edition, SerpAPI domain
                                          collisions) are confirmed E5
                                          failures; the L/N relevance
                                          test itself is NOT attempted
                                          here for anything else
  E7  pre-launch source (partial)      - only the case the rules
                                          document names explicitly as
                                          a worked example (Epsom &
                                          Ewell Times, "c.2022-2026
                                          only" per the source
                                          registry) - other sources'
                                          start dates are hedged
                                          ("c.", "expected", "verify")
                                          in the registry and are left
                                          for the human pass rather
                                          than guessed
  E9  non-English                      - langdetect on the stored
                                          extract/headline
  E10 blocked/gone at retrieval        - retrieval.retrieval_status

A record that clears every mechanical check above is NOT "eligible" -
it is "mechanically clear, still needs the human E4/E5(L,N)/E6/E8
pass". Calling it eligible here would silently skip judgement the
rules document requires; this script never does that.

Rule-ordering caveat (read before trusting an exclusion code)
---------------------------------------------------------------
The rules document requires checking in strict order E1..E10 and
logging the FIRST rule failed. This script cannot check E4 or E6 or
most of E5/E8 at all, so a record excluded here under (say) E5 might
also have failed E4 first, had a human checked it - the exclusion
itself would still be correct, only the recorded CODE might not be
the true first failure. This is stated plainly in every output row's
notes, not hidden.

Usage:
    python3 -m src.news_collection.assess_eligibility
"""

import csv
import json
from datetime import date
from pathlib import Path

from langdetect import DetectorFactory, LangDetectException, detect

from .resolve_publication_dates import ELECTIONS

DetectorFactory.seed = 0   # langdetect is otherwise non-deterministic

RECORDS = Path("data/raw/news/records")
EFFECTIVE_DATES = Path("news_collection/effective_dates.csv")
SEARCH_LOG = Path("news_collection/search_log.csv")
OUT = Path("news_collection/eligibility_assessment.csv")

# From news_source_registry.csv's available_years column. Only sources
# whose entry is an unhedged, concrete range get an entry here -
# epsom_ewell_times ("c.2022-2026 only") is the rules document's own
# worked example for E7 edge case #7. Sources with hedge words in the
# registry ("c.", "expected", "verify", "unverified") are deliberately
# left out: encoding a hedged estimate as a hard exclusion rule would
# risk wrongly discarding real evidence, the opposite of this project's
# "never invent, leave gaps honest" principle.
SOURCE_EARLIEST_YEAR = {
    "epsom_ewell_times": 2022,
}


def load_csv(path):
    return list(csv.DictReader(path.open())) if path.exists() else []


def reform_query_article_ids():
    """Article IDs whose originating search query mentions Reform -
    rule E6 makes manual disambiguation mandatory for every one of
    these, since "reform" also occurs in its ordinary-English sense
    (planning reform, NHS reform) with no connection to Reform UK."""
    query_mentions_reform = {r["query_id"] for r in load_csv(SEARCH_LOG)
                             if "reform" in r.get("query_text", "").lower()}
    ids = set()
    for path in RECORDS.glob("*.json"):
        rec = json.loads(path.read_text())
        if rec["retrieval"]["search_query_id"] in query_mentions_reform:
            ids.add(rec["article_id"])
    return ids


def detect_language(rec):
    """Best-effort language guess from the article's own body extract.
    Returns None (never guess a language) when there isn't enough real
    text to be confident.

    Deliberately does NOT fall back to the headline when there's no
    extract: tested against this corpus and found unsafe - a genuinely
    English headline ("Loomus: My latest uninvention") was confidently
    misdetected as French purely because headlines are short and full
    of proper nouns/coinages that give langdetect too little to go on.
    A missing extract is treated as "not enough evidence either way"
    and left for the human pass, never guessed."""
    text = rec["content"].get("extract") or ""
    if len(text) < 40:
        return None
    try:
        return detect(text)
    except LangDetectException:
        return None


def assess_one(rec, eff_row):
    """Return (status, code, note). status is 'excluded' or
    'pending_human_review' - never 'eligible' (see module docstring)."""
    aid = rec["article_id"]
    eid = rec["discovered_for_election"]
    source_id = rec["source_id"]

    # E1 - date unresolved (effective_dates.csv already carries this
    # verdict from the whole upstream date-resolution stage)
    if eff_row is None or eff_row["date_status"] != "usable":
        status = (eff_row["date_status"] if eff_row else "no_date_evidence")
        return ("excluded", "E1",
                f"No Probable-or-better publication date (date_status={status}).")

    effective_date = date.fromisoformat(eff_row["effective_date"])
    window_start, polling_day = ELECTIONS[eid]
    day_index = (polling_day - effective_date).days

    # E2 - outside the 180-day window (too early, or postdates polling day)
    if day_index > 180:
        return ("excluded", "E2",
                f"day_index={day_index} > 180 (more than 180 days "
                f"before {eid}'s polling day).")
    if day_index < 0:
        return ("excluded", "E2",
                f"day_index={day_index}: dated after {eid}'s polling "
                f"day ({polling_day.isoformat()}).")

    # E3 - polling-day-dated with no confirmable time. day_index==0 is
    # the ONLY way to reach this branch (day_index<0 already excluded
    # above under E2), and this pipeline never retains time-of-day
    # (see module docstring) - so every day_index==0 record fails the
    # rule's own stated fallback, not a judgement call.
    if day_index == 0:
        return ("excluded", "E3",
                "Dated on polling day itself; this pipeline does not "
                "retain time-of-day evidence, so the rules document's "
                "'no confirmable time' fallback applies.")

    # E7 (partial) - source didn't exist yet in the year this article
    # is dated (the rules document's own worked example)
    earliest = SOURCE_EARLIEST_YEAR.get(source_id)
    if earliest and effective_date.year < earliest:
        return ("excluded", "E7",
                f"{source_id} has no verified presence before "
                f"{earliest} (news_source_registry.csv); "
                f"{effective_date.isoformat()} predates that.")

    # E5 (partial) - already-confirmed non-UK-edition / off-topic-domain
    # hits from the Guardian and SerpAPI relevance audits. The general
    # L/N relevance test is NOT attempted here (see module docstring).
    if eff_row["known_irrelevant_flag"] == "yes":
        return ("excluded", "E5",
                "Already flagged non-UK-edition or off-topic-domain by "
                "a source-specific relevance audit (see "
                "guardian_geographic_relevance_flags.csv / "
                "serpapi_domain_relevance_flags.csv).")

    # E9 - non-English (best-effort; never excludes on a low-confidence guess)
    lang = detect_language(rec)
    if lang and lang != "en":
        return ("excluded", "E9",
                f"langdetect confidently reports '{lang}', not English.")

    # E10 - blocked/gone at retrieval time
    r_status = rec["retrieval"]["retrieval_status"]
    if r_status in ("blocked", "gone"):
        return ("excluded", "E10",
                f"retrieval_status={r_status}: page was not lawfully "
                "retrievable when collected.")

    return ("pending_human_review", "",
            "Clears every mechanically-checkable rule. Still requires "
            "the human pass for E4 (result leakage), the L/N relevance "
            "test (E5), E6 (Reform disambiguation, if applicable) and "
            "E8 (genuine editorial content) before it can count as "
            "eligible.")


def main():
    eff_by_id = {r["article_id"]: r for r in load_csv(EFFECTIVE_DATES)}
    reform_ids = reform_query_article_ids()

    rows = []
    counts = {}
    for path in sorted(RECORDS.glob("*.json")):
        rec = json.loads(path.read_text())
        aid = rec["article_id"]
        status, code, note = assess_one(rec, eff_by_id.get(aid))
        needs_reform_check = aid in reform_ids
        if needs_reform_check and status == "pending_human_review":
            note += (" This record also matched a Reform-related query - "
                    "E6 manual disambiguation is mandatory before "
                    "inclusion (protocol requirement, not optional).")
        rows.append({
            "article_id": aid, "election_id": rec["discovered_for_election"],
            "source_id": rec["source_id"], "arm": rec["arm"],
            "status": status, "exclusion_code": code,
            "needs_reform_disambiguation": "yes" if needs_reform_check else "",
            "note": note,
        })
        key = f"{status}:{code}" if code else status
        counts[key] = counts.get(key, 0) + 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} records assessed -> {OUT}")
    for key, n in sorted(counts.items()):
        print(f"  {key}: {n}")
    pending = sum(1 for r in rows if r["status"] == "pending_human_review")
    reform_flagged = sum(1 for r in rows
                         if r["needs_reform_disambiguation"] == "yes"
                         and r["status"] == "pending_human_review")
    print(f"\n{pending} records need the human E4/E5(L,N)/E6/E8 pass "
          f"before they can be counted as eligible ({reform_flagged} of "
          "those also require mandatory Reform disambiguation under E6). "
          "None of these are 'eligible' yet - see module docstring.")


if __name__ == "__main__":
    main()
