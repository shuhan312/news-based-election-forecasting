"""Estimate what it costs to run the extraction layers on the pending corpus.

    PYTHONPATH=src .venv/bin/python -m news_collection.estimate_extraction_budget

Written as a script rather than quoted as a figure because every input to the
estimate is measurable and the measurement will change: the pending count
moves as collection continues, and the article lengths move with it. A number
in a message goes stale; this does not.

Why the estimate matters
------------------------
The whole downstream feature layer currently rests on a 67-article pilot -
``article_entity_alignment.json`` names its own dataset
``context-cards-v1.0-pilot67``. The articles exist and have passed
eligibility; they have simply never been through extraction, which is why the
feature table carries "no coverage" almost everywhere and "what the coverage
said" almost nowhere.

Extraction is the step that changes that, and it is the step that costs money,
so the figure is produced before anything is spent rather than after.

Assumptions, all stated so they can be argued with
--------------------------------------------------
Token counts are estimated from stored article bytes at four characters per
token, which is the usual ratio for English prose and errs slightly high for
news copy. Prompt and output sizes are taken from the layer prompts in
``src/llm_extraction``. Prices are the published Sonnet rates; the Batch
discount and the cached-prompt discount are applied as separate, clearly
labelled multipliers so a change in either can be traced.

Nothing here submits anything.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ELIGIBILITY = REPO / "news_collection/eligibility_assessment_v2.csv"
TEXT_DIRECTORY = REPO / "data/raw/news/text"

# The extraction layers, each of which is a separate call with its own prompt.
EXTRACTION_LAYERS = (
    "stance_classification", "issue_classification", "framing_detection",
    "credit_blame", "electoral_consequence", "local_national_relevance",
    "temporal_horizon", "confidence_evidence",
)

# Characters per token. Four is the standard ratio for English prose; news
# copy runs slightly denser, so this errs towards over-estimating.
CHARS_PER_TOKEN = 4

# Per-layer prompt overhead: the instruction block, the controlled vocabulary
# and the response schema. Measured from the prompt builders rather than
# guessed, but rounded up.
PROMPT_TOKENS_PER_LAYER = 1_200

# Structured output per layer: the classification plus its evidence spans.
OUTPUT_TOKENS_PER_LAYER = 600

# Published Sonnet rates, dollars per million tokens.
INPUT_RATE = 3.00
OUTPUT_RATE = 15.00

# The Batch API halves both rates for work that can wait.
BATCH_MULTIPLIER = 0.5

# A cached prompt prefix is billed at a tenth on reads. Only the prompt and
# schema cache - the article text differs every call - so the discount applies
# to PROMPT_TOKENS_PER_LAYER and not to the article itself.
CACHE_READ_MULTIPLIER = 0.1


def pending_articles() -> list[dict]:
    """Articles that passed eligibility and have never been extracted."""

    with ELIGIBILITY.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if row.get("status") == "pending_human_review"]


def article_token_estimate(article_ids: set[str], sample: int = 1500) -> dict:
    """Mean and median input tokens per article, from stored text files.

    Sampled rather than measured exhaustively: the directory holds tens of
    thousands of files and the mean stabilises long before that. The sample
    size is reported so the estimate carries its own precision.
    """

    sizes: list[int] = []
    for path in TEXT_DIRECTORY.iterdir():
        if len(sizes) >= sample:
            break
        if path.is_file():
            sizes.append(path.stat().st_size)

    if not sizes:
        return {"sampled_files": 0, "mean_tokens": 0, "median_tokens": 0}

    sizes.sort()
    return {
        "sampled_files": len(sizes),
        "mean_tokens": round(sum(sizes) / len(sizes) / CHARS_PER_TOKEN),
        "median_tokens": round(sizes[len(sizes) // 2] / CHARS_PER_TOKEN),
    }


def estimate(article_count: int, tokens_per_article: int, *,
             layers: int = len(EXTRACTION_LAYERS),
             batch: bool = True, cache: bool = True) -> dict:
    """Cost for one configuration, with every component kept separate."""

    requests = article_count * layers
    prompt_tokens = PROMPT_TOKENS_PER_LAYER * (
        CACHE_READ_MULTIPLIER if cache else 1.0)
    input_tokens = requests * (tokens_per_article + prompt_tokens)
    output_tokens = requests * OUTPUT_TOKENS_PER_LAYER

    multiplier = BATCH_MULTIPLIER if batch else 1.0
    input_cost = input_tokens / 1_000_000 * INPUT_RATE * multiplier
    output_cost = output_tokens / 1_000_000 * OUTPUT_RATE * multiplier

    return {
        "articles": article_count,
        "layers": layers,
        "requests": requests,
        "input_tokens": round(input_tokens),
        "output_tokens": round(output_tokens),
        "input_cost_usd": round(input_cost, 2),
        "output_cost_usd": round(output_cost, 2),
        "total_usd": round(input_cost + output_cost, 2),
        "batch_discount_applied": batch,
        "prompt_caching_applied": cache,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate the extraction cost for the pending corpus.")
    parser.add_argument("--json", action="store_true",
                        help="print the estimate as JSON")
    arguments = parser.parse_args()

    pending = pending_articles()
    by_arm = Counter(row.get("arm", "unknown") for row in pending)
    by_election = Counter(row.get("election_id", "unknown") for row in pending)
    tokens = article_token_estimate({row["article_id"] for row in pending})

    full = estimate(len(pending), tokens["mean_tokens"])
    local_only = estimate(by_arm.get("local", 0), tokens["mean_tokens"])
    no_discounts = estimate(len(pending), tokens["mean_tokens"],
                            batch=False, cache=False)

    report = {
        "pending_articles": len(pending),
        "by_arm": dict(by_arm),
        "by_election": dict(by_election),
        "token_estimate": tokens,
        "assumptions": {
            "chars_per_token": CHARS_PER_TOKEN,
            "prompt_tokens_per_layer": PROMPT_TOKENS_PER_LAYER,
            "output_tokens_per_layer": OUTPUT_TOKENS_PER_LAYER,
            "input_rate_per_million_usd": INPUT_RATE,
            "output_rate_per_million_usd": OUTPUT_RATE,
            "batch_multiplier": BATCH_MULTIPLIER,
            "cache_read_multiplier": CACHE_READ_MULTIPLIER,
            "layers": list(EXTRACTION_LAYERS),
        },
        "options": {
            "everything_pending_batched_and_cached": full,
            "local_arm_only_batched_and_cached": local_only,
            "everything_pending_no_discounts": no_discounts,
        },
    }

    if arguments.json:
        print(json.dumps(report, indent=2))
        return

    print(f"Pending articles: {len(pending)}")
    print(f"  by arm      : {dict(by_arm)}")
    print(f"  by election : {dict(by_election)}")
    print(f"\nArticle length: mean {tokens['mean_tokens']:,} tokens, "
          f"median {tokens['median_tokens']:,} "
          f"(sampled {tokens['sampled_files']} stored text files)")
    print(f"Layers per article: {len(EXTRACTION_LAYERS)}")

    print("\n{:<44s} {:>9s} {:>12s} {:>12s} {:>10s}".format(
        "option", "requests", "input tok", "output tok", "USD"))
    for label, option in report["options"].items():
        print("{:<44s} {:>9,} {:>12,} {:>12,} {:>10.2f}".format(
            label.replace("_", " "), option["requests"],
            option["input_tokens"], option["output_tokens"],
            option["total_usd"]))

    print("\nNothing has been submitted. These are estimates only.")


if __name__ == "__main__":
    main()
