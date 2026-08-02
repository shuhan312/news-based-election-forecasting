"""One-election feature rows for the Woking South blind test.

    python3 -m src.news_features.build_woking_south_blind_features

Identical machinery to the Haslemere probe's feature build: the frozen
builder over a one-election grid, a release built with the extraction
module's own selection code, `load_records` filtered to exactly this
test's tranche. Role is ``test``: these rows are prediction inputs for
the frozen and protocol-pinned specifications, never fitting input.
No outcome column exists anywhere in this path.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from src.llm_extraction import run_corpus_extraction as extraction
from src.llm_extraction.run_woking_south_blind_extraction import WOKING_SOUTH
from src.news_features import build_feature_table as frozen

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "news_features/woking_south_blind_v1"
RELEASE_OUT = REPO / ("news_collection/woking_south_blind/"
                      "canonical_corpus_woking_south.json")
TRANCHE_FILE = REPO / "llm_context/corpus_extraction_outputs_wokingsouth1.json"

DECISIONS = REPO / "news_collection/woking_south_blind/eligibility_decisions.csv"
DATES = REPO / "news_collection/woking_south_blind/effective_dates.csv"


def build_release() -> tuple[dict, dict[str, dict]]:
    terminal = extraction.eligible_articles()
    usable, fallback_ids, census = extraction.load_tranche(
        "wokingsouthrelease", only_ids=set(terminal))
    for article in usable.values():
        text = ((article.get("title") or "") + " "
                + (article.get("body") or "")).lower()
        article["mentions_reform"] = "reform uk" in text

    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    identity = {"rules_version": "canonical-woking-south-blind-v1",
                "source_sha256": {str(p.relative_to(REPO)): _sha(p)
                                  for p in (DECISIONS, DATES)}}
    release_id = "canonical-wokingsouth-" + hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]
    by_arm = Counter((a.get("arm") or "?") for a in usable.values())
    report = {
        "release_id": release_id,
        "rules_version": identity["rules_version"],
        "scope": ("Woking South 2025-07-10 blind-test corpus: terminal "
                  "includes, usable dates, 1-180 days pre-poll, usable "
                  "text. Prediction inputs only; never fitting input."),
        "usable_feature_corpus": {
            "articles": len(usable),
            "by_arm": dict(sorted(by_arm.items())),
            "by_election": {WOKING_SOUTH: len(usable)},
            "by_window": dict(sorted(Counter(
                a["window"] for a in usable.values()).items())),
        },
        "terminal_include_union": {"articles": len(terminal)},
        "excluded_after_terminal_include": len(terminal) - len(usable),
        "source_sha256": identity["source_sha256"],
        "article_ids_sha256": hashlib.sha256(
            "\n".join(sorted(usable)).encode()).hexdigest(),
        "article_ids": sorted(usable),
    }
    return report, usable


def load_records() -> tuple[dict[str, dict], dict]:
    payload = json.loads(TRANCHE_FILE.read_text())
    records = {layer: {} for layer in frozen.live_layers()}
    provenance: Counter = Counter()
    for layer in frozen.live_layers():
        for record in payload.get("layers", {}).get(layer, []):
            if record.get("record") is None or record.get("validation_errors"):
                continue
            records[layer][record["article_id"]] = record
            provenance[(layer, "wokingsouth1",
                        (record.get("prompt_sha256") or "none")[:12])] += 1
    return records, {"per_layer_tranche_prompt": {
        f"{k[0]}|{k[1]}|{k[2]}": v for k, v in provenance.items()},
        "superseded_layers_honoured": {}}


frozen.OUT_CSV = OUT_DIR / "news_feature_table_wokingsouth.csv"
frozen.OUT_META = OUT_DIR / "news_feature_table_wokingsouth_metadata.json"
frozen.build_release = build_release
frozen.CANONICAL_MANIFEST = RELEASE_OUT
frozen.load_records = load_records
frozen.SPLIT_ROLE = {**frozen.SPLIT_ROLE, WOKING_SOUTH: "test"}
frozen.GRID_ELECTIONS = [WOKING_SOUTH]


def main() -> None:
    frozen.main()


if __name__ == "__main__":
    main()
