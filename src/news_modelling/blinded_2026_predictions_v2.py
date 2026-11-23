"""冻结扩充模型的盲化 2026 年预测（v2）。

v1 冻结归档了扩充之前的模型。本模块归档的是扩充所改变的唯一一样东西：
拟合集。其他一切都刻意与 v1 保持一致 —— 三个冻结的特征组、十二个时间段、
固定的岭回归惩罚系数、政党平均残差目标、截断并重新归一化的后处理、结果列
剥离、拒绝覆盖的冻结 —— 并且是从 v1 模块导入而不是复制过来的，因此两次
冻结不可能出现偏差。

v2 新增了什么
------------
一个拟合变体 ``pooled_2017_2021_byelections``：在 2017 年和 2021 年主要选举
以及八场留出期之前的补选上，按 (选举 x 政党) 计算的第一阶段政党平均残差。
借助 2025 年的补选，这次拟合包含了真实的英国改革党残差单元格 —— 这在项目中
尚属首次 —— 并与来自正式版本 v2 的新闻特征相连接（改革党训练文章：300 篇，
而 v1 为零篇）。八场补选中有六场没有任何被准入的文章；在经过审计的零值政策
下，它们的单元格以零计数和结构性空白的占比进入，因为一场已被搜索但没有符合
资格报道的选举是一个观测，而不是一个空缺。

已声明的揭盲结构保持不变，并与 v1 共用：只有一次揭盲事件；验证性系列是
六个已确认时间窗口上的合并组和全国组，现在在本变体之下，与重新校准的对照组
比较；本地组、累积时间段以及所有 v1 变体都属于敏感性分析。在看到结果之后
不得做任何选择。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np

from news_collection.run_byelection_stages import BYELECTION_POLLING_DAYS
from news_modelling.blinded_2026_predictions import (
    HOLDOUT_NEWS_ELECTION,
    PRIMARY_VARIANT as V1_PRIMARY_VARIANT,
    _fit_specification,
    predict_specification,
    sanitise_holdout_rows,
    write_outputs,
)
from news_modelling.production_news_experiment import (
    FIT_ELECTION,
    FIT_NEWS_ELECTION,
    FIXED_RIDGE_PENALTY,
    VALIDATION_ELECTION,
    VALIDATION_NEWS_ELECTION,
    ProductionExperimentError,
    _feature_index,
    party_key,
    validate_inputs,
)

V2_VARIANT = "pooled_2017_2021_byelections"

# 每场拟合选举的 第一阶段选举 ID -> 新闻表选举 ID。
# 主要选举的 ID 在两个系统中不同；补选的 ID 在两边都是同一个
# 长格式字符串，这一点通过断言保证，而不是想当然。
FIT_ELECTION_MAP = {
    FIT_ELECTION: FIT_NEWS_ELECTION,
    VALIDATION_ELECTION: VALIDATION_NEWS_ELECTION,
    **{election_id: election_id for election_id in BYELECTION_POLLING_DAYS},
}


def aggregate_v2_residuals(oof_rows: Iterable[dict]) -> list[dict]:
    """每个 (拟合选举, 政党) 一行残差，包括补选。

    与之前每一次拟合相同的"避免伪重复"规则：新闻是按 选举 x 政党 存在的，
    因此拟合时每个单元格只看到一个平均残差，而绝不是每位候选人一个。这些
    检查编码了扩充声称要实现的内容：改革党必须不出现在 2017 年（当时它还
    不存在），并且至少出现在一个 2025 年补选单元格中（它参加了这些补选；
    缺少这些单元格的拟合会悄悄退回到 v1 那种不区分政党的设计）。
    """

    residuals: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in oof_rows:
        election = row.get("election_id")
        if election not in FIT_ELECTION_MAP:
            continue
        key = party_key(row.get("standard_party_name"))
        if key is None:
            continue
        residuals[(election, key)].append(
            float(row["observed_vote_share"]) - float(row["predicted_vote_share"])
        )

    if (FIT_ELECTION, "reform_uk") in residuals:
        raise ProductionExperimentError("Unexpected Reform row in 2017 fitting data.")
    reform_byelection_cells = [
        election for (election, key) in residuals
        if key == "reform_uk" and election in BYELECTION_POLLING_DAYS
    ]
    if not reform_byelection_cells:
        raise ProductionExperimentError(
            "No Reform residual cell from any by-election; the v2 fit would "
            "not contain the enrichment it exists to add."
        )

    rows = [
        {
            "election_id": election,
            "news_election_id": FIT_ELECTION_MAP[election],
            "party_key": key,
            "candidate_rows": len(values),
            "mean_residual": float(np.mean(values)),
        }
        for (election, key), values in sorted(residuals.items())
    ]
    if len(rows) < 20:
        raise ProductionExperimentError(
            f"Only {len(rows)} v2 fitting rows; expected the 2017, 2021 and "
            "by-election party families together."
        )
    return rows


def build_v2_blinded_predictions(
    oof_rows: list[dict],
    holdout_rows: list[dict],
    features: list[dict],
    audit: dict,
    *,
    v1_manifest: dict,
    release_id: str,
) -> tuple[dict, list[dict]]:
    """在 v2 变体下拟合每一个冻结的设定，并预测 2026 年。

    设定网格、岭回归惩罚系数和后处理都来自与 v1 相同的冻结来源；只有拟合
    行不同。返回值中不包含任何 2026 年的结果。"""

    validate_inputs(oof_rows, audit)
    blinded = sanitise_holdout_rows(holdout_rows)
    feature_index = _feature_index(features)
    # 在拟合任何模型之前，每个拟合单元格都必须能在 v2 表中找到：
    # 否则一个缺失的补选单元格会在拟合中途、在某个任意的设定上
    # 以 KeyError 的形式暴露出来。
    periods = (
        audit["feature_table"]["windows"]
        + audit["feature_table"]["cumulative_periods"]
    )
    fitting_rows = aggregate_v2_residuals(oof_rows)
    for row in fitting_rows:
        for period in periods:
            if (row["news_election_id"], row["party_key"], period) not in feature_index:
                raise ProductionExperimentError(
                    f"feature table v2 has no cell for "
                    f"{row['news_election_id']}/{row['party_key']}/{period}"
                )

    specification_records = []
    prediction_rows: list[dict] = []
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
                "fit_variant": V2_VARIANT,
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
                    "fit_variant": V2_VARIANT,
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

    reform_cells = [row for row in fitting_rows if row["party_key"] == "reform_uk"]
    protocol = {
        "status": "blinded_2026_predictions_v2_frozen",
        "canonical_release_id": release_id,
        "holdout_news_election": HOLDOUT_NEWS_ELECTION,
        "blinded_candidate_rows": len(blinded),
        "fit_variant": {
            V2_VARIANT: (
                "primary for the enrichment comparison: party-mean Stage 1 "
                "residuals per election x party over 2017, 2021 and the "
                "eight pre-holdout by-elections, joined to news feature "
                "table v2"
            ),
        },
        "fitting_rows": len(fitting_rows),
        "fitting_elections": sorted({row["election_id"] for row in fitting_rows}),
        "reform_fitting_cells": [
            {"election_id": row["election_id"],
             "candidate_rows": row["candidate_rows"]}
            for row in reform_cells
        ],
        "ridge_penalty": FIXED_RIDGE_PENALTY,
        "penalty_selection":
            "fixed_before_validation; unchanged from the frozen experiment",
        "periods": periods,
        "specifications": specification_records,
        "v1_freeze": {
            "predictions_sha256": v1_manifest["blinded_predictions.csv"],
            "protocol_sha256": v1_manifest["frozen_protocol.json"],
            "v1_primary_variant": V1_PRIMARY_VARIANT,
        },
        "unblinding_rule": (
            "One unblinding event covering the v1 and v2 files together. "
            "The enrichment's confirmatory family is the combined and "
            "national arms over the six confirmed windows under "
            f"{V2_VARIANT}, each against its recalibrated control on "
            "overall MAE, reported beside the v1 primary variant and the "
            "untouched baseline. The local arm, cumulative periods and all "
            "other variants are sensitivity. No specification, window, arm "
            "or variant may be selected or promoted after outcomes are "
            "seen. Reform UK rows are reported separately with their row "
            "count visible; v2 coefficients rest on "
            "real but few Reform fitting cells and are not causal."
        ),
    }
    return protocol, prediction_rows
