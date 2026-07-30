"""Full-corpus context extraction: the three layers that survived the gate.

## What runs, and what does not

Three of the original eight layers are extracted. Every figure below is
validator-gated - `d4_findings_log.md` experiment 8 found that the earlier
kappas had been computed from records that merely parsed, and recomputing
them flipped two verdicts. The pre-gate numbers this docstring used to quote
are superseded, and the layers they justified are gone.

| Layer | Status | Basis |
|---|---|---|
| issues | **adopted** | 0.616 against the reviewer (n=53), 0.742 between arms - the only original layer clearing both rulers |
| stance (revised) | **adopted** | 0.741 / 0.848 after the redesign |
| framing (revised) | **adopted for 2 of 4 frames** | 0.705 and 0.635 between arms |
| credit_blame | **excluded** | 0.521 / 0.516 against the reviewer; a binary redesign scored worse still |
| consequence | **excluded** | 0.259 frozen; a redesign replicated at 0.598 on both arms against a 0.600 bar |
| temporal / horizon | **excluded** | failed the reviewer, the inter-model and a coarsened re-test |
| local_national_relevance | not in the D4 gate | never validated; not used |
| confidence_evidence | not in the D4 gate | never validated; not used |

The two rescue layers use their revised prompts, not the originals that
failed. That is the whole point of the redesign, and the outputs must be
read as three-level portrayal and four binary frames - not as the
five-level stance or sixteen-way framing the original schema described.

## Why the model is chosen per layer

Not once globally, and not on price. The three original layers require every
evidence span to appear character-for-character in the article, and on the
same 60 D4 articles Haiku satisfied that on 333 of 582 spans against Sonnet's
618 of 622 - which the validator turns into a third of the records being
discarded. So `issues` runs on Sonnet, verified again on the narrow tranche
at 327 of 327 spans.

The two revised layers dropped the span requirement in favour of a free-text
reason, and there the evidence points the other way: Haiku fails 0-2% on
format where Sonnet failed the framing rescue at 8.3%, and matches or beats
it on the judgement (stance 0.741 against 0.736). So they run on Haiku. The
framing choice is a genuine trade-off rather than a rout - Sonnet has better
human recall there, 0.583 against 0.491 - and it went to Haiku because an
8.3% format failure exceeds the health check's own 5% bar and would cost
roughly a hundred and thirty articles their frame data.

An earlier version of this docstring said the model was Haiku throughout, on
the strength of attribution at 0.600 and the Reform flag at 0.680. Neither
survived: attribution's 0.600 was ungated, and the Reform flag lives in the
excluded consequence layer and is now a deterministic pattern match instead.

## Why duplicates are not deduplicated first

The intended order was to extend the deduplication layer over the whole
corpus before paying to extract, so no duplicate is extracted twice. The
existing mapping makes that unnecessary: over 1,546 articles it found
1,538 independent articles and four duplicate families totalling eight
articles - a 0.5% duplicate rate, which is what independent searches
across different local outlets and the Guardian produce, as opposed to
syndicated wire copy. Extending the layer first would save under a dollar
and would require re-running the seven-step normalisation chain and the
eight-step dedup chain to produce v2 releases. The extraction cache keys
on article hash, so any article the later dedup marks as a duplicate has
simply been extracted once too often, at negligible cost, and its
duplicate flag still governs how it is counted in the features.

## What "all" means, and what it does not

`--tranche all` is every article with a **terminal include decision**, not
every article collected. The funnel, as it stands on 2026-07-30:

    19,020  article records collected
    11,787  with a resolvable publication date
     3,584  clearing every mechanical eligibility rule (E1-E3, E7, E9, E10)
     2,666  of those adjudicated on the four judgement rules (E4/E5/E6/E8)
     1,638  terminal include - what this runner extracts
       918  collected in the re-harvest and not yet adjudicated

The 918 are all local-arm articles from the four principal elections. They
cannot be extracted yet because E5-local is the one rule the frozen
classifier failed validation on, so each needs a human judgement or a
revised classifier that passes the same gate. At the 61% include rate the
adjudicated set shows, they should add roughly 560 articles, taking the
eventual corpus to about 2,200.

Extracting the 1,638 now and the rest later costs nothing extra: the batch
requests key on article content, so a second tranche re-extracts nothing.
What it does mean is that any feature table built from tonight's output is
built on 1,638 articles and must say so - the corpus is not final, and a
reader comparing article counts across documents needs to know which stage
of the funnel each figure comes from.

## Tranches

`narrow` extracts the four windows within thirty days of polling - the
highest-signal subset, small enough that a fault costs almost nothing to
find. It passed, and then turned out to be 89 of 1,638 articles drawn from
windows worth 5.6% of the corpus.

`far`, and any tranche whose name begins with it, draws from the two windows
that hold the other 94% - 180-to-91 days is 1,308 articles on its own, and
the production runner had never touched it. Each far draw excludes the
articles previous far draws used, so a fix designed from one draw's failures
is validated on articles it has not seen. Their manifests are separate files
for the same reason: overwriting `far` with `far2` would erase the record of
the gate that failed.

`all` is every remaining eligible article. It skips whatever earlier tranches
already extracted cleanly, so no article is submitted or paid for twice - the
tranches partition the corpus rather than overlapping it.

Usage:
    python3 -m src.llm_extraction.run_corpus_extraction submit narrow
    python3 -m src.llm_extraction.run_corpus_extraction collect narrow
    python3 -m src.llm_extraction.run_corpus_extraction submit far2
    python3 -m src.llm_extraction.run_corpus_extraction collect far2
    python3 -m src.llm_extraction.run_corpus_extraction submit all
    python3 -m src.llm_extraction.run_corpus_extraction collect all
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction import (credit_blame, electoral_consequence,
                               issue_classification)
from src.llm_extraction.frame_rescue import build_prompt as build_frame_prompt
from src.llm_extraction.stance_rescue import (build_prompt as build_stance_prompt,
                                              parties_present)
from src.llm_extraction.run_d4_validation import ARMS
from src.llm_extraction.run_pilot import load_articles
from src.news_modelling.window_schemes import assign

csv.field_size_limit(10_000_000)

# Model per layer, on measured compliance rather than one global choice.
#
# The narrow tranche exposed something the D4 gate could not see. D4 scored
# field agreement - kappa on primary_issue, attribution_type and the rest -
# computed from parsed records, and a record whose evidence span cannot be
# found still has a perfectly readable primary_issue. So the kappa
# comparison was blind to whether the quote was real.
#
# On the same 60 D4 articles with the same prompts, verbatim-span failures
# were: issues 35/60 for Haiku against 7/60 for Sonnet, credit_blame 33 vs
# 3, consequence 31 vs 5. That is not an audit blemish. The validators
# reject the whole record, so on Haiku more than half the corpus would
# carry no issue, attribution or consequence data at all.
#
# The two revised layers are the opposite case: they deliberately dropped
# the verbatim requirement in favour of a free-text reason, and Haiku fails
# 1-2% on them while scoring better than Sonnet on the judgement itself
# (0.729 against 0.641 on issues, 0.600 against 0.531 on attribution).
#
# So each layer runs on the model that can actually satisfy its contract.
# Mixed cost is about $90 over 1,638 articles against $56 all-Haiku - and
# the $56 version would discard half its own output.
LAYER_ARMS = {
    "issues": "sonnet",
    "credit_blame": "sonnet",
    "consequence": "sonnet",
    "stance_revised": "haiku",
    "framing_revised": "haiku",
}
# v1.2 adds one rule to the issues prompt and changes nothing else. The far
# gate failed on that layer at 5.6% schema failure against a 5% bar, and three
# of its five failures were the model volunteering a property the schema
# forbids - secondary_issues_note, issue_other_label, and political_relevance
# at a level the schema does not declare it. Rule 7 now names the two fields
# the schema provides for anything that needs saying, and states what an
# undeclared key costs. The schema contract itself is untouched, so records
# extracted under v1.1 and v1.2 are comparable; the manifest records which
# tranche used which, because a formatting instruction added mid-run is a
# version split a reader is entitled to see.
EXTRACTION_VERSION = "corpus-extraction-v1.3-2026-07-30"

RECORDS = Path("data/raw/news/records")
TEXT = Path("data/raw/news/text")
DECISIONS = Path("news_collection/corpus_eligibility_decisions.csv")
PILOT_SHEET = Path("news_collection/manual_review_sample.csv")
VALIDATION_SHEET = Path("news_collection/llm_validation_sample.csv")
EFFECTIVE_DATES = Path("news_collection/effective_dates_v2.csv")

POLLING = {
    "SCC-2013-05": date(2013, 5, 2),
    "SCC-2017-05": date(2017, 5, 4),
    "SCC-2021-05": date(2021, 5, 6),
    "ESWS-2026-05": date(2026, 5, 7),
}

# Windows within thirty days of polling: the narrow tranche.
NARROW_WINDOWS = {"final_72_hours", "7_to_4_days", "14_to_8_days",
                  "30_to_15_days"}

# The far windows, and why they get a gate of their own.
#
# The narrow tranche was chosen for being closest to polling day, which made
# it the right place to look for extraction faults that matter most. It is
# also 89 of 1,638 articles - 5.4% of the corpus - and every one of them sits
# in a window that together accounts for 5.6%. The 180-to-91-day window alone
# is 1,308 articles, 79.9%, and the production runner had never touched it.
#
# The failure modes the health check looks for are mostly prompt-driven rather
# than content-driven, and the D4 sample that validated these prompts was
# stratified by election and arm rather than by window, so it did contain far
# articles. But one figure will genuinely differ: an article five months
# before polling is far less likely to carry an election frame or a codeable
# political issue, so empty-record rates should rise. A zero is data rather
# than a fault, which is exactly why it needs measuring rather than assuming -
# the recalibrated empty-rate check is the only threshold that could trip on
# it, and it should trip here if anywhere.
#
# Splitting the run costs nothing but a batch cycle. These 89 articles belong
# to the 1,638 either way, and `all` now skips whatever has already been
# extracted, so the total paid is unchanged.
FAR_WINDOWS = {"180_to_91_days", "90_to_31_days"}
FAR_TRANCHE_SIZE = 89          # matched to the narrow tranche, for comparison

# The three original layers keep their frozen prompts and validators. The
# two rescue layers carry no validator here: their revised outputs are a
# small closed vocabulary, checked inline at collection time against the
# question that was asked, which is stricter than a schema check would be.
ORIGINAL_LAYERS = {
    "issues": (issue_classification.build_issue_prompt,
               issue_classification.validate_issue_record, 8000),
    "credit_blame": (credit_blame.build_cb_prompt,
                     credit_blame.validate_cb_record, 12000),
    "consequence": (electoral_consequence.build_ec_prompt,
                    electoral_consequence.validate_ec_record, 12000),
}

# Layers the full corpus does not pay for, and why.
#
# Both failed the pre-registered gate against the human gold labels on the
# arm with a near-complete sample - Sonnet, whose validator rejected 3 of 60
# credit_blame records and 5 of 60 consequence records. So this is not a
# small-n artefact, and it is not the span problem that sent these layers to
# Sonnet in the first place.
#
#   attribution_type       n=57  kappa 0.521  AC1 0.647  max marginal 0.579
#   consequence_direction  n=55  kappa 0.259  AC1 0.449  max marginal 0.727
#
# Neither qualifies for the pre-registered fallback route: it needs a
# marginal at or above 0.90 to trigger, and both are well below, so the
# kappa paradox does not excuse the low figures. The pre-stated coarsening
# re-test did not rescue either.
#
# Kappa is symmetric and does not say which side is wrong, and these six
# content fields - unlike the eligibility layer, which was blind re-coded at
# kappa 0.92-1.00 - have no human test-retest estimate to bound the human
# side. So "the model is wrong" is not a claim this evidence supports. What
# it does support is that the extraction cannot be shown to reproduce the
# construct, and a feature whose validity cannot be demonstrated either way
# fails the supervisor's constraint of being able to explain each decision.
#
# The two layers fail differently, which matters for what happens next.
# Consequence is a threshold disagreement concentrated in one cell: of 26
# disagreements, 18 are the human recording no consequence where the model
# found potential damage, and the model chose potential_damage on 30 of 55
# articles against the human's 40 of 55 "none". The models agree with each
# other far better than with the human there (0.587 against 0.259/0.136),
# which is the signature of a definitional gap rather than noise, and is the
# shape the stance layer had before its rescue took it from 0.32 to 0.85.
# Attribution is the opposite: disagreements scatter across cells, the
# marginals broadly match (human blame 33/57, model 29/57), and inter-model
# agreement is itself only 0.602 - no single definitional gap to close.
#
# So consequence is excluded pending one prompt-level rescue attempt scored
# against the human presence labels already recorded, and attribution is
# excluded outright. Removing them from the full run also drops two of the
# three Sonnet layers, which is the larger part of the corpus spend.
# Both rescues have now reported, so these reasons are final rather than
# provisional. Each layer had two attempts, the same as stance and framing.
EXCLUDED_LAYERS = {
    "credit_blame": ("fails D4 gate at kappa 0.521 (n=57); a binary redesign "
                     "scored 0.272 on blame, worse than the layer it replaced"),
    "consequence": ("fails D4 gate at kappa 0.259 (n=55); a redesign "
                    "replicated at 0.598 on both arms against a 0.600 bar"),
}

STANCE_DECISIONS = ("unfavourable", "favourable", "neither")
FRAME_KEYS = ("incumbent_judgement", "challenger_emergence",
              "voter_discontent", "local_impact")


def eligible_articles() -> dict[str, dict]:
    """Every article with a terminal `include` decision.

    Three sources, because eligibility was settled in three passes: the
    168-article human pilot, the 128-article validation sample, and the
    2,370-article remaining corpus assembled from the frozen-v2 and human
    streams. An article missing from the normalised text layer falls back
    to its raw extracted text, and that fallback is recorded per tranche
    rather than left implicit - the layer is provisional and does not
    cover the re-harvest.
    """
    include: dict[str, dict] = {}
    for r in csv.DictReader(DECISIONS.open()):
        if r["overall_decision"] == "include":
            include[r["article_id"]] = {"election_id": r["election_id"],
                                        "arm": r["arm"]}
    for sheet in (PILOT_SHEET, VALIDATION_SHEET):
        for r in csv.DictReader(sheet.open(encoding="utf-8-sig")):
            if r.get("final_reviewed_decision") == "include":
                include.setdefault(r["article_id"],
                                   {"election_id": r["election_id"],
                                    "arm": r["arm"]})
    return include


def load_tranche(tranche: str, only_ids: set[str] | None = None
                 ) -> tuple[dict[str, dict], list[str], dict]:
    """Articles for this tranche, the raw-text fallback ids, and a census.

    ``only_ids`` returns exactly those articles and applies no sampling or
    exclusion. Anything reading a tranche *after* it ran must use it, because
    the tranche rules are not stable over time: the far sampler excludes
    articles previous far draws used, so re-deriving `far2` after `far2` has
    been collected yields a third, different sample. The health check did that
    and scored far2's evidence spans against 89 articles far2 never saw,
    reporting 0 of 314 verified. The figure was an artefact of the checker, not
    a property of the extraction.
    """
    include = eligible_articles()
    dates = {r["article_id"]: r for r in csv.DictReader(EFFECTIVE_DATES.open())}
    normalised = load_articles()

    out: dict[str, dict] = {}
    fallback: list[str] = []
    census = {"eligible": len(include), "no_effective_date": 0,
              "not_a_principal_election": 0, "outside_all_windows": 0,
              "by_window": {}}

    for aid, meta in include.items():
        if only_ids is not None and aid not in only_ids:
            continue
        d = dates.get(aid)
        if not d or not d.get("effective_date"):
            census["no_effective_date"] += 1
            continue
        election = d["election_id"]
        if election not in POLLING:
            # By-elections are out of the news layer's scope under the
            # 2026-07-30 decision: their search coverage is 33% overall
            # and below 12% for nine of them, so features built from them
            # would be zeros meaning "not searched". Counted, not silent.
            census["not_a_principal_election"] += 1
            continue
        try:
            published = date.fromisoformat(d["effective_date"][:10])
        except ValueError:
            census["no_effective_date"] += 1
            continue
        placed = assign(published, POLLING[election],
                        scheme="original_email_180d")
        if placed.window is None:
            census["outside_all_windows"] += 1
            continue
        census["by_window"][placed.window] = (
            census["by_window"].get(placed.window, 0) + 1)
        if tranche == "narrow" and placed.window not in NARROW_WINDOWS:
            continue
        if tranche.startswith("far") and placed.window not in FAR_WINDOWS:
            continue

        if aid in normalised:
            article = dict(normalised[aid])
        else:
            # Not in the provisional normalised layer, so fall back to the
            # raw extracted text - unless that is missing too, which
            # happens for articles whose retrieval captured metadata but
            # no body. Those are counted and skipped: an article with no
            # text cannot be extracted, and crashing on one would take the
            # whole tranche down for a gap that belongs in the census.
            text_path = TEXT / f"{aid}.txt"
            if not text_path.exists():
                census["no_extracted_text"] = (
                    census.get("no_extracted_text", 0) + 1)
                census.setdefault("no_extracted_text_ids", []).append(aid)
                continue
            rec = json.loads((RECORDS / f"{aid}.json").read_text(
                encoding="utf-8", errors="replace"))
            article = {
                "article_id": aid, "canonical_article_id": aid,
                "election_id": election, "arm": meta["arm"],
                "title": rec["identity"].get("headline") or "",
                "body": text_path.read_text(
                    encoding="utf-8", errors="replace"),
                "source": rec["source_id"],
                "publication_datetime": d["effective_date"],
                "url": rec["identity"].get("canonical_url") or "",
            }
            fallback.append(aid)
        article["window"] = placed.window
        out[aid] = article

    if tranche.startswith("far") and only_ids is None:
        # A reproducible sample, proportional to each far window's share, so
        # the tranche is not silently all one window. Ordered by
        # sha256(article_id) for the same reason the D4 sampler was: it is
        # deterministic, independent of the corpus's insertion order, and
        # reproducible from the ids alone without storing a seed.
        # Exclude anything a previous far draw already used. A fix designed by
        # looking at how 89 articles failed cannot be validated on those same
        # 89: passing might mean only that the specific failures were patched.
        # So each far draw is fresh, and the frame shrinks by what has been
        # spent. 1,543 articles in these two windows leaves plenty of room.
        used = far_articles_already_drawn()
        if used:
            census["far_previously_drawn"] = len(used)
            out = {a: v for a, v in out.items() if a not in used}
        by_window: dict[str, list[str]] = {}
        for aid, art in out.items():
            by_window.setdefault(art["window"], []).append(aid)
        total = sum(len(v) for v in by_window.values())
        keep: set[str] = set()
        for window, ids in sorted(by_window.items()):
            quota = max(1, round(FAR_TRANCHE_SIZE * len(ids) / total))
            keep.update(sorted(ids, key=lambda a: hashlib.sha256(
                a.encode()).hexdigest())[:quota])
        census["far_sample"] = {
            "drawn": len(keep), "target": FAR_TRANCHE_SIZE,
            "per_window": {w: sum(1 for a in keep if out[a]["window"] == w)
                           for w in sorted(by_window)},
            "frame": {w: len(v) for w, v in sorted(by_window.items())}}
        out = {a: v for a, v in out.items() if a in keep}
        # The fallback list was built while walking the whole far frame, so
        # it has to be narrowed to the sample as well. Left unfiltered it
        # recorded 95 fallback ids for an 89-article tranche, which is not a
        # cosmetic problem: the manifest is what a reader would use to check
        # how much of a tranche came from provisional text.
        fallback = [a for a in fallback if a in keep]

    if tranche == "all" and only_ids is None:
        # Skip whatever earlier tranches already extracted. The docstring has
        # claimed since this module was written that the full run reuses those
        # extractions rather than repeating them; until now it did not, and
        # `all` would have re-submitted and re-paid for every gated article.
        done = already_extracted()
        if done:
            census["skipped_already_extracted"] = len(
                [a for a in out if a in done])
            out = {a: v for a, v in out.items() if a not in done}

    return out, fallback, census


def far_articles_already_drawn() -> set[str]:
    """Every article a previous far draw used, whether it succeeded or not.

    Read from the far batch manifests rather than the outputs, because an
    article that was submitted and failed has still been seen by the
    experiment: reusing it to validate a fix designed from its failure is the
    same error as reusing a passing one.
    """
    used: set[str] = set()
    for path in sorted(Path("llm_context").glob(
            "corpus_extraction_outputs_far*.json")):
        payload = json.loads(path.read_text())
        for rows in payload.get("layers", {}).values():
            used |= {r["article_id"] for r in rows}
    return used


def already_extracted() -> set[str]:
    """Article ids that a previous tranche already extracted successfully.

    Read from the outputs files rather than tracked separately, so the source
    of truth is the extraction itself. An article counts as done only if every
    layer being run produced a record the validator accepted - a partial
    extraction is not reusable, and re-running one article is cheaper than
    reasoning about which layer is missing.
    """
    live = [l for l in LAYER_ARMS if l not in EXCLUDED_LAYERS]
    done: set[str] = set()
    for path in sorted(Path("llm_context").glob(
            "corpus_extraction_outputs_*.json")):
        payload = json.loads(path.read_text())
        layers = payload.get("layers", {})
        if not all(l in layers for l in live):
            # A tranche collected before a layer existed, or one whose
            # collection stopped early, cannot certify an article as done.
            continue
        seen: dict[str, list[bool]] = {}
        for layer in live:
            for r in layers[layer]:
                accepted = (r.get("record") is not None
                            and not r.get("validation_errors"))
                seen.setdefault(r["article_id"], []).append(accepted)
        # Complete within this file: every layer that asked about the article
        # accepted its answer. Membership varies by layer on purpose -
        # stance_revised is only asked of articles naming a study party, so
        # requiring its presence would leave those articles permanently
        # unfinishable. Intersect across layers within a file; union across
        # files, because each file is a different tranche of articles.
        done |= {aid for aid, flags in seen.items() if all(flags)}
    return done


def _user_message(article: dict) -> str:
    meta = {k: article.get(k) for k in
            ("article_id", "canonical_article_id", "election_id", "arm",
             "publication_datetime", "source", "url")}
    return (f"ARTICLE METADATA (copy into the record's input section):\n"
            f"{json.dumps(meta, sort_keys=True, ensure_ascii=False)}\n\n"
            f"TITLE: {article.get('title') or ''}\n\n"
            f"BODY:\n{article.get('body') or ''}")


def _paths(tranche: str) -> tuple[Path, Path]:
    return (Path(f"llm_context/corpus_extraction_batches_{tranche}.json"),
            Path(f"llm_context/corpus_extraction_outputs_{tranche}.json"))


def _repair_flag_only(record: dict, errors: list[str], validate,
                      article: dict) -> tuple[list[str], list[str]]:
    """Set the review flag the model forgot, rather than binning the record.

    Every original layer's contract says that if any confidence falls below
    0.5 the record must carry `review_status: "flagged"`. Six of the nine
    issues records the narrow tranche lost failed on that rule alone -
    confidence 0.4 or 0.45, correctly reported, and the box simply not
    ticked. Their issue codes were sound and every evidence span verified.

    The flag is derivable from the confidence the model already gave, so a
    validator that discards the record for failing to derive it is throwing
    away 6.7% of a corpus over bookkeeping. This repairs the field, re-runs
    the same validator, and keeps the record only if nothing else is wrong -
    a record failing S2 *and* a span check is still rejected.

    The repair is recorded per article rather than applied silently, and its
    effect on the validated figures was measured before it was adopted: on
    the D4 sample it admits one further Sonnet record and moves the issues
    kappa from 0.616 to 0.622, changing no verdict, and admits none on Haiku.
    The prompt's contract is not edited - the model is still asked to flag,
    the validator still reports when it did not, and the repair is visible.
    """
    flag_only = [e for e in errors if "not flagged" in e]
    if not flag_only or len(flag_only) != len(errors):
        return errors, []
    sentinel = object()
    original = record.get("review_status", sentinel)
    record["review_status"] = "flagged"
    recheck = validate(record, article.get("body") or "",
                       article.get("title") or "")
    if recheck:
        # Restore rather than delete: the model may have written a different
        # value there, and a rejected record should leave the transcript
        # exactly as the model produced it.
        if original is sentinel:
            record.pop("review_status", None)
        else:
            record["review_status"] = original
        return errors, []
    return [], [f"review_status set to flagged by the collector: {flag_only}"]


def _arm_for(layer: str) -> tuple[dict, str]:
    arm = ARMS[LAYER_ARMS[layer]]
    return arm, (arm["model"] or "claude-sonnet-5")


def cmd_submit(tranche: str) -> None:
    arts, fallback, census = load_tranche(tranche)
    if not arts:
        print(f"tranche {tranche}: no articles - nothing submitted")
        return
    client = anthropic.Anthropic()
    batches: dict[str, str] = {}

    for layer, (build, _validate, max_tokens) in ORIGINAL_LAYERS.items():
        if layer in EXCLUDED_LAYERS:
            print(f"{layer}: NOT submitted - {EXCLUDED_LAYERS[layer]}")
            continue
        arm, model = _arm_for(layer)
        system = [{"type": "text", "text": build(),
                   "cache_control": {"type": "ephemeral"}}]
        requests = [Request(
            custom_id=aid,
            params=MessageCreateParamsNonStreaming(
                model=model, max_tokens=max_tokens, thinking=arm["thinking"],
                system=system,
                messages=[{"role": "user", "content": _user_message(a)}]))
            for aid, a in sorted(arts.items())]
        b = client.messages.batches.create(requests=requests)
        batches[layer] = b.id
        print(f"{layer}: {b.id} ({len(requests)} articles, {model})")

    # Stance asks only about parties the article names, decided in code so
    # the question set is reproducible; an article naming none is a
    # legitimate zero and is recorded rather than dropped silently.
    arm, model = _arm_for("stance_revised")
    stance_sets, stance_requests = {}, []
    for aid, a in sorted(arts.items()):
        parties = parties_present(a.get("title") or "", a.get("body") or "")
        if not parties:
            continue
        stance_sets[aid] = parties
        stance_requests.append(Request(
            custom_id=aid,
            params=MessageCreateParamsNonStreaming(
                model=model, max_tokens=6000, thinking=arm["thinking"],
                system=[{"type": "text", "text": build_stance_prompt(parties),
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": _user_message(a)}])))
    if stance_requests:
        b = client.messages.batches.create(requests=stance_requests)
        batches["stance_revised"] = b.id
        print(f"stance_revised: {b.id} ({len(stance_requests)} articles, "
              f"{len(arts) - len(stance_requests)} name no study party)")

    arm, model = _arm_for("framing_revised")
    frame_system = [{"type": "text", "text": build_frame_prompt(),
                     "cache_control": {"type": "ephemeral"}}]
    b = client.messages.batches.create(requests=[Request(
        custom_id=aid,
        params=MessageCreateParamsNonStreaming(
            model=model, max_tokens=6000, thinking=arm["thinking"],
            system=frame_system,
            messages=[{"role": "user", "content": _user_message(a)}]))
        for aid, a in sorted(arts.items())])
    batches["framing_revised"] = b.id
    print(f"framing_revised: {b.id} ({len(arts)} articles)")

    batch_path, _ = _paths(tranche)
    batch_path.write_text(json.dumps({
        "version": EXTRACTION_VERSION, "tranche": tranche,
        "layer_arms": {k: v for k, v in LAYER_ARMS.items()
                       if k not in EXCLUDED_LAYERS},
        "layer_models": {k: (ARMS[v]["model"] or "claude-sonnet-5")
                         for k, v in LAYER_ARMS.items()
                         if k not in EXCLUDED_LAYERS},
        "excluded_layers": EXCLUDED_LAYERS,
        # The prompt hash is recorded at SUBMIT time, not computed at collect
        # time, and the difference matters. The prompt can change between the
        # two - it did, three times on the issues layer in one afternoon - and
        # a hash computed at collect would then label records with a prompt
        # they were never produced from. That is worse than no hash, because it
        # looks like provenance. `collect` reads this and verifies the current
        # prompt still matches before it stamps or retries anything.
        "layer_prompt_sha256": _layer_prompt_fingerprints(),
        "articles": len(arts), "raw_text_fallback_ids": fallback,
        "census": census, "stance_question_sets": stance_sets,
        "layers": batches,
        "windows_in_tranche": sorted({a["window"] for a in arts.values()}),
    }, indent=2))
    print(f"\n-> {batch_path}")
    print(f"{len(arts)} articles, {len(batches)} layers, "
          f"{len(fallback)} on raw-text fallback")


# One retry, and only one. Fixed here rather than passed in, because a retry
# count chosen per run is a dial that can be turned until a gate passes, and
# this one must not be.
MAX_ATTEMPTS = 2


def _prompt_spec(layer: str, meta: dict):
    """How to prompt one layer: (system-text builder, max_tokens).

    Defined in one place because three call sites need it - the batch
    submission, the synchronous runner, and the retry - and if any of them
    built the prompt differently the records they produced would not be
    comparable. The builder takes an article id because `stance_revised` asks
    only about the parties an article names, so its prompt is per-article; the
    other two layers ignore the argument and return a constant.
    """
    if layer in ORIGINAL_LAYERS:
        build, _validate, max_tokens = ORIGINAL_LAYERS[layer]
        return (lambda _aid: build()), max_tokens
    if layer == "framing_revised":
        return (lambda _aid: build_frame_prompt()), 6000
    if layer == "stance_revised":
        sets = meta.get("stance_question_sets", {})
        return (lambda aid: build_stance_prompt(sets[aid])), 6000
    raise ValueError(f"no prompt spec for layer {layer}")


# A fixed party list used only to render the stance template for
# fingerprinting. stance_revised asks about the parties an article names, so
# its prompt differs per article and a single hash of one article's prompt
# would be an accident of which article came first. Rendering the template
# against a constant instead makes the fingerprint a property of the template:
# it changes when the template changes and not otherwise.
FINGERPRINT_PARTY_SET = ("conservative", "reform_uk")


def _layer_prompt_fingerprints() -> dict[str, str]:
    """One hash per live layer, identifying the prompt the run was submitted on.

    For issues and framing_revised the prompt is constant, so the hash is the
    prompt. For stance_revised it is the template rendered against
    FINGERPRINT_PARTY_SET - see above.
    """
    out = {}
    for layer in LAYER_ARMS:
        if layer in EXCLUDED_LAYERS:
            continue
        if layer == "stance_revised":
            text = build_stance_prompt(list(FINGERPRINT_PARTY_SET))
        else:
            build, _mt = _prompt_spec(layer, {})
            text = build(None)
        out[layer] = _prompt_sha256(text)
    return out


def _prompt_sha256(text: str) -> str:
    """Hash of the exact prompt bytes a record was produced from.

    Stamped on every record rather than only in the file's metadata, because
    the whole point is to survive a merge. The corpus already holds issues
    records from three prompt versions - 170 from v1.1, 78 from v1.2, 89 from
    v1.3 - and until now the version was recorded only at the top of each
    tranche file, so a feature table assembled from several tranches would
    have lost it. A hash rather than a version string because a string can be
    forgotten when the prompt changes, and a hash cannot.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _retry_failures(layer, rows, stats, arts, meta, client, model, arm):
    """Give each failed record one more attempt at the same validator.

    ## Why this is a retry and not a relaxation

    Measured on the far3 tranche: nine of 89 issues records failed, and
    re-running those nine unchanged produced nine passes. Every one returned
    `stop_reason == "end_turn"` with 696 to 3,642 output tokens against an
    8,000 budget, so truncation was not the cause and a larger budget would
    have changed nothing. The failures were variance in a structured-output
    task, not a defect in the prompt, the model, or the schema.

    So nothing here changes what a record must satisfy. The prompt bytes, the
    model, the thinking configuration and the validator are identical on the
    second attempt; the record simply gets one more draw. Three earlier
    attempts to fix this by editing the prompt were chasing noise, and one of
    them made the layer worse by naming a field that does not exist.

    The precedent is in this project already: the eligibility batch's state
    file records two `retry_batch_ids`, and that layer's validation was
    accepted on the same basis.

    ## Why not retrying is the biased option

    Failure correlates with article length - 6 of 24 articles over 8,000
    characters failed against 3 of 62 at or below it, 25% against 4.8%.
    Discarding failures therefore keeps a sample skewed towards short
    articles, which is a bias introduced by inaction rather than avoided by it.

    ## What this does select, and what the report must say

    The record kept is the first attempt that satisfied the validator, which
    is a selection over attempts rather than a random draw. The validator
    checks that evidence spans appear verbatim, so attempts with fewer or
    shorter quotations are marginally likelier to pass - meaning retained
    records may under-represent long or paraphrase-prone quotation. Every
    retry is recorded per article (`attempts`), so the count is reportable and
    the affected records are identifiable rather than invisible.
    """
    failed = [r for r in rows
              if r.get("record") is None or r.get("validation_errors")]
    if not failed:
        return rows, stats, 0, 0

    print(f"  {layer}: retrying {len(failed)} failed records "
          f"(attempt 2 of {MAX_ATTEMPTS}, same prompt and validator)",
          flush=True)
    build_system, max_tokens = _prompt_spec(layer, meta)
    by_id = {r["article_id"]: r for r in rows}
    usage_in = usage_out = 0
    recovered = 0

    for r in failed:
        aid = r["article_id"]
        r["attempts"] = 1
        r["first_attempt_errors"] = r.get("validation_errors")
        if aid not in arts:
            # An article the tranche no longer resolves cannot be retried; the
            # record stays failed rather than being quietly dropped.
            r["retry_note"] = "article not in tranche"
            continue
        try:
            system_text = build_system(aid)
            msg = client.messages.create(
                model=model, max_tokens=max_tokens, thinking=arm["thinking"],
                system=[{"type": "text", "text": system_text,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user",
                           "content": _user_message(arts[aid])}])
            usage_in += msg.usage.input_tokens
            usage_out += msg.usage.output_tokens
            text = "".join(b.text for b in msg.content if b.type == "text")
            parsed = json.loads(text.strip().removeprefix("```json")
                                .removeprefix("```").removesuffix("```"))
        except Exception as e:
            r["attempts"] = MAX_ATTEMPTS
            r["retry_note"] = f"retry failed: {type(e).__name__}"
            continue

        errors, repairs = _validate_record(layer, parsed, aid, arts, meta)
        r["attempts"] = MAX_ATTEMPTS
        r["stop_reason"] = msg.stop_reason
        if errors:
            # The second attempt is not preferred over the first: if it also
            # fails, the record stays failed and both error sets are kept.
            r["retry_errors"] = errors
            continue
        r["record"] = parsed
        r["validation_errors"] = []
        # The manifest's fingerprint, not a hash of this article's rendered
        # prompt: for stance_revised the rendered prompt differs per article, so
        # hashing it here would label retried records differently from
        # first-attempt ones and make the two look like different prompts.
        r["prompt_sha256"] = ((meta.get("layer_prompt_sha256") or {}).get(layer)
                              or _prompt_sha256(system_text))
        if repairs:
            r["repairs"] = repairs
        recovered += 1

    stats["ok"] += recovered
    stats["failed"] -= recovered
    stats["recovered_on_retry"] = recovered
    print(f"  {layer}: {recovered}/{len(failed)} recovered on the second "
          f"attempt", flush=True)
    return [by_id[r["article_id"]] for r in rows], stats, usage_in, usage_out


