"""Reduce a tranche's batch manifest to the digest its Git record needs.

A full manifest is what `collect` reads: the batch ids, the article ids to load
by, and - for stance_revised, whose prompt depends on which parties an article
names - the question set per article. On the full corpus that is 5,975 lines,
of which about 5,400 are machine-generated ids. Needed on disk, and poor value
in a commit history.

The same problem was already solved once in this project. `d4_llm_output_manifest.json`
began as 5,034 lines carrying 720 per-article hashes and was reduced to 90,
holding a per-file sha256 and per-layer parse counts - enough to prove a figure
came from those exact answers without reproducing them. This applies that
precedent to the batch manifests.

What the digest keeps, and why each entry is load-bearing for provenance:

* the batch ids, so a run can be re-retrieved from the API for 29 days;
* the per-layer prompt fingerprints written at submit time, which are what tie
  a record to the bytes that produced it;
* the models, the article count, and the window census;
* the excluded layers with the figure that excluded each;
* a sha256 over the sorted article id list, and another over the stance
  question sets. These replace the lists themselves: anyone holding the full
  manifest can recompute both and confirm it is the file this digest describes,
  which is the whole claim a committed manifest makes.

What it drops: the 1,374 article ids, the 1,006 stance question sets, and the
raw-text fallback id list - all reproducible from the retained local file, and
all verifiable against it by hash.

Usage:
    python3 -m src.llm_extraction.write_batch_manifest_digest all
    python3 -m src.llm_extraction.write_batch_manifest_digest all far far2 far3 narrow
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _sha256_of(value) -> str:
    """Hash a JSON value canonically, so the digest is reproducible.

    Sorted keys and no whitespace, because a hash that depended on formatting
    would fail to verify against a file someone had reindented.
    """
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def digest(tranche: str) -> dict:
    src = Path(f"llm_context/corpus_extraction_batches_{tranche}.json")
    m = json.loads(src.read_text())
    ids = sorted(m.get("article_ids") or [])
    stance = m.get("stance_question_sets") or {}
    fallback = m.get("raw_text_fallback_ids") or []
    return {
        "tranche": tranche,
        "version": m.get("version"),
        "layers": m.get("layers"),
        "layer_models": m.get("layer_models"),
        "layer_prompt_sha256": m.get("layer_prompt_sha256"),
        "excluded_layers": m.get("excluded_layers"),
        "articles": m.get("articles"),
        "census": m.get("census"),
        "windows_in_tranche": m.get("windows_in_tranche"),
        "article_ids_sha256": _sha256_of(ids) if ids else None,
        "article_ids_count": len(ids),
        "stance_question_sets_sha256": _sha256_of(stance) if stance else None,
        "stance_question_sets_count": len(stance),
        "raw_text_fallback_count": len(fallback),
        "source_file": src.name,
        "source_file_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "note": ("The article ids, stance question sets and fallback id list "
                 "are held in the local manifest named above, which is "
                 "gitignored for size. Recompute the hashes here against that "
                 "file to confirm it is the one this digest describes; the "
                 "canonical form is json.dumps(value, sort_keys=True, "
                 "separators=(',', ':'))."),
    }


def main() -> None:
    tranches = sys.argv[1:] or ["all"]
    out = Path("llm_context/corpus_extraction_batch_digests.json")
    existing = json.loads(out.read_text()) if out.exists() else {}
    for t in tranches:
        d = digest(t)
        existing[t] = d
        src_lines = len(
            (Path("llm_context") / d["source_file"]).read_text().splitlines())
        print(f"  {t:7s} {src_lines:5,} lines -> digest  "
              f"({d['article_ids_count']} article IDs, "
              f"{d['stance_question_sets_count']} stance question sets)")
    out.write_text(json.dumps(existing, indent=2, sort_keys=True))
    print(f"\n-> {out} ({len(out.read_text().splitlines())} lines, "
          f"{len(existing)} tranches)")


if __name__ == "__main__":
    main()
