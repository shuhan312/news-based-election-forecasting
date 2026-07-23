"""Second pass over the Publication Date Resolution stage's unresolved
records (resolve_publication_dates.py's needs_human_review and
unresolvable_missing_evidence rows) - gathers MORE real evidence where
it safely exists, and reclassifies records whose problem is actually a
retrieval/parsing defect rather than a genuine missing date.

This does not resolve any date itself. It only:
  1. Identifies records whose stored "HTML" is not HTML at all (a PDF,
     caught by its file signature) - a distinct, fixable data-quality
     defect, not evidence the article has no date.
  2. Re-scans genuine HTML pages with a NARROW, pre-validated set of
     extra patterns (see SAFE_EXTRA_PATTERNS below) and adds anything
     found as supplementary evidence in the resolution log - never
     used to auto-decide a boundary-relevant conflict, only to give a
     human reviewer more to go on.

Why this stops short of a general "scan more broadly" approach
-----------------------------------------------------------------
Tested exactly that first, against a real record
(epsom_ewell_times/af1614b7037a): scanning every element whose CSS
class merely contained the word "date" surfaced "18 July 2026" and "22
July 2026" - today's date at the time of this investigation, coming
from a "related articles" sidebar widget, not the article itself. That
is precisely the contamination the protocol prohibits (never treat a
retrieval-adjacent date as a publication date). A blanket broader scan
would make date evidence WORSE, not better, so it is rejected here as
a real, tested, negative finding - not left untried and assumed to be
fine.

The only additions allowed are the two patterns below, each verified
against a real record before being added:
  * BBC's "class=meta" byline text (e.g. "Published 3 May 2013"),
    confirmed against the BBC 2013 pilot/production record where it
    correctly REPEATS the visible dateline rather than contradicting
    it - it is treated as corroborating evidence for a
    conflict already under review, never a tie-breaker on its own.
  * A stricter "Published: <day> <Month> <year>" text pattern
    immediately following the headline element, which by construction
    cannot match a distant sidebar widget.

Usage:
    python3 -m src.news_collection.investigate_unresolved_dates
"""

import csv
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

LOG = Path("news_collection/date_resolution_log.csv")
HTML_DIR = Path("data/raw/news/html")
OUT = Path("news_collection/date_resolution_investigation.csv")

PUBLISHED_TEXT = re.compile(
    r"published\s*:?\s*(\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE)


def is_pdf(path):
    with path.open("rb") as fh:
        return fh.read(4) == b"%PDF"


def corroborating_evidence(soup):
    """Only the two pre-validated, narrow patterns described in the
    module docstring - deliberately not a general class-name scan."""
    found = []
    for el in soup.find_all(class_="meta"):
        text = el.get_text(" ", strip=True)
        m = PUBLISHED_TEXT.search(text)
        if m:
            found.append(("bbc_class_meta", m.group(1)))
    heading = soup.find(["h1"])
    if heading:
        # Only the text immediately after the headline, not the whole
        # page, so a sidebar widget several containers away cannot match.
        sibling_text = " ".join(
            s.get_text(" ", strip=True) for s in heading.find_next_siblings()[:2])
        m = PUBLISHED_TEXT.search(sibling_text)
        if m:
            found.append(("text_near_headline", m.group(1)))
    return found


def main():
    rows = list(csv.DictReader(LOG.open()))
    problem_rows = [r for r in rows if r["resolution_status"]
                    in ("needs_human_review", "unresolvable_missing_evidence")]

    out_rows = []
    pdf_count = 0
    corroborated_count = 0
    for r in problem_rows:
        html_path = HTML_DIR / f"{r['article_id']}.html"
        finding = {"article_id": r["article_id"],
                  "original_status": r["resolution_status"],
                  "defect_type": "", "corroborating_evidence": "",
                  "recommendation": ""}

        if not html_path.exists():
            finding["defect_type"] = "no_html_stored"
            finding["recommendation"] = (
                "Check retrieval.adapter in the raw record - API-sourced "
                "records (e.g. Guardian) never store HTML by design; "
                "their date conflict must be resolved from the API's own "
                "date fields, not page text.")
        elif is_pdf(html_path):
            pdf_count += 1
            finding["defect_type"] = "stored_content_is_pdf_not_html"
            finding["recommendation"] = (
                "Re-extract with a PDF text extractor (PyMuPDF, matching "
                "the project's PDF-handling convention elsewhere) instead "
                "of the HTML parser - this is a retrieval/parsing defect, "
                "not evidence the article lacks a date.")
        else:
            soup = BeautifulSoup(html_path.read_text(errors="replace"),
                                 "html.parser")
            evidence = corroborating_evidence(soup)
            if evidence:
                corroborated_count += 1
                finding["corroborating_evidence"] = "; ".join(
                    f"{src}={val}" for src, val in evidence)
                finding["recommendation"] = (
                    "Additional evidence found - present to the human "
                    "reviewer alongside the original conflict. Does NOT "
                    "auto-resolve a boundary-relevant conflict on its own.")
            else:
                finding["defect_type"] = "genuine_gap_no_further_evidence"
                finding["recommendation"] = (
                    "No further date evidence recoverable from stored "
                    "content. Needs a human to check the live/archived "
                    "page directly, or remains excluded.")
        out_rows.append(finding)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    print(f"{len(out_rows)} unresolved records re-examined -> {OUT}")
    print(f"  stored content is actually a PDF: {pdf_count}")
    print(f"  corroborating evidence found (still needs human sign-off "
          f"where boundary-relevant): {corroborated_count}")
    print(f"  genuine gaps, nothing more to recover: "
          f"{len(out_rows) - pdf_count - corroborated_count}")
    print("\nRejected approach: scanning every class name containing "
          "'date' was tested and surfaced a sidebar 'related articles' "
          "date instead of the article's own date - confirmed unsafe, "
          "not used here. See module docstring.")


if __name__ == "__main__":
    main()
