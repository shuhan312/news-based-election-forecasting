"""Pilot Retrieval Validation (News Retrieval Framework Validation, Task 4).

Retrieves a SMALL number of representative articles - at most one per
source per election window - to verify, end to end, that:

  * each retrieval route in the adapter design actually works
    (API search, Wayback CDX discovery, live-page fetch, capture fetch);
  * publication dates can be recovered from page metadata and land
    inside the expected 180-day window;
  * every retrieved record conforms to raw_news_schema.json.

Sources piloted (one thin slice per adapter class, chosen to cover the
hardest verified cases from the coverage audit):

  guardian_api      - GuardianAdapter route (API, server-side dates)
  surreylive        - WaybackAdapter route (robots forbids /search, so
                      discovery must go through CDX; 2013 reachability
                      is this project's hardest local requirement)
  bbc_surrey        - WaybackAdapter discovery + live fetch (BBC article
                      URLs persist, so captures act as an index of live
                      pages)
  guildford_dragon  - SiteSearchAdapter-family site (small WordPress
                      publisher with its own intact archive)

This is validation, not collection: <= 16 articles in total, generous
pauses, and nothing here feeds the modelling corpus.

Outputs
  data/raw/news_pilot/<article_id>.txt            full text (gitignored)
  news_protocol/evidence/pilot_records.json       schema records + checks
                                                  (committable; no full text)

Usage:
    python3 src/pilot_news_retrieval.py
"""

import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from jsonschema import Draft7Validator

load_dotenv()

USER_AGENT = ("Surrey-IRP-research-pilot/1.0 "
              "(academic research; contact: shuhanliu44@gmail.com)")
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT = 30
PAUSE_ARCHIVE = 6      # web.archive.org rate-limited us at 1.5s during Task 1
PAUSE_OTHER = 2

TEXT_DIR = Path("data/raw/news_pilot")
OUT_PATH = Path("news_protocol/evidence/pilot_records.json")
SCHEMA = json.loads(Path("news_protocol/raw_news_schema.json").read_text())
VALIDATOR = Draft7Validator(SCHEMA)

# 180-day windows from the protocol (news_research_protocol.md section 2).
ELECTIONS = {
    "SCC-2013-05":  (date(2012, 11, 3), date(2013, 5, 2)),
    "SCC-2017-05":  (date(2016, 11, 5), date(2017, 5, 4)),
    "SCC-2021-05":  (date(2020, 11, 7), date(2021, 5, 6)),
    "ESWS-2026-05": (date(2025, 11, 8), date(2026, 5, 7)),
}


def get(url, archive=False, timeout=TIMEOUT, retries=1, **kw):
    """One polite GET; sleeps afterwards; one retry on failure (the CDX
    endpoint intermittently times out under load). Returns response or
    None."""
    r = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, **kw)
            break
        except requests.RequestException as e:
            print(f"    fetch failed: {url[:90]} ({e.__class__.__name__})")
            if attempt < retries:
                time.sleep(10)
    time.sleep(PAUSE_ARCHIVE if archive else PAUSE_OTHER)
    return r


