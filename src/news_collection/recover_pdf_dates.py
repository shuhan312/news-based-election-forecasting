"""Recover publication-date evidence for the three records whose stored
"HTML" sidecar was actually a PDF, corrupted at collection time.

What happened (found 2026-07-23 during the date-quality investigation;
recorded in manual_review_decisions.csv, see Git history)
---------------------------------------------------------------------
Three Stage-M search hits were official election PDFs, not web pages:

  * a Statement of Persons Nominated (Tandridge District Council)
  * the LGBCE's final boundary-review report for Surrey
  * a Declaration of Results (Epsom & Ewell Borough Council)

The shared fetch path read every response with `resp.text`, which
decodes bytes as guessed text. That is fine for HTML but irreversibly
mangles PDF binary data (every non-decodable byte becomes U+FFFD), so
the stored sidecars cannot be parsed by any PDF reader. The root cause
is now fixed in adapters.py (is_pdf_response + raw_pdf routing into
data/raw/news/pdf/), but the three already-corrupted sidecars are
unrecoverable from disk - the only honest remedy is to fetch the same
canonical URLs again, binary-safe this time.

What this script does, and deliberately does not do
---------------------------------------------------
  1. Re-downloads each PDF from its canonical URL (raw bytes, verified
     against the %PDF file signature before anything is saved).
  2. Stores the intact copy under data/raw/news/pdf/{article_id}.pdf -
     a NEW sidecar next to the record, never overwriting the corrupted
     html/ sidecar (which stays as evidence of the defect) and never
     editing the raw record JSON itself (records are immutable).
  3. Extracts every piece of date evidence the PDF actually carries:
     the document-metadata creation/modification timestamps, plus any
     dated text on the first page (official notices carry their legally
     required publication date in the body text).
  4. Writes all of it to news_collection/pdf_date_recovery.csv for
     review - it does NOT auto-decide any date. These are ESWS-2026-05
     records, and a wrongly resolved date near that election's window
     could flip an eligibility decision, exactly the situation
     resolve_publication_dates.py routes to human review. Decisions
     belong in manual_review_decisions.csv once a human has looked.

Usage:
    python3 -m src.news_collection.recover_pdf_dates
"""

import csv
import json
import re
from pathlib import Path

import fitz  # PyMuPDF

from .adapters import http_get
from .schema import DIRS

RECORDS = Path("data/raw/news/records")
OUT = Path("news_collection/pdf_date_recovery.csv")

# The corrupted records, identified during the 2026-07-23 date-quality
# investigation (defect_type=stored_content_is_pdf_not_html). Hard-coded on purpose:
# this is a one-off remediation of a specific known defect, not a
# general re-fetch tool, and listing them here makes the scope auditable.
# First 3 identified and recovered 2026-07-23 (see manual_review_
# decisions.csv); remaining 9 surfaced when Stage M's later collection
# (which continued after that first pass) was re-checked by the same
# date-quality investigation and turned up more PDF hits from the
# same underlying pre-fix adapter defect.
CORRUPTED_PDF_RECORDS = [
    "NEWS-google_dated_search-04a8c7a65b28",  # Statement of Persons Nominated
    "NEWS-google_dated_search-5f37425836d7",  # LGBCE final boundary report
    "NEWS-google_dated_search-dbea7e392b72",  # Declaration of Results
    "NEWS-google_dated_search-08df95b1bd77",
    "NEWS-google_dated_search-2a2d626406a9",
    "NEWS-google_dated_search-442d80562cfd",
    "NEWS-google_dated_search-9e990ac857b9",
    "NEWS-google_dated_search-9edc32766662",
    "NEWS-google_dated_search-a7636afef375",
    "NEWS-google_dated_search-afc3bd05adec",
    "NEWS-google_dated_search-eb477830e1b8",
    "NEWS-google_dated_search-fb4ae8e23873",
]

# Dates written out in official-notice style, e.g. "24 April 2026" or
# "24th April 2026". Deliberately requires a written month name: purely
# numeric strings (04/2026, reference numbers) are too easy to mismatch.
TEXT_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{4})\b", re.IGNORECASE)

# PDF metadata timestamps look like "D:20260424094158+01'00'".
PDF_META_DATE = re.compile(r"D:(\d{4})(\d{2})(\d{2})")


def pdf_date_evidence(doc):
    """Every distinct piece of date evidence in the PDF, labelled by
    where it was found - same provenance discipline as the raw schema's
    date_evidence[] (label everything, resolve nothing here)."""
    evidence = []
    for key in ("creationDate", "modDate"):
        m = PDF_META_DATE.match(doc.metadata.get(key) or "")
        if m:
            evidence.append((f"pdf_metadata_{key}",
                             "-".join(m.groups())))
    # Body-text dates from the first page only: official notices state
    # their publication/signing date up front, while later pages of a
    # long report (the LGBCE one runs to dozens of pages) are full of
    # incidental dates (consultation periods, past elections) that are
    # NOT publication evidence and would only add noise.
    if doc.page_count:
        for m in TEXT_DATE.finditer(doc[0].get_text()):
            evidence.append(("first_page_text", m.group(0)))
    return evidence


def main():
    rows = []
    for aid in CORRUPTED_PDF_RECORDS:
        rec = json.loads((RECORDS / f"{aid}.json").read_text())
        url = rec["identity"]["canonical_url"]
        row = {"article_id": aid,
               "election_id": rec["discovered_for_election"],
               "canonical_url": url,
               "refetch_status": "", "pdf_path": "",
               "date_evidence": "", "note": ""}

        r = http_get(url)
        if r is None or r.status_code != 200:
            # An honest gap: source now gone/blocked. The record simply
            # stays unresolved - never substitute a guessed date.
            row["refetch_status"] = (
                f"failed_http_{getattr(r, 'status_code', 'none')}")
            row["note"] = ("Re-fetch failed; date remains unresolved. "
                           "Corrupted html/ sidecar kept as-is.")
            rows.append(row)
            continue
        if r.content[:5] != b"%PDF-":
            # The URL no longer serves a PDF (moved, replaced by an
            # error page, ...) - saving it would repeat the original
            # mistake of storing the wrong thing under this identity.
            row["refetch_status"] = "not_a_pdf_anymore"
            row["note"] = "Response lacks %PDF signature; nothing saved."
            rows.append(row)
            continue

        pdf_path = DIRS["pdf"] / f"{aid}.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(r.content)   # bytes, never a text decode
        row["refetch_status"] = "ok"
        row["pdf_path"] = str(pdf_path)

        doc = fitz.open(pdf_path)
        evidence = pdf_date_evidence(doc)
        row["date_evidence"] = "; ".join(f"{src}={val}"
                                         for src, val in evidence)
        if not evidence:
            row["note"] = ("Intact PDF recovered but it carries no "
                           "date evidence - a genuine gap, recorded "
                           "honestly rather than guessed.")
        rows.append(row)
        print(f"{aid}: {row['refetch_status']}, "
              f"{len(evidence)} piece(s) of date evidence")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} records -> {OUT}")
    print("No dates were auto-resolved: these are ESWS-2026-05 records "
          "whose dates could sit near eligibility boundaries, so any "
          "decision goes through manual_review_decisions.csv after "
          "human inspection of this evidence.")


if __name__ == "__main__":
    main()
