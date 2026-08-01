"""Resubmit the by-election issues layer after the credit outage.

    python3 -m src.llm_extraction.run_byelection_issues_resubmit

The byelection1 issues batch hit the account's zero credit balance:
623 of 627 requests were rejected by billing (never billed, never run)
and the automatic same-pass retry hit the same wall. The Haiku layers
finished and are on disk; only the Sonnet issues layer is missing.

The repair is deliberately shaped so the frozen collector keeps doing
all the judging. One new issues batch is submitted for the full 627
articles — re-paying for the 4 that succeeded costs cents and keeps the
layer a single complete batch — and the tranche manifest's issues batch
id is swapped to the new batch, with the outage batch id preserved in an
audit field. Re-running the frozen ``cmd_collect`` on the tranche then
rebuilds the outputs file with all three layers, identical validators,
identical row shapes, no bespoke merge code.

The submit refuses to run if the issues prompt no longer matches the
sha256 recorded at the original submission: a resubmission under a
drifted prompt would not be the same layer.
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

# Importing the wrapper applies the by-election path/POLLING patches to the
# frozen module; everything below must go through that patched instance.
from src.llm_extraction import run_byelection_extraction as wrapper

frozen = wrapper.frozen
MANIFEST = Path("llm_context/corpus_extraction_batches_byelection1.json")


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    import anthropic
    from anthropic.types.message_create_params import (
        MessageCreateParamsNonStreaming,
    )
    from anthropic.types.messages.batch_create_params import Request

    meta = json.loads(MANIFEST.read_text())

    submitted_sha = meta["layer_prompt_sha256"]["issues"]
    current_sha = frozen._layer_prompt_fingerprints()["issues"]
    if submitted_sha != current_sha:
        raise RuntimeError(
            "issues prompt has drifted since the original submission "
            f"({submitted_sha[:12]} -> {current_sha[:12]}); a resubmission "
            "would not be the same layer")

    arts, _fallback, _census = frozen.load_tranche(
        "byelection1", only_ids=set(meta["article_ids"]))
    if len(arts) != meta["articles"]:
        raise RuntimeError(
            f"tranche re-derivation returned {len(arts)} articles against "
            f"{meta['articles']} submitted; refusing to resubmit")

    build, _validate, max_tokens = frozen.ORIGINAL_LAYERS["issues"]
    arm, model = frozen._arm_for("issues")
    system = [{"type": "text", "text": build(),
               "cache_control": {"type": "ephemeral"}}]
    requests = [Request(
        custom_id=aid,
        params=MessageCreateParamsNonStreaming(
            model=model, max_tokens=max_tokens, thinking=arm["thinking"],
            system=system,
            messages=[{"role": "user",
                       "content": frozen._user_message(article)}]))
        for aid, article in sorted(arts.items())]

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)

    meta.setdefault("issues_resubmits", []).append({
        "replaced_batch_id": meta["layers"]["issues"],
        "reason": "credit balance exhausted mid-batch; 623/627 rejected "
                  "by billing, unbilled",
        "resubmitted_batch_id": batch.id,
    })
    meta["layers"]["issues"] = batch.id
    MANIFEST.write_text(json.dumps(meta, indent=2))

    print(f"issues resubmitted: {batch.id} ({len(requests)} articles, {model})")
    print(f"manifest updated -> {MANIFEST}")
    print("Run the frozen collect once the batch ends:")
    print("  python3 -m src.llm_extraction.run_byelection_extraction "
          "collect byelection1")


if __name__ == "__main__":
    main()
