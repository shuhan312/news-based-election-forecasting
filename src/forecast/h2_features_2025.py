"""H2 news features, 2025: how local news portrayed Reform, per council.

    PYTHONPATH=.:src python -m forecast.h2_features_2025 estimate   # free
    PYTHONPATH=.:src python -m forecast.h2_features_2025 submit     # Batches
    PYTHONPATH=.:src python -m forecast.h2_features_2025 collect
    PYTHONPATH=.:src python -m forecast.h2_features_2025 audit      # A4 check
    PYTHONPATH=.:src python -m forecast.h2_features_2025 features

Input: the Reform articles attributed to each council by
forecast.h2_news_2025 (published 1-30 April 2025, read from pre-polling-day
Wayback captures). Each article is sent twice, as two separate requests:

  stance    V1's revised stance layer, prompt unchanged, run on V1's
            Haiku arm (claude-haiku-4-5, thinking budget 4,000), which
            passed the same human-label gate as the Sonnet arm (kappa
            0.741 vs 0.736) at about 30% lower cost (cost policy).
            Its prompt names Surrey as the study area; it is sent verbatim
            all the same, because the validation was of this exact prompt.
  activity  the exploratory question (design A4): does the article report
            specific local Reform campaign activity?

Per council (design A4):
  V_c  Reform articles / all articles attributed to the council (M1)
  S_c  net portrayal of Reform = (favourable - unfavourable) / judged (M2)
  A_c  share of Reform articles reporting local campaign activity
       (exploratory, not in M2, not Holm-tested)

No 2025 result is read here. Cost is checked against the US$20 cap before
anything is submitted.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from pathlib import Path

from forecast import h2_news_2025 as news
from llm_eval.pricing import cost_usd
from src.llm_extraction import stance_rescue as v1

DATA = news.DATA
OUT_DIR = news.OUT_DIR
STATE = DATA / "batch_state.json"
OUTPUTS = DATA / "llm_outputs.json"
MODEL = "claude-haiku-4-5"           # V1's validated Haiku arm (cheapest)
AUDIT_MODEL = "claude-sonnet-5"      # V1's Sonnet arm, a stronger reader
# Thinking settings exactly as in V1's two arms (run_d4_validation.ARMS).
THINKING = {"claude-haiku-4-5": {"type": "enabled", "budget_tokens": 4000},
            "claude-sonnet-5": {"type": "adaptive"}}
AUDIT_N, AUDIT_SEED = 40, 20261014
BUDGET_USD = 20.0
ACTIVITY_MAX_TOKENS = 400

ACTIVITY_PROMPT = """You read a local news article from England, published \
in April 2025, before the 1 May 2025 local elections.

Question: does the article report SPECIFIC LOCAL campaign activity by Reform \
UK in the area it covers? Count as "yes" any of:
- a named local Reform UK candidate or councillor, doing or saying something;
- a local Reform UK event, rally, visit or canvassing;
- a councillor in the area defecting to Reform UK;
- a local incident involving Reform UK's campaign (leaflets, vandalism, \
complaints).
Answer "no" when Reform UK appears only in national news, opinion polls, or \
national figures' statements with no local campaign content, or only as a \
name in a list of parties or candidates.

Output ONLY a JSON object, no markdown fences:
{"local_campaign_activity": "yes|no", "reason": "<one sentence>"}"""


# --- articles -------------------------------------------------------------------------

def _aid(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:20]


def reform_articles() -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Unique Reform articles (id -> article) and council -> article ids.
    An article in a shared outlet that names two councils counts for both
    but is classified once."""
    by = news.attribute(news.window_articles())
    arts, councils = {}, {}
    for council, v in by.items():
        councils[council] = []
        for a in v["reform"]:
            aid = _aid(a["url"])
            arts[aid] = a
            councils[council].append(aid)
    return arts, councils


def _requests(arts: dict[str, dict], model: str = MODEL,
              which: tuple[str, ...] = ("stance", "activity")) -> list[dict]:
    """Batch requests. stance: V1's prompt over the parties the article
    names (Reform among them, or it is skipped). activity: the A4 question."""
    out = []
    for aid, a in sorted(arts.items()):
        title, body = a.get("headline") or "", a["text"]
        user = v1.build_user_message(title, body, a.get("published_date", ""),
                                     a["outlet"])
        parties = v1.parties_present(title, body)
        if "stance" in which and "reform_uk" in parties:
            out.append({"custom_id": f"s_{aid}", "params": {
                "model": model, "max_tokens": v1.MAX_TOKENS,
                "thinking": THINKING[model],
                "system": v1.build_prompt(parties),
                "messages": [{"role": "user", "content": user}]}})
        if "activity" in which:
            out.append({"custom_id": f"a_{aid}", "params": {
                "model": model, "max_tokens": ACTIVITY_MAX_TOKENS,
                "system": ACTIVITY_PROMPT,
                "messages": [{"role": "user", "content": user}]}})
    return out


def _estimate(reqs: list[dict], model: str) -> float:
    """Upper-bound cost: input ~ characters / 3.5; output at an allowance
    of 1,500 tokens per stance request (thinking included), 150 otherwise."""
    tin = sum(len(r["params"]["system"]) + len(r["params"]["messages"][0]
                                                 ["content"]) for r in reqs) / 3.5
    tout = sum(1500 if r["custom_id"].startswith("s_") else 150 for r in reqs)
    return cost_usd(model, int(tin), tout, batch=True)


def stage_estimate() -> None:
    arts, councils = reform_articles()
    reqs = _requests(arts)
    print(f"{len(arts)} Reform articles, {len(reqs)} requests, "
          f"estimated cost US${_estimate(reqs, MODEL):.2f} (Batches)")


# --- batches ----------------------------------------------------------------------------

