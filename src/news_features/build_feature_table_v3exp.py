"""Build the exploratory v3 feature table (v2 corpus + 29 new local).

    python3 -m src.news_features.build_feature_table_v3exp

The same frozen builder that produced v1 and v2, pointed at a third
lineage. Three globals move and one loader is filtered; everything
else - aggregation rules, zero-cell policy, split roles, the
12-election grid, the reporting gate itself - is byte-identical, so
whatever verdict the gate prints is the frozen rule's own answer to
the question this lineage exists for: do the reviewer's 29 newly
admitted local articles lift any local column over the 10-value bar?

- The release source becomes the v2 release machinery with its
  by-election decisions input repointed at the v3 assembly - the v2
  release JSON and its recorded hashes stay untouched on disk;
- outputs are written as ``*_v3exp`` beside the frozen tables;
- ``load_records`` is filtered to exclude the Haslemere probe tranche:
  its 20 articles belong to a different corpus (the probe's own
  release) and would fail this build's articles-subset assertion.

EXPLORATORY lineage: nothing here feeds or alters the confirmatory
chain; the unblinding preceded every judgement it contains.
"""

from __future__ import annotations

import glob
import json
from collections import Counter
from pathlib import Path

from src.news_collection import canonical_corpus_release_v2 as release_v2
from src.news_features import build_feature_table as frozen

V3_DECISIONS = Path(
    "news_collection/e5_local_backlog_v3/byelection_eligibility_decisions_v3.csv")
V3_RELEASE = Path(
    "news_collection/e5_local_backlog_v3/canonical_corpus_release_v3exp.json")

# Repoint the release machinery's by-election decisions input at the v3
# assembly. The module-level constant is read at build_release() time,
# so this rebinding is the entire change; the v2 release file on disk
# is never rewritten.
release_v2.BYELECTION_DECISIONS = (
    release_v2.REPO / V3_DECISIONS)

frozen.OUT_CSV = frozen.OUT_CSV.with_name("news_feature_table_v3exp.csv")
frozen.OUT_META = frozen.OUT_META.with_name(
    "news_feature_table_v3exp_metadata.json")
frozen.build_release = release_v2.build_release
frozen.CANONICAL_MANIFEST = V3_RELEASE
frozen.SPLIT_ROLE.update({
    election_id: "train"
    for election_id in release_v2.BYELECTION_POLLING_DAYS
})
frozen.GRID_ELECTIONS = sorted(
    set(release_v2.BYELECTION_POLLING_DAYS)
    | {"SCC-2013-05", "SCC-2017-05", "SCC-2021-05", "ESWS-2026-05"}
)

_original_load_records = frozen.load_records


def load_records_without_probe() -> tuple[dict[str, dict], dict]:
    """The frozen loader over every tranche EXCEPT the Haslemere probe.

    Replicates the loader's file walk with one file skipped rather than
    filtering afterwards, so provenance counts stay exact.
    """

    paths = [p for p in sorted(glob.glob(
        "llm_context/corpus_extraction_outputs_*.json"))
        if not p.endswith("corpus_extraction_outputs_haslemere1.json")]
    order = {"narrow": 0, "far": 1, "far2": 2, "far3": 3, "all": 9}

    def rank(path: str) -> int:
        name = Path(path).stem.replace("corpus_extraction_outputs_", "")
        return order.get(name, 5)

    records: dict[str, dict] = {layer: {} for layer in frozen.live_layers()}
    provenance: Counter = Counter()
    superseded_seen: dict[str, list[str]] = {}
    for path in sorted(paths, key=rank):
        payload = json.loads(Path(path).read_text())
        tranche = payload.get("tranche", Path(path).stem)
        superseded = set(payload.get("superseded_layers") or ())
        if superseded:
            superseded_seen[tranche] = sorted(superseded)
        for layer in frozen.live_layers():
            if layer in superseded:
                continue
            for record in payload.get("layers", {}).get(layer, []):
                if record.get("record") is None or record.get(
                        "validation_errors"):
                    continue
                records[layer][record["article_id"]] = record
                provenance[(layer, tranche,
                            (record.get("prompt_sha256") or "none")[:12])] += 1
    return records, {
        "per_layer_tranche_prompt": {
            f"{k[0]}|{k[1]}|{k[2]}": v for k, v in provenance.items()},
        "superseded_layers_honoured": superseded_seen,
    }


frozen.load_records = load_records_without_probe


def main() -> None:
    frozen.main()


if __name__ == "__main__":
    main()
