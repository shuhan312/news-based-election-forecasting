"""Build the six news worksheets the supervisor's brief asks for,
as a workbook that sits alongside the election master workbook.

    outputs/news_workbook_<date>/Surrey_Election_News_Workbook.xlsx

Sheets (names taken from the brief's tab list):

    NewsAPI Searches           national-arm searches, one row per query
    Local News Searches        local-arm searches, one row per query
    News Articles              one row per canonical corpus article
    Article-Party Context      one row per article x party
    Article-Candidate Context  one row per article x candidate
    Excluded Articles          one row per article excluded, with rule

Provenance note carried in the workbook itself: NewsAPI.org was
assessed and could not supply the historical Surrey coverage the
brief needs (free tier reaches back one month; Surrey local outlets
are not indexed), so the national arm ran on the Guardian Content
API and the local arm on publisher site search, Wayback CDX and
date-restricted Google. The sheet keeps the brief's name so the
workbook matches the requested tab list, and every row records the
route actually used.

Evidence quotes are included in the two context sheets, so the
workbook stays outside Git (outputs/ is untracked) and lives with
the OneDrive copies.

Usage:
    python3 -m src.news_features.build_news_workbook build
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .alignment import ELECTIONS

NC = Path("news_collection")
QUERY_INVENTORY = NC / "query_inventory.csv"
SEARCH_LOG = NC / "search_log.csv"
MAPPING = NC / "duplicate_mapping_layer_v1_provisional.csv"
NORMALISED = NC / "normalised_text_layer_v1_provisional.jsonl"
AVAILABILITY = NC / "article_version_temporal_availability_v1_provisional.csv"
URL_MAP = NC / "canonical_article_mapping_v1_provisional.csv"
ELIGIBILITY = NC / "eligibility_assessment.csv"
DECISIONS = NC / "corpus_eligibility_decisions.csv"
FROZEN = Path("llm_context/llm_context_layer_final.json")
WINDOWS = Path("news_features/article_time_window_assignment.json")
SCOPE = Path("news_features/news_scope_classification.json")

OUT_DIR = Path("outputs/news_workbook_2026-07-28")
OUT_XLSX = OUT_DIR / "Surrey_Election_News_Workbook.xlsx"

# route actually used per source, for the provenance column
ROUTE_NOTE = {
    "guardian_api": "Guardian Content API (NewsAPI.org substitute)",
    "google_dated_search": "Google date-restricted search",
    "surreylive": "publisher site search / Wayback CDX",
    "bbc_surrey": "Wayback CDX",
    "surrey_comet": "Wayback CDX",
    "guildford_dragon": "publisher site search / Wayback CDX",
    "farnham_herald": "Wayback CDX",
    "woking_news_mail": "Wayback CDX",
    "epsom_ewell_times": "Wayback CDX",
}


def _searches() -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per logged query, split by arm. Unsuccessful searches
    are included - the brief asks for them explicitly."""
    inv = {r["query_id"]: r for r in csv.DictReader(
        QUERY_INVENTORY.open())}
    rows = []
    for lg in csv.DictReader(SEARCH_LOG.open()):
        q = inv.get(lg["query_id"], {})
        rows.append({
            "Search ID": lg["query_id"],
            "Election": lg["election_id"],
            "Ward or division": lg.get("ward") or q.get("ward") or "",
            "Arm": lg.get("arm") or q.get("arm") or "",
            "Exact search query": lg.get("query_text")
            or q.get("query_text") or "(whole-domain archive listing)",
            "Query family": q.get("query_family", ""),
            "Domains searched": lg.get("source_id", ""),
            "Retrieval route": ROUTE_NOTE.get(lg.get("source_id"),
                                              lg.get("retrieval_route",
                                                     "")),
            "Date range start": lg.get("window_start", ""),
            "Date range end": lg.get("window_end", ""),
            "Search date": lg.get("executed_at", ""),
            "Sorting method": lg.get("ordering", ""),
            "Results returned": lg.get("results_returned", ""),
            "Records written": lg.get("records_written", ""),
            "Already held": lg.get("records_existing", ""),
            "Quarantined": lg.get("records_quarantined", ""),
            "Fetch failures": lg.get("fetch_failures", ""),
            "Search status": lg.get("search_status", ""),
            "Collection stage": q.get("stage", ""),
            "Protocol version": lg.get("protocol_version", ""),
        })
    df = pd.DataFrame(rows)
    national = df[df["Arm"] == "national"].reset_index(drop=True)
    local = df[df["Arm"] != "national"].reset_index(drop=True)
    return national, local