def _validate_record(layer: str, parsed: dict, aid: str, arts: dict,
                     meta: dict) -> tuple[list[str], list[str]]:
    """Validate one parsed record, returning (errors, repairs).

    Factored out so the batch path and the synchronous path apply the *same*
    checks. If they diverged, records extracted by the two transports would not
    be comparable, and the tranche gate compares them directly.
    """
    errors: list[str] = []
    repairs: list[str] = []
    if layer in ORIGINAL_LAYERS:
        _b, validate, _m = ORIGINAL_LAYERS[layer]
        article = arts.get(aid, {})
        errors = validate(parsed, article.get("body") or "",
                          article.get("title") or "")
        errors, repairs = _repair_flag_only(parsed, errors, validate, article)
    elif layer == "stance_revised":
        asked = set(meta["stance_question_sets"].get(aid, []))
        judged = {j["party"]: j.get("portrayal")
                  for j in parsed.get("judgements", [])}
        if set(judged) != asked:
            errors.append(f"answered {sorted(judged)}, asked {sorted(asked)}")
        bad = {p: v for p, v in judged.items()
               if v not in STANCE_DECISIONS}
        if bad:
            errors.append(f"outside vocabulary: {bad}")
    elif layer == "framing_revised":
        judged = {f["frame"]: f.get("present")
                  for f in parsed.get("frames", [])}
        if set(judged) != set(FRAME_KEYS):
            errors.append(f"answered {sorted(judged)}, "
                          f"asked {sorted(FRAME_KEYS)}")
    return errors, repairs


