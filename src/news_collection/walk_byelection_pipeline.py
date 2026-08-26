"""Walk the by-election corpus through the six production stages on paper.

    PYTHONPATH=src .venv/bin/python -m news_collection.walk_byelection_pipeline

The evidence register scopes 3,122 collected by-election articles out of the
news layer and records a ~213-Reform-observation estimate against them, with
the caveat that no cost figure means anything until the six unrun stages are
walked through. This module is that walk-through. It submits nothing, spends
nothing, and reads only files already on disk; its job is to turn "should we
enrich before unblinding 2026?" from a feeling into a stage-by-stage table of
articles, dollars, hours and risks.

Every projection rate is measured from the principal-election pipeline's own
artifacts rather than assumed, and each carries its provenance in the output.
Two facts discovered by measurement shape the whole estimate:

- **The arms funnel completely differently.** 88.0% of national records
  reached the eligibility review pool against 10.4% of local records, and
  65.4% of decided national candidates were included against 35.9% of local.
  A single blended "61%" would misprice the by-election corpus, which is
  local-heavy (2,129 of 3,122) — the reverse of the principal corpus.
- **Two of the ten by-elections are inside the 2026 holdout period.** Their
  articles (381) cannot become training data and are excluded from every
  figure here, not discounted.

The E5-local rule is priced as manual review. Its automated classifier
failed validation (kappa 0.476 against the 0.600 gate) and the declared
method does not permit auto-admission, so every local candidate that reaches
the review pool is costed at human speed under a stated rows-per-hour
assumption. There is no LLM shortcut in this estimate; finding one would be
a separate validation exercise with its own cost.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RECORDS_DIR = REPO / "data/raw/news/records"
TEXT_DIR = REPO / "data/raw/news/text"
DATES_CSV = REPO / "news_collection/effective_dates_v2.csv"
ELIGIBILITY_CSV = REPO / "news_collection/eligibility_assessment_v2.csv"
DECISIONS_CSV = REPO / "news_collection/corpus_eligibility_decisions.csv"
OUTPUT_DIR = REPO / "news_collection/byelection_walkthrough_v1"

# Articles for elections held on or after 2026-05-07 sit inside the sealed
# holdout period. They are excluded outright: enrichment exists to add
# TRAINING data, and nothing from the holdout period may become training.
HOLDOUT_DATE = date(2026, 5, 7)

# Principal raw local records, measured from the records store. The raw
# count feeds the review-pool-entry rate; it is larger than the 11,787
# assessed rows because dedup retires records before assessment.
PRINCIPAL_RAW = {"local": 13_411, "national": 2_488}

# The models the frozen pipeline actually used, and current prices in
# dollars per million tokens (claude-api reference, checked 2026-08-01).
# Sonnet 5 carries an introductory price until 2026-08-31; both are shown
# because the run may straddle that date.
PRICES = {
    "claude-sonnet-5": {"input": 3.00, "output": 15.00,
                        "intro_input": 2.00, "intro_output": 10.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00,
                         "intro_input": 1.00, "intro_output": 5.00},
}
ELIGIBILITY_MODEL = "claude-sonnet-5"
EXTRACTION_LAYERS = {
    "issues": "claude-sonnet-5",
    "stance": "claude-haiku-4-5",
    "framing": "claude-haiku-4-5",
}

# Frozen accounting conventions used for this recorded walkthrough: Batch API
# halves both rates, the shared prompt prefix is cached and billed at a
# tenth on reads, prompt overhead and structured output are rounded up.
BATCH_MULTIPLIER = 0.5
CACHE_READ_MULTIPLIER = 0.1
PROMPT_TOKENS_PER_REQUEST = 1_200
OUTPUT_TOKENS_PER_REQUEST = 600
CHARS_PER_TOKEN = 4

# Share of eligible articles that yielded a valid stance record in the
# principal run: 1,187 of 1,452 (evidence register section 4).
VALID_STANCE_RATE = 1_187 / 1_452

# Manual E5-local review speed. No throughput was recorded for the 138-row
# validation session, so this is an assumption, deliberately conservative,
# and overridable from the command line.
DEFAULT_REVIEW_ROWS_PER_HOUR = 40

# The strict deterministic Reform pattern; UKIP kept separate throughout.
REFORM_PATTERN = re.compile(r"\breform\s+uk\b", re.IGNORECASE)


def _election_date(election_id: str) -> date | None:
    """By-election ids end in YYYY-MM-DD; principal ids do not."""

    match = re.search(r"(\d{4})-(\d{2})-(\d{2})$", election_id)
    if not match:
        return None
    return date(*map(int, match.groups()))


def measure_byelection_corpus() -> dict:
    """Count the by-election records on disk and scan their stored text.

    Nothing here estimates: every number is a count over files that already
    exist. Token sizes come from stored text bytes at four characters per
    token, the same convention the extraction budget used.
    """

    per_election: dict[str, Counter] = {}
    token_sizes: list[int] = []
    for path in RECORDS_DIR.glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        election = str(record.get("discovered_for_election", ""))
        if "by-election" not in election:
            continue
        polling_day = _election_date(election)
        counts = per_election.setdefault(election, Counter())
        counts["articles"] += 1
        counts[record.get("arm", "unknown")] += 1
        if polling_day is not None and polling_day >= HOLDOUT_DATE:
            counts["holdout_period"] += 1

        content = record.get("content", {})
        if not content.get("has_full_text"):
            continue
        text_path = REPO / str(content.get("text_path", ""))
        if not text_path.is_file():
            continue
        counts["with_text"] += 1
        text = text_path.read_text(encoding="utf-8", errors="replace")
        if polling_day is not None and polling_day < HOLDOUT_DATE:
            token_sizes.append(len(text) // CHARS_PER_TOKEN)
            if REFORM_PATTERN.search(text):
                counts["reform_mentions_pre_holdout"] += 1

    usable = {
        election: counts for election, counts in per_election.items()
        if not counts.get("holdout_period")
    }
    excluded = {
        election: counts for election, counts in per_election.items()
        if counts.get("holdout_period")
    }
    token_sizes.sort()
    return {
        "byelections_found": len(per_election),
        "articles_total": sum(c["articles"] for c in per_election.values()),
        "usable": {
            "byelections": len(usable),
            "articles": sum(c["articles"] for c in usable.values()),
            "local": sum(c["local"] for c in usable.values()),
            "national": sum(c["national"] for c in usable.values()),
            "with_text": sum(c["with_text"] for c in usable.values()),
            "reform_mention_articles": sum(
                c["reform_mentions_pre_holdout"] for c in usable.values()
            ),
        },
        "excluded_holdout_period": {
            "byelections": sorted(excluded),
            "articles": sum(c["articles"] for c in excluded.values()),
            "reason": (
                "polling day on or after 2026-05-07; holdout-period news "
                "cannot become training data"
            ),
        },
        "article_tokens": {
            "measured_articles": len(token_sizes),
            "mean": round(sum(token_sizes) / len(token_sizes)) if token_sizes else 0,
            "median": token_sizes[len(token_sizes) // 2] if token_sizes else 0,
        },
        "per_election": {k: dict(v) for k, v in sorted(per_election.items())},
    }


def measure_principal_rates() -> dict:
    """Measure every projection rate from the principal pipeline's files.

    Rates are computed per arm because the two arms behave nothing alike,
    and each rate records the counts it came from so the projection can be
    audited without rerunning this script.
    """

    with DATES_CSV.open(encoding="utf-8", newline="") as handle:
        dates = list(csv.DictReader(handle))
    date_status = Counter(row["date_status"] for row in dates)

    with ELIGIBILITY_CSV.open(encoding="utf-8", newline="") as handle:
        assessed = list(csv.DictReader(handle))
    pool = Counter(
        row["arm"] for row in assessed if row["status"] == "pending_human_review"
    )

    with DECISIONS_CSV.open(encoding="utf-8", newline="") as handle:
        decisions = list(csv.DictReader(handle))
    decided = Counter(row["arm"] for row in decisions)
    included = Counter(
        row["arm"] for row in decisions if row["overall_decision"] == "include"
    )

    return {
        "review_pool_entry_rate": {
            arm: {
                "rate": pool[arm] / PRINCIPAL_RAW[arm],
                "from": f"{pool[arm]} pending_human_review of "
                        f"{PRINCIPAL_RAW[arm]} raw {arm} records",
            }
            for arm in ("local", "national")
        },
        "include_rate_among_decided": {
            arm: {
                "rate": included[arm] / decided[arm],
                "from": f"{included[arm]} include of {decided[arm]} decided",
            }
            for arm in ("local", "national")
        },
        "valid_stance_rate": {
            "rate": VALID_STANCE_RATE,
            "from": "1,187 valid stance records of 1,452 includes (register s4)",
        },
        "date_investigation_rate": {
            "rate": date_status["pending_human_review"] / len(dates),
            "from": f"{date_status['pending_human_review']} of {len(dates)} "
                    "principal rows needed manual date investigation",
        },
        "local_decision_backlog_note": (
            "Only 334 of 1,394 principal local pool rows were ever decided; "
            "the rest deferred behind the failed E5 classifier. The local "
            "include rate is therefore measured on a 334-row subset and is "
            "the weakest rate in this table."
        ),
    }


def _llm_cost(requests: int, article_tokens: int, model: str) -> dict:
    """Batch-discounted, cache-aware cost for one block of requests."""

    input_tokens = requests * (
        article_tokens + PROMPT_TOKENS_PER_REQUEST * CACHE_READ_MULTIPLIER
    )
    output_tokens = requests * OUTPUT_TOKENS_PER_REQUEST
    price = PRICES[model]

    def usd(input_rate: float, output_rate: float) -> float:
        return round(
            (input_tokens / 1e6 * input_rate + output_tokens / 1e6 * output_rate)
            * BATCH_MULTIPLIER, 2,
        )

    return {
        "model": model,
        "requests": requests,
        "input_tokens": round(input_tokens),
        "output_tokens": output_tokens,
        "usd_standard": usd(price["input"], price["output"]),
        "usd_intro_until_2026_08_31": usd(
            price["intro_input"], price["intro_output"]
        ),
    }


def project_stages(corpus: dict, rates: dict,
                   review_rows_per_hour: int) -> dict:
    """Project the six stages for both arms and for a national-only option.

    The national-only option exists because it dodges the E5-local manual
    bottleneck entirely; what it gives up (the attributable local arm) is
    stated rather than hidden.
    """

    usable = corpus["usable"]
    tokens = corpus["article_tokens"]["mean"]

    def scenario(local_raw: int, national_raw: int) -> dict:
        pool_local = round(
            local_raw * rates["review_pool_entry_rate"]["local"]["rate"]
        )
        pool_national = round(
            national_raw * rates["review_pool_entry_rate"]["national"]["rate"]
        )
        includes = round(
            pool_local * rates["include_rate_among_decided"]["local"]["rate"]
            + pool_national
            * rates["include_rate_among_decided"]["national"]["rate"]
        )
        eligibility = _llm_cost(
            pool_local + pool_national, tokens, ELIGIBILITY_MODEL
        )
        extraction = {
            layer: _llm_cost(includes, tokens, model)
            for layer, model in EXTRACTION_LAYERS.items()
        }
        manual_hours = round(pool_local / review_rows_per_hour, 1)
        total_standard = eligibility["usd_standard"] + sum(
            block["usd_standard"] for block in extraction.values()
        )
        total_intro = eligibility["usd_intro_until_2026_08_31"] + sum(
            block["usd_intro_until_2026_08_31"] for block in extraction.values()
        )
        return {
            "input_articles": {"local": local_raw, "national": national_raw},
            "stage_1_to_3_deterministic": {
                "articles": local_raw + national_raw,
                "usd": 0.0,
                "wall_clock": "runtime only; date-investigation queue "
                              f"projected at ~{round((local_raw + national_raw) * rates['date_investigation_rate']['rate'])} rows",
            },
            "stage_4_llm_eligibility": {
                **eligibility,
                "e5_local_manual_review_rows": pool_local,
                "e5_local_manual_review_hours": manual_hours,
            },
            "stage_5_decisions": {"usd": 0.0, "wall_clock": "runtime only"},
            "stage_6_extraction": extraction,
            "projected_review_pool": {
                "local": pool_local, "national": pool_national,
            },
            "projected_includes": includes,
            "usd_total_standard": round(total_standard, 2),
            "usd_total_intro_until_2026_08_31": round(total_intro, 2),
            "manual_review_hours": manual_hours,
            "wall_clock_working_days": (
                "3-5: deterministic stages under a day, two batch rounds "
                "usually within a day each, manual E5-local review "
                f"~{manual_hours}h at {review_rows_per_hour} rows/hour, "
                "then feature rebuild and the v2 freeze"
            ),
        }

    both_arms = scenario(usable["local"], usable["national"])
    national_only = scenario(0, usable["national"])
    national_only["gives_up"] = (
        "the local arm entirely: by-election local coverage is the corpus's "
        "only area-attributable-by-construction text, and local remains "
        "below the reporting threshold precisely for want of volume"
    )

    reform_yield = round(
        corpus["usable"]["reform_mention_articles"]
        * rates["include_rate_among_decided"]["national"]["rate"]
        * rates["valid_stance_rate"]["rate"]
    )
    return {
        "scenario_a_both_arms": both_arms,
        "scenario_b_national_only": national_only,
        "expected_reform_training_records": {
            "estimate": reform_yield,
            "method": (
                "measured pre-holdout Reform-mention articles x national "
                "include rate x valid-stance rate; an Estimate under the "
                "register's rules, not an observed count"
            ),
        },
        "training_grain_change": (
            "8 pre-holdout by-elections would take the per-election grain "
            "from 2 training cells toward 10; the two holdout-period "
            "by-elections add nothing"
        ),
        "risks": [
            "E5-local has no validated automated route: the manual hours "
            "are load-bearing, and a fresh validation attempt would be a "
            "separate cost with an uncertain outcome",
            "review-pool and include rates are transferred from principal "
            "elections; by-election coverage may funnel differently, and "
            "the local include rate rests on a 334-row decided subset",
            "search completeness varies by by-election (under 12% to 100%), "
            "so only share-based features are safe - already the frozen "
            "feature sets' design",
            "cross-corpus duplicates with principal articles are not "
            "measured here and would shrink the pool at dedup",
            "the six stage implementations are principal-election-shaped; "
            "adapting them to by-election ids is development time not "
            "priced in dollars",
        ],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Cost the by-election enrichment without sending anything."
    )
    parser.add_argument(
        "--review-rows-per-hour", type=int,
        default=DEFAULT_REVIEW_ROWS_PER_HOUR,
        help="assumed manual E5-local review speed",
    )
    arguments = parser.parse_args()

    corpus = measure_byelection_corpus()
    rates = measure_principal_rates()
    projection = project_stages(corpus, rates, arguments.review_rows_per_hour)

    report = {
        "status": "walkthrough_only_nothing_submitted",
        "review_rows_per_hour_assumption": arguments.review_rows_per_hour,
        "corpus_measured": corpus,
        "principal_rates_measured": rates,
        "projection": projection,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "walkthrough_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    a = projection["scenario_a_both_arms"]
    b = projection["scenario_b_national_only"]
    print(f"usable articles          : {corpus['usable']['articles']} "
          f"({corpus['usable']['local']} local / {corpus['usable']['national']} national), "
          f"{corpus['excluded_holdout_period']['articles']} holdout-period excluded")
    print(f"reform-mention articles  : {corpus['usable']['reform_mention_articles']} (pre-holdout, strict pattern)")
    print(f"A both arms              : ${a['usd_total_intro_until_2026_08_31']}-"
          f"{a['usd_total_standard']}, {a['manual_review_hours']}h manual, "
          f"~{a['projected_includes']} includes")
    print(f"B national only          : ${b['usd_total_intro_until_2026_08_31']}-"
          f"{b['usd_total_standard']}, 0h manual, "
          f"~{b['projected_includes']} includes")
    print(f"expected Reform records  : ~{projection['expected_reform_training_records']['estimate']}")
    print(f"written to               : {OUTPUT_DIR}")
    print("requests sent            : none")


if __name__ == "__main__":
    main()
