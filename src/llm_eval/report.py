"""Write a pipeline result as one Markdown page and one JSON file.

The Markdown is for a person: verdict first, then the audit (because a label
problem changes how every number below it should be read), then the scores.
The JSON holds everything, for diffs between runs.
"""

from __future__ import annotations

import json
from pathlib import Path


def _fmt(score: dict, name: str) -> str:
    value, ci = score.get(name), score.get(f"{name}_ci95")
    if value is None:
        return "n/a"
    return f"{value:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else f"{value:.3f}"


def _audit_lines(audit: dict) -> list[str]:
    lines = []
    for f in audit["flags"]:
        if f["check"] == "rule_consistency":
            lines.append(
                f"- **Rule mismatch** in batch `{f['origin']}` "
                f"(stratum `{f['stratum']}`, label {f['label']}): "
                f"{f['violations']} of {f['checked']} labels use a reason code "
                f"outside the stratum's rules: {f['codes']}")
        elif f["check"] == "base_rate_drift":
            key = next(k for k in f if k not in
                       ("check", "origins", "rates", "n", "p_value"))
            lines.append(
                f"- **Base-rate drift** for {key} `{f[key]}`: positive rate "
                f"{f['rates'][0]:.0%} in `{f['origins'][0]}` vs "
                f"{f['rates'][1]:.0%} in `{f['origins'][1]}` "
                f"(n = {f['n'][0]}, {f['n'][1]}; Fisher p = {f['p_value']:.1e})")
        elif f["check"] == "provenance":
            lines.append(f"- **Provenance:** {f['message']} "
                         f"({f['ai_assisted_labels']} of {f['total']} labels)")
    return lines or ["- No flags."]


def to_markdown(result: dict) -> str:
    o = result["overall"]
    gate = result.get("gate")
    verdict = ("no gate configured" if gate is None
               else "PASS" if gate["pass"] else "FAIL")
    # A pass against flawed labels is not a clean pass, so the flag count
    # sits in the verdict line itself, not only further down.
    n_flags = len(result["audit"]["flags"])
    if n_flags:
        verdict += (f", with {n_flags} reference-label audit flag"
                    f"{'s' if n_flags > 1 else ''} (read section 1)")
    lines = [
        f"# llm_eval report: {result['task']}",
        "",
        f"**Verdict: {verdict}.** Split `{result['split']}`, n = {o['n']} "
        f"({o['positives']} positive). Predictions: "
        f"`{result['run']['source']}`.",
        "",
        "## 1. Reference-label audit",
        "",
        "Read this first: a flag here changes what the scores below mean.",
        "",
        *_audit_lines(result["audit"]),
        "",
        "## 2. Scores (95% bootstrap CI)",
        "",
        "| metric | value |",
        "|---|---|",
        *[f"| {m} | {_fmt(o, m)} |"
          for m in ("kappa", "recall", "precision", "f1", "agreement")],
    ]
    if gate:
        lines += ["", "## 3. Gate", "", "| metric | value | bar | result |",
                  "|---|---:|---:|---|"]
        lines += [f"| {m} | {c['value']} | {c['bar']} | "
                  f"{'pass' if c['pass'] else 'FAIL'} |"
                  for m, c in gate["checks"].items()]
    for field, groups in result.get("subgroups", {}).items():
        lines += ["", f"## Subgroups by `{field}`", "",
                  "| group | n | kappa | recall | precision |",
                  "|---|---:|---|---|---|"]
        lines += [f"| {g} | {s['n']} | {_fmt(s, 'kappa')} | "
                  f"{_fmt(s, 'recall')} | {_fmt(s, 'precision')} |"
                  for g, s in groups.items()]
    run = result["run"]
    if run["source"] == "api":
        lines += ["", "## Cost", "",
                  f"Estimated ${run['estimate']['estimated_cost_usd']}, "
                  f"actual ${run['usage']['actual_cost_usd']}; "
                  f"{run['estimate']['cached']} answers reused from cache; "
                  f"{len(run['failed'])} failed (retried next run)."]
    if result["missing_predictions_counted_negative"]:
        lines += ["", f"Note: {result['missing_predictions_counted_negative']}"
                  " examples had no prediction and were counted negative."]
    return "\n".join(lines) + "\n"


def write(result: dict, out_dir: str | Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md, js = out_dir / "report.md", out_dir / "results.json"
    md.write_text(to_markdown(result), encoding="utf-8")
    js.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return md, js
