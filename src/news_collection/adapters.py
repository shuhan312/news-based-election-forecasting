"""Production source adapters, implementing the validated designs of
news_protocol/source_adapter_framework.md section 4.

Adapters discover and retrieve ONLY.  They never judge eligibility,
never deduplicate, never resolve metadata conflicts, never infer dates.
Each search() returns SearchHit dicts; each fetch() returns a
raw_news_schema record plus its raw sidecar material.

Validation findings baked in:
  * CDX pacing 6s + retries (rate-limited at 1.5s during validation)
  * CDX candidate ranking by URL priors (permalink dates / trailing
    article IDs) because urlkey order buries in-window publications
  * challenge-page detection (Cloudflare interstitials return HTTP 200)
  * capture-URL verification (Wayback redirects dead URLs to homepages)
  * robots: SurreyLive/BBC/Comet search paths are never touched -
    their discovery goes through CDX (proposal P1)
"""

import os
import re
import time
from urllib.parse import quote_plus

import requests

from .schema import build_record, extract_html_metadata

USER_AGENT = ("Surrey-IRP-news-collector/1.0 "
              "(academic research; contact: shuhanliu44@gmail.com)")
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT = 30
PAUSE_ARCHIVE = 6          # web.archive.org budget from validation
PAUSE_OTHER = 1.5


def http_get(url, archive=False, timeout=TIMEOUT, retries=1, **kw):
    """Single polite GET with retry; failure returns None (callers log
    the failure - a failed fetch is data, not an exception)."""
    r = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, **kw)
            break
        except requests.RequestException:
            if attempt < retries:
                time.sleep(10)
    time.sleep(PAUSE_ARCHIVE if archive else PAUSE_OTHER)
    return r


def is_challenge_page(meta):
    h = (meta.get("headline") or "").lower()
    return any(x in h for x in ("one moment", "just a moment",
                                "access denied", "attention required"))


