"""一次性的 2026 年揭盲：将冻结的预测与真实结果比较评分。

本模块执行项目最终的验证性步骤，其构建方式保证运行它只可能有一种含义：

1. **完整性优先。** 在读取任何一个观测值之前，每个冻结的预测文件都会被
   重新计算哈希，并与冻结时提交的 sha256 清单进行比对，v2 协议中嵌入的
   v1 哈希副本也会被检查。如果自冻结以来有任何一个字节发生了变化，揭盲
   就拒绝启动 —— 给被篡改过的预测评分比不评分更糟糕。
2. **只揭盲一次。** 如果输出目录已存在，就拒绝运行。没有任何参数可以
   覆盖这一点：第二次"揭盲"相当于对一个已知答案重新打分。
3. **不做选择。** 每一个归档的设定都会被评分并写出。验证性结论来自两个
   事先声明的系列 —— 在六个已确认时间窗口上的合并组和全国组，分别在 v1
   主变体和 v2 扩充变体之下 —— 每一个都在总体 MAE 上与其重新校准的对照组
   比较，并给出竞选单元级别的 bootstrap 区间。其他所有内容（本地组、累积
   时间段、仅 2017 年的复现）都会被评分，并标注为敏感性分析。输出程序只
   报告计数和列表；它从不排名，从不挑选最好的一行，并在每张表旁边打印
   解读规则。

评分约定沿用自冻结的 2026 年之前的实验：在受支持的候选人行（有新闻覆盖的
六个政党系列）上计算 MAE，英国改革党单独报告并显示其行数，使用基线模型包
自身的随机种子进行竞选单元 bootstrap，并根据双席位分配计算席位层面的准确率。
观测值来自第一阶段留出集文件 —— 正是其预测列输入了各次冻结的那个文件；
它的观测列在新闻层中是第一次、也是唯一一次在这里被读取。
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from news_modelling.news_estimator import bootstrap_improvement

V1_DIR = Path("news_features/blinded_2026_predictions_v1")
V2_DIR = Path("news_features/blinded_2026_predictions_v2")
HOLDOUT = Path(
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "holdout_predictions.csv"
)
OUTPUT_DIR = Path("news_features/unblinding_2026_v1")

# 两个事先声明的验证性系列，与冻结协议中的表述
# 完全一致。凡是不在这里匹配到的都属于敏感性分析。
CONFIRMATORY = {
    "v1": {"fit_variant": "pooled_2017_2021",
           "analyses": ("combined_exploratory", "national_exploratory"),
           "period_role": "confirmed_window"},
    "v2": {"fit_variant": "pooled_2017_2021_byelections",
           "analyses": ("combined_exploratory", "national_exploratory"),
           "period_role": "confirmed_window"},
}


class UnblindingRefused(RuntimeError):
    """合法揭盲的前提条件不成立。"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze_integrity() -> dict:
    """证明被评分的文件就是被冻结的那些文件。"""

    report = {}
    for name, directory in (("v1", V1_DIR), ("v2", V2_DIR)):
        manifest = json.loads((directory / "sha256_manifest.json").read_text())
        for filename in ("blinded_predictions.csv", "frozen_protocol.json"):
            actual = _sha256(directory / filename)
            if actual != manifest[filename]:
                raise UnblindingRefused(
                    f"{name}/{filename} does not match its frozen sha256; "
                    "refusing to score altered predictions"
                )
            report[f"{name}/{filename}"] = actual

    # v2 协议在其自身冻结时嵌入了 v1 的哈希；如果不匹配，
    # 就意味着这两个文件并不是相互对照着冻结的。
    v2_protocol = json.loads((V2_DIR / "frozen_protocol.json").read_text())
    v1_manifest = json.loads((V1_DIR / "sha256_manifest.json").read_text())
    chain = v2_protocol["v1_freeze"]
    if (chain["predictions_sha256"] != v1_manifest["blinded_predictions.csv"]
            or chain["protocol_sha256"] != v1_manifest["frozen_protocol.json"]):
        raise UnblindingRefused(
            "v2 protocol's embedded v1 hashes disagree with the v1 manifest"
        )
    return report


def load_observed() -> dict[str, dict]:
    """新闻层中第一次被许可读取 2026 年结果的地方。"""

    observed = {}
    with HOLDOUT.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            observed[row["candidate_contest_id"]] = {
                "observed_vote_share": float(row["observed_vote_share"]),
                "observed_elected": row["observed_elected"],
                "baseline_predicted_share": float(row["predicted_vote_share"]),
                "baseline_predicted_elected": row["predicted_elected"],
                "election_id": row["election_id"],
                "division_id": row["division_id"],
                "is_reform_uk": row["is_reform_uk"],
            }
    return observed


def _metric_block(rows: list[dict], prediction_key: str) -> dict:
    """按行计算的 MAE/RMSE，形式与冻结实验相同。"""

    if not rows:
        return {"rows": 0}
    errors = np.array([
        row[prediction_key] - row["observed_vote_share"] for row in rows
    ])
    return {
        "rows": len(rows),
        "contests": len({(row["election_id"], row["division_id"])
                         for row in rows}),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
    }


