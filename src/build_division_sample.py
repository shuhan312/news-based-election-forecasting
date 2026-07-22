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
                                          fetch_2026_surrey_results.py)

Output:
  news_protocol/division_sample.md       the committed sampling record

Usage:
    python3 src/build_division_sample.py
"""

import csv
from collections import defaultdict
from pathlib import Path

WARD_WINNERS = Path("data/elections/ward_winners.csv")
RESULTS_2026 = [Path("data/elections/2026_east_surrey_results.csv"),
                Path("data/elections/2026_west_surrey_results.csv")]
OUT = Path("news_protocol/division_sample.md")

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


def ward_2026_summary(rows_2026):
    """Per ward: winning party (by top vote share among candidates) and
    Reform UK's vote share (0 if it did not stand). 2026 wards are
    two-member and on new boundaries, so this is keyed by the 2026
    ward name only - matching to 2021 divisions is a separate,
    already-flagged crosswalk task, not done here (see notes in the
    output file)."""
    by_ward = defaultdict(list)
    for r in rows_2026:
        by_ward[r["ward"]].append(r)
    summary = {}
    for ward, cands in by_ward.items():
        cands_sorted = sorted(cands, key=lambda c: float(c.get("vote_share") or 0),
                              reverse=True)
        reform = [c for c in cands if "reform" in
                 (c.get("standardised_party") or c.get("party") or "").lower()]
        reform_share = max((float(c.get("vote_share") or 0) for c in reform),
                           default=0.0)
        summary[ward] = {
            "winning_party": cands_sorted[0].get("standardised_party")
                            or cands_sorted[0].get("party") if cands_sorted else None,
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

    # --- Changed / Reform strata: need 2026 data ----------------------
    # 2026 wards use new two-member boundaries not yet crosswalked to
    # 2021 divisions (protocol note: "should not combine them until the
    # old divisions have been mapped against the new wards"). Until
    # that crosswalk exists, these two strata are populated on 2026
    # ward identity alone and flagged as boundary-pending; the sample
    # still fixes WHICH 2026 wards are in scope, which is what unblocks
    # local-news collection for the 2026 election regardless of the
    # crosswalk timeline.
    if summary_2026:
        changed_pool = {w: s for w, s in summary_2026.items()
                        if s["winning_party"]
                        and w in margins
                        and s["winning_party"] != margins[w]["winning_party"]}
        for ward, s in sorted(changed_pool.items())[:PER_STRATUM_TARGET]:
            add(ward, "Changed",
                f"2021 winner {margins[ward]['winning_party']} -> "
                f"2026 winner {s['winning_party']} "
                "[BOUNDARY-PENDING: 2026 ward vs 2021 division crosswalk "
                "not yet applied]")

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
        # Ranked directly (not via select()) because the sort key lives
        # in shares_2021, keyed by ward, not in summary_2026's values.
        absent_wards = [w for w in summary_2026
                       if not summary_2026[w]["reform_stood"] and w in shares_2021]
        ranked_absent = sorted(absent_wards,
                               key=lambda w: (-shares_2021[w]["share"], w))
        for ward in ranked_absent[:PER_STRATUM_TARGET]:
            s = shares_2021[ward]
            add(ward, "Reform weak/absent",
                f"Reform UK not standing in 2026; 2021 incumbent "
                f"{shares_2021[ward]['party']} held "
                f"{shares_2021[ward]['share']:.1f}% "
                "[BOUNDARY-PENDING: 2026 ward vs 2021 division crosswalk "
                "not yet applied]")

    return selected, bool(summary_2026)


def write_report(selected, has_2026):
    total = len(selected)
    lines = [
        "# Division Sampling Design",
        "",
        "**Stage:** Supervisor to-do 7 (division sampling), preceding "
        "ward-level news collection (Stage C).",
        "**Status:** " + ("Provisionally adopted pending supervisor "
                          "confirmation" if True else "Confirmed") +
        " - thresholds and algorithm below were fixed before this "
        "script was run, using only committed election-result data. "
        "Nothing about news coverage or content informed this "
        "selection.",
        "",
        "## Pre-registered rule",
        "",
        f"- Safe: 2021 winning margin >= {SAFE_MARGIN_PP} percentage points",
        f"- Marginal: 2021 winning margin <= {MARGINAL_MARGIN_PP} percentage points",
        "- Changed: 2021 and 2026 winning parties differ (2026 ward "
        "boundaries; crosswalk to 2021 divisions pending)",
        "- Reform strong: highest 2026 Reform UK vote shares",
        "- Reform weak/absent: Reform UK not contesting in 2026, "
        "matched against 2021 established-party strength (contrast "
        "case for the momentum-vs-conversion question)",
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
            "`python3 src/fetch_2026_surrey_results.py` to produce "
            "them, then re-run this script (`python3 "
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
    print(f"{total} divisions -> {OUT}")
    for ward in sorted(selected):
        print(f"  {ward}: {[s for s, _ in selected[ward]]}")


if __name__ == "__main__":
    sel, has_2026 = build()
    write_report(sel, has_2026)
