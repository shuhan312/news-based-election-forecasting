"""Turn extracted article records into the news feature table the model joins.

## The grain, and why it is not the one the brief imagines

The brief asks for features per ward. The corpus cannot deliver that: in the
current canonical 1,632-article release, 46 came from a ward-specific search and
body-text matching against the 108 published area names recovers 22 more -
**4.2% carry an unambiguous area, 94.2% name no unambiguous Surrey area at
all**. Coverage is too sparse and uneven for a general ward-level feature.

So the table is keyed on **(election, party, window)**. Joining it to the
baseline's (election, area, party) rows broadcasts each value across the areas
of its election. That is a real limitation and it is stated here rather than
hidden by a feature name: a news feature in this table can explain differences
between elections and between parties, never between areas within an election.

## Which features can carry a coefficient, measured rather than assumed

Cell counts inside the training period (2013 + 2017), from
`diagnose_feature_grain`:

    per election                2 cells  - cannot fit; two points determine a
                                          line exactly and generalise nothing
    per election x party       10 cells  - usable, median 162 articles per cell

Every feature is therefore emitted with a `training_variation` verdict, and the
election-level ones say `insufficient` rather than being silently offered to a
model that cannot learn from them. They are still computed: the 3,122 collected
but unprocessed by-election articles would add eight more election-level cells
if that pipeline is ever run, and a column that already exists costs nothing to
populate later.

**Reform UK has zero training-period articles** - the party did not exist in
2013 or 2017. No Reform-specific news coefficient can be estimated. Any
relationship must be learned party-generically, from the five parties present in
the training period, and applied to Reform. That is the central extrapolation of
this project and it belongs in the report, not in a footnote.

## Counts and shares, both, for a measured reason

A count is contaminated by how deeply a contest was searched; a share is not,
because search depth moves numerator and denominator together. By-election
search completeness ranges from under 12% to 100%, which is why by-elections
were scoped out of count-based features - so every count here has a companion
share, and the share is what a specification should prefer whenever contests
with different search depths are compared.

## Deduplication, and the assertion that guards it

Tranche output files overlap: far2's articles were re-extracted in the full run
while its stance and framing records were left in place, so concatenating the
files double-counts **98 articles for framing and 66 for stance** - raw rows
exceeded the corpus, 1,730 framing rows against 1,632 articles. Records are
therefore deduplicated on `article_id`, newest tranche winning, and the build
asserts that the unique article count never exceeds the corpus size. A silent
double count would inflate every volume feature for the affected elections.

Usage:
    python3 -m src.news_features.build_feature_table
"""

from __future__ import annotations

import csv
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.run_corpus_extraction import (EXCLUDED_LAYERS,
                                                     FRAME_KEYS, LAYER_ARMS)
from src.llm_extraction.stance_rescue import PARTY_ALIASES
from src.news_collection.canonical_corpus_release import (
    OUTPUT as CANONICAL_MANIFEST,
    build_release,
)
from src.news_features.actor_party_attribution import (parties_for_actors,
                                                       publication_date)

OUT_CSV = Path("news_features/news_feature_table_v1.csv")
OUT_META = Path("news_features/news_feature_table_v1_metadata.json")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_relative(path: Path) -> str:
    """Serialise a lineage path portably, whether a wrapper bound it absolute or relative."""

    resolved = path if path.is_absolute() else (REPO_ROOT / path)
    return str(resolved.resolve().relative_to(REPO_ROOT))

# The six windows the supervisor confirmed on 2026-07-30 ("Keep the news windows
# you already implemented... That is fine. No need to change them"), ordered from
# earliest to latest so a cumulative snapshot is a prefix of this list.
WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")

