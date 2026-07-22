"""Record construction and validation for the Raw News Collection stage.

Everything that turns fetched source material into a raw_news_schema.json
record lives here, so every adapter produces byte-identical structure.

Production changes relative to the pilot, all driven by validation
findings and the stage boundaries:

* Publication dates are NEVER resolved.  Every candidate date found is
  preserved in `date_evidence` with its provenance.  `published_date`
  is filled only when all parseable candidates agree on one calendar
  day; when they conflict (the BBC 2013 case) it stays null, the grade
  becomes `Uncertain`, and the record is flagged for the downstream
  Publication Date Resolution stage in `notes`.
* Raw HTML (or the raw API response) is preserved as a sidecar file so
  later stages can re-extract without re-fetching.  The schema has no
  html field (additionalProperties is false and the schema is a
  completed component), so sidecar paths follow a fixed convention:
      data/raw/news/records/<article_id>.json   the schema record
      data/raw/news/html/<article_id>.html      raw HTML as fetched
      data/raw/news/api_raw/<article_id>.json   raw API response item
      data/raw/news/text/<article_id>.txt       extracted raw text
* Records failing schema validation are quarantined to
  data/raw/news/quarantine/, never silently dropped.
"""

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from jsonschema import Draft7Validator

from . import SCHEMA_VERSION

SCHEMA_PATH = Path("news_protocol/raw_news_schema.json")
VALIDATOR = Draft7Validator(json.loads(SCHEMA_PATH.read_text()))

RAW_ROOT = Path("data/raw/news")
DIRS = {name: RAW_ROOT / name
        for name in ("records", "html", "api_raw", "text", "quarantine")}


