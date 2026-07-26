"""Phase 6 / Step 2 - pilot sampling and prompt construction (pure
logic; no API call in this module).

Sampling method (recorded, deterministic, no cherry-picking):

    frame       all articles whose duplicate-mapping status is
                use_as_canonical_input AND whose layer quality is
                valid_full_text (1,535 records at v1);
    strata      election_id x arm (local / national) - eight cells
                covering every election and both sides of the
                local-vs-national comparison;
    quotas      LOCAL_QUOTA per election from the local arm,
                NATIONAL_QUOTA per election from the national arm;
    ordering    within each stratum, candidates sort by
                sha256(article_id) - a fixed pseudo-random order that
                no one can steer and anyone can reproduce; the first
                k are taken. No manual selection anywhere.
    Reform UK   after the base sample, articles whose title or body
                mentions "reform uk" are topped up (same hash order)
                until the sample holds >= REFORM_MIN such articles -
                the specialised layer needs real positives to be
                exercised.

Prompt construction: one shared SYSTEM prompt (instructions + the
full v1.1 JSON schema + the hard rules) marked with cache_control so
the Batches API bills it once per cache window, plus a per-article
user message carrying metadata and the normalised text. The system
prompt contains no timestamps and no per-run values - byte-stable,
cache-friendly, reproducible.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA_PATH = Path("llm_context/llm_context_schema_v1.json")

LOCAL_QUOTA = 6          # per election
NATIONAL_QUOTA = 10      # per election
REFORM_MIN = 10          # minimum Reform-mentioning articles in sample

PILOT_VERSION = "pilot-v1.0-2026-07-26"

# Prompt v1.1 (Step 2.5): three pilot-driven refinements - hardened
# verbatim-quotation rule (the pilot's dominant error was
# ellipsis-shortened quotes), offsets removed from the model's job,
# leakage flags now need evidence AND an explanation, and the issue
# taxonomy moves to issues-v1.2 (adds election_administration).
PROMPT_VERSION = "prompt-v1.1-2026-07-26"


def _hash_order(aid: str) -> str:
    return hashlib.sha256(aid.encode()).hexdigest()


def select_pilot_sample(articles: list[dict]) -> dict:
    """Deterministic stratified sample.

    ``articles``: [{article_id, election_id, arm, mentions_reform}].
    Returns {selected: [ids], strata: {...}, method: str} - the
    method string goes verbatim into the audit file."""
    by_stratum: dict[tuple, list[dict]] = {}
    for a in articles:
        by_stratum.setdefault((a["election_id"], a["arm"]), []).append(a)

    selected: list[str] = []
    strata_report = {}
    for (election, arm), members in sorted(by_stratum.items()):
        quota = LOCAL_QUOTA if arm == "local" else NATIONAL_QUOTA
        ranked = sorted(members, key=lambda a: _hash_order(a["article_id"]))
        take = [a["article_id"] for a in ranked[:quota]]
        selected.extend(take)
        strata_report[f"{election}/{arm}"] = {
            "pool": len(members), "quota": quota, "taken": len(take)}

    # ---- Reform UK top-up (deterministic, same hash order) ----------
    have = {a["article_id"] for a in articles
            if a["mentions_reform"]} & set(selected)
    reform_pool = sorted(
        (a for a in articles
         if a["mentions_reform"] and a["article_id"] not in selected),
        key=lambda a: _hash_order(a["article_id"]))
    topped_up = []
    while len(have) + len(topped_up) < REFORM_MIN and reform_pool:
        topped_up.append(reform_pool.pop(0)["article_id"])
    selected.extend(topped_up)

    return {"selected": sorted(selected),
            "strata": strata_report,
            "reform_in_base": len(have),
            "reform_topped_up": len(topped_up),
            "method": (
                "Frame: canonical (use_as_canonical_input) full-text "
                "articles. Strata: election x arm. Quotas: "
                f"{LOCAL_QUOTA} local + {NATIONAL_QUOTA} national per "
                "election. Within-stratum order: sha256(article_id) - "
                "fixed, unsteerable, reproducible; first k taken. "
                f"Reform UK top-up to >= {REFORM_MIN} mentioning "
                "articles in the same hash order. No manual selection.")}


def select_revalidation_set(pilot_results: list[dict],
                            articles: dict[str, dict]) -> dict:
    """Targeted Step 2.5 re-validation set - NOT a full pilot rerun.

    Deterministic, recorded selection covering every category the
    specification names:

        failures     every pilot article that failed validation
                     (the before/after comparison hinges on these);
        flagged      3 low-confidence (review-routed) records;
        reform       3 records that activated the Reform UK layer;
        long         the 3 longest pilot articles by body words
                     (truncation regression check at the 40k limit);
        leakage      2 pilot records with leakage risk >= high or
                     any contains_* flag;
        admin        2 corpus articles whose titles match election-
                     administration keywords (polling station, postal
                     vote, returning officer, election day) - the new
                     taxonomy code needs real positives.

    Category ties are broken by sha256(article_id); overlaps are
    kept once. ``articles`` is the full eligible corpus (admin picks
    may fall outside the original pilot)."""
    import re
    picked: list[str] = []

    def add(ids, k=None):
        ranked = sorted(ids, key=_hash_order)
        for aid in (ranked if k is None else ranked[:k]):
            if aid not in picked:
                picked.append(aid)

    valid = [r for r in pilot_results
             if r.get("record") and not r["validation_errors"]]
    add([r["article_id"] for r in pilot_results
         if r["validation_errors"] or r.get("batch_result")
         != "succeeded"])                                   # failures
    add([r["article_id"] for r in valid
         if r["record"].get("review_status") == "flagged"], 3)
    add([r["article_id"] for r in valid
         if r["record"]["reform_uk"].get("reform_uk_present")], 3)
    pilot_ids = [r["article_id"] for r in pilot_results
                 if r["article_id"] in articles]
    longest = sorted(pilot_ids,
                     key=lambda a: -len(articles[a]["body"].split()))
    add(longest[:3])
    add([r["article_id"] for r in valid
         if r["record"]["leakage"].get("leakage_risk") in
         ("high", "disqualifying")
         or any(r["record"]["leakage"].get(f) for f in
                ("contains_poll", "contains_prediction",
                 "contains_election_result"))], 2)
    admin_re = re.compile(r"polling station|postal vote|returning "
                          r"officer|election day|count centre|"
                          r"polling day", re.I)
    add([aid for aid, a in articles.items()
         if admin_re.search(a["title"])], 2)

    return {"selected": sorted(picked),
            "method": (
                "Targeted re-validation, not a pilot rerun: ALL pilot "
                "validation failures; 3 review-flagged, 3 Reform-"
                "active and 2 leakage-flagged pilot records; 3 "
                "longest pilot articles (40k truncation check); 2 "
                "corpus articles with election-administration title "
                "keywords (new taxonomy code needs real positives). "
                "Ties broken by sha256(article_id); overlaps kept "
                "once. Deterministic and reproducible.")}


def build_system_prompt() -> str:
    """The shared extraction instruction block. Byte-stable: no
    clocks, no run ids - so prompt caching works across the batch and
    reruns produce the identical prompt."""
    schema = SCHEMA_PATH.read_text().strip()
    return f"""You are a political-content extraction system for an academic study \