def _articles() -> pd.DataFrame:
    """One row per canonical corpus article, with the brief's
    article-data fields and the derived timing/scope values."""
    mapping = {r["article_id"]: r for r in csv.DictReader(
        MAPPING.open())}
    avail = {r["article_id"]: r for r in csv.DictReader(
        AVAILABILITY.open())}
    urls = {r["article_id"]: r for r in csv.DictReader(URL_MAP.open())}
    windows = {r["article_id"]: r for r in json.loads(
        WINDOWS.read_text())["assigned"]}
    scope = {r["article_id"]: r for r in json.loads(
        SCOPE.read_text())["records"]}

    rows = []
    for line in NORMALISED.open():
        a = json.loads(line)
        aid = a["article_id"]
        m = mapping.get(aid, {})
        w = windows.get(aid, {})
        s = scope.get(aid, {})
        ge = (s.get("affected_area") or {})
        gflags = (s.get("geographic_flags") or {})
        pflags = (s.get("political_flags") or {})
        body = a.get("body_text") or ""
        rows.append({
            "Article ID": aid,
            "Canonical article ID": m.get("canonical_article_id", ""),
            "Duplicate group": m.get("duplicate_group_id", ""),
            "Downstream usage": m.get("downstream_usage_status", ""),
            "Election": a.get("election_id", ""),
            "Collection arm": a.get("arm", ""),
            "Publication": a.get("source_name", ""),
            "Retrieval route": ROUTE_NOTE.get(a.get("source_name"), ""),
            "Author": a.get("author_text", ""),
            "Headline": a.get("title", ""),
            "Article URL": urls.get(aid, {}).get("canonical_url", ""),
            "Publication date": avail.get(aid, {}).get("published_at",
                                                       ""),
            "Word count": len(body.split()) if body else 0,
            "Text quality": a.get("quality_status", ""),
            "Days before polling": w.get("days_before_polling", ""),
            "Individual time window": w.get("individual_time_window",
                                            ""),
            "Scope classification": s.get("scope_classification", ""),
            "Affected area level": ge.get("level", ""),
            "Affected area names": "; ".join(ge.get("names") or []),
            "Surrey mentioned": gflags.get("surrey_mentioned", ""),
            "Ward mentioned": gflags.get("ward_mentioned", ""),
            "Candidate mentioned": gflags.get("candidate_mentioned",
                                              ""),
            "National leader mentioned":
                pflags.get("national_party_leader_mentioned", ""),
            "Issue scope": s.get("issue_scope", ""),
            "Local relevance score": s.get("local_relevance_score", ""),
            "National relevance score":
                s.get("national_relevance_score", ""),
            "Scope confidence": s.get("confidence", ""),
            "Extraction status": ("extracted" if aid in scope
                                  else "not yet extracted"),
        })
    return pd.DataFrame(rows).sort_values(
        ["Election", "Publication date", "Article ID"]).reset_index(
        drop=True)