def _seat_accuracy(rows: list[dict], flag_key: str) -> dict:
    """当选 / 未当选判断正确的候选人行所占的比例。"""

    if not rows:
        return {"rows": 0}
    correct = sum(
        1 for row in rows
        if str(row[flag_key]) == str(row["observed_elected"])
    )
    return {"rows": len(rows), "correct": correct,
            "accuracy": round(correct / len(rows), 4)}


def _bootstrap_rows(rows: list[dict], comparator_key: str) -> list[dict]:
    return [
        {
            "election_id": row["election_id"],
            "area_id": row["division_id"],
            "baseline_absolute_error":
                abs(row[comparator_key] - row["observed_vote_share"]),
            "news_absolute_error":
                abs(row["news_enhanced_prediction"]
                    - row["observed_vote_share"]),
        }
        for row in rows
    ]


def score_specification(spec_rows: list[dict], observed: dict,
                        *, with_bootstrap: bool) -> dict:
    """为一个 (variant, analysis, period) 预测行块评分。"""

    joined = []
    for row in spec_rows:
        outcome = observed[row["candidate_contest_id"]]
        joined.append({
            **outcome,
            "supported": row["included_in_reported_metrics"] == "True",
            "is_reform": row["is_reform_uk"] == "True",
            "baseline_prediction": float(row["baseline_prediction"]),
            "recalibrated_prediction": float(row["recalibrated_prediction"]),
            "news_enhanced_prediction":
                float(row["news_enhanced_prediction"]),
            "news_predicted_elected": row["news_predicted_elected"],
        })
    supported = [row for row in joined if row["supported"]]
    reform = [row for row in supported if row["is_reform"]]

    def scope(rows: list[dict]) -> dict:
        baseline = _metric_block(rows, "baseline_prediction")
        recalibrated = _metric_block(rows, "recalibrated_prediction")
        news = _metric_block(rows, "news_enhanced_prediction")
        return {
            "baseline": baseline,
            "recalibrated_without_news": recalibrated,
            "news_enhanced": news,
            "news_vs_raw_baseline_mae":
                baseline.get("mae", 0) - news.get("mae", 0),
            "news_vs_recalibrated_mae":
                recalibrated.get("mae", 0) - news.get("mae", 0),
        }

    result = {
        "all_supported_parties": scope(supported),
        "reform_uk": scope(reform),
        "seat_accuracy_news": _seat_accuracy(joined, "news_predicted_elected"),
    }
    if with_bootstrap:
        result["bootstrap_news_vs_recalibrated"] = bootstrap_improvement(
            _bootstrap_rows(supported, "recalibrated_prediction"))
        result["bootstrap_news_vs_raw_baseline"] = bootstrap_improvement(
            _bootstrap_rows(supported, "baseline_prediction"))
    return result


def _load_predictions(directory: Path) -> dict[tuple, list[dict]]:
    blocks: dict[tuple, list[dict]] = defaultdict(list)
    with (directory / "blinded_predictions.csv").open(
            encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["fit_variant"], row["analysis"], row["period"],
                   row["period_role"], row["analysis_role"])
            blocks[key].append(row)
    return blocks


def _is_confirmatory(version: str, key: tuple) -> bool:
    family = CONFIRMATORY[version]
    variant, analysis, _period, period_role, _role = key
    return (variant == family["fit_variant"]
            and analysis in family["analyses"]
            and period_role == family["period_role"])


def run_unblinding() -> dict:
    """核验、一次性读取结果、为所有内容评分，并按系列报告。"""

    if OUTPUT_DIR.exists():
        raise UnblindingRefused(
            f"{OUTPUT_DIR} already exists. The unblinding happens once; "
            "these results are final."
        )
    integrity = verify_freeze_integrity()
    observed = load_observed()

    results = {"integrity": integrity, "files": {}}
    baseline_rows = [
        {**outcome,
         "baseline_prediction": outcome["baseline_predicted_share"]}
        for outcome in observed.values()
        # 只在 2026 年的两场主要选举上为基线评分，
        # 与每个冻结预测文件覆盖的范围相同。
        if outcome["election_id"].startswith("surrey-county-council-2026")
    ]
    results["baseline_all_2026_rows"] = _metric_block(
        baseline_rows, "baseline_prediction")
    results["baseline_seat_accuracy"] = _seat_accuracy(
        baseline_rows, "baseline_predicted_elected")
    reform_baseline = [row for row in baseline_rows
                      if row["is_reform_uk"] == "True"]
    results["baseline_reform_rows"] = _metric_block(
        reform_baseline, "baseline_prediction")
    results["baseline_reform_seat_accuracy"] = _seat_accuracy(
        reform_baseline, "baseline_predicted_elected")

    for version, directory in (("v1", V1_DIR), ("v2", V2_DIR)):
        blocks = _load_predictions(directory)
        scored = []
        for key in sorted(blocks):
            confirmatory = _is_confirmatory(version, key)
            entry = {
                "fit_variant": key[0], "analysis": key[1], "period": key[2],
                "period_role": key[3], "analysis_role": key[4],
                "family": "confirmatory" if confirmatory else "sensitivity",
                "metrics": score_specification(
                    blocks[key], observed, with_bootstrap=confirmatory),
            }
            scored.append(entry)
        results["files"][version] = scored

    return results


