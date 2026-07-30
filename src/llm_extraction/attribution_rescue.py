"""A second attempt at the credit-and-blame layer, on a diagnosis the
five-way confusion matrix was hiding.

The frozen layer failed the D4 gate on both arms: kappa 0.521 (Sonnet, n=57)
and 0.516 (Haiku), with the fallback route unavailable at a largest marginal
of 0.579. An earlier note in this project concluded that no definitional fix
was diagnosable, because the disagreements scattered across seven cells with
marginals that broadly matched - human blame 33 of 57, model 29 - unlike the
consequence layer, whose disagreements concentrated in a single cell.

That conclusion was wrong, and the reason is worth recording: the five-way
field was averaging two very different failures into one mediocre number.
Splitting the existing frozen output into the two binaries this module asks
about - derived from `attribution_type_set`, so no new API call was needed -
separates them:

    binary            Sonnet kappa   Haiku kappa   human pos / model pos
    blame present         0.564          0.565            36 / 34
    credit present        0.181          0.483             8 / 29

Blame is nearly there and its marginals match. Credit has the same shape the
consequence layer had: the model finds credit in 29 of 52 articles where the
reviewer finds it in 8, a threshold set roughly three and a half times lower.
The human distribution is why the average hid this - blame is 33 of 57 of the
reviewer's labels, so blame's competence and credit's incompetence combined
into 0.521 and looked like one uniform failure.

Two further faults in the frozen instrument, both already documented:

* The reviewer was told to record the single *principal* attribution;
  `credit_blame.py` never asks the model to rank its attributions. Scoring
  the model's first row against that instruction tested a rule only one side
  received. Independent binaries have no principal, so the rule disappears.
* The reviewer used `mixed` on 3 articles and `unclear` on 5 - 8 of 57, 14% -
  and the model used neither once across all 57 records, though both are in
  its enum. Under two binaries, both-yes *is* mixed and both-no *is* none, so
  the `mixed` labels become matchable rather than structurally unpairable.

The design is the framing rescue's, applied here: replace one many-way
judgement with independent binary presence questions, each written as a
single testable claim rather than a category label to interpret. That took
framing from a sixteen-way failure to two of four frames recovered, and the
same move took stance from 0.32 to 0.85.

What this module adds beyond the split is an explicit bar for what counts as
an attribution at all, because the credit figures say the model's bar is far
below the reviewer's. The bar is stated as three conditions that can be
checked rather than as a matter of degree, and the exclusions name the cases
pre-election coverage is full of: a promise, a plan, a manifesto pledge, a
politician defending their own record. None of those attributes an outcome to
anyone, because in a promise there is no outcome yet.

THE SCORING RULE, STATED BEFORE THE BATCH IS SUBMITTED
------------------------------------------------------
Declared here so it cannot be selected after the numbers are seen. This
layer's verdict has already moved twice under scoring corrections - set
membership, then validator gating - and both were real faults; a third
correction chosen after the fact would not be.

* Each binary is judged on its own, exactly as the four framing frames were.
  One may pass while the other fails. Gate: Cohen's kappa >= 0.60, or the
  pre-registered fallback (Gwet's AC1 >= 0.60 with agreement >= 80%) only if
  a marginal reaches 0.90.
* Human mapping: `blame_present` is true for human labels `blame` and
  `mixed`; `credit_present` is true for `credit` and `mixed`; `none` is false
  for both. Human `unclear` is EXCLUDED from both binaries - the reviewer
  recorded that an attribution exists but its direction is not determinable,
  which is not an answer either binary can be paired against.
* A binary whose human positive count is below 10 is reported
  `undetermined_insufficient_positives`, not failed - the same minimum the
  framing rescue used, for the same reason: below it a single disagreement
  moves kappa by more than a tenth. On the D4 sample the reviewer's credit
  positives number 8, so **credit is expected to come back undetermined**.
  That is stated in advance rather than discovered afterwards.
* No coarsening, collapse or re-pairing beyond the above. If both binaries
  fail, the layer is dropped and that is the finding.

What is at stake: `blame_count` and `recency_weighted_blame` need the blame
binary only; `credit_count` and `net_attribution` need credit. So blame
clearing on its own recovers two of the layer's four pre-registered features.

Usage:
    python3 -m src.llm_extraction.attribution_rescue submit haiku
    python3 -m src.llm_extraction.attribution_rescue collect haiku
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

RESCUE_VERSION = "attribution-rescue-v1.0-2026-07-30"

# Must exceed the Haiku arm's fixed 4,000-token thinking budget: the API
# requires budget_tokens < max_tokens. The stance rescue set this to 2,000 and
# every Haiku request errored while every Sonnet request succeeded, Sonnet's
# thinking being adaptive with no fixed budget to exceed.
MAX_TOKENS = 6000

DIRECTIONS = {
    "blame": (
        "Does the article report anyone BLAMING a named party, council "
        "administration or governing group for something that has gone wrong? "
        "The blame may come from the journalist's own narration or from "
        "someone the article quotes - a politician, a resident, an "
        "organisation."
    ),
    "credit": (
        "Does the article report anyone CREDITING a named party, council "
        "administration or governing group for something that has gone well? "
        "Same sources count as for blame."
    ),
}


def build_prompt() -> str:
    """The system prompt: byte-stable, so it caches once per batch."""
    questions = "\n\n".join(f'{i}. "{k}": {v}'
                            for i, (k, v) in enumerate(DIRECTIONS.items(),
                                                       start=1))
    keys = ", ".join(f'"{k}"' for k in DIRECTIONS)
    return f"""You read news articles for an academic study of pre-election \