def _context_sheets() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Article-Party and Article-Candidate context, one row per
    article x entity, straight from the frozen extraction layer."""
    cards = json.loads(FROZEN.read_text())["cards"]
    party_rows, cand_rows = [], []
    for c in cards:
        aid = c["article_id"]
        meta = c["article_metadata"]
        pe = c.get("political_entities") or {}
        stance = {r["target_name"]: r
                  for r in (c.get("stance") or {}).get(
                      "entity_stances") or []}
        for p in pe.get("party_context") or []:
            st = stance.get(p["party"], {})
            span = (p.get("evidence_span") or {}).get("text", "")
            party_rows.append({
                "Article ID": aid,
                "Election": meta["election_id"],
                "Publication": meta["source"],
                "Headline": meta["title"],
                "Party as mentioned": p["party"],
                "Overall context": p.get("overall_context", ""),
                "Sentiment": p.get("stance", ""),
                "Blame": p.get("blame", ""),
                "Credit": p.get("credit", ""),
                "Competence": p.get("competence", ""),
                "Integrity": p.get("integrity", ""),
                "Main associated issue": p.get("associated_issue", ""),
                "Directly quoted": p.get("directly_quoted", ""),
                "Support trajectory": p.get("support_trajectory", ""),
                "Challenger credibility":
                    p.get("challenger_credibility", ""),
                "Voter switching discussed":
                    p.get("voter_switching_discussed", ""),
                "Switching from party":
                    p.get("switching_origin_party", ""),
                "Switching to party":
                    p.get("switching_destination_party", ""),
                "Local relevance score":
                    p.get("local_relevance_score", ""),
                "Electoral relevance score":
                    p.get("electoral_relevance_score", ""),
                "Stance layer sentiment": st.get("stance", ""),
                "Confidence": p.get("confidence", ""),
                "Supporting text": span,
                "Review status": c["validation_status"]["per_layer"]
                .get("pilot_full_schema", ""),
            })
        for cc in pe.get("candidate_context") or []:
            span = (cc.get("evidence_span") or {}).get("text", "")
            cand_rows.append({
                "Article ID": aid,
                "Election": meta["election_id"],
                "Publication": meta["source"],
                "Headline": meta["title"],
                "Candidate name": cc.get("name", ""),
                "Party": cc.get("party", ""),
                "Mention count": cc.get("mention_count", ""),
                "Prominence": cc.get("prominence", ""),
                "Sentiment": cc.get("stance", ""),
                "Blame": cc.get("blame", ""),
                "Credit": cc.get("credit", ""),
                "Competence": cc.get("competence", ""),
                "Integrity": cc.get("integrity", ""),
                "Main issue": cc.get("main_issue", ""),
                "Directly quoted": cc.get("directly_quoted", ""),
                "Credibility": cc.get("credibility", ""),
                "Momentum": cc.get("momentum", ""),
                "Protest candidate": cc.get("protest_candidate", ""),
                "Confidence": cc.get("confidence", ""),
                "Supporting text": span,
            })
    return (pd.DataFrame(party_rows).sort_values(
                ["Election", "Article ID", "Party as mentioned"]
            ).reset_index(drop=True),
            pd.DataFrame(cand_rows).sort_values(
                ["Election", "Article ID", "Candidate name"]
            ).reset_index(drop=True))


EXCLUSION_TEXT = {
    "E1": "Publication date unresolved (no Probable-or-better date)",
    "E2": "Outside the 180-day pre-election window",
    "E3": "Dated polling day with no confirmable pre-poll time",
    "E5": "Known-irrelevant source or edition",
    "E7": "Source published before its launch date",
    "E9": "Not retrievable",
    "E10": "Not English language",
}


def _excluded() -> pd.DataFrame:
    """One row per excluded article, with the rule that excluded it.
    The brief asks for exclusions to remain auditable."""
    decisions = {r["article_id"]: r for r in csv.DictReader(
        DECISIONS.open())}
    rows = []
    for r in csv.DictReader(ELIGIBILITY.open()):
        d = decisions.get(r["article_id"], {})
        if r["status"] == "excluded":
            reason = EXCLUSION_TEXT.get(r["exclusion_code"],
                                        r["exclusion_code"])
            stage = "mechanical rule"
        elif d.get("overall_decision") == "exclude":
            reason = d.get("e5_decision") or d.get("e4_reason_code") \
                or "human/LLM eligibility review"
            stage = "eligibility review"
        else:
            continue
        rows.append({
            "Article ID": r["article_id"],
            "Election": r["election_id"],
            "Publication": r["source_id"],
            "Arm": r["arm"],
            "Exclusion stage": stage,
            "Exclusion rule": r["exclusion_code"] or "E4/E5/E6/E8",
            "Reason for exclusion": reason,
            "Reform disambiguation required":
                r.get("needs_reform_disambiguation", ""),
            "Note": r.get("note", ""),
        })
    return pd.DataFrame(rows).sort_values(
        ["Election", "Exclusion rule", "Article ID"]).reset_index(
        drop=True)


def _provenance() -> pd.DataFrame:
    return pd.DataFrame([
        {"Item": "News API used",
         "Value": "Guardian Content API (national arm)",
         "Note": "NewsAPI.org assessed first: free tier reaches back "
                 "one month only and Surrey local outlets are not "
                 "indexed, so it could not supply 2013/2017/2021 "
                 "coverage. Substitution recorded per row."},
        {"Item": "Local routes",
         "Value": "publisher site search, Wayback CDX, "
                  "date-restricted Google",
         "Note": "Seven Surrey publishers from the brief's list."},
        {"Item": "Ward-tier sampling frame",
         "Value": "17 divisions",
         "Note": "Pre-registered per supervisor to-do 7 "
                 "(news_protocol/division_sample.md); strata are "
                 "safe, marginal, changed, Reform-strong, "
                 "Reform-weak."},
        {"Item": "Time windows",
         "Value": "180-91, 90-31, 30-15, 14-8, 7-4 days, final 72h",
         "Note": "Per the main brief; cumulative windows also "
                 "computed."},
        {"Item": "Context extraction",
         "Value": "claude-sonnet-5, frozen schema v1-final",
         "Note": "67-article stratified pilot extracted so far; "
                 "every classification carries a verbatim supporting "
                 "passage and a confidence score."},
        {"Item": "Evidence rule",
         "Value": "quote-or-nothing",
         "Note": "Supporting text is string-matched against the "
                 "article; unmatched quotes are rejected, never "
                 "stored."},
    ])


def build() -> None:
    national, local = _searches()
    articles = _articles()
    party_ctx, cand_ctx = _context_sheets()
    excluded = _excluded()
    prov = _provenance()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xl:
        prov.to_excel(xl, sheet_name="News Provenance", index=False)
        national.to_excel(xl, sheet_name="NewsAPI Searches",
                          index=False)
        local.to_excel(xl, sheet_name="Local News Searches",
                       index=False)
        articles.to_excel(xl, sheet_name="News Articles", index=False)
        party_ctx.to_excel(xl, sheet_name="Article-Party Context",
                           index=False)
        cand_ctx.to_excel(xl, sheet_name="Article-Candidate Context",
                          index=False)
        excluded.to_excel(xl, sheet_name="Excluded Articles",
                          index=False)

        # freeze headers and add filters on every data sheet
        for name in xl.book.sheetnames:
            ws = xl.book[name]
            ws.freeze_panes = "A2"
            if ws.max_row > 1:
                ws.auto_filter.ref = ws.dimensions

    for name, df in (("NewsAPI Searches", national),
                     ("Local News Searches", local),
                     ("News Articles", articles),
                     ("Article-Party Context", party_ctx),
                     ("Article-Candidate Context", cand_ctx),
                     ("Excluded Articles", excluded)):
        print(f"  {name:<28} {len(df):>6} rows x {len(df.columns)} cols")
    print(f"-> {OUT_XLSX}")


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