# Cumulative periods, taken from `window_schemes.ORIGINAL_EMAIL.cumulative`
# rather than invented here. That definition cites the supervisor's own email
# and reads "everything from 1 to N days before polling" - the trailing N days,
# accumulating backwards from polling day.
#
# The first version of this file got both the count and the direction wrong: it
# emitted four snapshots named `as_at_90_days` and so on, built from
# `WINDOWS[:1]`, which is the 180-to-91-day band - the *earliest* coverage, the
# complement of what the definition asks for. `previous_90_days` is the last 90
# days before polling, which is `90_to_31_days` and everything after it. Reusing
# the scheme's own labels also means a feature name here matches the one the
# extraction pipeline already assigns, instead of introducing a second
# vocabulary for the same periods.
def _cumulative_members() -> dict[str, tuple[str, ...]]:
    """Window names inside each cumulative period, from the frozen scheme."""
    from src.news_modelling.window_schemes import ORIGINAL_EMAIL
    spans = {name: (lo, hi) for name, lo, hi in ORIGINAL_EMAIL.windows}
    out: dict[str, tuple[str, ...]] = {}
    for label, limit in ORIGINAL_EMAIL.cumulative:
        # A window belongs to a cumulative period when it lies entirely inside
        # it. `previous_7_days` therefore takes final_72_hours and 7_to_4_days
        # and not the 14-to-8-day band, which straddles the boundary.
        out[label] = tuple(w for w in WINDOWS if spans[w][1] <= limit)
    return out


SNAPSHOTS = _cumulative_members()

# The supervisor's chronological split. Recorded per row so a specification can
# filter on it without re-deriving the split, and so the training-variation
# verdict below can be computed from the table itself.
SPLIT_ROLE = {"SCC-2013-05": "train", "SCC-2017-05": "train",
              "SCC-2021-05": "validation", "ESWS-2026-05": "test"}

# Two points determine a line exactly. Three is where a residual first exists;
# ten is where a coefficient is worth reporting. Stated here because "enough
# variation" is otherwise a judgement made silently inside a model fit.
MIN_CELLS_TO_FIT = 3
MIN_CELLS_TO_REPORT = 10

# The election grid. None (the default, and v1's behaviour) derives the grid
# from the elections that have at least one corpus article. A release whose
# scope registers elections that legitimately ended with zero eligible
# articles sets this explicitly, because the zero-cell policy below applies
# to elections exactly as it applies to periods: a completed search with no
# eligible article is an observation of zero coverage, not a missing election.
GRID_ELECTIONS: list[str] | None = None

# Also aggregate the issue and framing layers per (election, party, window),
# by attributing each article to the parties its extraction record names in
# `political_relevance.affected_actors`.
#
# OFF by default, and deliberately so. Every result in the repository was
# computed from tables built with the per-election aggregation, so v1 and v2
# must keep rebuilding byte-identically; a test asserts exactly that. The
# v3party wrapper turns this on and writes to its own paths, which is the only
# place the new columns appear.
#
# The per-election columns are still emitted when this is on. Having both
# grains in one file is what makes the change auditable: within any cell the
# election column is identical across all six parties by construction, and the
# party column is not.
PARTY_CONTENT_ATTRIBUTION = False

# Extraction tranches to ignore when loading records. Empty by default, which
# is v1's and v2's behaviour.
#
# `load_records` reads every `corpus_extraction_outputs_*.json` on disk, and a
# tranche can legitimately exist whose articles no canonical release admits.
# The E5 local extension is exactly that: its triage failed validation at
# kappa 0.4762 against a 0.600 bar, so its Farnham Herald articles were never
# admitted to a release - yet the tranche was extracted anyway, on 2026-08-02,
# nine hours AFTER feature table v2 was written. The assertion in `main` is
# right to refuse that mixture. Naming the tranche here is the scoped way to
# satisfy it: it states which corpus a build is made of, rather than relaxing
# the guard that checks.
EXCLUDED_TRANCHES: set[str] = set()