def _submit(reqs: list[dict], key: str) -> None:
    import anthropic
    cost = _estimate(reqs, reqs[0]["params"]["model"])
    spent = sum(s.get("estimate_usd", 0) for s in _state().values())
    if spent + cost > BUDGET_USD:
        raise RuntimeError(f"estimated US${spent + cost:.2f} exceeds the "
                           f"US${BUDGET_USD} cap; nothing submitted")
    batch = anthropic.Anthropic().messages.batches.create(requests=reqs)
    state = _state()
    state[key] = {"batch_id": batch.id, "requests": len(reqs),
                  "estimate_usd": round(cost, 2)}
    STATE.write_text(json.dumps(state, indent=2))
    print(f"{key}: batch {batch.id}, {len(reqs)} requests, ~US${cost:.2f}")


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def stage_submit() -> None:
    arts, _ = reform_articles()
    _submit(_requests(arts), "main")


def _parse(text: str) -> dict | None:
    try:
        return json.loads(text.strip().removeprefix("```json")
                          .removeprefix("```").removesuffix("```"))
    except json.JSONDecodeError:
        return None


def _collect(key: str) -> dict[str, dict]:
    """custom_id -> parsed answer, once the batch has ended. Answers that
    fail to parse or fall outside the vocabulary are kept as errors, not
    coerced."""
    import anthropic
    client = anthropic.Anthropic()
    batch_id = _state()[key]["batch_id"]
    while (b := client.messages.batches.retrieve(batch_id)
           ).processing_status != "ended":
        print(key, b.processing_status, b.request_counts, flush=True)
        time.sleep(120)
    out, tin, tout = {}, 0, 0
    for r in client.messages.batches.results(batch_id):
        if r.result.type != "succeeded":
            out[r.custom_id] = {"error": r.result.type}
            continue
        msg = r.result.message
        tin, tout = tin + msg.usage.input_tokens, tout + msg.usage.output_tokens
        parsed = _parse("".join(c.text for c in msg.content
                                if c.type == "text"))
        if r.custom_id.startswith("s_"):
            judged = {j.get("party"): j.get("portrayal")
                      for j in (parsed or {}).get("judgements", [])}
            value = judged.get("reform_uk")
            ok = value in v1.DECISIONS
        else:
            value = (parsed or {}).get("local_campaign_activity")
            ok = value in ("yes", "no")
        out[r.custom_id] = {"value": value} if ok else {
            "error": f"invalid answer: {value!r}"}
    model = _state()[key].get("model", MODEL)
    print(f"{key}: actual cost US${cost_usd(model, tin, tout):.2f}")
    return out


def stage_collect() -> None:
    OUTPUTS.write_text(json.dumps(_collect("main"), indent=1))
    print(f"-> {OUTPUTS}")


# --- A4 classifier check ----------------------------------------------------------------

def stage_audit() -> None:
    """Re-read 40 random stance-judged Reform articles with a stronger
    model, same prompt; kappa < 0.60 stops H2 (design A4). An agreement
    audit, not human validation."""
    from llm_eval.metrics import multiclass_kappa
    outputs = json.loads(OUTPUTS.read_text())
    judged = sorted(k[2:] for k, v in outputs.items()
                    if k.startswith("s_") and "value" in v)
    sample = random.Random(AUDIT_SEED).sample(judged, min(AUDIT_N, len(judged)))
    arts, _ = reform_articles()
    if "audit" not in _state():
        reqs = _requests({a: arts[a] for a in sample}, AUDIT_MODEL, ("stance",))
        _submit(reqs, "audit")
        state = _state()
        state["audit"]["model"] = AUDIT_MODEL
        STATE.write_text(json.dumps(state, indent=2))
    second = _collect("audit")
    pairs = [(outputs[f"s_{a}"]["value"], second[f"s_{a}"]["value"])
             for a in sample if "value" in second.get(f"s_{a}", {})]
    k = multiclass_kappa([p[0] for p in pairs], [p[1] for p in pairs])
    result = {"model": MODEL, "second_reader": AUDIT_MODEL, "pairs": len(pairs),
              "kappa": round(k, 3),
              "agreement": round(sum(a == b for a, b in pairs) / len(pairs), 3),
              "gate": 0.60, "passes": k >= 0.60}
    (OUT_DIR / "stance_audit.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


# --- per-council features ---------------------------------------------------------------

def stage_features() -> None:
    outputs = json.loads(OUTPUTS.read_text())
    counts = json.loads((OUT_DIR / "coverage_counts.json").read_text())
    _, councils = reform_articles()
    table = {}
    for council, aids in sorted(councils.items()):
        stance = [outputs[f"s_{a}"]["value"] for a in aids
                  if "value" in outputs.get(f"s_{a}", {})]
        activity = [outputs[f"a_{a}"]["value"] for a in aids
                    if "value" in outputs.get(f"a_{a}", {})]
        table[council] = {
            "V": counts["per_council"][council]["V_reform_share"],
            "reform_articles": len(aids),
            "stance_judged": len(stance),
            "S": round((stance.count("favourable")
                        - stance.count("unfavourable")) / len(stance), 3)
            if stance else None,
            "A_exploratory": round(activity.count("yes") / len(activity), 3)
            if activity else None,
        }
    errors = sum("error" in v for v in outputs.values())
    (OUT_DIR / "features.json").write_text(json.dumps(
        {"design": "v2_design/direction1_design.md (A4)",
         "llm_errors": errors, "per_council": table}, indent=2) + "\n",
        encoding="utf-8")
    for c, t in table.items():
        print(f"{c:24}", t)


if __name__ == "__main__":
    {"estimate": stage_estimate, "submit": stage_submit,
     "collect": stage_collect, "audit": stage_audit,
     "features": stage_features}[sys.argv[1]]()
