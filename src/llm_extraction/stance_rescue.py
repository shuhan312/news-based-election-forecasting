"""Phase 6 / D4 addendum - a rescue attempt for the failed stance layer.

## Why the original layer failed

`stance_classification.py` failed both rulers: kappa 0.482-0.490 against
the human coding and 0.316 between the two model arms. Diagnosing the
inter-model disagreement on the 60 D4 articles located two causes, and
they are design faults rather than model failures. Of 61 party-level
comparisons only 30 agreed:

* **16 (26%) were inclusion disputes** - one arm created a row for a
  party and the other did not. The layer leaves the choice of which
  entities to evaluate entirely to the model ("one row per political
  entity that the article represents in any evaluative way"), gated
  behind two subjective conditions: the representation must be
  evaluative, and it must carry a verbatim evidence span. Sonnet
  produced 168 rows to Haiku's 140 - 20% more inclusive on identical
  input. The two arms were answering different question sets.

* **15 (25%) were direction disputes, and 11 of those involved
  `mixed`** - `mixed vs negative`, `mixed vs positive`,
  `negative vs mixed`. That is not a disagreement about whether coverage
  is hostile; it is a disagreement about the threshold at which both
  valences present in one article stop being "predominantly negative"
  and become "mixed". `mixed` acts as a catch-all whose boundary each
  model draws differently.

Only 4 of 61 comparisons were substantive direction conflicts
(negative vs neutral, positive vs neutral). Remove the two design faults
and agreement would sit near 93%.

## What this layer changes, and what it deliberately does not

Two changes, each aimed at one diagnosed fault:

1. **The party list is fixed by code, not chosen by the model.** Party
   presence is decided by deterministic alias matching against the
   article text (`parties_present`), and the model is then asked about
   exactly those parties. Both arms therefore answer identical question
   sets, and the inclusion boundary becomes reproducible by construction
   rather than a judgement that can drift.

2. **`mixed` is removed; the model must commit.** Three values only -
   `unfavourable`, `favourable`, `neither` - with an explicit
   instruction to name the predominant direction when an article carries
   both. This is the coarsening the `test_coarsened_agreement.py` run
   could not achieve after the fact, because collapsing a recorded
   `mixed` cannot recover which direction predominated.

The verbatim evidence-span requirement is dropped for this layer only.
In the original it suppressed recall: a model that could see hostile
framing but could not isolate one clean quotable span was pushed by rule
3 into omitting the row entirely. A short free-text reason is requested
instead, which keeps the output auditable without making a quote a
precondition for reporting a judgement.

## What is unchanged, so the comparison stays fair

Same 60 D4 articles, same two model arms, same batch pricing, same gate
(kappa >= 0.60 with the pre-registered AC1 fallback), and the same human
gold labels as a secondary reference. Inter-model reliability is the
primary criterion here for the reason given in section 3b of
`d4_gate_outcome_and_decisions.md`: the human labels were single-pass and
were collected under an instruction that contradicted this very layer,
so they cannot arbitrate it on their own.

## Honest status

This is a post-hoc redesign of a layer that failed, so a pass here is
reported as "stance recovered at reduced granularity under a revised
layer", never as if the original had passed. The redesign was driven by
a diagnosis of *why* the disagreement occurred, not by searching for a
formulation that scores well - the two changes above were fixed before
any rescue output existed.

Usage:
    python3 -m src.llm_extraction.stance_rescue submit [arm]
    python3 -m src.llm_extraction.stance_rescue collect [arm]
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.run_d4_validation import ARMS, load_d4_articles
from src.llm_extraction.run_pilot import MODEL

RESCUE_VERSION = "stance-rescue-v1.0-2026-07-30"

# Must exceed the largest arm's thinking budget: the API requires
# budget_tokens < max_tokens, and the Haiku arm reserves 4,000 for
# thinking. The first submission set this to 2,000 and every Haiku request
# errored out for that reason while Sonnet - which uses adaptive thinking
# and so has no fixed budget to exceed - succeeded on all 34. Recorded
# rather than quietly corrected, because the asymmetry is a real trap for
# anyone adding a fixed-budget arm later.
MAX_TOKENS = 6000

# Party aliases for deterministic presence detection. Deliberately
# conservative: a party counts as present only on an unambiguous surface
# form, so the question set is reproducible from the text alone. Reform's
# aliases exclude the bare word "reform" - that is the ordinary English
# word the E6 eligibility rule exists to disambiguate, and admitting it
# here would reintroduce exactly the confusion E6 removes.
PARTY_ALIASES = {
    "conservative": [r"\bconservatives?\b", r"\btor(?:y|ies)\b",
                     r"\bconservative party\b"],
    "labour": [r"\blabour\b"],
    "liberal_democrat": [r"\bliberal democrats?\b", r"\blib dems?\b",
                         r"\bliberal democrat party\b"],
    "green": [r"\bgreen party\b", r"\bthe greens\b", r"\bgreens\b"],
    "reform_uk": [r"\breform uk\b", r"\breform party\b"],
    "ukip": [r"\bukip\b", r"\buk independence party\b"],
}

PARTY_LABELS = {
    "conservative": "the Conservative Party",
    "labour": "the Labour Party",
    "liberal_democrat": "the Liberal Democrats",
    "green": "the Green Party",
    "reform_uk": "Reform UK",
    "ukip": "UKIP",
}

DECISIONS = ("unfavourable", "favourable", "neither")


def parties_present(title: str, body: str) -> list[str]:
    """Which study parties the article unambiguously names.

    Deterministic and identical for every model arm - this is the change
    that removes the inclusion judgement from the model's hands. Returns
    a stable order so the rendered prompt is byte-stable and caches.
    """
    text = f"{title}\n{body}".lower()
    return [p for p in PARTY_ALIASES
            if any(re.search(pat, text) for pat in PARTY_ALIASES[p])]


def build_prompt(parties: list[str]) -> str:
    """The system prompt, rendered per question set.

    Not byte-stable across articles, because the party list differs - so
    cache hits only occur between articles that name the same parties.
    That is the price of fixing the question set, and it is worth paying:
    a shared prompt that left the party list to the model is what made
    the original layer irreproducible.
    """
    named = "\n".join(f"- {PARTY_LABELS[p]}" for p in parties)
    return f"""You judge how a news article portrays named political parties, for an \
