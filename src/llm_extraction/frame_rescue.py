"""A rescue attempt for the failed framing layer, using the stance recipe.

## Why the original failed, and why the same fix might apply

`framing_detection.py` asks for one `primary_frame` chosen from sixteen
categories. It failed both rulers - kappa 0.483 against the human coding,
0.502 between the two model arms - and a coarsened re-test that grouped the
sixteen into three thematic families still failed (0.496 / 0.523), so the
problem is not granularity.

The diagnosis borrows from stance. That layer failed for two reasons, both
of which were the model being handed an unguided choice: which entities
deserve a row, and where the boundary of the `mixed` catch-all sits. Fixing
both took it from 0.316 to 0.848 between arms.

`primary_frame` is the same shape of problem. Asking "which of these
sixteen frames is the *primary* one" is a sixteen-way ranking judgement,
and nothing in the prompt says how to rank. An article that judges the
council's competence *and* portrays voters as fed up genuinely contains two
frames; which one is "primary" is a question the article does not answer,
so two models resolve it differently and disagree - while agreeing
completely about what the article contains.

The coarsened re-test could not detect this, because collapsing a recorded
`primary_frame` into a family still inherits the ranking that produced it.
You cannot recover "both were present" from a field that only ever stored
one winner.

## What this layer changes

**One ranking becomes four independent presence questions.** For each of
four frames the model answers only: is this frame present in this article,
yes or no. Frames are not mutually exclusive, none is "primary", and an
article may carry all four or none. There is no ranking left to disagree
about.

**The four frames are fixed here, chosen for the research question, not
for what scores well.** They are declared before any output exists. Each
maps from a group of the original sixteen, so nothing new is being measured
- the same content is being asked about in a form two raters can agree on:

* `incumbent_judgement` - the article passes judgement on how the governing
  administration has performed. From the original government_performance,
  governance_failure, financial_pressure, public_service_quality,
  accountability, competence, integrity, leadership.
* `challenger_emergence` - the article presents a party outside the
  established order as a rising or credible force. From
  challenger_emergence, electoral_competition,
  national_political_momentum. This is the frame the research question
  cares about most directly: Reform UK is the insurgent under study.
* `voter_discontent` - the article portrays voters as dissatisfied, angry,
  or wanting to punish someone. From anti_incumbent_sentiment,
  voter_dissatisfaction. Paired with the above because the standard theory
  of insurgent voting is discontent plus an available alternative, and
  separating the two lets the data speak to whether both are needed.
* `local_impact` - the article frames the matter through concrete local
  consequences for residents. From local_community_impact, policy_conflict.
  Carried because the local-versus-national comparison is one of the
  supervisor's named contrasts.

Four of the original sixteen categories map to none of these -
`other`, plus the three that describe an article's genre rather than its
frame. Their absence is deliberate and recorded: this layer measures four
named frames, not a partition of all possible framing.

**No verbatim evidence span**, for the reason it was dropped in the stance
rescue: it suppressed recall, pushing a model that could see a frame but
could not isolate one clean quotable sentence into answering "not present".
A one-sentence free-text reason is requested instead.

## Honest status

This is the second and final rescue attempt in this family. If it passes,
framing enters the feature set as four binary presence indicators - not as
a sixteen-category classification, and reported that way. If it fails,
framing is excluded on four independent attempts (original, coarsened,
this redesign, on two model arms each), which is a far stronger basis for
exclusion than one disagreement with one coder.

Iterating further would mean tuning a prompt against the validation sample
until it passed, which is selection on the evaluation data by another name.
Two principled attempts is the limit set in advance.

Usage:
    python3 -m src.llm_extraction.frame_rescue submit [arm]
    python3 -m src.llm_extraction.frame_rescue collect [arm]
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

RESCUE_VERSION = "frame-rescue-v1.0-2026-07-30"

# Must exceed the Haiku arm's fixed 4,000-token thinking budget, because
# the API requires budget_tokens < max_tokens. The stance rescue's first
# submission set this to 2,000 and every Haiku request errored while every
# Sonnet request succeeded - Sonnet uses adaptive thinking and has no fixed
# budget to exceed. Recorded here so the same trap is not walked into twice.
MAX_TOKENS = 6000

# The four frames, with the question each one puts to the model. The
# wording matters more than usual: these are the entire specification a
# model has to work from, so each is written as a single testable claim
# about the article rather than as a category label to be interpreted.
FRAMES = {
    "incumbent_judgement": (
        "Does the article pass judgement on how the governing administration "
        "has performed - its competence, its finances, the quality of the "
        "services it runs, its integrity, or its leadership? This includes "
        "criticism and defence alike; the question is whether the article "
        "puts the administration's record on trial, not whether it approves."
    ),
    "challenger_emergence": (
        "Does the article present a party outside the established order as a "
        "rising or credible force - gaining support, worth taking seriously, "
        "or capable of winning where it previously could not?"
    ),
    "voter_discontent": (
        "Does the article portray voters as dissatisfied, angry, or wanting "
        "to punish someone - fed up with how things are, or looking for an "
        "alternative? The discontent must be attributed to voters or "
        "residents, not merely expressed by a politician."
    ),
    "local_impact": (
        "Does the article frame the matter through concrete consequences for "
        "local residents - a road, a school, a development, a service they "
        "use - rather than as politics in the abstract?"
    ),
}


def build_prompt() -> str:
    """The system prompt.

    Byte-stable across every article, unlike the stance rescue's - the
    question set here does not depend on the article's content, so the
    whole prompt caches once per batch and is billed at the cache-read
    rate for the remaining requests.
    """
    questions = "\n\n".join(
        f'{i}. "{key}": {text}'
        for i, (key, text) in enumerate(FRAMES.items(), start=1))
    keys = ", ".join(f'"{k}"' for k in FRAMES)
    return f"""You identify narrative frames in news articles, for an academic study \