def render_findings(results: dict) -> str:
    """完整报告两个系列。只有计数和列表；不排名。"""

    def family_table(version: str) -> list[str]:
        rows = [e for e in results["files"][version]
                if e["family"] == "confirmatory"]
        lines = [
            "| analysis | window | baseline MAE | recalibrated MAE | "
            "news MAE | news vs recalibrated | 95% CI | Reform news MAE | "
            "Reform vs recalibrated |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
        ]
        for entry in rows:
            overall = entry["metrics"]["all_supported_parties"]
            reform = entry["metrics"]["reform_uk"]
            ci = entry["metrics"]["bootstrap_news_vs_recalibrated"]
            lines.append(
                f"| {entry['analysis']} | {entry['period']} | "
                f"{overall['baseline']['mae']:.4f} | "
                f"{overall['recalibrated_without_news']['mae']:.4f} | "
                f"{overall['news_enhanced']['mae']:.4f} | "
                f"{overall['news_vs_recalibrated_mae']:+.4f} | "
                f"[{ci.get('improvement_ci_lower', 0):+.4f}, "
                f"{ci.get('improvement_ci_upper', 0):+.4f}] | "
                f"{reform['news_enhanced']['mae']:.4f} | "
                f"{reform['news_vs_recalibrated_mae']:+.4f} |"
            )
        improved = sum(
            1 for entry in rows
            if entry["metrics"]["all_supported_parties"]
            ["news_vs_recalibrated_mae"] > 0)
        improved_raw = sum(
            1 for entry in rows
            if entry["metrics"]["all_supported_parties"]
            ["news_vs_raw_baseline_mae"] > 0)
        lines += [
            "",
            f"- **{improved} of {len(rows)}** confirmatory comparisons "
            "improve overall MAE over the recalibrated control; "
            f"**{improved_raw} of {len(rows)}** over the untouched baseline.",
        ]
        return lines

    def sensitivity_counts(version: str) -> str:
        rows = [e for e in results["files"][version]
                if e["family"] == "sensitivity"]
        improved = sum(
            1 for entry in rows
            if entry["metrics"]["all_supported_parties"]
            ["news_vs_recalibrated_mae"] > 0)
        return (f"{improved} of {len(rows)} sensitivity comparisons improve "
                "on their recalibrated control (full detail in "
                "unblinding_results.json; sensitivity results cannot be "
                "promoted).")

    baseline = results["baseline_all_2026_rows"]
    reform_baseline = results["baseline_reform_rows"]
    seats = results["baseline_seat_accuracy"]
    reform_seats = results["baseline_reform_seat_accuracy"]
    return "\n".join([
        "# The 2026 unblinding",
        "",
        "**One-time confirmatory comparison, performed on the frozen,",
        "hash-verified prediction files. Every specification is reported;",
        "nothing was selected after outcomes were seen.**",
        "",
        "## The untouched baseline on 2026",
        "",
        f"- Overall MAE {baseline['mae']:.4f} across {baseline['rows']} "
        f"candidate rows in {baseline['contests']} two-member wards; "
        f"seat-call accuracy {seats['accuracy']:.4f}.",
        f"- Reform UK: MAE {reform_baseline['mae']:.4f} over "
        f"{reform_baseline['rows']} rows; seat-call accuracy "
        f"{reform_seats['accuracy']:.4f}.",
        "",
        "## Confirmatory family - v1 primary (pooled 2017+2021)",
        "",
        *family_table("v1"),
        "",
        "## Confirmatory family - v2 enrichment (2017+2021+by-elections)",
        "",
        *family_table("v2"),
        "",
        "## Sensitivity families",
        "",
        f"- v1: {sensitivity_counts('v1')}",
        f"- v2: {sensitivity_counts('v2')}",
        "",
        "## Interpretation rule (pre-declared, reproduced verbatim in the",
        "frozen protocols)",
        "",
        "No specification, window, arm or variant may be selected or",
        "promoted because of these numbers. The confirmatory counts above,",
        "with their bootstrap intervals, are the project's answer to the",
        "supervisor's central question.",
        "",
    ])


def main() -> None:
    results = run_unblinding()
    OUTPUT_DIR.mkdir(parents=True)
    (OUTPUT_DIR / "unblinding_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")
    findings = render_findings(results)
    (OUTPUT_DIR / "unblinding_findings.md").write_text(
        findings, encoding="utf-8")
    print(findings)
    print(f"-> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