# The set the v1 lineage needs, named so a test can reach it: the `__main__`
# block below is the v1 build, and configuration only reachable by running a
# script is configuration nothing can check.
#
# `byelection1` is here for a different reason from the other three. It is the
# enrichment, which release v2 admits and v1 by definition does not - a scope
# difference, not a rejected corpus. The other three are the two single-
# contest case studies and the E5 local extension, which no release admits.
V1_EXCLUDED_TRANCHES = frozenset(
    {"byelection1", "e5local1", "haslemere1", "wokingsouth1"})

# Issue codes aggregated into the six pre-registered issue features. Anything
# outside this map lands in `issue_other`, which is reported rather than
# dropped: an issue the taxonomy does not cover is a fact about the coverage.
#
# Known defect, kept verbatim (2026-08-14): these members were drafted from
# the feature plan's shorthand, not from the extraction prompt's `issue_code`
# enum, so `crime_policing`, `planning_housing`, `waste_recycling` and
# `schools_send` never match and 166 coded records route to `issue_other`
# (61/50/5/50). The frozen v1/v2 tables were built with this map, their
# byte-identical rebuild tests pin it, and the blinded-freeze rule forbids
# regeneration - so the defect stays here, on the record. Future builds must
# pass ISSUE_GROUPS_CORRECTED explicitly; `tests/test_issue_group_mapping.py`
# pins both behaviours.
ISSUE_GROUPS = {
    "immigration": ("immigration", "asylum", "small_boats"),
    "crime_policing": ("crime", "policing", "antisocial_behaviour"),
    "housing_planning": ("housing", "planning", "development", "green_belt"),
    "council_services": ("council_services", "roads_transport", "waste",
                         "social_care", "schools_sen", "council_finance",
                         "council_tax", "council_performance"),
    "national_politics": ("national_politics", "national_economy",
                          "party_leadership", "scandal"),
}

# The corrected map for any post-freeze (v3+) build: member strings taken
# from the extraction prompt's `issue_code` enum itself.
ISSUE_GROUPS_CORRECTED = {
    "immigration": ("immigration",),
    "crime_policing": ("crime_policing",),
    "housing_planning": ("planning_housing",),
    "council_services": ("council_finance", "council_tax",
                         "roads_transport", "waste_recycling",
                         "social_care", "schools_send",
                         "council_performance"),
    "national_politics": ("national_politics", "national_economy",
                          "scandal"),
}


def live_layers() -> list[str]:
    return [l for l in LAYER_ARMS if l not in EXCLUDED_LAYERS]


def load_records() -> tuple[dict[str, dict], dict]:
    """Deduplicated accepted records per layer, newest tranche winning.

    Returns (records, provenance). `records[layer][article_id]` is the accepted
    record; `provenance` counts which tranche and prompt fingerprint each
    article's records came from, so a feature row can be traced to the prompts
    behind it.
    """
    paths = sorted(glob.glob("llm_context/corpus_extraction_outputs_*.json"))
    # "all" is the production run and must win over the gate tranches, so files
    # are applied oldest-first and later writes overwrite earlier ones. Sorting
    # by name puts "all" first alphabetically, which is the wrong order - hence
    # the explicit key rather than relying on the filename.
    order = {"narrow": 0, "far": 1, "far2": 2, "far3": 3, "all": 9}
    def rank(p: str) -> int:
        name = Path(p).stem.replace("corpus_extraction_outputs_", "")
        return order.get(name, 5)

    records: dict[str, dict[str, dict]] = {l: {} for l in live_layers()}
    provenance: Counter = Counter()
    superseded_seen: dict[str, list[str]] = {}

    for path in sorted(paths, key=rank):
        payload = json.loads(Path(path).read_text())
        tranche = payload.get("tranche", Path(path).stem)
        if tranche in EXCLUDED_TRANCHES:
            continue
        superseded = set(payload.get("superseded_layers") or ())
        if superseded:
            superseded_seen[tranche] = sorted(superseded)
        for layer in live_layers():
            if layer in superseded:
                continue
            for r in payload.get("layers", {}).get(layer, []):
                if r.get("record") is None or r.get("validation_errors"):
                    continue
                records[layer][r["article_id"]] = r
                provenance[(layer, tranche,
                            (r.get("prompt_sha256") or "none")[:12])] += 1
    return records, {"per_layer_tranche_prompt": {f"{k[0]}|{k[1]}|{k[2]}": v
                                                  for k, v in provenance.items()},
                     "superseded_layers_honoured": superseded_seen}


