"""Probe R1-R3: can Kent's results and divisions be obtained from Democracy Club?

Availability only. Candidacy and result payloads are reduced to counts and
presence flags in memory. No vote count, winner flag or other outcome value is
read into the output or printed. Criteria: v2_design/feasibility_probe_v1/criteria.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

OUT = Path("v2_design/feasibility_probe_v1/results_availability.json")
API = "https://candidates.democracyclub.org.uk/api/next/ballots/"
ELECTIONS = ("local.kent.2017-05-04", "local.kent.2021-05-06",
             "local.kent.2025-05-01")


def ballots(election_id: str) -> list[dict]:
    rows, url, params = [], API, {"election_id": election_id, "page_size": 200}
    while url:
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        body = r.json()
        rows.extend(body["results"])
        url, params = body.get("next"), None
    return rows


def summarise(election_id: str) -> dict:
    rows = [b for b in ballots(election_id) if not b.get("cancelled")]
    n = len(rows)
    with_candidates = sum(1 for b in rows if b.get("candidacies"))
    # Presence only: a non-empty results object, values never inspected.
    with_results = sum(1 for b in rows if b.get("results"))
    return {
        "election_id": election_id,
        "divisions": n,
        "candidacies": sum(len(b.get("candidacies") or []) for b in rows),
        "uncontested": sum(1 for b in rows if b.get("uncontested")),
        "R1_candidate_list_share": round(with_candidates / n, 4) if n else None,
        "R2_result_record_share": round(with_results / n, 4) if n else None,
        "division_slugs": sorted(b["post"]["slug"] for b in rows),
        "division_ids": sorted(b["post"]["id"] for b in rows),
    }


def main() -> None:
    summaries = [summarise(e) for e in ELECTIONS]
    boundary = []
    for a, b in zip(summaries, summaries[1:]):
        sa, sb = set(a["division_ids"]), set(b["division_ids"])
        boundary.append({
            "from": a["election_id"], "to": b["election_id"],
            "shared_division_ids": len(sa & sb),
            "share_of_later_divisions_unchanged":
                round(len(sa & sb) / len(sb), 4) if sb else None,
        })
    payload = {"criteria": "v2_design/feasibility_probe_v1/criteria.md",
               "elections": summaries, "R3_boundary_continuity": boundary}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for s in summaries:
        print(s["election_id"], s["divisions"], s["candidacies"],
              s["R1_candidate_list_share"], s["R2_result_record_share"])
    for b in boundary:
        print(b)


if __name__ == "__main__":
    main()
