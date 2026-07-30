"""A second attempt at the electoral-consequence layer, on a diagnosis.

The frozen layer failed the D4 gate badly: against the human gold labels,
kappa 0.259 on the Sonnet arm (n=55) and 0.136 on Haiku, with raw agreement
of 52.7% - barely better than guessing on a five-value field. The pre-stated
coarsening re-test did not rescue it either (binary kappa 0.318).

Before rewriting anything, the disagreement was tabulated rather than
assumed, because kappa is symmetric and does not say which side is wrong.
The confusion matrix, human rows against Sonnet columns, n=55:

                     none  potential_benefit  potential_damage   total
    none               22          2                 16            40
    potential_damage    0          0                  7             7
    unclear             0          0                  3             3
    mixed_impact        0          1                  2             3
    potential_benefit   0          0                  2             2
    total              22          3                 30

Two things are visible and neither is noise. First, eighteen of the
twenty-six disagreements sit in one place: the human recorded no electoral
consequence and the model found one. Second, the marginals are far apart -
the human called 40 of 55 articles "none", the model 22, and the model chose
potential_damage on 30 of 55. This is a disagreement about whether a
consequence is present at all, not about which direction it runs.

The supporting evidence that the fault is definitional rather than random:
the two models agree with each other on this field far better than either
agrees with the human (0.587 against 0.259 and 0.136). Models drawing
arbitrary answers would not converge with each other. That pattern - models
consistent among themselves, both distant from the human - is exactly what
the stance layer showed before its rescue took it from kappa 0.32 to 0.85,
and the fix there was to take an unguided judgement away from the model.

The unguided judgement here is the threshold. The frozen prompt asked for
"the possible electoral reading AS THE ARTICLE SUGGESTS IT", which leaves
the model to decide how much suggestion is enough, and it set that bar much
lower than the human reviewer did. So this version states the bar as a
testable condition instead of a matter of degree:

* An electoral consequence requires a clause about an ELECTORAL QUANTITY -
  votes, seats, a majority, control of the council, winning or losing, a
  party's level of support, or turnout.
* A problem being described, a service failing, a politician being
  criticised, or a policy going wrong is NOT an electoral consequence, however
  strongly it might imply one. The article has to make the electoral step.

The other three changes follow the two rescues that worked:

* Three values, not five. `mixed` and `unclear` are removed. A model given
  somewhere to hide uses it, and the frozen layer's own output shows the
  reverse failure too - it never once chose `mixed` or `unclear` across 57
  attribution records while the human used them on 14% of articles.
* No verbatim span. The layer's evidence requirement is what made the
  validator reject a third of Haiku's records; a one-sentence free-text
  reason is what the stance and framing rescues used and both parse cleanly.
* One judgement per article, matching the granularity the human actually
  recorded, so no positional scoring rule applies to one side only. That
  fault - scoring the model's first row against a human instruction to
  record the principal one - was found in the attribution layer and is not
  repeated here.

THE SCORING RULE, STATED BEFORE THE BATCH IS SUBMITTED
------------------------------------------------------
Declared here so that it cannot be selected after seeing the numbers. The
frozen layer's verdict was reached by three successive scoring corrections,
each of which moved it, and that is not a mistake worth making a fourth time.

* PRIMARY TEST - presence. The human's `none` maps to absent; every other
  human value (`potential_damage`, `potential_benefit`, `mixed_impact`,
  `unclear`) maps to present, because each asserts that a consequence exists.
  The model's `none` maps to absent, `damage` and `benefit` to present.
  Gate: Cohen's kappa >= 0.60, or the pre-registered fallback (Gwet's AC1 >=
  0.60 with agreement >= 80%) only if a marginal reaches 0.90.
* SECONDARY TEST - direction, run only if presence passes, and reported
  either way. Restricted to articles both sides call present. Human
  `mixed_impact` and `unclear` are EXCLUDED from this test, because the
  revised vocabulary offers no value they could match and pairing them
  against a forced choice would score the instrument, not the model.
* No other coarsening, collapse or re-pairing will be applied to this layer.
  If both tests fail, the layer is dropped and that is the finding.

Usage:
    python3 -m src.llm_extraction.consequence_rescue submit haiku
    python3 -m src.llm_extraction.consequence_rescue collect haiku
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.run_d4_validation import ARMS, load_d4_articles
from src.llm_extraction.run_pilot import MODEL

RESCUE_VERSION = "consequence-rescue-v1.0-2026-07-30"

# Must exceed the Haiku arm's fixed 4,000-token thinking budget: the API
# requires budget_tokens < max_tokens. The stance rescue set this to 2,000
# and every Haiku request errored while every Sonnet request succeeded,
# because Sonnet's thinking is adaptive and has no fixed budget to exceed.
MAX_TOKENS = 6000

DECISIONS = ("none", "damage", "benefit")

# The electoral quantities that make a clause an electoral consequence. Named
# explicitly rather than left to the model's sense of what counts, which is
# the whole point of this revision.
ELECTORAL_QUANTITIES = ("votes", "seats", "a majority", "control of the "
                        "council", "winning or losing an election or a ward",
                        "a party's level of support", "turnout")


def build_prompt() -> str:
    """The system prompt: byte-stable, so it caches once per batch."""
    quantities = ", ".join(ELECTORAL_QUANTITIES)
    values = ", ".join(f'"{d}"' for d in DECISIONS)
    return f"""You read news articles for an academic study of pre-election \
coverage in Surrey, England, and answer one question about each.

THE QUESTION: does this article assert an electoral consequence, and if so, \
in which direction?