def primary_issue(record: dict) -> str | None:
    """The issue code, unwrapped from whichever shape the schema produced."""
    value = (record.get("issues") or {}).get("primary_issue")
    if isinstance(value, dict):
        value = value.get("issue_code") or value.get("code")
    return value or None


def issue_group(code: str | None, groups: dict = ISSUE_GROUPS) -> str:
    if not code:
        return "none"
    for group, members in groups.items():
        if code in members:
            return group
    return "issue_other"


def main() -> None:
    records, provenance = load_records()
    article_ids = set().union(*(set(v) for v in records.values()))

    # Freeze the corpus before joining extraction records. The release manifest
    # is the one place that unions the main, pilot and validation eligibility
    # streams and then applies dates, principal-election scope, the confirmed
    # six windows and text availability. This prevents the 120-local main-table
    # subset from being mixed with the 188-local corpus used here.
    release, canonical_articles = build_release()
    CANONICAL_MANIFEST.write_text(
        json.dumps(release, indent=2), encoding="utf-8"
    )
    corpus_size = release["usable_feature_corpus"]["articles"]

    # Extraction records can legitimately cover fewer articles than the corpus
    # (a layer may fail validation), but they may never introduce an article
    # from another release. Stopping here is safer than writing a plausible-
    # looking table whose denominator came from a different corpus version.
    unexpected_ids = article_ids - set(canonical_articles)
    assert not unexpected_ids, (
        f"{len(unexpected_ids)} extraction article(s) are outside canonical "
        f"release {release['release_id']}; first ids: "
        f"{sorted(unexpected_ids)[:5]}"
    )
    articles = {
        aid: canonical_articles[aid]
        for aid in article_ids
        if aid in canonical_articles
    }

    # The guard the duplicate-counting hazard demands. An inflated article count
    # would inflate every volume feature, and it would do so silently.
    assert len(articles) <= corpus_size, (
        f"deduplication failed: {len(articles)} unique articles against a "
        f"corpus of {corpus_size}. Concatenating tranche files double-counts, "
        f"which is what this assertion exists to catch.")
    print(f"records: {
        {l: len(v) for l, v in records.items()} }")
    print(f"unique articles: {len(articles)} of a {corpus_size}-article corpus")

    # --- accumulate per (election, party, window) -------------------------
    # Party-varying counters. The party key comes from the stance layer's own
    # judgement list, which was built from deterministic alias matching, so a
    # party appears here exactly when the article names it.
    party_cells: dict[tuple, Counter] = defaultdict(Counter)
    # The same counters again, split by collection arm. Added 2026-07-30 for
    # the five-arm comparison the supervisor's original email asks for
    # (baseline / local / national / combined / full).
    #
    # Without this the arm comparison is vacuous by construction: the only
    # arm-aware columns in the table were `local_article_count`,
    # `national_article_count` and `local_share`, all of which sit at the
    # per-election grain and therefore carry **two** distinct training values.
    # A "local news model" built from a feature with two training values is
    # not a local news model; it is the election indicator under another name.
    # Splitting the per-party portrayal counters - the only block with ten
    # training cells - is what makes "does local coverage do a different job
    # from national coverage" a question the table can actually be asked.
    #
    # `arm` here is the **collection** arm: which search stream retrieved the
    # article, which is the same definition `local_article_count` above
    # already uses, so the new columns reconcile with the existing ones rather
    # than introducing a second notion of local. The alternative definition -
    # the LLM's own `scope_classification` - lives at article level and is
    # a content judgement rather than a provenance fact. Mixing the two inside
    # one table would make `local_article_count` and `local_party_article_count`
    # count different things under the same word.
    party_arm_cells: dict[tuple, Counter] = defaultdict(Counter)
    # Election-level counters, kept separate because their grain differs and
    # conflating them would hide that one has two training cells and the other
    # has ten.
    election_cells: dict[tuple, Counter] = defaultdict(Counter)
    # How the content attribution actually landed, recorded in the metadata.
    # An attribution rate is the first thing to check when a party-level
    # content feature behaves oddly, and it is not recoverable from the table.
    attribution: Counter = Counter()

    for aid, article in articles.items():
        election, window, arm = (article["election_id"], article["window"],
                                 article.get("arm") or "unknown")
        ekey = (election, window)
        election_cells[ekey]["article_count"] += 1
        election_cells[ekey][f"{arm}_article_count"] += 1
        election_cells[ekey][f"source__{article.get('source') or 'unknown'}"] += 1
        if article.get("mentions_reform"):
            election_cells[ekey]["reform_named_count"] += 1

        # Parties this article names, for the content layers. Read from the
        # ISSUE record because that is the only layer the extraction gave a
        # `political_relevance` block to; the framing record for the same
        # article inherits this set below, which is what makes a party-level
        # frame feature possible without re-running the extraction. Empty when
        # PARTY_CONTENT_ATTRIBUTION is off, so every loop over it is a no-op
        # and the per-election behaviour is untouched.
        content_parties: set[str] = set()

        issues = records["issues"].get(aid)
        if issues is not None:
            group = issue_group(primary_issue(issues["record"]))
            election_cells[ekey][f"issue_{group}_count"] += 1
            election_cells[ekey]["issues_coded"] += 1
            if PARTY_CONTENT_ATTRIBUTION:
                relevance = issues["record"].get("political_relevance") or {}
                content_parties = parties_for_actors(
                    relevance.get("affected_actors"),
                    publication_date(article))
                attribution["articles_with_issue_record"] += 1
                attribution["articles_attributed" if content_parties
                            else "articles_no_party_found"] += 1
                for party in content_parties:
                    cell = party_cells[(election, party, window)]
                    cell[f"party_issue_{group}_count"] += 1
                    cell["party_issues_coded"] += 1

        framing = records["framing_revised"].get(aid)
        if framing is not None:
            election_cells[ekey]["framing_coded"] += 1
            present = {f["frame"]: bool(f.get("present"))
                       for f in framing["record"].get("frames") or []}
            for frame in FRAME_KEYS:
                if present.get(frame):
                    election_cells[ekey][f"frame_{frame}_count"] += 1
            # The framing record carries no actors of its own, so it inherits
            # the set established for its article above. An article with a
            # framing record but no issue record contributes nothing here -
            # 17 of 2,576 - because there is no actor list to inherit.
            for party in content_parties:
                cell = party_cells[(election, party, window)]
                cell["party_framing_coded"] += 1
                for frame in FRAME_KEYS:
                    if present.get(frame):
                        cell[f"party_frame_{frame}_count"] += 1

        stance = records["stance_revised"].get(aid)
        if stance is not None:
            for judgement in stance["record"].get("judgements") or []:
                party, portrayal = judgement["party"], judgement.get("portrayal")
                cell = party_cells[(election, party, window)]
                cell["party_article_count"] += 1
                cell[f"portrayal_{portrayal}"] += 1
                # Same increments, keyed by arm as well. Written as a second
                # accumulator rather than by deriving the all-arm figure from
                # the arm split, so every column already published keeps
                # exactly the value it had; the reconciliation assertion below
                # is what proves the two stay consistent.
                arm_cell = party_arm_cells[(election, party, arm, window)]
                arm_cell["party_article_count"] += 1
                arm_cell[f"portrayal_{portrayal}"] += 1

    # --- emit one row per (election, party, window-or-snapshot) -----------
    def summed(cells: dict, key_prefix: tuple, windows) -> Counter:
        total = Counter()
        for w in windows:
            total.update(cells.get(key_prefix + (w,), Counter()))
        return total

    parties = sorted({p for (_e, p, _w) in party_cells})
    elections = (sorted(GRID_ELECTIONS) if GRID_ELECTIONS is not None
                 else sorted({e for (e, _w) in election_cells}))
    periods = [(w, (w,)) for w in WINDOWS] + list(SNAPSHOTS.items())

    rows = []
    zero_article_cells = []
    for election in elections:
        for party in parties:
            for period_name, member_windows in periods:
                p = summed(party_cells, (election, party), member_windows)
                e = summed(election_cells, (election,), member_windows)
                by_arm = {
                    arm: summed(
                        party_arm_cells,
                        (election, party, arm),
                        member_windows,
                    )
                    for arm in ("local", "national")
                }
                total = e["article_count"]
                # Keep the full election x party x period grid, including a
                # completed search that found no eligible article.  The old
                # build dropped these rows and turned a real zero into a
                # missing observation.  In particular, all six party rows for
                # SCC 2017's final 72 hours disappeared, so a chronological
                # model could silently train on a different set of elections
                # depending on the chosen window.
                #
                # Count features are genuine zeroes.  Share features remain
                # blank where their denominator is zero: zero of zero is not a
                # party share of zero, it is undefined.  This distinction lets
                # a later model choose an explicit missing-value policy rather
                # than receiving a fabricated proportion.
                if not total:
                    zero_article_cells.append({
                        "election_id": election,
                        "standard_party_key": party,
                        "period": period_name,
                    })
                unfav = p["portrayal_unfavourable"]
                fav = p["portrayal_favourable"]
                row = {
                    "election_id": election,
                    "standard_party_key": party,
                    "period": period_name,
                    "period_kind": "window" if period_name in WINDOWS else "snapshot",
                    "split_role": SPLIT_ROLE.get(election, "unknown"),
                    # --- per election x party: the usable grain -----------
                    "party_article_count": p["party_article_count"],
                    "party_article_share": round(p["party_article_count"] / total, 6) if total else "",
                    "unfavourable_count": unfav,
                    "favourable_count": fav,
                    "net_portrayal": fav - unfav,
                    "net_portrayal_share": round((fav - unfav) / p["party_article_count"], 6)
                                            if p["party_article_count"] else "",
                    # --- per election: two training cells, kept for later --
                    "article_count": total,
                    "local_article_count": e["local_article_count"],
                    "national_article_count": e["national_article_count"],
                    "local_share": round(e["local_article_count"] / total, 6) if total else "",
                    "independent_source_count": sum(
                        1 for k in e if k.startswith("source__")),
                    "reform_named_count": e["reform_named_count"],
                    "reform_share_of_coverage": round(e["reform_named_count"] / total, 6) if total else "",
                }

                # Emit the same party-level signal separately for local and
                # national collection arms. These are the columns needed for
                # the supervisor's baseline/local/national/combined comparison;
                # election-level local_share alone has only two training values
                # and cannot identify a local-news coefficient.
                for arm, arm_party in by_arm.items():
                    arm_total = e[f"{arm}_article_count"]
                    arm_party_count = arm_party["party_article_count"]
                    arm_unfav = arm_party["portrayal_unfavourable"]
                    arm_fav = arm_party["portrayal_favourable"]
                    prefix = f"{arm}_"
                    row[f"{prefix}party_article_count"] = arm_party_count
                    row[f"{prefix}party_article_share"] = (
                        round(arm_party_count / arm_total, 6)
                        if arm_total else ""
                    )
                    row[f"{prefix}unfavourable_count"] = arm_unfav
                    row[f"{prefix}favourable_count"] = arm_fav
                    row[f"{prefix}net_portrayal"] = arm_fav - arm_unfav
                    row[f"{prefix}net_portrayal_share"] = (
                        round((arm_fav - arm_unfav) / arm_party_count, 6)
                        if arm_party_count else ""
                    )

                # Collection arm is exhaustive in the canonical release. These
                # checks catch a misspelled/new arm or an aggregation error at
                # the exact row where it occurs, before any model can consume
                # understated combined counts.
                for key in (
                    "party_article_count",
                    "portrayal_unfavourable",
                    "portrayal_favourable",
                    "portrayal_neither",
                ):
                    assert p[key] == sum(block[key] for block in by_arm.values()), (
                        f"arm reconciliation failed for {election}/{party}/"
                        f"{period_name}/{key}: combined={p[key]}, "
                        f"local+national="
                        f"{sum(block[key] for block in by_arm.values())}"
                    )

                for group in list(ISSUE_GROUPS) + ["issue_other", "none"]:
                    n = e[f"issue_{group}_count"]
                    row[f"issue_{group}_count"] = n
                    row[f"issue_{group}_share"] = (
                        round(n / e["issues_coded"], 6) if e["issues_coded"] else "")
                for frame in FRAME_KEYS:
                    n = e[f"frame_{frame}_count"]
                    row[f"frame_{frame}_count"] = n
                    row[f"frame_{frame}_share"] = (
                        round(n / e["framing_coded"], 6) if e["framing_coded"] else "")

                # The same two layers at party grain, emitted beside the
                # per-election columns above rather than replacing them. The
                # denominator is this party's own coded articles, so the share
                # answers "of the coverage naming this party, how much was
                # about immigration" - a composition, not a volume. That
                # distinction is what stops the new feature from being the
                # article count under another name, and it is checked before
                # any specification uses these columns.
                if PARTY_CONTENT_ATTRIBUTION:
                    coded = p["party_issues_coded"]
                    row["party_issues_coded"] = coded
                    for group in list(ISSUE_GROUPS) + ["issue_other", "none"]:
                        n = p[f"party_issue_{group}_count"]
                        row[f"party_issue_{group}_count"] = n
                        row[f"party_issue_{group}_share"] = (
                            round(n / coded, 6) if coded else "")
                    framed = p["party_framing_coded"]
                    row["party_framing_coded"] = framed
                    for frame in FRAME_KEYS:
                        n = p[f"party_frame_{frame}_count"]
                        row[f"party_frame_{frame}_count"] = n
                        row[f"party_frame_{frame}_share"] = (
                            round(n / framed, 6) if framed else "")
                rows.append(row)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as handle:
        # Pin LF so the generated CSV is byte-stable across platforms and does
        # not appear to contain trailing whitespace in repository checks.
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    # --- the training-variation verdict, computed from the table ----------
    # A feature is only offered to a model if it varies across training rows.
    # Computed here rather than asserted in a docstring so it cannot go stale.
    train_rows = [r for r in rows if r["split_role"] == "train"]
    by_period: dict[str, list] = defaultdict(list)
    for r in train_rows:
        by_period[r["period"]].append(r)

    verdicts = {}
    for column in rows[0]:
        if column in ("election_id", "standard_party_key", "period",
                      "period_kind", "split_role"):
            continue
        # Counted WITHIN a period, not across them. A specification uses one
        # window or one snapshot, so variation between windows is not variation
        # the fit can see. Pooling across periods inflated article_count from 2
        # distinct training values to 14 and would have offered it as usable to
        # a model that sees two - the first version of this verdict did exactly
        # that, which is why it is computed per period now.
        best = max((len({r[column] for r in group if r[column] != ""})
                    for group in by_period.values()), default=0)
        pooled = len({r[column] for r in train_rows if r[column] != ""})
        verdicts[column] = {
            "distinct_training_values_within_period": best,
            "distinct_training_values_pooled_across_periods": pooled,
            "verdict": ("insufficient" if best < MIN_CELLS_TO_FIT
                        else "fittable_not_reportable" if best < MIN_CELLS_TO_REPORT
                        else "usable"),
        }

    usable = [c for c, v in verdicts.items() if v["verdict"] == "usable"]
    # Absent, not null, when the attribution is off: every metadata file this
    # builder has ever written would otherwise gain a key, which is a diff on
    # five committed artefacts in exchange for no information.
    #
    # `party_cell_multiplier` is above 1 by design - an article naming two
    # parties bears on both and is counted for both, so the party-level counts
    # do not sum to the election-level one and should not be expected to.
    attribution_block = {
        **attribution,
        "party_cell_multiplier": round(
            sum(r["party_issues_coded"] for r in rows
                if r["period_kind"] == "window")
            / max(attribution["articles_attributed"], 1), 4),
    } if PARTY_CONTENT_ATTRIBUTION else None

    OUT_META.write_text(json.dumps({
        "rows": len(rows),
        "expected_rows": len(elections) * len(parties) * len(periods),
        "elections": elections,
        "parties": parties,
        "periods": [p for p, _ in periods],
        "unique_articles": len(articles),
        "corpus_size": corpus_size,
        "canonical_corpus_release_id": release["release_id"],
        # Wrappers rebind CANONICAL_MANIFEST together with build_release.
        # Serialise that bound path rather than labelling every derived table
        # as v1, which would make v2 and the case-study tables claim the wrong
        # corpus lineage in their metadata.
        "canonical_corpus_manifest": _repo_relative(CANONICAL_MANIFEST),
        "canonical_corpus_by_arm":
            release["usable_feature_corpus"]["by_arm"],
        "terminal_include_articles":
            release["terminal_include_union"]["articles"],
        "excluded_after_terminal_include":
            release["excluded_after_terminal_include"],
        "grain": "election x party x period",
        "empty_cell_policy": (
            "Retain completed election-party-period cells with zero articles. "
            "Counts are 0; shares with a zero denominator are blank."
        ),
        "zero_article_cells": zero_article_cells,
        "grain_note": ("Not area-level: 94.2% of canonical articles carry no "
                       "unambiguous Surrey-area attribution, and the remaining "
                       "coverage is too sparse and uneven to support a general "
                       "ward-level feature."),
        # Sum disjoint windows only.  Including cumulative snapshots would
        # count the same article several times and the previous implementation
        # actually counted non-empty *cells*, despite calling the field
        # articles.
        "reform_training_articles": sum(
            r["party_article_count"] for r in train_rows
            if r["standard_party_key"] == "reform_uk"
            and r["period_kind"] == "window"
        ),
        "training_variation": verdicts,
        "usable_columns": usable,
        **({"party_content_attribution": attribution_block}
           if attribution_block else {}),
        "provenance": provenance,
    }, indent=2))

    print(f"\nrows: {len(rows)}  ({len(elections)} elections x {len(parties)} "
          f"parties x {len(periods)} periods, zero-article cells retained)")
    print(f"columns with usable training variation: {len(usable)} of "
          f"{len(verdicts)}")
    for column, v in sorted(
            verdicts.items(),
            key=lambda kv: -kv[1]["distinct_training_values_within_period"]):
        if v["verdict"] == "insufficient":
            continue
        print(f"    {column:34s} "
              f"{v['distinct_training_values_within_period']:3d} within period"
              f"   ({v['distinct_training_values_pooled_across_periods']:3d} pooled)"
              f"   {v['verdict']}")
    print(f"\n  insufficient: "
          f"{sum(1 for v in verdicts.values() if v['verdict']=='insufficient')} columns")
    print(f"-> {OUT_CSV}\n-> {OUT_META}")


if __name__ == "__main__":
    # Running this module IS the v1 build, and those four tranches put 948
    # articles outside release v1, which stops it on the corpus assertion -
    # correctly, since a table mixing corpora is the failure that assertion
    # exists to prevent.
    #
    # Applied here rather than as the module default because importing this
    # module must stay inert: `build_haslemere_probe_features` and
    # `build_woking_south_blind_features` import it and need exactly the
    # tranches this set removes.
    EXCLUDED_TRANCHES = set(V1_EXCLUDED_TRANCHES)
    main()
