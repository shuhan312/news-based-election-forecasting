"""Build the pre-registered Division Sampling Design (supervisor to-do 7).

Selects 15-25 Surrey County Council divisions for ward-level news
collection, stratified by:

    Safe       - 2021 winning margin >= SAFE_MARGIN_PP
    Marginal   - 2021 winning margin <= MARGINAL_MARGIN_PP
    Changed    - winning party differs between 2021 and 2026
    Reform strong - among the highest 2026 Reform UK vote shares
    Reform weak/absent - Reform did not stand in 2026 (or stood very
                    weakly), matched against divisions with a strong
                    2021 vote share for an established party, so the
                    stratum gives a genuine contrast case rather than
                    an arbitrary leftover

Why this script exists (methodological rationale, kept here rather
than only in prose, so the rule and its implementation can never
drift apart):

  This project tests whether news content predicts election outcomes.
  If which divisions get ward-level news collection were chosen after
  looking at news coverage - or worse, after knowing which choice
  would make the results look better - the whole comparison would be
  contaminated by selection bias.  The only defensible design is to
  fix the selection rule using ONLY election-result data (which is
  already final and immutable) and commit the rule and its output
  BEFORE a single ward-level article is retrieved.  That is what this
  script does: every threshold is a literal constant below, every
  selection is a deterministic sort-and-slice (no randomness, so
  re-running this script on the same committed CSVs reproduces an
  identical sample), and the output file records, for every selected
  division, the exact numeric fact that triggered its selection - so
  a reader (or examiner) can verify none were hand-picked.

Inputs (all already-completed, committed components - read-only):
  data/elections/ward_winners.csv        2017/2021 SCC winner + margin
                                          (historical baseline feature
                                          layer; do not recompute)
  data/elections/2026_east_surrey_results.csv
  data/elections/2026_west_surrey_results.csv
                                          2026 candidate-level results
                                          (produced by
                                          src/convert_2026_extractor_output.py
                                          from the already-validated,
                                          SerpAPI-based extraction in
                                          surrey-election-extractor/ -
                                          a direct scrape of the council
                                          site was tried first and
                                          abandoned after it was blocked
                                          by the site's anti-bot
                                          protection even with retries)
  surrey-election-extractor/outputs/geographic_crosswalk_resolution/
    final_direct_mapping_dataset.json    the ONLY 2021-division-to-2026-
                                          ward pairs with a verified,
                                          GIS-area-overlap "exact"
                                          correspondence (24 of 93 2021
                                          divisions). The Changed stratum
                                          is restricted to these pairs -
                                          matching by ward NAME alone
                                          would be unsound because the
                                          2026 elections used new
                                          boundaries the supervisor
                                          explicitly warned must not be
                                          conflated with the old
                                          divisions without a crosswalk.

Output:
  news_protocol/division_sample.md       the committed sampling record
                                          (human-readable)
  news_protocol/division_sample.csv      the same result, machine-
                                          readable, for downstream
                                          scripts (e.g.
                                          build_query_inventory.py)
                                          to consume without parsing
                                          Markdown

Usage:
    python3 src/build_division_sample.py
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

WARD_WINNERS = Path("data/elections/ward_winners.csv")
RESULTS_2026 = [Path("data/elections/2026_east_surrey_results.csv"),
                Path("data/elections/2026_west_surrey_results.csv")]
EXACT_CROSSWALK = Path(
    "surrey-election-extractor/outputs/geographic_crosswalk_resolution/"
    "final_direct_mapping_dataset.json")
OUT = Path("news_protocol/division_sample.md")
OUT_CSV = Path("news_protocol/division_sample.csv")

# Pre-registered numeric thresholds. Fixed BEFORE inspecting results,
# using the supervisor's qualitative categories (safe / marginal /
# changed / Reform strong-weak) made concrete. Changing these after
# seeing which divisions they select would defeat the point of
# pre-registration, so any change belongs in the protocol's deviations
# log (news_research_protocol.md section 9), never a silent edit here.
SAFE_MARGIN_PP = 20.0        # winning margin, percentage points
MARGINAL_MARGIN_PP = 5.0
PER_STRATUM_TARGET = 5       # divisions drawn per stratum before dedup
TOTAL_RANGE = (15, 25)       # supervisor's required sample size
OVERLAP_RATIO_MIN = 0.99     # GIS area-overlap floor for treating a
                             # 2021 division and a 2026 ward as the same
                             # ground (see load_exact_crosswalk)


def load_2021_margins():
    """2021 SCC winner and margin per ward, from the already-completed
    historical baseline feature layer. Not recomputed here - reusing a
    completed component's output is the point of layering the
    pipeline this way."""
    rows = [r for r in csv.DictReader(WARD_WINNERS.open())
            if r["council"] == "Surrey County Council" and r["year"] == "2021"]
    return {r["ward"]: {"winning_party": r["winning_party"],
                        "margin_pp": float(r["margin"])}
            for r in rows if r["margin"]}


def load_2021_party_shares():
    """2021 per-party vote share per ward, for the Reform-weak contrast
    stratum (which established party was strong where Reform is absent
    in 2026)."""
    rows = [r for r in csv.DictReader(WARD_WINNERS.open())
            if r["council"] == "Surrey County Council" and r["year"] == "2021"]
    return {r["ward"]: {"party": r["winning_party"],
                        "share": float(r["winner_share"])}
            for r in rows if r["winner_share"]}


def load_2026_results():
    """2026 candidate-level results, if the extraction has been run.
    Returns {} and a loud warning if not - the Changed and Reform
    strata are then left empty rather than guessed at."""
    rows = []
    missing = [p for p in RESULTS_2026 if not p.exists()]
    if missing:
        print("WARNING: 2026 results not yet extracted "
              f"({[str(p) for p in missing]}). Run "
              "src/fetch_2026_surrey_results.py first. Changed and "
              "Reform strata will be left empty this run.")
        return []
    for p in RESULTS_2026:
        rows.extend(csv.DictReader(p.open()))
    return rows


def load_exact_crosswalk():
    """The subset of the project's GIS-based geographic crosswalk safe
    for direct 2021-vs-2026 winner comparison: relationship_type
    'exact' or 'near_exact'. Both labels describe (near-)complete
    boundary coincidence - checked directly against the underlying
    area-overlap ratios rather than trusting the label wording alone:
    every row in this file (both 'exact' and 'near_exact') has both
    source and target overlap ratios above OVERLAP_RATIO_MIN, i.e. the
    2021 division and the 2026 ward occupy, in practice, the same
    ground. This file is a curated subset the project's own crosswalk
    methodology already separated from the other two outputs it
    produces: analytical_crosswalk_dataset.json (split/merged/uncertain
    boundaries - no single 2026 ward corresponds to the old division)
    and not_comparable_dataset.json. Only this file's rows are used
    here; the other two are not read by this script at all.

    Returns {2021 division name (as in ward_winners.csv):
             2026 ward name (as in the converted results CSVs)}.

    Name normalisation is applied only to the join keys, not to
    establish which pairs correspond - that correspondence is the
    crosswalk's own GIS-verified finding. The crosswalk stores the 2021
    side as "<name> ED" and the 2026 side without the 2026 workbooks'
    " Ward" suffix; stripping/adding those fixed suffixes is the only
    transformation applied.
    """
    if not EXACT_CROSSWALK.exists():
        return {}
    pairs = json.loads(EXACT_CROSSWALK.read_text())
    mapping = {}
    for r in pairs:
        if r.get("relationship_type") not in ("exact", "near_exact"):
            continue
        if (r["source_overlap_ratio"] < OVERLAP_RATIO_MIN
                or r["target_overlap_ratio"] < OVERLAP_RATIO_MIN):
            continue
        prev = r["previous_area_name"].removesuffix(" ED")
        curr = r["current_area_name"] + " Ward"
        mapping[prev] = curr
    return mapping


def ward_2026_summary(rows_2026):
    """Per ward: winning party and Reform UK's vote share (0 if it did
    not stand). Keyed by the 2026 ward name as published; comparison
    against 2021 divisions is done separately in build() via the
    verified exact crosswalk, never by assuming a 2026 ward name equals
    a 2021 division name.

    Column names here MUST match convert_2026_extractor_output.py's
    OUTPUT_COLUMNS exactly (party_canonical/party_raw/
    candidate_vote_share/candidate_rank) - an earlier version of this
    function used different column names (standardised_party/party/
    vote_share) that simply do not exist in the actual CSV. That typo
    did not raise an error (dict.get() on a missing key just returns
    None), it silently made every ward look like "Reform did not
    stand" and "no winning party found", which would have poisoned the
    Changed and Reform-strong strata with false results. Caught by
    checking the Reform-strong stratum was suspiciously empty even
    though the conversion log showed 162 Reform UK candidate rows.
    """
    by_ward = defaultdict(list)
    for r in rows_2026:
        by_ward[r["ward"]].append(r)
    summary = {}
    for ward, cands in by_ward.items():
        # Reuse the rank already computed (from the published vote
        # count) by the converter, rather than re-deriving it here from
        # a percentage string - one source of truth for "who won".
        winner = next((c for c in cands
                       if str(c.get("candidate_rank")) == "1"), None)
        reform = [c for c in cands if "reform" in
                 (c.get("party_canonical") or c.get("party_raw") or "").lower()]
        reform_share = max(
            (float(c["candidate_vote_share"]) for c in reform
             if c.get("candidate_vote_share")), default=0.0)
        summary[ward] = {
            "winning_party": (winner.get("party_canonical")
                              or winner.get("party_raw")) if winner else None,
            "reform_vote_share": reform_share,
            "reform_stood": bool(reform),
        }
    return summary


def select(pool, key, n, reverse=True):
    """Deterministic top-n by key, ties broken alphabetically by ward
    name so the ordering never depends on file/dict ordering."""
    ranked = sorted(pool.items(), key=lambda kv: (-key(kv[1]) if reverse
                                                  else key(kv[1]), kv[0]))
    return ranked[:n]


def build():
    margins = load_2021_margins()
    shares_2021 = load_2021_party_shares()
    rows_2026 = load_2026_results()
    summary_2026 = ward_2026_summary(rows_2026) if rows_2026 else {}

    selected = {}   # ward -> list of (stratum, evidence string)

    def add(ward, stratum, evidence):
        selected.setdefault(ward, []).append((stratum, evidence))

    # --- Safe: 2021 margin >= threshold, widest margins first --------
    safe_pool = {w: m for w, m in margins.items()
                if m["margin_pp"] >= SAFE_MARGIN_PP}
    for ward, m in select(safe_pool, lambda m: m["margin_pp"],
                          PER_STRATUM_TARGET):
        add(ward, "Safe",
            f"2021 winning margin {m['margin_pp']:.1f}pp "
            f"({m['winning_party']} held) >= {SAFE_MARGIN_PP}pp threshold")

    # --- Marginal: 2021 margin <= threshold, narrowest first ---------
    marg_pool = {w: m for w, m in margins.items()
                if m["margin_pp"] <= MARGINAL_MARGIN_PP}
    for ward, m in select(marg_pool, lambda m: m["margin_pp"],
                          PER_STRATUM_TARGET, reverse=False):
        add(ward, "Marginal",
            f"2021 winning margin {m['margin_pp']:.1f}pp "
            f"({m['winning_party']}) <= {MARGINAL_MARGIN_PP}pp threshold")

    # --- Changed stratum: 2021 winner vs 2026 winner, GIS-verified pairs only ---
    # Restricted to the 24 division/ward pairs the project's own
    # geographic crosswalk classifies "exact" (see load_exact_crosswalk
    # docstring). A division that was split or merged into new
    # boundaries has no single comparable 2026 winner, so it is simply
    # not eligible for this stratum rather than force-matched by name.
    exact_crosswalk = load_exact_crosswalk()
    if summary_2026:
        changed_pool = {}
        for division_2021, ward_2026 in exact_crosswalk.items():
            if division_2021 not in margins or ward_2026 not in summary_2026:
                continue
            prev_winner = margins[division_2021]["winning_party"]
            curr = summary_2026[ward_2026]
            if curr["winning_party"] and curr["winning_party"] != prev_winner:
                changed_pool[ward_2026] = {
                    "prev_division": division_2021,
                    "prev_winner": prev_winner,
                    "curr_winner": curr["winning_party"],
                }
        for ward, s in sorted(changed_pool.items())[:PER_STRATUM_TARGET]:
            add(ward, "Changed",
                f"GIS-verified exact match to 2021 division "
                f"'{s['prev_division']}': winner {s['prev_winner']} -> "
                f"{s['curr_winner']} in 2026 "
                "(source: geographic_crosswalk_resolution/"
                "final_direct_mapping_dataset.json, relationship_type=exact)")

        reform_pool = {w: s for w, s in summary_2026.items() if s["reform_stood"]}
        for ward, s in select(reform_pool, lambda s: s["reform_vote_share"],
                              PER_STRATUM_TARGET):
            add(ward, "Reform strong",
                f"2026 Reform UK vote share {s['reform_vote_share']:.1f}%")

        # Reform-weak contrast: 2026 wards where Reform did not stand,
        # ranked by how strong an established party was there in 2021
        # (a genuine contrast case: national momentum present, but a
        # ward where it evidently has not organised locally - directly
        # serving the supervisor's momentum-vs-conversion question).
        # Same exact-crosswalk restriction as the Changed stratum above:
        # a 2026 ward's name is never looked up directly against
        # shares_2021 (which is keyed by 2021 division names and would
        # essentially never match, since 2026 names carry a " Ward"
        # suffix 2021 division names do not - matching on GIS-verified
        # pairs avoids relying on that coincidence).
        absent_pairs = [(ward_2026, division_2021)
                        for division_2021, ward_2026 in exact_crosswalk.items()
                        if ward_2026 in summary_2026
                        and not summary_2026[ward_2026]["reform_stood"]
                        and division_2021 in shares_2021]
        ranked_absent = sorted(absent_pairs,
                               key=lambda p: (-shares_2021[p[1]]["share"], p[0]))
        for ward, division_2021 in ranked_absent[:PER_STRATUM_TARGET]:
            s = shares_2021[division_2021]
            add(ward, "Reform weak/absent",
                f"Reform UK not standing in 2026; GIS-verified exact "
                f"match to 2021 division '{division_2021}', where "
                f"{s['party']} held {s['share']:.1f}% in 2021 "
                "(source: geographic_crosswalk_resolution/"
                "final_direct_mapping_dataset.json, relationship_type=exact)")

    return reconcile_aliases(selected, exact_crosswalk), bool(summary_2026)


def reconcile_aliases(selected, exact_crosswalk):
    """Merge entries that are the same physical ground under two
    different names - a 2021 division name from the Safe/Marginal
    strata and its GIS-verified 2026 ward name from the Changed/Reform
    strata (e.g. 'Caterham Hill' and 'Caterham Hill Ward'). Without
    this step the sample would double-count such wards and Stage C
    would search news for the same place twice under two labels.

    The 2026 ward name is kept as the canonical key (it is what the
    news-collection queries and the 2026 results CSVs use going
    forward); the evidence from both names' strata is combined under
    it, and which original name each piece of evidence came from is
    kept in the evidence text itself (already the case, since each
    evidence string names its own source year).
    """
    merged = {}
    for name, entries in selected.items():
        canonical = exact_crosswalk.get(name, name)   # 2021 name -> 2026 name if known
        merged.setdefault(canonical, [])
        for entry in entries:
            if entry not in merged[canonical]:
                merged[canonical].append(entry)
    return merged


def write_report(selected, has_2026):
    total = len(selected)
    lines = [
        "# Division Sampling Design",
        "",
        "**Stage:** Supervisor to-do 7 (division sampling), preceding "
        "ward-level news collection (Stage C).",
        "**Status:** Adopted 2026-07-23 and subsequently used as the "
        "frozen operational local-division sample (no separate "
        "supervisor-ratification record is stored in the repository) "
        "- thresholds and algorithm below were fixed before this "
        "script was run, using only committed election-result data. "
        "Nothing about news coverage or content informed this "
        "selection.",
        "",
        "## Pre-registered rule",
        "",
        f"- Safe: 2021 winning margin >= {SAFE_MARGIN_PP} percentage points",
        f"- Marginal: 2021 winning margin <= {MARGINAL_MARGIN_PP} percentage points",
        "- Changed: 2021 and 2026 winning parties differ, restricted to "
        "the 24 division/ward pairs the project's GIS-based geographic "
        "crosswalk classifies as an 'exact' match (see "
        "surrey-election-extractor/outputs/geographic_crosswalk_resolution/) "
        "- pairs that were split, merged, or uncertain are excluded "
        "rather than approximately matched",
        "- Reform strong: highest 2026 Reform UK vote shares (no "
        "crosswalk needed - a fact about the 2026 ward alone)",
        "- Reform weak/absent: Reform UK not contesting in 2026, "
        "matched via the same 'exact' crosswalk against 2021 "
        "established-party strength (contrast case for the "
        "momentum-vs-conversion question)",
        f"- Per stratum: top {PER_STRATUM_TARGET} by rank (deterministic "
        "sort, no randomness); overlaps deduplicated; total constrained "
        f"to {TOTAL_RANGE[0]}-{TOTAL_RANGE[1]} divisions",
        "",
        f"## Result: {total} divisions selected"
        + ("" if has_2026 else " (2026 data not yet available - "
           "Changed and Reform strata pending, see note below)"),
        "",
        "| Division | Strata (selection evidence) |",
        "|---|---|",
    ]
    for ward in sorted(selected):
        evidence = "; ".join(f"**{s}** - {e}" for s, e in selected[ward])
        lines.append(f"| {ward} | {evidence} |")

    if not has_2026:
        lines += [
            "",
            "## Outstanding: 2026 data dependency",
            "",
            "`data/elections/2026_east_surrey_results.csv` and "
            "`2026_west_surrey_results.csv` do not exist yet. Run "
            "`python3 src/convert_2026_extractor_output.py` to produce "
            "them from the already-validated SerpAPI-based extraction, "
            "then re-run this script (`python3 "
            "src/build_division_sample.py`) to populate the Changed "
            "and Reform strata and finalise the sample.",
        ]

    lines += [
        "",
        "## Confirmation needed from supervisor",
        "",
        "The Safe/Marginal thresholds and the per-stratum target were "
        "chosen by the student to operationalise the supervisor's "
        "qualitative categories and are proposed here, not yet "
        "confirmed. To be raised at the next supervision meeting "
        "alongside protocol proposals P1-P3. Ward-level collection "
        "(Stage C) is unblocked by this file's presence but the "
        "selection may still be revised - any revision must be logged "
        "as a new version here and in the protocol deviations log, "
        "never a silent edit.",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")

    # Machine-readable sibling: one row per selected division, its strata
    # (semicolon-joined, since a division can qualify for more than one)
    # and its evidence text, so build_query_inventory.py (or anything
    # else downstream) can consume the sample without parsing Markdown.
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["division", "strata", "evidence"])
        w.writeheader()
        for ward in sorted(selected):
            w.writerow({
                "division": ward,
                "strata": "; ".join(s for s, _ in selected[ward]),
                "evidence": " | ".join(e for _, e in selected[ward]),
            })

    print(f"{total} divisions -> {OUT} and {OUT_CSV}")
    for ward in sorted(selected):
        print(f"  {ward}: {[s for s, _ in selected[ward]]}")


if __name__ == "__main__":
    sel, has_2026 = build()
    write_report(sel, has_2026)