of pre-election news coverage in Surrey, England. For each article you receive, \
produce ONE JSON object conforming exactly to the JSON Schema below.
Prompt version: {PROMPT_VERSION}. Set issues.taxonomy_version to "issues-v1.2"; \
use the issue code "election_administration" for polling arrangements, voting \
procedures, counting arrangements and other election-process reporting.

Hard rules - violating any of these makes the output unusable:
1. EVIDENCE OR NOTHING. Every claim's evidence_span.text must be copied \
CHARACTER-FOR-CHARACTER from the article body (or title, with from_title \
true). NEVER shorten a quote with "..." or any ellipsis, NEVER splice two \
passages together, NEVER reconstruct a quotation from memory. If a passage \
is long, choose a SHORTER CONTIGUOUS span instead. Do NOT output char_start \
or char_end - the verbatim text is the identifier. A validator string-matches \
every span against the text and rejects anything that is not an exact copy.
2. DO NOT GUESS. If the article does not state something, use null, empty \
arrays, "not_addressed" / "not_indicated" / "uncertain" values, and explain \
gaps in ambiguity_notes. An honest empty section beats an invented one.
3. NO OUTCOME PREDICTION. electoral_consequences records what the ARTICLE \
implies, never your own forecast of any election result.
4. STANCE HAS A TARGET. Judgements are per party / per candidate; there is \
no article-level sentiment and you must not produce one.
5. REFORM UK CONSISTENCY. If Reform UK is absent, reform_uk_present is \
false and every other flag in that section stays false/null. Any positive \
Reform flag requires an evidence quote.
6. CONFIDENCE IS HONEST. Report confidence in [0,1] per claim. If any \
claim's confidence is below 0.5, set review_status to "flagged".
6b. LEAKAGE NEEDS PROOF. If you set contains_poll, contains_prediction or \
contains_election_result to true, you MUST provide leakage.evidence_span \
(verbatim) AND leakage.explanation (why this content risks contaminating \
pre-election analysis). Unsupported leakage classification is forbidden.
7. COPY INPUT METADATA verbatim into the input section - do not re-derive \
publication dates or identifiers.
8. Output ONLY the JSON object. No markdown fences, no commentary.

The JSON Schema (contract llm-context-v1.1-2026-07-26):

{schema}"""


def build_user_message(meta: dict, title: str, body: str) -> str:
    """Per-article message: metadata block first (stable rendering,
    sorted keys), then the text. The extractor copies the metadata
    into the record's input section."""
    return (f"ARTICLE METADATA (copy into the record's input section):\n"
            f"{json.dumps(meta, sort_keys=True, ensure_ascii=False)}\n\n"
            f"TITLE: {title}\n\nBODY:\n{body}")


def parse_model_json(text: str) -> dict:
    """Parse the model's reply into a dict. Tolerates accidental
    markdown fences (rule 8 violations happen); raises ValueError on
    anything that is not a single JSON object."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    obj = json.loads(t)
    if not isinstance(obj, dict):
        raise ValueError("model output is not a JSON object")
    return obj
