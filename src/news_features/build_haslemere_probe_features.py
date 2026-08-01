"""Build the Haslemere probe's one-election feature rows (exploratory).

    python3 -m src.news_features.build_haslemere_probe_features

The frozen feature builder, pointed at a one-election corpus. Every
aggregation rule, share definition, zero-cell policy and window
assignment is ``build_feature_table``'s code unchanged; this wrapper
rebinds the same module globals the v2 wrapper rebinds, plus one more
(``load_records``), because the probe must see exactly one extraction
tranche where production saw many:

- the corpus source becomes a Haslemere-only release built with the
  extraction module's own ``eligible_articles``/``load_tranche``
  machinery (the probe extraction wrapper already binds that module's
  decisions, dates and polling registry at import);
- ``load_records`` reads only ``corpus_extraction_outputs_haslemere1``,
  with the frozen loader's acceptance rule reproduced verbatim (a
  record counts only if non-null and validation-clean) - the global
  glob would otherwise pull in 1,632 principal articles and fail the
  builder's own subset assertion;
- the grid is the single probe election, labelled ``test``: these rows
  exist to be PREDICTED from by the frozen v2 models and are never
  fitting input, so fit-side verdicts printed by the builder describe
  one election and are not used.

Outputs live under ``news_features/haslemere_probe/`` and touch no
principal, v1 or v2 artefact.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

# Importing the extraction wrapper applies its module bindings: probe
# decisions and effective dates, silenced pilot/validation sheets, and
# the probe election in POLLING. The census/submit/collect entry point
# is untouched - only the bindings are wanted here.
from src.llm_extraction import run_corpus_extraction as extraction
from src.llm_extraction.run_haslemere_probe_extraction import HASLEMERE
from src.news_features import build_feature_table as frozen

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "news_features/haslemere_probe"
RELEASE_OUT = REPO / "news_collection/haslemere_probe/canonical_corpus_haslemere.json"
TRANCHE_FILE = REPO / "llm_context/corpus_extraction_outputs_haslemere1.json"

DECISIONS = REPO / "news_collection/haslemere_probe/eligibility_decisions.csv"
DATES = REPO / "news_collection/haslemere_probe/effective_dates.csv"


def build_probe_release() -> tuple[dict, dict[str, dict]]:
    """Haslemere-only analogue of the canonical release builders.

    Same selection machinery (terminal includes -> usable text inside
    the election's own windows), same ``mentions_reform`` stamp, same
    identity discipline: the release id hashes the rules version and
    the source-file digests, so a changed input is a changed release.
    """

    terminal = extraction.eligible_articles()
    usable, fallback_ids, census = extraction.load_tranche(
        "haslemereproberelease", only_ids=set(terminal))
    for article in usable.values():
        text = ((article.get("title") or "") + " "
                + (article.get("body") or "")).lower()
        article["mentions_reform"] = "reform uk" in text
    census["terminal_includes"] = len(terminal)
    census["raw_text_fallback"] = len(fallback_ids)

    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    source_hashes = {
        str(path.relative_to(REPO)): _sha(path) for path in (DECISIONS, DATES)
    }
    identity = {
        "rules_version": "canonical-haslemere-probe-news-v1",
        "source_sha256": source_hashes,
    }
    release_id = "canonical-haslemere-" + hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]

    by_arm = Counter((a.get("arm") or "unknown") for a in usable.values())
    by_window = Counter(a["window"] for a in usable.values())
    report = {
        "release_id": release_id,
        "rules_version": identity["rules_version"],
        "scope": (
            "The Haslemere 2026-07-07 by-election probe corpus only: "
            "terminal include decisions from the human-plus-LLM stage 5 "
            "assembly, usable date, 1-180 days before its polling day, "
            "usable text. Exploratory; never fitting input."
        ),
        "probe_census": census,
        "usable_feature_corpus": {
            "articles": len(usable),
            "by_arm": dict(sorted(by_arm.items())),
            "by_election": {HASLEMERE: len(usable)},
            "by_window": dict(sorted(by_window.items())),
        },
        "terminal_include_union": {"articles": len(terminal)},
        "excluded_after_terminal_include": census.get("terminal_includes", 0)
            - len(usable),
        "source_sha256": source_hashes,
        "article_ids_sha256": hashlib.sha256(
            "\n".join(sorted(usable)).encode("utf-8")).hexdigest(),
        "article_ids": sorted(usable),
    }
    return report, usable


def load_probe_records() -> tuple[dict[str, dict], dict]:
    """The frozen loader's acceptance rule, over the one probe tranche."""

    payload = json.loads(TRANCHE_FILE.read_text())
    tranche = payload.get("tranche", "haslemere1")
    records: dict[str, dict[str, dict]] = {
        layer: {} for layer in frozen.live_layers()}
    provenance: Counter = Counter()
    for layer in frozen.live_layers():
        for r in payload.get("layers", {}).get(layer, []):
            if r.get("record") is None or r.get("validation_errors"):
                continue
            records[layer][r["article_id"]] = r
            provenance[(layer, tranche,
                        (r.get("prompt_sha256") or "none")[:12])] += 1
    return records, {
        "per_layer_tranche_prompt": {
            f"{k[0]}|{k[1]}|{k[2]}": v for k, v in provenance.items()},
        "superseded_layers_honoured": {},
    }


frozen.OUT_CSV = OUT_DIR / "news_feature_table_haslemere.csv"
frozen.OUT_META = OUT_DIR / "news_feature_table_haslemere_metadata.json"
frozen.build_release = build_probe_release
frozen.CANONICAL_MANIFEST = RELEASE_OUT
frozen.load_records = load_probe_records
frozen.SPLIT_ROLE = {**frozen.SPLIT_ROLE, HASLEMERE: "test"}
frozen.GRID_ELECTIONS = [HASLEMERE]


def main() -> None:
    frozen.main()


if __name__ == "__main__":
    main()