def sha256(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def make_article_id(source_id, canonical_ref):
    """Deterministic ID from the canonical reference: re-retrieving the
    same URL can never mint a second identity (idempotent collection)."""
    return f"NEWS-{source_id}-{sha256(canonical_ref)[:12]}"


# ---------------------------------------------------------------------------
# HTML metadata extraction (shared by every HTML-fetching adapter).
# Identical candidate-date harvesting to the validated pilot extractor:
# JSON-LD, OpenGraph/meta tags, visible <time> elements - all kept.
# ---------------------------------------------------------------------------

def extract_html_metadata(html):
    soup = BeautifulSoup(html, "html.parser")
    meta = {"headline": None, "byline": None, "dates": []}

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            blocks = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        blocks = blocks if isinstance(blocks, list) else [blocks]
        for b in blocks:
            if not isinstance(b, dict):
                continue
            for node in (b.get("@graph") if isinstance(b.get("@graph"), list)
                         else [b]):
                if not isinstance(node, dict):
                    continue
                if node.get("datePublished"):
                    meta["dates"].append({"value": str(node["datePublished"]),
                                          "found_in": "json_ld"})
                if not meta["headline"] and node.get("headline"):
                    meta["headline"] = str(node["headline"])
                author = node.get("author")
                if not meta["byline"] and isinstance(author, dict):
                    meta["byline"] = author.get("name")

    for prop in ("article:published_time", "og:article:published_time"):
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            meta["dates"].append({"value": tag["content"],
                                  "found_in": "opengraph"})
    for name in ("parsely-pub-date", "date", "article.published"):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            meta["dates"].append({"value": tag["content"],
                                  "found_in": "meta_tag"})
    if not meta["headline"]:
        og = soup.find("meta", attrs={"property": "og:title"})
        meta["headline"] = (og["content"].strip() if og and og.get("content")
                            else (soup.title.get_text(strip=True)
                                  if soup.title else None))
    t = soup.find("time", attrs={"datetime": True})
    if t:
        meta["dates"].append({"value": t["datetime"],
                              "found_in": "visible_dateline"})

    container = soup.find("article") or soup
    paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    meta["text"] = "\n".join(x for x in paras if len(x) > 40)
    return meta


def parse_date(value):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
    if m:
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            return None
    return None


def summarise_dates(evidence):
    """Stage-boundary rule: PRESERVE, never resolve.

    Returns (published_date_or_None, confidence, needs_review_note).
    - all parseable candidates agree  -> that date; Confirmed if any
      machine-readable source, else Probable
    - candidates disagree             -> None + Uncertain + review flag
      (never pick one - the BBC 2013 pilot case)
    - nothing parseable               -> None + Missing + review flag
    """
    parsed = {}
    for ev in evidence:
        d = parse_date(ev["value"])
        if d:
            parsed.setdefault(d, set()).add(ev["found_in"])
    if not parsed:
        return None, "Missing", "no parseable publication date; downstream date review required"
    if len(parsed) == 1:
        d, sources = next(iter(parsed.items()))
        machine = {"json_ld", "opengraph", "meta_tag", "api_field"}
        return d, ("Confirmed" if sources & machine else "Probable"), None
    return None, "Uncertain", (
        "conflicting publication dates "
        f"({', '.join(x.isoformat() for x in sorted(parsed))}); "
        "downstream date review required")


# ---------------------------------------------------------------------------
# Record assembly + persistence.
# ---------------------------------------------------------------------------

def build_record(*, source_id, arm, election_id, adapter, access_route,
                 query_id, requested_url, http_status, final_url,
                 archive_url, canonical_url, offline_citation=None,
                 publisher, meta, retrieval_status=None):
    """Assemble one schema record from extracted metadata.  The caller
    persists it with save_record(); nothing is written here."""
    text = (meta.get("text") or "").strip()
    pub_date, confidence, review_note = summarise_dates(meta.get("dates", []))
    return {
        "schema_version": SCHEMA_VERSION,
        "article_id": make_article_id(source_id,
                                      canonical_url or offline_citation
                                      or requested_url),
        "source_id": source_id,
        "arm": arm,
        "discovered_for_election": election_id,
        "retrieval": {
            "adapter": adapter,
            "adapter_version": "1.0.0",
            "access_route": access_route,
            "search_query_id": query_id,
            "retrieved_at": datetime.now(timezone.utc)
                            .isoformat(timespec="seconds"),
            "http_status": http_status,
            "retrieval_status": retrieval_status
                                or ("ok" if text else "parse_failed"),
            "requested_url": requested_url,
            "final_url": final_url,
            "archive_url": archive_url,
        },
        "identity": {
            "canonical_url": canonical_url,
            "offline_citation": offline_citation,
            "publisher": publisher,
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
            "text_path": None,        # filled by save_record once written
            "extract": (text[:497] + "..." if len(text) > 500
                        else (text or None)),
            "word_count": len(text.split()) if text else None,
            "text_sha256": sha256(text) if text else None,
        },
        "notes": review_note,
    }


def save_record(record, *, text=None, raw_html=None, raw_api=None):
    """Persist one record plus its raw sidecars.

    Validates against the schema first; invalid records go to the
    quarantine directory with their validation errors attached, and the
    caller is told so it can log the failure - nothing is discarded.
    Returns (status, article_id) where status is 'ok', 'exists' or
    'quarantined'.
    """
    for d in DIRS.values():
        d.mkdir(parents=True, exist_ok=True)
    aid = record["article_id"]

    if text:
        path = DIRS["text"] / f"{aid}.txt"
        path.write_text(text)
        record["content"]["text_path"] = str(path)
    if raw_html is not None:
        (DIRS["html"] / f"{aid}.html").write_text(raw_html, errors="replace")
    if raw_api is not None:
        (DIRS["api_raw"] / f"{aid}.json").write_text(
            json.dumps(raw_api, indent=1))

    errors = [e.message for e in VALIDATOR.iter_errors(record)]
    if errors:
        (DIRS["quarantine"] / f"{aid}.json").write_text(
            json.dumps({"validation_errors": errors, "record": record},
                       indent=1))
        return "quarantined", aid

    out = DIRS["records"] / f"{aid}.json"
    if out.exists():
        # Same canonical reference fetched again (e.g. two queries hit
        # the same article): keep the first record - cross-SOURCE copies
        # have different IDs and are all kept for the dedup stage.
        return "exists", aid
    out.write_text(json.dumps(record, indent=1))
    return "ok", aid
