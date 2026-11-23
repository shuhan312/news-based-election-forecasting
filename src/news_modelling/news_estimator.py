"""新闻层估计器：方法 A（残差法）和方法 B（联合法）。

在此之前，`src/news_modelling/` 能够构建特征、选择特征并诊断覆盖情况，但其中
没有任何东西拟合模型 —— 项目的核心问题（"在选举历史基线之上，新闻能否改善对
英国改革党得票率的预测？"）没有任何代码能够回答。本模块就是这段代码。

按照研究设计的两种方法
---------------------------------------
**方法 A —— 残差法。** 对每一行符合条件的历史候选人数据，取第一阶段的折外
预测，构造

    residual = observed_vote_share - baseline_prediction

并只用新闻特征对该残差建模。最终预测为 ``baseline_prediction +
predicted_adjustment``。这是主要方法，因为它直接衡量研究问题所问的内容：
新闻是否携带了选举历史基线尚未拥有的信息。一个什么也预测不出来的残差模型，
就是"新闻在这里没有带来任何东西"最干净的表述。

**方法 B —— 联合法。** 在一个模型中拟合 ``observed ~ baseline_prediction +
news features``，让模型对基线重新加权，而不是把基线视为固定的。之所以与 A
比较，是因为两者失败的方式不同：A 无法重新缩放一个存在系统性偏差的基线，B
可以；但 B 也可能把新闻信号吸收进基线系数，从而报告一个实际上只是重新校准
的改进。同时报告两者可以让这种区别显露出来，而不是把它隐藏在一个数字里。

为什么用岭回归，为什么用闭式解
------------------------------
与无新闻基线的架构 A（`candidate_share_model.py`）的选择相同，理由也相同：
岭回归有一个可以手工核对的闭式解，而一个正确的弹性网络需要迭代求解器，
其收敛性本身就还需要论证。训练矩阵这么小 —— 某些折中改革党只有个位数的
行 —— 一个行为完全可检查的估计器，比一个也许能把特征选得稍好一点的估计器
更重要。

惩罚系数在每一折的训练行内部选择，绝不在被预测的行上选择。在评估行上调出
的惩罚系数会通过超参数泄露答案，这是整个项目所要避免的那种泄漏的一种隐蔽
形式。

本模块拒绝做什么
------------------------------
它不接触 2026 年 5 月 7 日的留出集。折的构造读取第一阶段的划分清单，并且只在
开发折上评估；留出集只能通过一个显式的、单独命名的调用才能访问，而比较框架
不会发出这个调用。导师的一贯约束是：2026 年留出集不得被用来选择任何东西，
而遵守这一点最安全的方式，就是让选择路径根本没有通往它的途径。

它也不做插补。没有基线预测或没有观测得票率的行会被丢弃，并记录原因 —— 相对于
一个未知基线的残差不是残差，而填补一个值会人为制造出两层之间的一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np

# 惩罚系数网格。跨越四个数量级，因为新闻的设计
# 矩阵比基线的小得多、共线性也强得多，所以
# 有用的惩罚系数无法事先知道；这么宽的网格使得
# 选出的值具有信息量，而不是一个狭窄范围造成的假象。
PENALTY_GRID = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)

# 如果拟合时的行数少于这个值，该折的估计仍会报告，但
# 会被标记。十行是一个界限：低于它，即使只有寥寥几列的岭回归拟合
# 描述的也只是它自身的噪声；设置这个标记是为了让读者
# 永远不会在没有附带警告的情况下看到这样的数字。
MIN_ROWS_FOR_STABLE_FIT = 10

# bootstrap 设置与基线模型包保持一致，使两层的区间
# 可以直接比较，而不仅仅是相似。
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260728


class RidgeModel:
    """闭式解的岭回归，经过中心化，使截距不被收缩。

    刻意几乎照抄基线的 `RidgeShareModel`，而不是导入它：基线模型包是冻结的，
    从中引用一个类会把新闻层与一个不得改变的包耦合在一起。这段运算足够短，
    复制它的代价比那种耦合要小。
    """

    def __init__(self, l2_penalty: float) -> None:
        if l2_penalty < 0:
            raise ValueError("The ridge L2 penalty must be non-negative.")
        self._l2 = float(l2_penalty)
        self._coefficients: np.ndarray | None = None
        self._intercept: float | None = None
        self._design_means: np.ndarray | None = None
        self._design_scales: np.ndarray | None = None

    def fit(self, design: np.ndarray, target: np.ndarray) -> "RidgeModel":
        if design.shape[0] != target.shape[0]:
            raise ValueError("Design matrix and target must align one-to-one.")
        if design.shape[0] == 0:
            raise ValueError("Cannot fit on an empty training set.")

        # 在这里做标准化，而不是指望调用方已经
        # 做过。新闻特征的尺度相差极大 —— 计数是
        # 几十的量级，情感比例在 [0,1] 之间，时效权重在
        # [0,1] 之间 —— 未经标准化的岭回归惩罚会悄悄地
        # 对计数列施加比比例列重数百倍的惩罚，
        # 而这是一个没有任何人做出过的建模决策。
        means = design.mean(axis=0)
        scales = design.std(axis=0)
        # 常数列的方差为零；除以零会
        # 产生 NaN，并在整个拟合过程中传播。这样的
        # 列本来就不携带任何信息，所以把它的缩放系数设为一
        # 并中心化为恰好为零，使它不产生任何贡献。
        scales = np.where(scales > 0, scales, 1.0)
        standardised = (design - means) / scales

        target_mean = float(target.mean())
        centred_target = target - target_mean

        # w = (X'X + lambda I)^-1 X'y，以求解线性方程组的方式计算，而不是
        # 显式求逆，以便在共线矩阵上保持数值稳定。
        # 对两边都做中心化，使截距不进入
        # 被惩罚的方程组：截距就是训练集均值，不被收缩。
        n_features = standardised.shape[1]
        gram = standardised.T @ standardised + self._l2 * np.eye(n_features)
        self._coefficients = np.linalg.solve(
            gram, standardised.T @ centred_target)
        self._design_means = means
        self._design_scales = scales
        self._intercept = target_mean
        return self

    def predict(self, design: np.ndarray) -> np.ndarray:
        if self._coefficients is None:
            raise ValueError("The model must be fitted before predicting.")
        if design.shape[1] != self._coefficients.shape[0]:
            raise ValueError(
                "Design matrix has a different width than at fit time.")
        standardised = (design - self._design_means) / self._design_scales
        return standardised @ self._coefficients + self._intercept

    @property
    def coefficients(self) -> np.ndarray:
        """标准化设计矩阵上的系数，而不是原始列上的系数。

        因为 ``fit`` 在内部做了标准化，这里的系数应理解为"该特征每变化一个
        标准差时目标的变化量"，而不是每变化一个单位。一个原始效应为每篇文章
        1.5、标准差为 1.7 篇文章的特征，在这里大约显示为 2.6。这是比较单位
        不同的特征（计数对比例）时的正确尺度，但不得把它报告为每篇文章的效应。
        要还原每篇文章的效应，请除以该特征在训练集上的标准差，
        ``feature_scales`` 提供了这一可能。
        """
        if self._coefficients is None:
            raise ValueError("The model has not been fitted.")
        return self._coefficients.copy()

    @property
    def feature_scales(self) -> np.ndarray:
        """用于标准化每一列的训练集标准差。

        公开出来，是为了在需要把结果表述为"每篇文章"而不是"每个标准差"时，
        能把系数换算回特征自身的单位。常数列在这里为 1.0，即拟合时所使用的
        替代值。"""
        if self._design_scales is None:
            raise ValueError("The model has not been fitted.")
        return self._design_scales.copy()

    @property
    def intercept(self) -> float:
        if self._intercept is None:
            raise ValueError("The model has not been fitted.")
        return self._intercept

    @property
    def l2_penalty(self) -> float:
        return self._l2


def design_matrix(rows: Sequence[Mapping[str, object]],
                  columns: Sequence[str]) -> np.ndarray:
    """行 x 命名列组成的浮点矩阵，缺失值按零读取。

    零是这些特定列、而且只是这些列的正确填充值：每个新闻特征都是计数、占比
    或对文章的加权和，因此"没有文章贡献"确实就是零。这不是一条通用的插补
    规则，不得用于基线的预测变量 —— 在那里，缺失的上一届得票率意味着"未知"，
    而不是"没有人投票"，基线版本中关于空值语义的文档正是为了保护这一区别
    而存在的。
    """
    return np.array(
        [[float(row.get(c) or 0.0) for c in columns] for row in rows],
        dtype=float)


def select_penalty(design: np.ndarray, target: np.ndarray,
                   groups: Sequence[str]) -> tuple[float, dict]:
    """在训练行内部用留一组法（leave-one-group-out）选择 L2 惩罚系数。

    组是竞选单元（选举 x 选区）。留出整个竞选单元而不是单独的行很重要，
    因为同一竞选单元中的候选人共享相同的新闻：按行划分会让模型在预测某个
    竞选单元的其余部分时，看到该竞选单元的一部分新闻，从而选出一个针对
    这种优势调好的惩罚系数。

    返回惩罚系数以及尝试过的内容的记录，使这一选择出现在输出中，而不仅仅
    存在于拟合好的对象里。
    """
    unique_groups = sorted(set(groups))
    scores: dict[float, float] = {}

    # 只有一个组时，没有东西可以留出。返回网格的
    # 中点并如实说明是诚实的做法；而悄悄返回样本内最好的
    # 惩罚系数，等于报告一个从未经过检验的调参值。
    if len(unique_groups) < 2:
        return 1.0, {"method": "default_no_inner_split",
                     "reason": f"only {len(unique_groups)} contest(s) in "
                               f"the training rows, so no held-out group "
                               f"exists to score a penalty against",
                     "penalty": 1.0}

    group_array = np.array(groups)
    for penalty in PENALTY_GRID:
        errors = []
        for held in unique_groups:
            mask = group_array != held
            if mask.sum() == 0 or (~mask).sum() == 0:
                continue
            try:
                model = RidgeModel(penalty).fit(design[mask], target[mask])
            except (ValueError, np.linalg.LinAlgError):
                # 在这个惩罚系数下方程组奇异，说明该惩罚系数
                # 对这个设计来说太小；把它记录为不可用，而不是
                # 让整个扫描过程崩溃。
                errors = None
                break
            predicted = model.predict(design[~mask])
            errors.extend(np.abs(predicted - target[~mask]).tolist())
        if errors:
            scores[penalty] = float(np.mean(errors))

    if not scores:
        return 1.0, {"method": "default_all_penalties_unusable",
                     "penalty": 1.0}
    best = min(scores, key=scores.get)
    return best, {"method": "leave_one_contest_out",
                  "penalty": best,
                  "mean_absolute_error_by_penalty":
                      {str(k): round(v, 5) for k, v in scores.items()}}


@dataclass
class FoldFit:
    """一折的拟合及其预测，附带该折自身的诊断。"""

    fold: str
    approach: str
    train_rows: int
    test_rows: int
    train_reform_rows: int
    test_reform_rows: int
    penalty: float
    penalty_choice: dict
    feature_columns: list[str]
    coefficients: dict[str, float]
    intercept: float
    predictions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_reform(row: Mapping[str, object]) -> bool:
    return str(row.get("standard_party_name") or
               row.get("party_id") or "").strip().lower() in (
        "reform uk", "reform_uk")


def fit_fold(train: Sequence[Mapping[str, object]],
             test: Sequence[Mapping[str, object]],
             feature_columns: Sequence[str],
             *, approach: str, fold_name: str) -> FoldFit:
    """在一折上拟合一种方法，并预测其测试行。

    ``approach`` 为 "residual"（目标：观测值减去基线）或 "joint"（目标：观测值，
    并把基线预测作为额外的一列纳入）。两者只在目标以及基线是否作为特征这两点
    上不同 —— 其他一切都刻意保持一致，这样它们结果上的任何差异都可以归因于
    这一选择，而不是两条分叉的流水线。
    """
    if approach not in ("residual", "joint"):
        raise ValueError(f"Unknown approach: {approach!r}")

    columns = list(feature_columns)
    if approach == "joint":
        # 基线预测作为一个特征进入，模型可以
        # 对它重新加权。明确命名它，使它在系数表中
        # 可见 —— 如果一个联合模型的新闻系数全部为零、
        # 基线系数为 1.0，那么它什么也没发现，而这一点
        # 应该一眼就能看出来。
        columns = columns + ["baseline_prediction"]

    def target_of(rows):
        if approach == "residual":
            return np.array([float(r["residual"]) for r in rows])
        return np.array([float(r["observed_vote_share"]) for r in rows])

    warnings: list[str] = []
    train_design = design_matrix(train, columns)
    train_target = target_of(train)
    groups = [f"{r.get('election_id')}|{r.get('area_id')}" for r in train]

    if len(train) < MIN_ROWS_FOR_STABLE_FIT:
        warnings.append(
            f"fitted on {len(train)} rows, below the {MIN_ROWS_FOR_STABLE_FIT}"
            f"-row threshold for a stable ridge fit - treat the coefficients "
            f"as descriptive, not as estimates")

    penalty, penalty_choice = select_penalty(train_design, train_target, groups)
    model = RidgeModel(penalty).fit(train_design, train_target)

    predictions = []
    if test:
        test_design = design_matrix(test, columns)
        raw = model.predict(test_design)
        for row, value in zip(test, raw):
            baseline = float(row["predicted_vote_share"])
            if approach == "residual":
                adjustment = float(value)
                final = baseline + adjustment
            else:
                adjustment = float(value) - baseline
                final = float(value)
            predictions.append({
                "election_id": row.get("election_id"),
                "area_id": row.get("area_id"),
                "party": row.get("standard_party_name") or row.get("party_id"),
                "is_reform_uk": _is_reform(row),
                "observed_vote_share": float(row["observed_vote_share"]),
                "baseline_prediction": baseline,
                "news_adjustment": adjustment,
                "news_enhanced_prediction": final,
                "baseline_absolute_error": abs(baseline -
                                               float(row["observed_vote_share"])),
                "news_absolute_error": abs(final -
                                           float(row["observed_vote_share"])),
            })

    return FoldFit(
        fold=fold_name, approach=approach,
        train_rows=len(train), test_rows=len(test),
        train_reform_rows=sum(1 for r in train if _is_reform(r)),
        test_reform_rows=sum(1 for r in test if _is_reform(r)),
        penalty=penalty, penalty_choice=penalty_choice,
        feature_columns=columns,
        coefficients={c: float(v) for c, v in
                      zip(columns, model.coefficients)},
        intercept=model.intercept,
        predictions=predictions, warnings=warnings)


def metrics(predictions: Sequence[Mapping[str, object]]) -> dict:
    """基线误差、新闻增强后的误差，以及两者之差。

    对所有行以及英国改革党分别报告，因为研究问题专门针对改革党，而一个完全
    由其他政党带来的改进回答的是另一个问题。

    当新闻模型更好时，``improvement`` 为正。它是同一批行上平均绝对误差之差，
    因此不需要归一化 —— 但它也会以比例的形式报告，因为 0.1 个百分点的提升
    在 3 个百分点的基线误差上和在 10 个百分点的基线误差上意义不同。
    """

    def block(rows) -> dict:
        if not rows:
            return {"rows": 0}
        base = np.array([r["baseline_absolute_error"] for r in rows])
        news = np.array([r["news_absolute_error"] for r in rows])
        base_err = np.array([r["baseline_prediction"] -
                             r["observed_vote_share"] for r in rows])
        news_err = np.array([r["news_enhanced_prediction"] -
                             r["observed_vote_share"] for r in rows])
        baseline_mae = float(base.mean())
        news_mae = float(news.mean())
        return {
            "rows": len(rows),
            "contests": len({(r["election_id"], r["area_id"]) for r in rows}),
            "baseline_mae": baseline_mae,
            "news_mae": news_mae,
            "baseline_rmse": float(np.sqrt((base_err ** 2).mean())),
            "news_rmse": float(np.sqrt((news_err ** 2).mean())),
            "improvement_mae": baseline_mae - news_mae,
            "improvement_proportion": (
                (baseline_mae - news_mae) / baseline_mae
                if baseline_mae > 0 else None),
            "rows_improved": int((news < base).sum()),
            "rows_worsened": int((news > base).sum()),
        }

    rows = list(predictions)
    return {
        "all_parties": block(rows),
        "reform_uk": block([r for r in rows if r["is_reform_uk"]]),
    }


def bootstrap_improvement(predictions: Sequence[Mapping[str, object]],
                          *, resamples: int = BOOTSTRAP_RESAMPLES,
                          seed: int = BOOTSTRAP_SEED) -> dict:
    """MAE 改进量的竞选单元级 bootstrap 区间。

    重抽样的是竞选单元而不是行：同一竞选单元中的候选人共享相同的新闻和相同的
    基线折，因此把每一行候选人数据当作独立抽样会低估区间 —— 这与任务说明对
    基线不确定性提出的"考虑分组"要求相同。

    跨越零的区间就是研究问题的答案，而不是方法的失败，并会如实报告。
    """
    rows = list(predictions)
    if not rows:
        return {"resamples": 0, "reason": "no predictions"}

    by_contest: dict[tuple, list] = {}
    for r in rows:
        by_contest.setdefault((r["election_id"], r["area_id"]), []).append(r)
    contests = list(by_contest)
    if len(contests) < 2:
        return {"resamples": 0,
                "reason": f"{len(contests)} contest(s) - a bootstrap over "
                          f"one group would resample the same rows every "
                          f"time and report a zero-width interval"}

    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(resamples):
        picked = rng.integers(0, len(contests), size=len(contests))
        sample = [row for i in picked for row in by_contest[contests[i]]]
        base = np.mean([r["baseline_absolute_error"] for r in sample])
        news = np.mean([r["news_absolute_error"] for r in sample])
        draws.append(base - news)
    draws = np.array(draws)
    return {
        "resamples": resamples, "seed": seed,
        "contests_resampled": len(contests),
        "improvement_mean": float(draws.mean()),
        "improvement_ci_lower": float(np.percentile(draws, 2.5)),
        "improvement_ci_upper": float(np.percentile(draws, 97.5)),
        "proportion_of_draws_favouring_news": float((draws > 0).mean()),
    }