of pre-election coverage in Surrey, England.

For each of the four frames below, answer one question: is this frame present \
in this article, yes or no.

{questions}

Rules:
1. THE FRAMES ARE INDEPENDENT. They are not alternatives and none is \
"primary". An article may carry all four, some, or none. Judge each one \
separately, as if it were the only question asked.
2. PRESENT MEANS THE ARTICLE DOES THIS, not that the topic could be read that \
way. A frame is present when the article actually organises some of its \
material that way - through what it emphasises, whom it quotes, or how it \
explains why something matters. A single passing clause is not a frame.
3. DO NOT INFER FROM THE SUBJECT. A story about a school is not automatically \
"local_impact"; it is local_impact when the article dwells on what this means \
for the people who use that school. A story mentioning a party's poll rating \
is not automatically "challenger_emergence"; it is that frame when the article \
presents the party as rising or credible.
4. JUDGE THE ARTICLE, NOT THE POLITICS. You are not assessing whether the \
framing is fair, and not supplying your own view of the parties involved.
5. GIVE A SHORT REASON per frame - one sentence naming what in the article \
drives the answer. No verbatim quotation is required.
6. Output ONLY a JSON object of this exact shape, with all four frames \
present, no markdown fences:

{{"frames": [{{"frame": "<one of {keys}>", "present": true, \
"reason": "<one sentence>"}}]}}

Prompt version: {RESCUE_VERSION}."""


def build_user_message(title: str, body: str, date: str, source: str) -> str:
    return (f"SOURCE: {source}\nPUBLISHED: {date}\n\nTITLE: {title}\n\n"
            f"BODY:\n{body}")


def _paths(arm: str) -> tuple[Path, Path]:
    suffix = "" if arm == "sonnet" else f"_{arm}"
    return (Path(f"llm_context/frame_rescue_batch{suffix}.json"),
            Path(f"llm_context/frame_rescue_outputs{suffix}.json"))


def cmd_submit(arm_name: str = "haiku") -> None:
    arm = ARMS[arm_name]
    model = arm["model"] or MODEL
    arts, _fallback = load_d4_articles()
    client = anthropic.Anthropic()

    # Every article is asked about all four frames - unlike the stance
    # rescue, where the party list depends on who the article names. Frames
    # are properties of the article itself, so there is nothing to filter
    # and no article is skipped. That also makes the comparison base the
    # full 60 articles x 4 frames = 240 pairs.
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
        "articles": len(requests), "frames": list(FRAMES)}, indent=2))
    print(f"{arm_name}: batch {batch.id} ({len(requests)} articles x "
          f"{len(FRAMES)} frames)")
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
                judged = {f["frame"]: bool(f["present"])
                          for f in parsed.get("frames", [])}
                # A model that answered about three frames, or invented a
                # fifth, has not answered the question asked. Recorded as a
                # validation error rather than partially used: scoring the
                # overlap would credit it for the part it happened to cover.
                errors = []
                if set(judged) != set(FRAMES):
                    errors.append(f"answered about {sorted(judged)}, "
                                  f"asked about {sorted(FRAMES)}")
                entry["frames"] = judged
                entry["reasons"] = {f["frame"]: f.get("reason")
                                    for f in parsed.get("frames", [])}
                entry["validation_errors"] = errors
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                entry["frames"] = None
                entry["validation_errors"] = [f"unparseable: {e}"]
        else:
            entry["frames"] = None
            entry["validation_errors"] = [f"batch: {result.result.type}"]
        rows.append(entry)

    ok = sum(1 for r in rows if r["frames"] and not r["validation_errors"])
    out_path.write_text(json.dumps({
        "version": RESCUE_VERSION, "arm": arm_name, "model": meta["model"],
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
        "articles_ok": ok, "articles_total": len(rows),
        "frames": list(FRAMES), "results": rows}, indent=2))
    print(f"{ok}/{len(rows)} clean -> {out_path}")


if __name__ == "__main__":
    _cmd = sys.argv[1]
    _arm = sys.argv[2] if len(sys.argv) > 2 else "haiku"
    {"submit": cmd_submit, "collect": cmd_collect}[_cmd](_arm)
