"""冻结新闻层的盲化 2026 年预测。

导师的设计以一项检验收尾："The most important test is whether adding news
context improves prediction on an election that was not used to train the
model"（最重要的检验是：在一场未被用于训练模型的选举上，加入新闻语境能否
改善预测），并且必须是盲化的 ——"predictions are saved first and only then
compared to reality"（先保存预测，然后才与现实比较）。本模块生成的就是那个
"先保存"的文件。它是第一段被允许打开第一阶段留出集文件的新闻层代码，而且
打开它只有一个目的：复制 2026 年候选人行的身份列和*预测*列。所有观测列都在
加载时被剥离，本模块中没有任何函数计算误差、指标或任何形式的比较。揭盲是
一个单独的、之后的、唯一一次的事件。

两个拟合变体，都在看到任何 2026 年结果之前于此冻结
----------------------------------------------------------------------
**pooled_2017_2021（主变体）。** 导师的划分是：2013-2019 年训练，2021 年
验证，2026 年最终测试。基于验证的选择已经完成 —— 而且它什么也没选中：18 个
已确认窗口的比较中有 0 个得到改进 —— 标准的最后一步是在训练集加验证集上
重新拟合。合并使残差模型的拟合行从五个 选举 x 政党 行增加到最多十一个，并且
借助 2021 年获得了它唯一的英国改革党残差观测。选择这个变体作为主变体是现在、
在盲化状态下做出并记录的；它没有参考任何 2026 年的结果，在揭盲之后也不能
重新考虑。

**fit_2017_only（协议复现）。** 与冻结的 2026 年之前实验完全相同的拟合，
原封不动地应用于 2026 年的特征。之所以保留，是因为 2026 年之前的结论是在
这个协议下得出的，因此必须在合并重拟合之外，同时存在对该协议的 2026 年检验。

其他一切都原封不动地沿用自冻结的实验：三个冻结的特征组、十二个时间段、固定
为 1.0 的岭回归惩罚系数、政党平均残差目标（绝不做按候选人的伪重复）、只对
经过审计的结构性空白做零值替换、在每个竞选单元内先截断负值再重新归一化，
以及"不受支持的小党不做调整、但仍保留在分母中"的规则。

本文件不做什么
--------------------------
它不读取 2026 年观测到的得票率、排名或当选标记；它不计算任何误差；它不在
各设定之间做选择。已声明的揭盲结构（哪些比较是主要的、哪些是敏感性分析）
被写入协议 JSON，因此之后的比较步骤已经没有任何自由度可言。
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np

from news_modelling.news_estimator import RidgeModel
from news_modelling.production_news_experiment import (
    FIT_ELECTION,
    FIT_NEWS_ELECTION,
    FIXED_RIDGE_PENALTY,
    VALIDATION_ELECTION,
    VALIDATION_NEWS_ELECTION,
    ProductionExperimentError,
    _feature_index,
    _float_or_structural_zero,
    _truthy,
    aggregate_fitting_residuals,
    party_key,
    validate_inputs,
)

# 为最终测试而留出的两场第一阶段选举。两者都映射到
# 同一个新闻选举 ESWS-2026-05：语料库是针对 2026 年 5 月
# 这一整个事件收集的，而东 / 西萨里只是同一投票日的行政划分，
# 并不是两个不同的新闻环境。
HOLDOUT_ELECTIONS = (
    "surrey-county-council-2026-east-surrey",
    "surrey-county-council-2026-west-surrey",
)
HOLDOUT_NEWS_ELECTION = "ESWS-2026-05"
HOLDOUT_SPLIT_ROLE = "primary_holdout"

# 携带 2026 年结果或由其派生的列。它们在
# 读取留出集文件的那一刻就被移除，绝不能出现在本模块写出的
# 任何输出中。盲化被执行两次：一次在加载时
# （strip_outcome_columns），一次在写出时（assert_blind_fieldnames）。
OUTCOME_COLUMNS = (
    "observed_vote_share",
    "observed_rank",
    "observed_elected",
    "error",
    "absolute_error",
    "squared_error",
)

# 主拟合变体，在揭盲之前声明。在预测文件已经存在之后
# 修改这个常量会在 git 中留下痕迹，并且
# 被它所写出的协议禁止。
PRIMARY_VARIANT = "pooled_2017_2021"


class BlindingViolation(RuntimeError):
    """某个输入或输出会把 2026 年的结果暴露给新闻层。"""


def strip_outcome_columns(rows: Iterable[dict]) -> list[dict]:
    """返回 ``rows`` 的副本，其中所有结果列都已移除。

    第一阶段模型包在训练时为它自己的留出集打过分，所以磁盘上的文件包含
    观测列。新闻层最多只能把它们带到这个函数为止，不能再往前带。
    """

    cleaned = []
    for row in rows:
        cleaned.append({
            key: value for key, value in row.items()
            if key not in OUTCOME_COLUMNS
        })
    return cleaned


def assert_blind_fieldnames(fieldnames: Iterable[str]) -> None:
    """拒绝任何提到了结果列的输出 schema。"""

    exposed = sorted(set(fieldnames) & set(OUTCOME_COLUMNS))
    if exposed:
        raise BlindingViolation(
            f"Output would contain outcome columns: {exposed}. The blinded "
            "prediction file may carry predictions only."
        )


def sanitise_holdout_rows(rows: list[dict]) -> list[dict]:
    """把留出集文件筛选为 2026 年主要选举的行，并对它们进行盲化。

    2026 年 5 月之后的补选也在留出集文件中，但新闻层在 7 月 30 日已把补选
    排除在范围之外，没有它们的特征行，所以它们被排除，而不是被悄悄地给予
    零调整。
    """

    principal = [
        row for row in rows if row.get("election_id") in HOLDOUT_ELECTIONS
    ]
    if not principal:
        raise ProductionExperimentError(
            "No 2026 principal-election rows found in the holdout file."
        )
    wrong_role = {
        str(row.get("split_role")) for row in principal
        if str(row.get("split_role")) != HOLDOUT_SPLIT_ROLE
    }
    if wrong_role:
        raise ProductionExperimentError(
            f"2026 principal rows carry unexpected split roles {sorted(wrong_role)}."
        )

    blinded = strip_outcome_columns(principal)

    # 剥离必须真的生效；一个被改名的结果列会让它
    # 悄无声息地失效，所以要对照已声明的列表进行核验。
    for row in blinded:
        leaked = sorted(set(row) & set(OUTCOME_COLUMNS))
        if leaked:
            raise BlindingViolation(f"Outcome columns survived the strip: {leaked}")

    identifiers = [str(row["candidate_contest_id"]) for row in blinded]
    if len(identifiers) != len(set(identifiers)):
        raise ProductionExperimentError(
            "Duplicate candidate_contest_id rows in the 2026 holdout input."
        )
    merged = [
        identifier for identifier, row in zip(identifiers, blinded)
        if _truthy(row.get("is_reform_uk")) and _truthy(row.get("is_ukip"))
    ]
    if merged:
        raise ProductionExperimentError(
            f"{len(merged)} 2026 row(s) merge Reform UK and UKIP."
        )
    return blinded


def aggregate_pooled_residuals(oof_rows: Iterable[dict]) -> list[dict]:
    """2017 年和 2021 年合在一起，每个 (选举, 政党) 一行残差。

    与冻结实验相同的"避免伪重复"规则：新闻值是按 选举 x 政党 存在的，因此
    拟合时每个 选举 x 政党 只看到一个平均残差，而绝不是数百行被复制的
    候选人数据。
    """

    residuals: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in oof_rows:
        election = row.get("election_id")
        if election not in (FIT_ELECTION, VALIDATION_ELECTION):
            continue
        key = party_key(row.get("standard_party_name"))
        if key is None:
            continue
        residuals[(election, key)].append(
            float(row["observed_vote_share"]) - float(row["predicted_vote_share"])
        )

    # 英国改革党在 2017 年还不存在；出现 2017 年的改革党行就意味着
    # 政党连接出了问题，科学设定也是错的。
    if (FIT_ELECTION, "reform_uk") in residuals:
        raise ProductionExperimentError("Unexpected Reform row in 2017 fitting data.")
    # 合并变体的全部意义包括那唯一一条 2021 年的改革党
    # 观测。缺少它会改变主变体的含义，
    # 所以对它进行断言，而不是容忍其缺失。
    if (VALIDATION_ELECTION, "reform_uk") not in residuals:
        raise ProductionExperimentError("The 2021 Reform residual row is missing.")

    news_election = {
        FIT_ELECTION: FIT_NEWS_ELECTION,
        VALIDATION_ELECTION: VALIDATION_NEWS_ELECTION,
    }
    rows = [
        {
            "election_id": election,
            "news_election_id": news_election[election],
            "party_key": key,
            "candidate_rows": len(values),
            "mean_residual": float(np.mean(values)),
        }
        for (election, key), values in sorted(residuals.items())
    ]
    if len(rows) < 8:
        raise ProductionExperimentError(
            f"Only {len(rows)} pooled fitting rows; expected the 2017 and "
            "2021 party families together."
        )
    return rows


def _fitting_rows_for_variant(variant: str, oof_rows: list[dict]) -> list[dict]:
    """返回某个已声明变体的冻结拟合行。"""

    if variant == "pooled_2017_2021":
        return aggregate_pooled_residuals(oof_rows)
    if variant == "fit_2017_only":
        # 复用实验自身的聚合器，使复现变体
        # 不可能偏离它所复现的协议。
        fitting = aggregate_fitting_residuals(oof_rows)
        return [
            {**row, "election_id": FIT_ELECTION,
             "news_election_id": FIT_NEWS_ELECTION}
            for row in fitting.values()
        ]
    raise ProductionExperimentError(f"Unknown fitting variant: {variant!r}")


def _fit_specification(
    fitting_rows: list[dict],
    feature_index: dict,
    *,
    period: str,
    feature_columns: list[str],
) -> tuple[RidgeModel, dict]:
    """在该变体的政党平均残差上，为一个 组 / 时间段 拟合岭回归。"""

    design = np.array([
        [
            _float_or_structural_zero(
                feature_index[(row["news_election_id"], row["party_key"], period)],
                column,
            )
            for column in feature_columns
        ]
        for row in fitting_rows
    ], dtype=float)
    target = np.array([row["mean_residual"] for row in fitting_rows], dtype=float)
    model = RidgeModel(FIXED_RIDGE_PENALTY).fit(design, target)
    record = {
        "training_rows": len(fitting_rows),
        "training_reform_rows": sum(
            1 for row in fitting_rows if row["party_key"] == "reform_uk"
        ),
        "intercept_mean_training_residual": model.intercept,
        "standardised_coefficients": {
            column: float(value)
            for column, value in zip(feature_columns, model.coefficients)
        },
    }
    return model, record


def _normalise_contests(rows: list[dict], raw_column: str, output_column: str) -> int:
    """截断为负的原始得票率，并把每个竞选单元重新归一化为 100。

    第一阶段自身的 2026 年预测在每个竞选单元中的总和恰好为 100
    （normalisation_status = 'normalised'），所以 100 是正确的目标，新闻调整
    不能悄悄改变基线的尺度。竞选单元的键包含选举，因为东萨里和西萨里是
    两场独立的第一阶段选举。
    """

    by_contest: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_contest[(row["election_id"], row["division_id"])].append(row)

    clipped = 0
    for contest_rows in by_contest.values():
        raw = []
        for row in contest_rows:
            value = float(row[raw_column])
            if value < 0:
                clipped += 1
                value = 0.0
            raw.append(value)
        total = sum(raw)
        if total <= 0:
            raise ProductionExperimentError("A contest has no positive prediction.")
        for row, value in zip(contest_rows, raw):
            row[output_column] = 100.0 * value / total
    return clipped


def _assign_ranks(rows: list[dict], share_column: str, seats_column: str) -> None:
    """确定性的竞选单元内排名和席位分配。

    平局按 candidate_contest_id 打破，因此本模块的两次运行永远不会得出不同
    结果；打破平局的规则记录在协议中。"当选"指排名在该竞选单元的席位数
    之内，而对于 2026 年来说席位数是选举前就已知的事实（双席位分区）。
    """

    by_contest: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_contest[(row["election_id"], row["division_id"])].append(row)

    for contest_rows in by_contest.values():
        seats = int(contest_rows[0][seats_column])
        ordered = sorted(
            contest_rows,
            key=lambda row: (-float(row[share_column]),
                             str(row["candidate_contest_id"])),
        )
        for position, row in enumerate(ordered, start=1):
            row["news_predicted_rank"] = position
            row["news_predicted_elected"] = position <= seats


def predict_specification(
    blinded_rows: list[dict],
    feature_index: dict,
    model: RidgeModel,
    *,
    period: str,
    feature_columns: list[str],
) -> tuple[list[dict], dict]:
    """把一个拟合好的设定应用到每一行盲化的 2026 年候选人数据上。

    与冻结实验完全对应：受支持的政党获得模型的调整量（新闻特征加截距），
    不受支持的小党不做调整但仍保留在分母中，并且重新校准的对照组预测和
    新闻增强后的预测都会按竞选单元进行截断和重新归一化。
    """

    rows = [dict(row) for row in blinded_rows]
    for row in rows:
        key = party_key(row.get("standard_party_name"))
        row["party_key"] = key
        row["baseline_prediction"] = float(row["predicted_vote_share"])
        row["news_adjustment"] = 0.0
        if key is not None:
            feature = feature_index[(HOLDOUT_NEWS_ELECTION, key, period)]
            vector = np.array([[
                _float_or_structural_zero(feature, column)
                for column in feature_columns
            ]], dtype=float)
            row["news_adjustment"] = float(model.predict(vector)[0])
        row["raw_recalibrated"] = (
            row["baseline_prediction"]
            + (model.intercept if key is not None else 0.0)
        )
        row["raw_news_enhanced"] = (
            row["baseline_prediction"] + row["news_adjustment"]
        )

    clipped = {
        "recalibrated": _normalise_contests(
            rows, "raw_recalibrated", "recalibrated_prediction"
        ),
        "news_enhanced": _normalise_contests(
            rows, "raw_news_enhanced", "news_enhanced_prediction"
        ),
    }
    _assign_ranks(rows, "news_enhanced_prediction", "analysis_number_of_seats")
    return rows, clipped


def build_blinded_predictions(
    oof_rows: list[dict],
    holdout_rows: list[dict],
    features: list[dict],
    audit: dict,
) -> tuple[dict, list[dict]]:
    """在两个变体下拟合每一个冻结的设定，并预测 2026 年。

    返回协议记录和预测行。返回值中不包含任何 2026 年的结果；
    ``sanitise_holdout_rows`` 在形成任何预测之前就已把它们移除。
    """

    validate_inputs(oof_rows, audit)
    blinded = sanitise_holdout_rows(holdout_rows)
    feature_index = _feature_index(features)
    periods = (
        audit["feature_table"]["windows"]
        + audit["feature_table"]["cumulative_periods"]
    )

    specification_records = []
    prediction_rows: list[dict] = []
    variants = ("pooled_2017_2021", "fit_2017_only")
    for variant in variants:
        fitting_rows = _fitting_rows_for_variant(variant, oof_rows)
        for analysis_name, specification in audit["frozen_feature_sets"].items():
            for period in periods:
                columns = list(specification["columns"])
                model, fit_record = _fit_specification(
                    fitting_rows, feature_index,
                    period=period, feature_columns=columns,
                )
                rows, clipped = predict_specification(
                    blinded, feature_index, model,
                    period=period, feature_columns=columns,
                )
                period_role = (
                    "confirmed_window" if "previous_" not in period
                    else "cumulative_sensitivity"
                )
                specification_records.append({
                    "fit_variant": variant,
                    "analysis": analysis_name,
                    "analysis_role": specification["analysis_role"],
                    "period": period,
                    "period_role": period_role,
                    "feature_columns": columns,
                    "ridge_penalty": FIXED_RIDGE_PENALTY,
                    "negative_raw_shares_clipped": clipped,
                    **fit_record,
                })
                for row in rows:
                    prediction_rows.append({
                        "fit_variant": variant,
                        "analysis": analysis_name,
                        "analysis_role": specification["analysis_role"],
                        "period": period,
                        "period_role": period_role,
                        "election_id": row["election_id"],
                        "candidate_contest_id": row["candidate_contest_id"],
                        "division_id": row["division_id"],
                        "standard_party_name": row["standard_party_name"],
                        "party_key": row["party_key"] or "",
                        "included_in_reported_metrics": row["party_key"] is not None,
                        "is_reform_uk": row["party_key"] == "reform_uk",
                        "is_ukip": row["party_key"] == "ukip",
                        "analysis_number_of_seats": row["analysis_number_of_seats"],
                        "baseline_prediction": row["baseline_prediction"],
                        "recalibrated_prediction": row["recalibrated_prediction"],
                        "news_adjustment_before_contest_normalisation":
                            row["news_adjustment"],
                        "news_enhanced_prediction": row["news_enhanced_prediction"],
                        "news_predicted_rank": row["news_predicted_rank"],
                        "news_predicted_elected": row["news_predicted_elected"],
                    })

    protocol = {
        "status": "blinded_2026_predictions_frozen",
        "canonical_release_id": audit["canonical_release"]["release_id"],
        "holdout_elections": list(HOLDOUT_ELECTIONS),
        "holdout_news_election": HOLDOUT_NEWS_ELECTION,
        "blinded_candidate_rows": len(blinded),
        "outcome_columns_stripped_at_load": list(OUTCOME_COLUMNS),
        "fit_variants": {
            "pooled_2017_2021": (
                "primary: refit on train plus completed validation (2017 + "
                "2021 election x party mean residuals), the supervisor's "
                "split structure; includes the single 2021 Reform residual row"
            ),
            "fit_2017_only": (
                "protocol replication of the frozen pre-2026 experiment "
                "(five 2017 party rows, no Reform); reported as sensitivity"
            ),
        },
        "primary_fit_variant": PRIMARY_VARIANT,
        "ridge_penalty": FIXED_RIDGE_PENALTY,
        "penalty_selection": "fixed_before_validation; unchanged from the frozen experiment",
        "tie_break_rule": (
            "within-contest ranks order by news-enhanced share descending, "
            "then candidate_contest_id ascending"
        ),
        "periods": periods,
        "specifications": specification_records,
        "unblinding_rule": (
            "One unblinding event only. Report every specification in this "
            "file. The primary confirmatory family is the combined and "
            "national arms over the six confirmed windows under the "
            "pooled_2017_2021 variant, each compared against its recalibrated "
            "control on overall MAE. The local arm, cumulative periods and "
            "the fit_2017_only variant are sensitivity results. No "
            "specification, window, arm or variant may be selected or "
            "promoted after outcomes are seen. Reform UK rows are reported "
            "separately with their row count visible; coefficients are "
            "party-generic, not Reform-specific, and not causal."
        ),
    }
    return protocol, prediction_rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_outputs(
    protocol: dict,
    predictions: list[dict],
    output_dir: str | Path,
    *,
    input_paths: dict[str, Path],
) -> dict:
    """写出冻结的协议、盲化预测及其哈希。

    拒绝覆盖：这个文件的全部价值就在于，在任何人查看 2026 年结果之前，它就
    已经存在并且未被改动。重建需要手动删除该目录，而 git 会显示这一操作。"""

    output = Path(output_dir)
    predictions_path = output / "blinded_predictions.csv"
    if predictions_path.exists():
        raise BlindingViolation(
            f"{predictions_path} already exists. The blinded prediction file "
            "is frozen once written; delete the directory manually only if "
            "the freeze is being deliberately and visibly redone."
        )
    output.mkdir(parents=True, exist_ok=True)

    fieldnames = list(predictions[0])
    assert_blind_fieldnames(fieldnames)
    with predictions_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(predictions)

    # 输入哈希使冻结可以端到端地审计：即本次运行读取的确切的特征
    # 表、可估计性报告和第一阶段文件。
    protocol = dict(protocol)
    protocol["input_sha256"] = {
        name: _sha256(path) for name, path in sorted(input_paths.items())
    }
    protocol_path = output / "frozen_protocol.json"
    protocol_path.write_text(
        json.dumps(protocol, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "blinded_predictions.csv": _sha256(predictions_path),
        "frozen_protocol.json": _sha256(protocol_path),
        "prediction_rows": len(predictions),
        "note": (
            "Record these hashes in the evidence register. Any change to "
            "either file after the freeze is detectable against them."
        ),
    }
    manifest_path = output / "sha256_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