academic study of pre-election coverage in Surrey, England.

You will be asked about EXACTLY these parties, all of which the article names:

{named}

For each one, answer the single question: does this article portray that party \
favourably, unfavourably, or neither?

Rules:
1. JUDGE THE PORTRAYAL, NOT THE PARTY. You are reading how the article \
represents the party - not whether you agree with it, and not the party's own \
opinions quoted in the article.
2. UNFAVOURABLE INCLUDES UNFAVOURABLE FACTS. An article reporting that a party \
lost heavily, is falling in the polls, faces a scandal, or is blamed for a \
failure portrays that party unfavourably - even when the reporting is entirely \
neutral in tone. You are not judging whether the journalist editorialised; you \
are judging whether a reader finishes the article thinking better or worse of \
that party.
3. COMMIT TO A DIRECTION. There is no "mixed" option. When an article carries \
both favourable and unfavourable material about the same party, name the \
direction that predominates. Use "neither" only when the article genuinely \
does not move the reader either way - a bare mention in a candidate list, a \
procedural notice, a passing reference with no evaluative weight.
4. ONE ANSWER PER PARTY LISTED. Do not add parties, do not omit any.
5. GIVE A SHORT REASON. One sentence per party saying what in the article \
drives the answer. No verbatim quotation is required.
6. Output ONLY a JSON object of this exact shape, no markdown fences:

{{"judgements": [{{"party": "<one of the keys below>", \
"portrayal": "unfavourable|favourable|neither", "reason": "<one sentence>"}}]}}