def is_pdf_response(resp):
    """True if a fetched page is actually a PDF, not HTML.

    Found 2026-07-23: three site-search hits were official election PDFs
    (a Statement of Persons Nominated, an LGBCE boundary report, a
    declaration of results). fetch() was reading every response with
    `resp.text`, which decodes bytes as (guessed) text - fine for HTML,
    but it silently mangles PDF binary data into a string full of U+FFFD
    replacement characters, destroying the file beyond recovery. Checked
    both by the declared content-type and the file's own %PDF signature,
    since a misconfigured server can send a PDF without the right header.
    """
    ctype = (resp.headers.get("Content-Type") or "").lower()
    return "application/pdf" in ctype or resp.content[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# Guardian Content API - the national arm's verified full-archive route.
# ---------------------------------------------------------------------------

class GuardianAdapter:
    """search() = one Content API page; the API also carries body text
    and machine-readable dates, so fetch() needs no second request."""

    name = "guardian"
    PAGE_SIZE = 50
    MAX_PAGES = 2          # deterministic cap per query, stated in report

    def __init__(self, api_key):
        self.key = api_key

    def search(self, query):
        hits, pages_meta = [], []
        for page in range(1, self.MAX_PAGES + 1):
            r = http_get("https://content.guardianapis.com/search", params={
                "q": query["query_text"],
                "from-date": query["window_start"],
                "to-date": query["window_end"],
                "page": page, "page-size": self.PAGE_SIZE,
                "order-by": "oldest",           # deterministic ordering
                "show-fields": "bodyText,byline,firstPublicationDate",
                # Restrict to Guardian's UK edition. Verified 2026-07-23:
                # without this, generic national-topic phrasing (e.g.
                # 'party leadership', 'opinion poll AND voters') matches
                # Guardian's US and Australia editions too - a live
                # comparison query returned australia-news/us-related
                # hits without this parameter and only uk-news/politics/
                # commentisfree (UK edition) hits with it. An audit of
                # the corpus already collected without this filter found
                # 284/2854 Guardian records (~10%) from the us-news/
                # australia-news sections - see
                # audit_guardian_geographic_relevance.py, which flags
                # (not deletes) those already-collected records for the
                # eligibility stage rather than fixing them retroactively.
                "production-office": "uk",
                "api-key": self.key,
            })
            if r is None or r.status_code != 200:
                pages_meta.append({"page": page, "status":
                                   getattr(r, "status_code", None)})
                break
            body = r.json().get("response", {})
            pages_meta.append({"page": page, "status": 200,
                               "total": body.get("total")})
            for item in body.get("results", []):
                hits.append({"api_item": item, "url": item.get("webUrl")})
            if page >= body.get("pages", 1):
                break
        return hits, pages_meta

    def fetch(self, hit, query):
        item = hit["api_item"]
        f = item.get("fields", {})
        dates = [{"value": item.get("webPublicationDate", ""),
                  "found_in": "api_field"}]
        if f.get("firstPublicationDate"):
            dates.append({"value": f["firstPublicationDate"],
                          "found_in": "api_field"})
        meta = {"headline": item.get("webTitle"), "byline": f.get("byline"),
                "text": f.get("bodyText", ""), "dates": dates}
        record = build_record(
            source_id="guardian_api", arm=query["arm"],
            election_id=query["election_id"], adapter="guardian",
            access_route="api", query_id=query["query_id"],
            requested_url="https://content.guardianapis.com/search",
            http_status=200, final_url=item.get("webUrl"),
            archive_url=None, canonical_url=item.get("webUrl"),
            publisher="guardian_api", meta=meta)
        return record, {"text": meta["text"], "raw_api": item}


# ---------------------------------------------------------------------------
# Wayback CDX - discovery AND fallback fetching for the robots-restricted
# publishers (SurreyLive, BBC Surrey, Surrey Comet), per proposal P1.
# ---------------------------------------------------------------------------

class WaybackAdapter:
    name = "wayback"

    SITES = {   # CDX target + whether the live URL usually still works
        "surreylive":   {"cdx_url": "getsurrey.co.uk",
                         "match": "domain", "prefer_live": False},
        "bbc_surrey":   {"cdx_url": "bbc.co.uk/news/uk-england-surrey",
                         "match": "prefix", "prefer_live": True},
        "surrey_comet": {"cdx_url": "surreycomet.co.uk",
                         "match": "domain", "prefer_live": False},
        "guildford_dragon": {"cdx_url": "guildford-dragon.com",
                             "match": "domain", "prefer_live": True},
        # Route substitution, not scope expansion: these three
        # publishers are already in the approved protocol (stage B),
        # but their site-search endpoints render results with
        # client-side JavaScript, so static harvesting returned zero
        # links for two of them (collection report U1). The CDX route
        # reaches the same publishers' archived articles instead.
        "farnham_herald":    {"cdx_url": "farnhamherald.com",
                              "match": "domain", "prefer_live": True},
        "woking_news_mail":  {"cdx_url": "wokingnewsandmail.co.uk",
                              "match": "domain", "prefer_live": True},
        "epsom_ewell_times": {"cdx_url": "epsomandewelltimes.com",
                              "match": "domain", "prefer_live": True},
    }

    def search(self, query):
        cfg = self.SITES[query["source_id"]]
        params = {
            "url": cfg["cdx_url"], "matchType": cfg["match"],
            "from": query["window_start"].replace("-", ""),
            "to": query["window_end"].replace("-", ""),
            "filter": ["statuscode:200", "mimetype:text/html"],
            "collapse": "urlkey", "limit": 2000, "output": "json",
        }
        # query_text carries the CDX original-URL regex from the inventory
        if query["query_text"]:
            params["filter"].append(f"original:{query['query_text']}")
        r = http_get("https://web.archive.org/cdx/search/cdx",
                     archive=True, timeout=60, retries=2, params=params)
        if r is None or r.status_code != 200:
            return [], [{"status": getattr(r, "status_code", None)}]
        try:
            rows = r.json()[1:]
        except ValueError:
            return [], [{"status": r.status_code, "note": "non-JSON"}]
        hits = [{"timestamp": row[1], "url": row[2]}
                for row in rows if self._articleish(row[2])]
        return self._rank(hits, query), [{"status": 200,
                                          "cdx_rows": len(rows)}]

    @staticmethod
    def _articleish(url):
        if "?" in url or "#" in url:
            return False
        bad = ("/search", "/tag/", "/category/", "/all-about/", "/authors/",
               "/wp-", "robots.txt", "/feed", "/page/", "/incoming/")
        if any(b in url.lower() for b in bad):
            return False
        path = re.sub(r"^https?://[^/]+", "", url).rstrip("/")
        return path.count("/") >= 2 and len(path) > 15

    @staticmethod
    def _rank(hits, query):
        """Validated URL priors: date permalinks first, else newest
        trailing article ID first (recency correlates with in-window
        publication; nothing is discarded on this basis - ranking only
        decides fetch order under the per-query budget)."""
        ys = {query["window_start"][:4], query["window_end"][:4]}
        dated = [h for h in hits
                 if any(f"/{y}/" in h["url"] for y in ys)]
        if dated:
            return dated + [h for h in hits if h not in dated]

        def trailing_id(h):
            m = re.search(r"(\d{6,9})/?$", h["url"])
            return int(m.group(1)) if m else -1
        return sorted(hits, key=trailing_id, reverse=True)

    def fetch(self, hit, query):
        cfg = self.SITES[query["source_id"]]
        original, ts = hit["url"], hit["timestamp"]
        live = http_get(original) if cfg["prefer_live"] else None
        if live is not None and live.status_code == 200:
            resp, requested, route, archive_url = (live, original,
                                                   "live_page", None)
        else:
            archive_url = f"https://web.archive.org/web/{ts}/{original}"
            resp = http_get(archive_url, archive=True)
            requested, route = archive_url, "wayback_capture"
        status = getattr(resp, "status_code", None)
        is_pdf = resp is not None and status == 200 and is_pdf_response(resp)
        # See is_pdf_response's docstring: .text on a PDF response corrupts
        # it irrecoverably, so PDFs are diverted before that call is made.
        html = "" if is_pdf else (resp.text if resp is not None else "")
        meta = extract_html_metadata(html) if html else {"dates": []}
        # capture-URL verification: Wayback redirects dead URLs to other
        # captures (often the homepage) - record that as blocked rather
        # than storing a wrong page under the article's identity
        r_status = None
        if resp is None:
            r_status = "gone"
        elif status != 200:
            r_status = "blocked"
        elif route == "wayback_capture" and original.rstrip("/") not in \
                (getattr(resp, "url", "") or ""):
            r_status, meta = "gone", {"dates": [], "text": ""}
        elif is_challenge_page(meta):
            r_status, meta = "blocked", {"dates": [], "text": ""}
        record = build_record(
            source_id=query["source_id"], arm=query["arm"],
            election_id=query["election_id"], adapter="wayback",
            access_route=route, query_id=query["query_id"],
            requested_url=requested, http_status=status,
            final_url=getattr(resp, "url", None), archive_url=archive_url,
            canonical_url=original, publisher=query["source_id"],
            meta=meta, retrieval_status=r_status)
        return record, {"text": meta.get("text"),
                        "raw_html": html if (status == 200 and not is_pdf) else None,
                        "raw_pdf": resp.content if is_pdf else None}


# ---------------------------------------------------------------------------
# Publisher site search - only for the four robots-permitting publishers.
# ---------------------------------------------------------------------------

class SiteSearchAdapter:
    name = "site_search"

    SITES = {   # verified robots-permitting search endpoints (audit 2026-07-22)
        "woking_news_mail":  "https://www.wokingnewsandmail.co.uk/?s={q}",
        "farnham_herald":    "https://www.farnhamherald.com/search?query={q}",
        "guildford_dragon":  "https://guildford-dragon.com/?s={q}",
        "epsom_ewell_times": "https://epsomandewelltimes.com/?s={q}",
    }
    MAX_HITS = 10          # per-query fetch budget for staged collection

    def search(self, query):
        url = self.SITES[query["source_id"]].format(
            q=quote_plus(query["query_text"]))
        r = http_get(url)
        if r is None or r.status_code != 200:
            return [], [{"status": getattr(r, "status_code", None)}]
        # harvest same-site article-like links from the results page;
        # site search has no reliable server-side date filter, so window
        # membership is left entirely to downstream date resolution
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        host = re.sub(r"^https?://(www\.)?|/.*$", "", url)
        seen, hits = set(), []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if host not in href or not WaybackAdapter._articleish(href):
                continue
            if href not in seen:
                seen.add(href)
                hits.append({"url": href, "timestamp": None})
        return hits[:self.MAX_HITS], [{"status": 200,
                                       "links_found": len(seen)}]

    # Oversize guard (added 2026-07-26). A news article is tens of KB;
    # broad keyword queries occasionally hit multi-hundred-MB pages -
    # the worst real case was a 1.6 GB genealogy database stored as
    # "body text", which alone held a quarter of the corpus's disk
    # footprint. Anything past this cap cannot be a news article, so
    # the fetch is recorded honestly as oversize (a retrieval status,
    # like blocked/gone) and NO body is stored. This changes what is
    # STORED for non-articles, never what is discovered or judged.
    MAX_FETCH_BYTES = 8 * 1024 * 1024   # 8 MB

    def fetch(self, hit, query):
        r = http_get(hit["url"])
        status = getattr(r, "status_code", None)
        oversize = (r is not None
                    and len(getattr(r, "content", b"") or b"")
                    > self.MAX_FETCH_BYTES)
        if oversize:
            record = build_record(
                source_id=query["source_id"], arm=query["arm"],
                election_id=query["election_id"], adapter="site_search",
                access_route="live_page", query_id=query["query_id"],
                requested_url=hit["url"], http_status=status,
                final_url=getattr(r, "url", None), archive_url=None,
                canonical_url=hit["url"], publisher=query["source_id"],
                meta={"dates": []}, retrieval_status="oversize")
            return record, {"text": None, "raw_html": None,
                            "raw_pdf": None}
        is_pdf = r is not None and status == 200 and is_pdf_response(r)
        # PDFs never go through .text (see is_pdf_response's docstring for
        # why) and are not HTML-parsed - extract_html_metadata is an HTML
        # parser and would find nothing useful anyway. This is an honest
        # "no date evidence from this stage" gap, same status as an API
        # source that never stores page HTML by design.
        html = "" if is_pdf else (r.text if r is not None else "")
        meta = extract_html_metadata(html) if html else {"dates": []}
        r_status = None
        if r is None:
            r_status = "gone"
        elif status != 200:
            r_status = "blocked"
        elif is_challenge_page(meta):
            r_status, meta = "blocked", {"dates": [], "text": ""}
        record = build_record(
            source_id=query["source_id"], arm=query["arm"],
            election_id=query["election_id"], adapter="site_search",
            access_route="live_page", query_id=query["query_id"],
            requested_url=hit["url"], http_status=status,
            final_url=getattr(r, "url", None), archive_url=None,
            canonical_url=hit["url"], publisher=query["source_id"],
            meta=meta, retrieval_status=r_status)
        return record, {"text": meta.get("text"),
                        "raw_html": html if (status == 200 and not is_pdf) else None,
                        "raw_pdf": r.content if is_pdf else None}


# ---------------------------------------------------------------------------
# Google Programmable Search - automates the Google discovery route
# proposal P3 (news_collection/raw_news_collection_report.md section 6).
#
# Separate and unrelated to SerpAPI: this calls Google's own official
# Custom Search JSON API (googleapis.com/customsearch/v1), which is
# built for exactly this kind of programmatic use and does not violate
# Google's search-results scraping restriction the way querying
# google.com directly would. It shares no code, credentials or quota
# with surrey-election-extractor's SerpApiSearchProvider (a different,
# third-party service) - the two can run side by side without any
# interaction.
#
# Requires two separate pieces of configuration, both free to obtain:
#   GOOGLE_CSE_API_KEY - an API key from Google Cloud Console
#   GOOGLE_CSE_ENGINE_ID - a "cx" ID from a Programmable Search Engine
#                          configured at programmablesearchengine.google.com
#                          (set to search the whole web, not one site,
#                          so it can find whichever Surrey outlet
#                          covered a given ward/candidate/party query)
# Free tier: 100 queries/day. Stage M currently has 631 queries, so a
# full run needs to be spread over roughly a week, or paid past the
# free tier (~$5 per 1,000 queries) - the runner's --budget flag
# already caps how many queries one invocation executes, so this is a
# matter of how the user schedules invocations, not new code.
#
# Per protocol change control (news_research_protocol.md section 9):
# this route is built and ready, but the registry still records
# google_dated_search as manual-only until the supervisor confirms
# proposal P3 - see build_query_inventory.py's comment on this adapter
# for how that pending status is kept visible rather than silently
# overwritten.
# ---------------------------------------------------------------------------

class GoogleCseAdapter:
    name = "google_cse"
    ENDPOINT = "https://www.googleapis.com/customsearch/v1"
    PAGE_SIZE = 10          # Google CSE's fixed page size
    MAX_RESULTS = 20        # 2 pages per query - a deliberate cap so one
                            # query cannot consume a large share of the
                            # free daily quota by itself

    def __init__(self, api_key=None, engine_id=None):
        self.api_key = api_key or os.getenv("GOOGLE_CSE_API_KEY")
        self.engine_id = engine_id or os.getenv("GOOGLE_CSE_ENGINE_ID")

    def search(self, query):
        if not self.api_key or not self.engine_id:
            # Missing credentials is a configuration gap, not a search
            # failure - report it plainly rather than pretending zero
            # results were found (protocol: never silently discard).
            return [], [{"status": None,
                        "note": "GOOGLE_CSE_API_KEY/GOOGLE_CSE_ENGINE_ID "
                                "not configured"}]
        hits, pages_meta = [], []
        for start in range(1, self.MAX_RESULTS + 1, self.PAGE_SIZE):
            r = http_get(self.ENDPOINT, params={
                "key": self.api_key, "cx": self.engine_id,
                "q": query["query_text"],
                # sort by date where Google can infer one; exact 180-day
                # window enforcement still happens downstream from each
                # page's own extracted date evidence, same as every
                # other adapter - this only improves ranking, it is not
                # trusted as a hard filter.
                "sort": "date", "start": start,
            })
            if r is None or r.status_code != 200:
                pages_meta.append({"start": start, "status":
                                   getattr(r, "status_code", None)})
                break
            body = r.json()
            pages_meta.append({"start": start, "status": 200,
                               "total": body.get("searchInformation", {})
                                       .get("totalResults")})
            items = body.get("items", [])
            for item in items:
                hits.append({"url": item.get("link"),
                            "title": item.get("title"),
                            "snippet": item.get("snippet")})
            if len(items) < self.PAGE_SIZE:
                break
        return hits, pages_meta

    def fetch(self, hit, query):
        # CSE returns a URL + snippet, never full content - the actual
        # page still has to be fetched and parsed like any other live
        # page, so this delegates to the same fetch logic SiteSearchAdapter
        # already uses rather than duplicating it.
        proxy = SiteSearchAdapter()
        record, raw = proxy.fetch(hit, query)
        record["retrieval"]["adapter"] = "google_cse"
        return record, raw


# ---------------------------------------------------------------------------
# SerpAPI - a second, independent automated route for Stage M, using the
# student's own personal SerpAPI account (a free-tier quota registered
# separately, unrelated to any other use of SerpAPI elsewhere in this
# repository - see news_protocol/ for the distinction). Same interface
# and same credential-safety discipline as GoogleCseAdapter: reads its
# key from an environment variable only, never logs it, reports a
# missing-credential gap honestly instead of pretending zero results.
#
# Having two independent search-engine adapters lets Stage M run through
# whichever quota is available (or both, splitting the 810 queries
# across them) without changing anything else in the pipeline - the
# runner and schema treat every adapter identically.
# ---------------------------------------------------------------------------

class SerpApiAdapter:
    name = "serpapi"
    ENDPOINT = "https://serpapi.com/search.json"
    MAX_RESULTS = 20   # matches GoogleCseAdapter's per-query cap, for the
                       # same reason: one query should not eat a large
                       # share of a limited free quota

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("SERPAPI_API_KEY")

    def search(self, query):
        if not self.api_key:
            return [], [{"status": None,
                        "note": "SERPAPI_API_KEY not configured"}]
        r = http_get(self.ENDPOINT, params={
            "engine": "google", "q": query["query_text"],
            "num": self.MAX_RESULTS, "api_key": self.api_key,
        })
        if r is None or r.status_code != 200:
            return [], [{"status": getattr(r, "status_code", None)}]
        body = r.json()
        if "error" in body:
            # SerpAPI reports quota/auth problems in a 200-status JSON
            # body, not always via HTTP status - surface that plainly
            # rather than treating it as zero real results.
            return [], [{"status": 200, "error": body["error"]}]
        hits = [{"url": item.get("link"), "title": item.get("title"),
                "snippet": item.get("snippet")}
               for item in body.get("organic_results", [])]
        return hits, [{"status": 200,
                      "total": body.get("search_information", {})
                              .get("total_results")}]

    def fetch(self, hit, query):
        # Same reasoning as GoogleCseAdapter.fetch: SerpAPI returns a
        # link + snippet only, so the actual page fetch/parse logic is
        # shared rather than duplicated.
        proxy = SiteSearchAdapter()
        record, raw = proxy.fetch(hit, query)
        record["retrieval"]["adapter"] = "serpapi"
        return record, raw


# ---------------------------------------------------------------------------
# Serper.dev - the third Google-results route, adopted 2026-07-25.
#
# Why a third adapter for the same job: Stage M's history is a chain of
# closed doors, each documented in the deviations log. The original
# plan was hand-run Google searches (google.com ToS forbids automating
# them). SerpApi automated that lawfully but its free tier (student's
# personal account, 250 searches/month) was exhausted at 266/810
# queries. Google's own Custom Search JSON API (proposal P3) was then
# configured, but Google no longer grants NEW customers access to it -
# every correctly-configured request returns 403 "This project does
# not have the access to Custom Search JSON API" (verified 2026-07-25;
# the API is scheduled for full shutdown on 2027-01-01). Serper.dev is
# a SerpApi-equivalent commercial proxy for real Google results whose
# free allowance (2,500 queries) covers the remaining 544 queries.
#
# Methodological continuity: all three automated routes query the SAME
# Google index, so switching billing/transport does not change what
# can be discovered - the already-executed serpapi rows in
# search_log.csv remain valid and comparable. Like its siblings, this
# adapter reports a missing-credential or quota problem honestly per
# query instead of pretending zero results.
# ---------------------------------------------------------------------------
class SerperAdapter:
    name = "serper"
    ENDPOINT = "https://google.serper.dev/search"
    MAX_RESULTS = 20   # same per-query cap as the other search adapters

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("SERPER_API_KEY")

    def search(self, query):
        if not self.api_key:
            return [], [{"status": None,
                        "note": "SERPER_API_KEY not configured"}]
        # Date-window restriction (added 2026-07-25, deviations log
        # v1.4): the route is NAMED google_dated_search, but the first
        # automated sweeps sent keywords only - Google then ranks
        # present-day pages first, and with a 20-result cap per query,
        # in-window 2013/2017 articles risk being crowded out entirely.
        # Google's cdr (custom date range) filter, passed through
        # serper's tbs parameter, restricts results to the query's
        # pre-registered election window. Dates use Google's M/D/YYYY.
        def _us(d):  # "2013-01-01" -> "1/1/2013"
            y, m, day = d.split("-")
            return f"{int(m)}/{int(day)}/{y}"
        tbs = (f"cdr:1,cd_min:{_us(query['window_start'])},"
               f"cd_max:{_us(query['window_end'])}")
        try:
            r = requests.post(
                self.ENDPOINT,
                headers={"X-API-KEY": self.api_key,
                         "Content-Type": "application/json"},
                json={"q": query["query_text"], "num": self.MAX_RESULTS,
                      "tbs": tbs},
                timeout=TIMEOUT)
        except requests.RequestException as e:
            return [], [{"status": None, "error": str(e)}]
        if r.status_code != 200:
            # 403 = bad key, 400 = malformed, 429 = out of credits -
            # all surfaced with the real status so the runner logs a
            # failed search, never a fake zero-result one.
            return [], [{"status": r.status_code, "error": r.text[:200]}]
        body = r.json()
        hits = [{"url": item.get("link"), "title": item.get("title"),
                "snippet": item.get("snippet")}
               for item in body.get("organic", [])]
        return hits, [{"status": 200, "total": len(hits)}]

    def fetch(self, hit, query):
        # Link + snippet only, like the other search adapters - the
        # shared article-page fetch/parse lives in SiteSearchAdapter.
        proxy = SiteSearchAdapter()
        record, raw = proxy.fetch(hit, query)
        record["retrieval"]["adapter"] = "serper"
        return record, raw


# ---------------------------------------------------------------------------
# Manual import - Google-discovered URLs, archive transcriptions.
# ---------------------------------------------------------------------------

class ManualImportAdapter:
    """Ingests a human-completed worksheet (CSV of url/citation rows) so
    manual material flows through the same schema and logging as
    automated material.  URL rows are fetched like site-search hits;
    citation-only rows become offline_citation records."""

    name = "manual_import"

    def search(self, query):
        import csv
        from pathlib import Path
        sheet = Path(query["query_text"])      # inventory stores the path
        if not sheet.exists():
            return [], [{"status": None, "note": "worksheet missing"}]
        rows = list(csv.DictReader(sheet.open()))
        return ([{"url": r.get("url") or None,
                  "citation": r.get("citation") or None,
                  "timestamp": None} for r in rows],
                [{"status": 200, "rows": len(rows)}])

    def fetch(self, hit, query):
        if hit["url"]:
            proxy = SiteSearchAdapter()
            return proxy.fetch(hit, query)
        record = build_record(
            source_id=query["source_id"], arm=query["arm"],
            election_id=query["election_id"], adapter="manual_import",
            access_route="manual_transcription", query_id=query["query_id"],
            requested_url=None, http_status=None, final_url=None,
            archive_url=None, canonical_url=None,
            offline_citation=hit["citation"],
            publisher=query["source_id"],
            meta={"dates": [], "text": ""}, retrieval_status="ok")
        return record, {}


ADAPTERS = {
    "api": GuardianAdapter,            # instantiated with key by runner
    "wayback_cdx": WaybackAdapter,
    "site_search": SiteSearchAdapter,
    "manual_import": ManualImportAdapter,
    "google_cse": GoogleCseAdapter,    # instantiated with key by runner;
                                       # no-op search() until credentials
                                       # are configured (see class comment)
    "serpapi": SerpApiAdapter,         # student's own personal account;
                                       # same no-op-until-configured behaviour
    "serper": SerperAdapter,           # Google results via serper.dev -
                                       # see class comment for the route history
    # NewsAPI stays dormant: blocked for every window on the current
    # tier (audit).  It gains an adapter here only after an upgrade
    # re-verifies coverage via src/check_newsapi_coverage.py.
}