def sha(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def make_id(source_id, canonical_ref):
    return f"NEWS-{source_id}-{sha(canonical_ref)[:12]}"


# --------------------------------------------------------------------------
# Metadata extraction shared by every HTML route.
# The raw schema demands *evidence* for every candidate date, so this
# returns them all with their provenance labels and lets grade_dates()
# apply the confidence rules afterwards.
# --------------------------------------------------------------------------

def extract_html_metadata(html):
    soup = BeautifulSoup(html, "html.parser")
    meta = {"headline": None, "byline": None, "dates": []}

    # 1) JSON-LD blocks: the most reliable machine-readable source.
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            blocks = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        blocks = blocks if isinstance(blocks, list) else [blocks]
        for b in blocks:
            if not isinstance(b, dict):
                continue
            # some sites nest the article object under @graph
            for node in (b.get("@graph") if isinstance(b.get("@graph"), list)
                         else [b]):
                if not isinstance(node, dict):
                    continue
                if node.get("datePublished"):
                    meta["dates"].append(
                        {"value": str(node["datePublished"]),
                         "found_in": "json_ld"})
                if not meta["headline"] and node.get("headline"):
                    meta["headline"] = str(node["headline"])
                author = node.get("author")
                if not meta["byline"] and isinstance(author, dict):
                    meta["byline"] = author.get("name")

    # 2) OpenGraph / standard meta tags.
    for prop, label in [("article:published_time", "opengraph"),
                        ("og:article:published_time", "opengraph")]:
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            meta["dates"].append({"value": tag["content"],
                                  "found_in": label})
    for name in ["parsely-pub-date", "date", "article.published"]:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            meta["dates"].append({"value": tag["content"],
                                  "found_in": "meta_tag"})
    if not meta["headline"]:
        og = soup.find("meta", attrs={"property": "og:title"})
        meta["headline"] = (og["content"].strip() if og and og.get("content")
                            else (soup.title.get_text(strip=True)
                                  if soup.title else None))

    # 3) Visible <time datetime=...> elements.
    t = soup.find("time", attrs={"datetime": True})
    if t:
        meta["dates"].append({"value": t["datetime"],
                              "found_in": "visible_dateline"})

    # Body text: prefer <article> paragraphs, fall back to all <p>.
    container = soup.find("article") or soup
    paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    meta["text"] = "\n".join(x for x in paras if len(x) > 40)
    return meta


def parse_date(value):
    """Best-effort ISO parse of a candidate date string -> date or None."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
    if m:
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            return None
    return None


def grade_dates(evidence):
    """Apply the confidence grades of article_eligibility_rules.md §3.
    Confirmed: >=1 machine-readable date, and all parseable candidates
    agree on the calendar day.  Probable: exactly one parseable
    candidate.  Uncertain: candidates disagree.  Missing: none."""
    parsed = {}
    for ev in evidence:
        d = parse_date(ev["value"])
        if d:
            parsed.setdefault(d, set()).add(ev["found_in"])
    if not parsed:
        return None, "Missing"
    if len(parsed) == 1:
        d, sources = next(iter(parsed.items()))
        machine = {"json_ld", "opengraph", "meta_tag", "api_field"}
        return d, ("Confirmed" if sources & machine else "Probable")
    return sorted(parsed)[0], "Uncertain"     # keep earliest, flag conflict


def build_record(source_id, arm, election_id, adapter, access_route,
                 query_id, requested_url, resp, canonical_url,
                 archive_url, meta):
    """Assemble one raw-schema record + write full text to data/."""
    text = (meta.get("text") or "").strip()
    pub_date, confidence = grade_dates(meta.get("dates", []))
    article_id = make_id(source_id, canonical_url or requested_url)
    text_path = None
    if text:
        TEXT_DIR.mkdir(parents=True, exist_ok=True)
        text_path = str(TEXT_DIR / f"{article_id}.txt")
        Path(text_path).write_text(text)
    return {
        "schema_version": "1.0",
        "article_id": article_id,
        "source_id": source_id,
        "arm": arm,
        "discovered_for_election": election_id,
        "retrieval": {
            "adapter": adapter,
            "adapter_version": "pilot-1.0",
            "access_route": access_route,
            "search_query_id": query_id,
            "retrieved_at": datetime.now(timezone.utc)
                            .isoformat(timespec="seconds"),
            "http_status": getattr(resp, "status_code", None),
            "retrieval_status": "ok" if text else "parse_failed",
            "requested_url": requested_url,
            "final_url": getattr(resp, "url", None),
            "archive_url": archive_url,
        },
        "identity": {
            "canonical_url": canonical_url,
            "offline_citation": None,
            "publisher": source_id,
            "headline": meta.get("headline"),
            "subheading": None,
            "byline": meta.get("byline"),
            "language": "en",
        },
        "dates": {
            "published_date": pub_date.isoformat() if pub_date else None,
            "published_time": None,
            "updated_date": None,
            "date_confidence": confidence,
            "date_evidence": meta.get("dates", []),
        },
        "content": {
            "has_full_text": bool(text),
            "text_path": text_path,
            "extract": text[:497] + "..." if len(text) > 500 else (text or None),
            "word_count": len(text.split()) if text else None,
            "text_sha256": sha(text) if text else None,
        },
        "notes": None,
    }


# --------------------------------------------------------------------------
# Route 1: Guardian Content API (GuardianAdapter slice).
# --------------------------------------------------------------------------

def pilot_guardian(records):
    key = os.getenv("GUARDIAN_KEY")
    for eid, (start, end) in ELECTIONS.items():
        qid = f"PILOT-guardian-{eid}"
        r = get("https://content.guardianapis.com/search", params={
            "q": "\"Surrey County Council\"",
            "from-date": start.isoformat(), "to-date": end.isoformat(),
            "page-size": 1, "order-by": "relevance",
            "show-fields": "bodyText,byline,firstPublicationDate",
            "api-key": key,
        })
        results = (r.json()["response"].get("results", [])
                   if r is not None and r.status_code == 200 else [])
        if not results:
            print(f"  guardian {eid}: no result")
            continue
        item, f = results[0], results[0].get("fields", {})
        # The API is machine-readable end to end: dates arrive as fields,
        # so date_evidence is built directly instead of parsing HTML.
        meta = {
            "headline": item.get("webTitle"),
            "byline": f.get("byline"),
            "text": f.get("bodyText", ""),
            "dates": [{"value": item.get("webPublicationDate", ""),
                       "found_in": "api_field"}]
                     + ([{"value": f["firstPublicationDate"],
                          "found_in": "api_field"}]
                        if f.get("firstPublicationDate") else []),
        }
        records.append(build_record(
            "guardian_api", "national", eid, "guardian", "api", qid,
            "https://content.guardianapis.com/search", r,
            item.get("webUrl"), None, meta))
        print(f"  guardian {eid}: {item.get('webTitle')!r}")


# --------------------------------------------------------------------------
# Routes 2-4: CDX discovery + page fetch (Wayback / live).
# --------------------------------------------------------------------------

def looks_like_article(url):
    """Filter CDX hits down to plausible article pages: no query strings,
    no obvious index/tag/service paths, reasonable path depth."""
    if "?" in url or "#" in url:
        return False
    bad = ("/search", "/tag/", "/category/", "/all-about/", "/authors/",
           "/wp-", "robots.txt", "/feed", "/page/", "/incoming/")
    if any(b in url.lower() for b in bad):
        return False
    path = re.sub(r"^https?://[^/]+", "", url).rstrip("/")
    return path.count("/") >= 2 and len(path) > 15


def cdx_discover(site_url, match_type, start, end, url_regex=None,
                 limit=500):
    """One CDX query inside a window -> list of (timestamp, original).
    limit=500 because urlkey ordering is alphabetical: a small limit
    returns an arbitrary alphabetical slice of the window, which the
    first pilot run showed rarely contains in-window *publications*."""
    params = {
        "url": site_url, "matchType": match_type,
        "from": start.strftime("%Y%m%d"), "to": end.strftime("%Y%m%d"),
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "urlkey", "limit": limit, "output": "json",
    }
    if url_regex:
        params["filter"].append(f"original:{url_regex}")
    r = get("https://web.archive.org/cdx/search/cdx", archive=True,
            timeout=60, retries=2, params=params)
    if r is None or r.status_code != 200:
        return []
    try:
        rows = r.json()[1:]
    except ValueError:
        return []
    return [(row[1], row[2]) for row in rows if looks_like_article(row[2])]


def is_challenge_page(meta):
    """Cloudflare-style interstitials masquerade as HTTP 200; their
    captured copies must be skipped, not recorded as articles."""
    h = (meta.get("headline") or "").lower()
    return any(x in h for x in ("one moment", "just a moment",
                                "access denied", "attention required"))


def rank_candidates(hits, source_id, start, end):
    """Order CDX hits so that pages *published* in-window come first.

    The first pilot run showed the failure mode this fixes: CDX bounds
    the *capture* time, so urlkey-ordered hits are dominated by old
    articles that merely got re-crawled inside the window.  Two cheap,
    source-specific priors correct for that:

    * guildford_dragon uses /YYYY/MM/DD/ permalinks, so the publication
      month is readable from the URL itself - keep only in-window ones;
    * surreylive and bbc_surrey end article URLs with a numeric ID that
      grows over time, so sorting by that ID descending puts the newest
      articles (the ones actually published in-window) first.
    """
    if source_id == "guildford_dragon":
        # every year-month the window touches
        months = set()
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            months.add(f"/{y}/{m:02d}/")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return [h for h in hits if any(mm in h[1] for mm in months)]

    def trailing_id(hit):
        m = re.search(r"(\d{6,9})/?$", hit[1])
        return int(m.group(1)) if m else -1
    return sorted(hits, key=trailing_id, reverse=True)


def pilot_capture_site(records, source_id, arm, site_url, match_type,
                       url_regex, prefer_live, max_tries=4):
    """Shared slice for surreylive / bbc_surrey / guildford_dragon:
    discover candidates via CDX, then apply date-verified selection -
    fetch a candidate, recover its publication date from page metadata,
    and only accept it if that date is inside the window.  This mirrors
    the loop the production WaybackAdapter must implement (capture time
    is never publication time - eligibility rule E7)."""
    for eid, (start, end) in ELECTIONS.items():
        qid = f"PILOT-{source_id}-{eid}"
        hits = rank_candidates(
            cdx_discover(site_url, match_type, start, end, url_regex),
            source_id, start, end)
        if not hits:
            print(f"  {source_id} {eid}: no in-window CDX candidate")
            continue
        accepted = None
        for ts, original in hits[:max_tries]:
            live_resp, capture_used = None, None
            if prefer_live:
                live_resp = get(original)
            if live_resp is not None and live_resp.status_code == 200:
                resp, requested, route = live_resp, original, "live_page"
            else:
                capture_used = f"https://web.archive.org/web/{ts}/{original}"
                resp = get(capture_used, archive=True)
                requested, route = capture_used, "wayback_capture"
            if resp is None or resp.status_code != 200:
                continue
            meta = extract_html_metadata(resp.text)
            if is_challenge_page(meta):
                continue
            rec = build_record(
                source_id, arm, eid, "wayback" if route == "wayback_capture"
                else "site_search", route, qid, requested, resp,
                original, capture_used, meta)
            pub = rec["dates"]["published_date"]
            in_window = (pub is not None
                         and start <= date.fromisoformat(pub) < end)
            # prefer a dated record over an undated one as the kept
            # evidence, and stop as soon as a hit is truly in-window
            if accepted is None or pub is not None:
                accepted = rec
            if in_window:
                break
        if accepted:
            records.append(accepted)
            print(f"  {source_id} {eid}: "
                  f"[{accepted['retrieval']['access_route']}] "
                  f"pub={accepted['dates']['published_date']} "
                  f"{str(accepted['identity']['headline'])[:60]!r}")
        else:
            print(f"  {source_id} {eid}: all candidates failed")


def main():
    records = []
    print("Guardian API slice")
    pilot_guardian(records)
    print("SurreyLive slice (CDX discovery; robots forbids /search)")
    pilot_capture_site(records, "surreylive", "local",
                       "getsurrey.co.uk", "domain", ".*election.*",
                       prefer_live=False)   # historic URLs pre-date rebrand
    print("BBC Surrey slice (CDX discovery, live fetch preferred)")
    pilot_capture_site(records, "bbc_surrey", "local",
                       "bbc.co.uk/news/uk-england-surrey", "prefix",
                       None, prefer_live=True)
    print("Guildford Dragon slice (own archive intact, live fetch)")
    pilot_capture_site(records, "guildford_dragon", "local",
                       "guildford-dragon.com", "domain", ".*election.*",
                       prefer_live=True)

    # ---- Schema + window validation for every record -------------------
    summary = []
    for rec in records:
        errors = [e.message for e in VALIDATOR.iter_errors(rec)]
        pub = rec["dates"]["published_date"]
        eid = rec["discovered_for_election"]
        start, end = ELECTIONS[eid]
        in_window = (start <= date.fromisoformat(pub) < end) if pub else None
        summary.append({
            "article_id": rec["article_id"], "source_id": rec["source_id"],
            "election": eid, "schema_valid": not errors,
            "schema_errors": errors,
            "published_date": pub,
            "date_confidence": rec["dates"]["date_confidence"],
            "date_in_window": in_window,
            "has_full_text": rec["content"]["has_full_text"],
            "access_route": rec["retrieval"]["access_route"],
        })

    OUT_PATH.write_text(json.dumps({
        "run_date": "2026-07-22",
        "purpose": ("Pilot Retrieval Validation (Task 4): one article per "
                    "source per election window, validated against "
                    "raw_news_schema.json. Validation scaffolding only - "
                    "these records do not enter the modelling corpus."),
        "validation_summary": summary,
        "records": records,
    }, indent=2))

    ok = sum(1 for s in summary if s["schema_valid"])
    dated = sum(1 for s in summary if s["date_in_window"])
    print(f"\n{len(records)} records; {ok} schema-valid; "
          f"{dated} with confirmed in-window publication dates")
    print(f"written to {OUT_PATH}")


if __name__ == "__main__":
    main()