coverage in Surrey, England, and answer two questions about each.

{questions}

An attribution is present only when all three of these hold:

(a) a NAMED party, administration or governing group - not an unnamed \
"the council", not an individual acting in a personal capacity;
(b) a SPECIFIC outcome or state of affairs that already exists or has already \
happened - a service that is failing or working, a budget overspent or \
balanced, a road repaired or left unrepaired, a decision taken;
(c) a STATEMENT IN THE ARTICLE linking the two - someone saying, or the \
journalist reporting, that this outcome is that group's doing.

Rules:
1. THE TWO QUESTIONS ARE INDEPENDENT. They are not opposites. An article may \
carry both (one group blamed, another credited, or the same group both), or \
one, or neither. Judge each as if it were the only question asked.
2. A PROMISE IS NOT AN ATTRIBUTION. Pre-election coverage is full of parties \
saying what they will do - a pledge, a manifesto, a plan, a candidate's \
priorities, "we would fix this". None of these attributes an outcome to \
anyone, because in a promise the outcome does not exist yet. Answer "no" for \
these unless the article separately reports an attribution about something \
already done.
3. SELF-DEFENCE IS NOT CREDIT. A politician rejecting criticism, explaining a \
decision, or saying the situation is not as bad as claimed is defending a \
record, not being credited for an outcome. Neither is a neutral report that \
something happened while a party was in office, with no one saying the party \
brought it about.
4. BEING NAMED IS NOT BEING BLAMED OR CREDITED. A candidate list, an election \
notice, a quotation on an unrelated subject, or a party simply appearing in \
the article does not make it an attribution.
5. JUDGE THE ARTICLE, NOT THE POLITICS. You are not assessing whether the \
blame or credit is deserved, and not supplying your own view of the parties.
6. GIVE A SHORT REASON per question - one sentence naming who is blamed or \
credited, for what, and by whom. When the answer is "no", say briefly what \
the article does instead. No verbatim quotation is required.
7. Output ONLY a JSON object of this exact shape, with both questions \
answered, no markdown fences:

{{"attributions": [{{"direction": "<one of {keys}>", "present": true, \
"party": "<the named group, or null when absent>", \
"reason": "<one sentence>"}}]}}

Prompt version: {RESCUE_VERSION}."""


def build_user_message(title: str, body: str, date: str, source: str) -> str:
    return (f"SOURCE: {source}\nPUBLISHED: {date}\n\nTITLE: {title}\n\n"
            f"BODY:\n{body}")


def _paths(arm: str) -> tuple[Path, Path]:
    suffix = "" if arm == "sonnet" else f"_{arm}"
    return (Path(f"llm_context/attribution_rescue_batch{suffix}.json"),
            Path(f"llm_context/attribution_rescue_outputs{suffix}.json"))


def cmd_submit(arm_name: str = "haiku") -> None:
    arm = ARMS[arm_name]
    model = arm["model"] or MODEL
    arts, _fallback = load_d4_articles()
    client = anthropic.Anthropic()

    # Every article is asked both questions and none is filtered: whether an
    # attribution is present is a property of the article, so there is no
    # analogue of the stance rescue's party-presence screen. The comparison
    # base is the same 60 articles the frozen layer was scored on, keeping the
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
        "articles": len(requests), "directions": list(DIRECTIONS)}, indent=2))
    print(f"{arm_name}: batch {batch.id} ({len(requests)} articles x "
          f"{len(DIRECTIONS)} questions)")
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
                rowsin = parsed.get("attributions") or []
                judged = {r["direction"]: bool(r.get("present"))
                          for r in rowsin if r.get("direction")}
                errors = []
                # A model that answered one question, or invented a third,
                # has not answered what was asked. Scoring the overlap would
                # credit it for the part it happened to cover.
                if set(judged) != set(DIRECTIONS):
                    errors.append(f"answered about {sorted(judged)}, "
                                  f"asked about {sorted(DIRECTIONS)}")
                # A present attribution with no group named breaks condition
                # (a), and without it the answer cannot be checked.
                for r in rowsin:
                    if r.get("present") and not r.get("party"):
                        errors.append(f"{r.get('direction')} present with no "
                                      f"party named")
                entry["attributions"] = judged
                entry["parties"] = {r["direction"]: r.get("party")
                                    for r in rowsin if r.get("direction")}
                entry["reasons"] = {r["direction"]: r.get("reason")
                                    for r in rowsin if r.get("direction")}
                entry["validation_errors"] = errors
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                entry["attributions"] = None
                entry["validation_errors"] = [f"unparseable: {e}"]
        else:
            entry["attributions"] = None
            entry["validation_errors"] = [f"batch: {result.result.type}"]
        rows.append(entry)

    ok = sum(1 for r in rows
             if r["attributions"] and not r["validation_errors"])
    out_path.write_text(json.dumps({
        "version": RESCUE_VERSION, "arm": arm_name, "model": meta["model"],
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
        "articles_ok": ok, "articles_total": len(rows),
        "directions": list(DIRECTIONS), "results": rows}, indent=2))
    print(f"{ok}/{len(rows)} clean -> {out_path}")


if __name__ == "__main__":
    _cmd = sys.argv[1]
    _arm = sys.argv[2] if len(sys.argv) > 2 else "haiku"
    {"submit": cmd_submit, "collect": cmd_collect}[_cmd](_arm)