def _sync_layer(layer: str, arts: dict, meta: dict) -> tuple[list[dict], dict]:
    """Run one layer article-by-article on the standard API instead of Batches.

    Why this exists. The Batches API trades latency for half the price, and its
    only guarantee is 24 hours. On 2026-07-30 the Haiku batches returned in 2 to
    10 minutes while Sonnet batches ran 15 to 90, with two sitting at zero of 89
    complete for over an hour - one of which was cancelled and one of which held
    up a gate three times over. Standard-rate requests cost twice as much and
    return in seconds, which for an 89-article gate is a good trade and for the
    1,400-article corpus run is not.

    Everything the model sees is identical to the batch path: same prompt bytes,
    same model, same thinking configuration, same max_tokens, built from the same
    manifest the batch was submitted from. Only the transport differs, so a
    record produced here is comparable to one produced there. The rows this
    returns have the same shape, and are validated by the same
    `_validate_record`, so the health check cannot tell - and does not need to
    tell - which transport produced a given article.

    The per-article loop is deliberately serial. Extraction is not latency
    critical at this size, a serial loop cannot trip a rate limit, and a failure
    stops at one article instead of an in-flight fan-out.
    """
    client = anthropic.Anthropic()
    arm, model = _arm_for(layer)
    rows: list[dict] = []
    stats = {"ok": 0, "failed": 0}
    usage_in = usage_out = 0

    # One shared prompt builder, so the synchronous path, the batch path and
    # the retry cannot drift apart. stance_revised used to raise here because
    # its prompt is per-article; the builder handles that, so every layer can
    # now run on either transport.
    build_system, max_tokens = _prompt_spec(layer, meta)
    targets = sorted(arts if layer != "stance_revised"
                     else meta.get("stance_question_sets", {}))

    for i, aid in enumerate(targets, start=1):
        a = arts[aid]
        entry: dict = {"article_id": aid, "batch_result": "sync"}
        try:
            system_text = build_system(aid)
            msg = client.messages.create(
                model=model, max_tokens=max_tokens, thinking=arm["thinking"],
                system=[{"type": "text", "text": system_text,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": _user_message(a)}])
            usage_in += msg.usage.input_tokens
            usage_out += msg.usage.output_tokens
            text = "".join(b.text for b in msg.content if b.type == "text")
            parsed = json.loads(text.strip().removeprefix("```json")
                                .removeprefix("```").removesuffix("```"))
        except json.JSONDecodeError as e:
            entry["record"] = None
            entry["validation_errors"] = [f"unparseable: {e}"]
            stats["failed"] += 1
            rows.append(entry)
            continue
        except Exception as e:                       # transport or API error
            # Recorded as a failure rather than retried into a different
            # answer, which is the same rule the batch path follows.
            entry["record"] = None
            entry["validation_errors"] = [f"api: {type(e).__name__}: {e}"]
            stats["failed"] += 1
            rows.append(entry)
            continue

        errors, repairs = _validate_record(layer, parsed, aid, arts, meta)
        entry["record"] = parsed
        entry["validation_errors"] = errors
        entry["prompt_sha256"] = _prompt_sha256(system_text)
        if repairs:
            entry["repairs"] = repairs
            stats["repaired"] = stats.get("repaired", 0) + 1
        stats["ok" if not errors else "failed"] += 1
        rows.append(entry)
        if i % 20 == 0:
            print(f"  {layer}: {i}/{len(targets)}", flush=True)

    rows, stats, ru_in, ru_out = _retry_failures(
        layer, rows, stats, arts, meta, client, model, arm)
    usage_in += ru_in
    usage_out += ru_out

    print(f"{layer} (sync, standard rate): {stats}")
    return rows, {"input_tokens": usage_in, "output_tokens": usage_out,
                  "model": model, "transport": "standard_api"}


def cmd_collect(tranche: str, sync_layers: set[str] | None = None) -> None:
    batch_path, out_path = _paths(tranche)
    meta = json.loads(batch_path.read_text())
    client = anthropic.Anthropic()
    arts, _fallback, _census = load_tranche(tranche)

    # Wait only for the layers the gate depends on. An excluded layer's batch
    # was already submitted and paid for, and its results stay retrievable for
    # 29 days, so there is nothing to lose by collecting it on a later pass -
    # but waiting for one blocks the gate, and behind the gate sits the
    # full-corpus run. The first version of this loop waited for every layer
    # and left the chain stalled 68 minutes on credit_blame, a layer whose
    # output is not going to be used.
    # A layer named in sync_layers is run here on the standard API instead of
    # being waited for. Its batch has been cancelled, so waiting would only
    # yield 89 canceled results and fail the gate for a transport problem.
    sync_layers = sync_layers or set()
    required = {l: b for l, b in meta["layers"].items()
                if l not in EXCLUDED_LAYERS and l not in sync_layers}
    pending = {l: b for l, b in meta["layers"].items()
               if l not in sync_layers}
    while pending:
        for layer, bid in list(pending.items()):
            b = client.messages.batches.retrieve(bid)
            print(f"{layer}: {b.processing_status} {b.request_counts}")
            if b.processing_status == "ended":
                pending.pop(layer)
        if not any(l in pending for l in required):
            if pending:
                print(f"proceeding without {sorted(pending)} - excluded from "
                      f"the gate; collect again later to record them")
            break
        time.sleep(120)

    ended = {l: b for l, b in meta["layers"].items()
             if l not in pending and l not in sync_layers}
    results: dict = {"version": EXTRACTION_VERSION, "tranche": tranche,
                     "layer_models": meta.get("layer_models", {}),
                     "layers_not_collected": sorted(pending),
                     "layers": {}}
    usage_in = usage_out = 0
    per_layer_usage: dict[str, dict] = {}

    for layer, bid in ended.items():
        rows, stats = [], {"ok": 0, "failed": 0}
        lin = lout = 0
        # The hash comes from the manifest, written at submit time, not from
        # the prompt as it stands now. If the prompt has changed since
        # submission the two differ, and that is reported rather than papered
        # over: the records came from the submitted prompt, and a retry on the
        # current one would not be the "same prompt, second attempt" it claims
        # to be.
        build_system, _mt = _prompt_spec(layer, meta)
        submitted_sha = (meta.get("layer_prompt_sha256") or {}).get(layer)
        current_sha = _layer_prompt_fingerprints().get(layer)
        prompt_drifted = bool(submitted_sha and current_sha
                              and submitted_sha != current_sha)
        if prompt_drifted:
            print(f"  {layer}: WARNING prompt changed since submission "
                  f"({submitted_sha[:12]} -> {current_sha[:12]}); records keep "
                  f"the submitted hash and failures are NOT retried",
                  flush=True)
        for result in client.messages.batches.results(bid):
            aid = result.custom_id
            entry: dict = {"article_id": aid,
                           "batch_result": result.result.type}
            if result.result.type != "succeeded":
                entry["record"] = None
                entry["validation_errors"] = [f"batch: {result.result.type}"]
                stats["failed"] += 1
                rows.append(entry)
                continue
            msg = result.result.message
            usage_in += msg.usage.input_tokens
            usage_out += msg.usage.output_tokens
            lin += msg.usage.input_tokens
            lout += msg.usage.output_tokens
            text = "".join(x.text for x in msg.content if x.type == "text")
            try:
                parsed = json.loads(text.strip().removeprefix("```json")
                                    .removeprefix("```").removesuffix("```"))
            except json.JSONDecodeError as e:
                entry["record"] = None
                entry["validation_errors"] = [f"unparseable: {e}"]
                stats["failed"] += 1
                rows.append(entry)
                continue

            errors, repairs = _validate_record(layer, parsed, aid, arts, meta)
            entry["record"] = parsed
            entry["validation_errors"] = errors
            entry["prompt_sha256"] = submitted_sha or "unrecorded_at_submit"
            if repairs:
                entry["repairs"] = repairs
                stats["repaired"] = stats.get("repaired", 0) + 1
            stats["ok" if not errors else "failed"] += 1
            rows.append(entry)

        # The retry belongs here as much as in the synchronous path, and its
        # absence here was a real hole: the full corpus run submits batches, so
        # without this it would have reproduced the 10% issues failure rate
        # that the retry exists to remove. The failed fraction is small, so the
        # retry goes out at standard rate rather than as a second batch - it is
        # on the critical path and another batch means another unbounded wait.
        arm_cfg = ARMS[LAYER_ARMS[layer]]
        if prompt_drifted:
            rin = rout = 0
            stats["retry_skipped"] = "prompt changed since submission"
        else:
            rows, stats, rin, rout = _retry_failures(
                layer, rows, stats, arts, meta, client,
                meta.get("layer_models", {}).get(layer) or "claude-sonnet-5",
                arm_cfg)
        usage_in += rin
        usage_out += rout
        lin += rin
        lout += rout

        results["layers"][layer] = rows
        per_layer_usage[layer] = {
            "input_tokens": lin, "output_tokens": lout,
            "model": meta.get("layer_models", {}).get(layer),
            "retry_at_standard_rate": {"input_tokens": rin,
                                       "output_tokens": rout}}
        print(f"{layer}: {stats}")

    for layer in sorted(sync_layers):
        rows, u = _sync_layer(layer, arts, meta)
        results["layers"][layer] = rows
        per_layer_usage[layer] = u
        usage_in += u["input_tokens"]
        usage_out += u["output_tokens"]

    results["usage"] = {"input_tokens": usage_in, "output_tokens": usage_out}
    results["usage_by_layer"] = per_layer_usage
    # Recorded per tranche, because standard-rate and batch-rate tokens are
    # priced differently and the health check's cost projection has to know
    # which it is looking at.
    results["sync_layers"] = sorted(sync_layers)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"-> {out_path}")


if __name__ == "__main__":
    _cmd, _tranche = sys.argv[1], sys.argv[2]
    # Third argument, collect only: a comma-separated list of layers to run on
    # the standard API rather than wait for a batch.
    _sync = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else set()
    if _cmd == "collect":
        cmd_collect(_tranche, sync_layers=_sync)
    else:
        {"submit": cmd_submit}[_cmd](_tranche)