An electoral consequence is asserted when the article contains a clause - \
written by the journalist or spoken by someone it quotes - about one of these \
electoral quantities: {quantities}.

Rules:
1. THE ELECTORAL STEP MUST BE IN THE ARTICLE. A problem being reported, a \
service failing, a budget overrunning, a politician being criticised or \
praised, a resident being angry - none of these is an electoral consequence, \
however strongly you think it implies one. The article itself has to make the \
step to votes, seats, support or control. If it does not, the answer is \
"none". This is the most common correct answer.
2. DO NOT SUPPLY THE INFERENCE. You are not being asked what the electoral \
effect of this news would be. You are being asked whether the article states \
one. Your own political reasoning is not evidence.
3. NAME WHOSE POSITION CHANGES. When a consequence is asserted, say which \
party or administration it is about, using the article's own terms.
4. DIRECTION IS FROM THAT PARTY'S POINT OF VIEW. "damage" means the article \
asserts their electoral position may worsen - losing votes, seats, support or \
control. "benefit" means it may improve. If the article asserts a consequence \
for two parties in opposite directions, answer for the party the article \
gives most weight to; do not answer "none" and do not invent a third value.
5. GIVE A SHORT REASON - one sentence naming what in the article drives the \
answer. When the answer is not "none", the reason must point at the clause \
about the electoral quantity. No verbatim quotation is required.
6. Output ONLY a JSON object of this exact shape, no markdown fences:

{{"electoral_consequence": "<one of {values}>", \
"party": "<party or administration, or null when none>", \
"reason": "<one sentence>"}}

Prompt version: {RESCUE_VERSION}."""


def build_user_message(title: str, body: str, date: str, source: str) -> str:
    return (f"SOURCE: {source}\nPUBLISHED: {date}\n\nTITLE: {title}\n\n"
            f"BODY:\n{body}")


def _paths(arm: str) -> tuple[Path, Path]:
    suffix = "" if arm == "sonnet" else f"_{arm}"
    return (Path(f"llm_context/consequence_rescue_batch{suffix}.json"),
            Path(f"llm_context/consequence_rescue_outputs{suffix}.json"))


def cmd_submit(arm_name: str = "haiku") -> None:
    arm = ARMS[arm_name]
    model = arm["model"] or MODEL
    arts, _fallback = load_d4_articles()
    client = anthropic.Anthropic()

    # Every article is asked, and none is filtered: whether a consequence is
    # asserted is a property of the article, so there is no analogue of the
    # stance rescue's party-presence screen. The comparison base is therefore
    # the same 60 articles the frozen layer was scored on, which keeps the
    # before-and-after figures on one denominator.
    system = [{"type": "text", "text": build_prompt(),
               "cache_control": {"type": "ephemeral"}}]
    requests = [Request(
        custom_id=aid,
        params=MessageCreateParamsNonStreaming(
            model=model, max_tokens=MAX_TOKENS, thinking=arm["thinking"],
            system=system,
            messages=[{"role": "user", "content": build_user_message(
                a["title"], a["body"], a.get("publication_datetime", ""),
                a.get("source", ""))}]))
        for aid, a in sorted(arts.items())]

    batch = client.messages.batches.create(requests=requests)
    batch_path, _ = _paths(arm_name)
    batch_path.write_text(json.dumps({
        "version": RESCUE_VERSION, "arm": arm_name, "model": model,
        "thinking": arm["thinking"], "batch_id": batch.id,
        "articles": len(requests), "decisions": list(DECISIONS)}, indent=2))
    print(f"{arm_name}: batch {batch.id} ({len(requests)} articles)")
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
        entry: dict = {"article_id": result.custom_id,
                       "batch_result": result.result.type}
        if result.result.type == "succeeded":
            msg = result.result.message
            usage_in += msg.usage.input_tokens
            usage_out += msg.usage.output_tokens
            text = "".join(b.text for b in msg.content if b.type == "text")
            try:
                parsed = json.loads(text.strip().removeprefix("```json")
                                    .removeprefix("```").removesuffix("```"))
                value = parsed.get("electoral_consequence")
                errors = []
                # A value outside the declared vocabulary is not partially
                # usable: the whole point of this revision is that the
                # vocabulary has three members, and a model inventing a
                # fourth has not answered the question that was asked.
                if value not in DECISIONS:
                    errors.append(f"value {value!r} not in {DECISIONS}")
                # A consequence with no party named breaks rule 3, and the
                # direction is defined relative to that party - without it
                # the answer cannot be interpreted.
                if value in ("damage", "benefit") and not parsed.get("party"):
                    errors.append(f"{value} with no party named")
                entry["decision"] = value
                entry["party"] = parsed.get("party")
                entry["reason"] = parsed.get("reason")
                entry["validation_errors"] = errors
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                entry["decision"] = None
                entry["validation_errors"] = [f"unparseable: {e}"]
        else:
            entry["decision"] = None
            entry["validation_errors"] = [f"batch: {result.result.type}"]
        rows.append(entry)

    ok = sum(1 for r in rows if r["decision"] and not r["validation_errors"])
    out_path.write_text(json.dumps({
        "version": RESCUE_VERSION, "arm": arm_name, "model": meta["model"],
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
        "articles_ok": ok, "articles_total": len(rows),
        "decisions": list(DECISIONS), "results": rows}, indent=2))
    print(f"{ok}/{len(rows)} clean -> {out_path}")


if __name__ == "__main__":
    _cmd = sys.argv[1]
    _arm = sys.argv[2] if len(sys.argv) > 2 else "haiku"
    {"submit": cmd_submit, "collect": cmd_collect}[_cmd](_arm)