The permitted party keys are: {", ".join(parties)}.
Prompt version: {RESCUE_VERSION}."""


def build_user_message(title: str, body: str, date: str, source: str) -> str:
    return (f"SOURCE: {source}\nPUBLISHED: {date}\n\nTITLE: {title}\n\n"
            f"BODY:\n{body}")


def _paths(arm: str) -> tuple[Path, Path]:
    suffix = "" if arm == "sonnet" else f"_{arm}"
    return (Path(f"llm_context/stance_rescue_batch{suffix}.json"),
            Path(f"llm_context/stance_rescue_outputs{suffix}.json"))


def cmd_submit(arm_name: str = "haiku") -> None:
    arm = ARMS[arm_name]
    model = arm["model"] or MODEL
    arts, _fallback = load_d4_articles()
    client = anthropic.Anthropic()

    requests, question_sets, skipped = [], {}, []
    for aid, a in sorted(arts.items()):
        parties = parties_present(a["title"], a["body"])
        if not parties:
            # No study party named, so there is nothing to judge. Recorded
            # rather than silently dropped: an article with no party is a
            # legitimate zero, not a missing measurement.
            skipped.append(aid)
            continue
        question_sets[aid] = parties
        requests.append(Request(
            custom_id=aid,
            params=MessageCreateParamsNonStreaming(
                model=model, max_tokens=MAX_TOKENS,
                thinking=arm["thinking"],
                system=[{"type": "text", "text": build_prompt(parties),
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": build_user_message(
                    a["title"], a["body"], a.get("publication_datetime", ""),
                    a.get("source", ""))}])))

    batch = client.messages.batches.create(requests=requests)
    batch_path, _ = _paths(arm_name)
    batch_path.write_text(json.dumps({
        "version": RESCUE_VERSION, "arm": arm_name, "model": model,
        "thinking": arm["thinking"], "batch_id": batch.id,
        "articles": len(requests),
        "articles_without_any_study_party": skipped,
        "question_sets": question_sets}, indent=2))
    print(f"{arm_name}: batch {batch.id} ({len(requests)} articles, "
          f"{len(skipped)} with no study party named)")
    print(f"-> {batch_path}")


def cmd_collect(arm_name: str = "haiku") -> None:
    batch_path, out_path = _paths(arm_name)
    meta = json.loads(batch_path.read_text())
    client = anthropic.Anthropic()

    while True:
        b = client.messages.batches.retrieve(meta["batch_id"])
        print(f"{arm_name}: {b.processing_status} {b.request_counts}")
        if b.processing_status == "ended":
            break
        time.sleep(120)

    rows, usage_in, usage_out = [], 0, 0
    for result in client.messages.batches.results(meta["batch_id"]):
        aid = result.custom_id
        entry: dict = {"article_id": aid,
                       "batch_result": result.result.type,
                       "asked_about": meta["question_sets"].get(aid, [])}
        if result.result.type == "succeeded":
            msg = result.result.message
            usage_in += msg.usage.input_tokens
            usage_out += msg.usage.output_tokens
            text = "".join(b.text for b in msg.content if b.type == "text")
            try:
                parsed = json.loads(text.strip().removeprefix("```json")
                                    .removeprefix("```").removesuffix("```"))
                judged = {j["party"]: j.get("portrayal")
                          for j in parsed.get("judgements", [])}
                # Validate against the asked set and the closed vocabulary.
                # A model that answers about a party it was not asked
                # about, or invents a value, is a failure to record - not
                # something to coerce into looking valid.
                errors = []
                asked = set(entry["asked_about"])
                if set(judged) != asked:
                    errors.append(f"answered about {sorted(judged)}, "
                                  f"asked about {sorted(asked)}")
                bad = {p: v for p, v in judged.items() if v not in DECISIONS}
                if bad:
                    errors.append(f"values outside the vocabulary: {bad}")
                entry["judgements"] = judged
                entry["reasons"] = {j["party"]: j.get("reason")
                                    for j in parsed.get("judgements", [])}
                entry["validation_errors"] = errors
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                entry["judgements"] = None
                entry["validation_errors"] = [f"unparseable: {e}"]
        else:
            entry["judgements"] = None
            entry["validation_errors"] = [f"batch: {result.result.type}"]
        rows.append(entry)

    ok = sum(1 for r in rows if r["judgements"] and not r["validation_errors"])
    out_path.write_text(json.dumps({
        "version": RESCUE_VERSION, "arm": arm_name, "model": meta["model"],
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
        "articles_ok": ok, "articles_total": len(rows),
        "results": rows}, indent=2))
    print(f"{ok}/{len(rows)} clean -> {out_path}")


if __name__ == "__main__":
    _cmd = sys.argv[1]
    _arm = sys.argv[2] if len(sys.argv) > 2 else "haiku"
    {"submit": cmd_submit, "collect": cmd_collect}[_cmd](_arm)
