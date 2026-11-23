"""加载并验证冻结的第一阶段模型包。

Prompt 2 的第一项要求："Load and validate the model bundle produced by
Stage 1... The application must fail safely if the selected Stage 1 model
bundle is incomplete or incompatible"（加载并验证第一阶段生成的模型包……
如果所选的第一阶段模型包不完整或不兼容，应用必须安全地失败），以及
"Do not alter or overwrite the Stage 1 model bundle."（不得修改或覆盖第一阶段模型包。）

本模块是新闻层接触第一阶段的唯一途径，并且所有内容都以只读方式打开。
这并不是出于礼貌。第一阶段的折外预测正是残差模型的衡量基准；如果新闻层
能够写入模型包，那么事后就无法区分"新闻结果令人失望"和"基线被悄悄
重新生成"这两种情况。

这里"兼容"的含义
----------------------------
不仅仅是"文件存在"。下面的检查都是这样一些检查：一旦它们失败，就会产生一个
在训练错误目标的同时却报告成功的新闻模型：

- **清单哈希仍然匹配**，因此描述该模型包的指标描述的正是实际被读取的
  文件；
- **折外预测存在，并且每行唯一**，因为残差是按候选人定义的，同一位候选人
  有两个预测时，会悄悄地选用最后读到的那一个；
- **折外预测不是样本内拟合** —— Prompt 2 明确规定新闻层必须在折外预测上
  训练，而每一行上记录的划分角色正是证明这一点的依据；
- **英国改革党（Reform UK）和英国独立党（UKIP）的标签存在，且从不同时为真**，
  这是把"两者分开"的要求重新表述为数据的一项性质。
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

# Prompt 1 要求模型包必须包含的文件。缺少其中任何一个的模型包都是不完整的，
# 无论它还包含了什么别的东西。
REQUIRED_FILES: tuple[str, ...] = (
    "model.pkl", "preprocessor.pkl", "architecture.json", "feature_schema.json",
    "feature_dictionary.csv", "leakage_audit.csv", "split_manifest.csv",
    "training_rows.csv", "out_of_fold_predictions.csv", "holdout_predictions.csv",
    "metrics.json", "reform_metrics.json", "data_quality_report.json",
    "model_card.md", "requirements-lock.txt", "training_config.yaml",
)

# 折外预测必须来自滚动起点折。带有其他任何划分角色的行
# 都是留出集或开发阶段的预测，不得用作残差训练的
# 基线。
OUT_OF_FOLD_ROLE = "rolling_origin_fold"


class BundleIncompatible(RuntimeError):
    """第一阶段模型包不能用作基线。

    单独定义一个类型，使调用方能够区分"这个模型包不可用"和"这个模型
    拟合失败"。前者可以通过重建第一阶段来解决；后者则不能。
    """


@dataclass(frozen=True)
class Stage1Bundle:
    """经过验证的、只读的第一阶段模型包视图。"""

    directory: Path
    architecture: dict
    metrics: dict
    reform_metrics: dict
    manifest: dict
    out_of_fold: tuple[dict, ...]
    holdout: tuple[dict, ...]
    split_manifest: tuple[dict, ...]
    warnings: tuple[str, ...] = field(default=())

    # -- 新闻层需要展示的事实 -------------------------

    @property
    def bundle_version(self) -> str:
        return str(self.architecture.get("bundle_version", "unknown"))

    @property
    def selected_architecture(self) -> str:
        return str(self.architecture.get("selected_model_type", "unknown"))

    @property
    def training_date(self) -> str:
        return str(self.architecture.get("training_date", "unknown"))

    @property
    def reform_rows_out_of_fold(self) -> int:
        return sum(1 for row in self.out_of_fold if _truthy(row.get("is_reform_uk")))

    def summary(self) -> dict:
        """Prompt 2 要求应用在加载之后展示的内容。"""

        overall = self.metrics.get("out_of_fold", {}).get("overall", {})
        holdout = self.metrics.get("primary_holdout", {}).get("overall", {})
        reform = self.reform_metrics.get("out_of_fold", {}).get("reform_uk", {})
        selection = self.architecture.get("selection", {})
        return {
            "bundle_version": self.bundle_version,
            "selected_architecture": self.selected_architecture,
            "selected_automatically": selection.get("selected_automatically"),
            "training_date": self.training_date,
            "packages": self.architecture.get("packages", {}),
            "random_seed": self.architecture.get("random_seed"),
            "baseline_out_of_fold_rows": len(self.out_of_fold),
            "baseline_out_of_fold_mae": overall.get("mae"),
            "baseline_holdout_mae": holdout.get("mae"),
            "reform_out_of_fold_rows": self.reform_rows_out_of_fold,
            "reform_out_of_fold_mae": reform.get("mae"),
            "reform_small_sample_warning": self.reform_metrics.get(
                "out_of_fold", {}).get("small_sample_warning"),
            "split_method": self.architecture.get("split_method"),
            "holdout_elections": sorted({
                str(row["election_id"]) for row in self.holdout
            }),
            # 原样沿用而不做概括，因为一个新闻结果如果在报告时
            # 不附带基线自身的局限性，读起来就好像
            # 基线没有任何局限。
            "known_limitations_reference": "docs/candidate_model_card.md",
            "warnings": list(self.warnings),
        }


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> tuple[dict, ...]:
    with path.open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle))


def load_stage1_bundle(
    directory: str | Path,
    *,
    verify_hashes: bool = True,
) -> Stage1Bundle:
    """读取模型包、检查它并返回它。从不写入。

    ``verify_hashes`` 把每个文件与 ``bundle_manifest.json`` 进行比对。
    默认开启：清单存在的目的正是让后续阶段能够证明它加载的就是某组指标
    所描述的那个模型包，而一项默认关闭的核验是没有人会去运行的。
    """

    path = Path(directory)
    if not path.is_dir():
        raise BundleIncompatible(f"Stage 1 bundle directory not found: {path}")

    missing = [name for name in REQUIRED_FILES if not (path / name).exists()]
    if missing:
        raise BundleIncompatible(
            f"Stage 1 bundle at {path} is incomplete. Missing: {missing}. "
            "Rebuild it with `python -m no_news_baseline.cli train`."
        )

    warnings: list[str] = []

    manifest_path = path / "bundle_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    if verify_hashes and manifest.get("files"):
        mismatched = []
        for name, expected in manifest["files"].items():
            candidate = path / name
            if not candidate.exists():
                mismatched.append(f"{name} (missing)")
                continue
            actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual != expected:
                mismatched.append(f"{name} (hash differs)")
        if mismatched:
            raise BundleIncompatible(
                f"Stage 1 bundle at {path} does not match its own manifest: "
                f"{mismatched}. The metrics in this bundle describe different "
                "files from the ones on disk; rebuild rather than proceed."
            )
    elif verify_hashes:
        warnings.append(
            "bundle_manifest.json is absent or empty, so file integrity was "
            "not verified."
        )

    architecture = _read_json(path / "architecture.json")
    out_of_fold = _read_csv(path / "out_of_fold_predictions.csv")
    holdout = _read_csv(path / "holdout_predictions.csv")
    split_manifest = _read_csv(path / "split_manifest.csv")

    _validate_predictions(out_of_fold, warnings)

    bundle = Stage1Bundle(
        directory=path,
        architecture=architecture,
        metrics=_read_json(path / "metrics.json"),
        reform_metrics=_read_json(path / "reform_metrics.json"),
        manifest=manifest,
        out_of_fold=out_of_fold,
        holdout=holdout,
        split_manifest=split_manifest,
        warnings=tuple(warnings),
    )
    return bundle


def _validate_predictions(rows: tuple[dict, ...], warnings: list[str]) -> None:
    """检查折外预测表是否符合残差模型的要求。"""

    if not rows:
        raise BundleIncompatible(
            "out_of_fold_predictions.csv is empty. The residual model has "
            "nothing to compute a residual against."
        )

    required = {
        "candidate_contest_id", "election_id", "division_id", "split_role",
        "standard_party_name", "is_reform_uk", "is_ukip",
        "predicted_vote_share", "observed_vote_share",
    }
    absent = sorted(required - set(rows[0]))
    if absent:
        raise BundleIncompatible(
            f"out_of_fold_predictions.csv lacks required columns: {absent}"
        )

    identifiers = [str(row["candidate_contest_id"]) for row in rows]
    if len(identifiers) != len(set(identifiers)):
        duplicated = len(identifiers) - len(set(identifiers))
        raise BundleIncompatible(
            f"{duplicated} candidate row(s) carry more than one out-of-fold "
            "prediction. A residual is defined per candidate, so which "
            "prediction is used would depend on read order."
        )

    # Prompt 2："Training uses Stage 1 out-of-fold predictions."（训练使用第一阶段的折外预测。）
    # 来自其他任何划分角色的行都是样本内或留出集的数字，会使残差
    # 变成基线已经见过该行所造成的假象。
    wrong_role = {
        str(row.get("split_role")) for row in rows
        if str(row.get("split_role")) != OUT_OF_FOLD_ROLE
    }
    if wrong_role:
        raise BundleIncompatible(
            f"out_of_fold_predictions.csv contains rows with split roles "
            f"{sorted(wrong_role)}. Only {OUT_OF_FOLD_ROLE!r} rows are "
            "genuinely out of fold."
        )

    both = [
        str(row["candidate_contest_id"]) for row in rows
        if _truthy(row.get("is_reform_uk")) and _truthy(row.get("is_ukip"))
    ]
    if both:
        raise BundleIncompatible(
            f"{len(both)} row(s) are labelled both Reform UK and UKIP. The two "
            "parties must remain separate throughout."
        )

    unscored = sum(
        1 for row in rows
        if str(row.get("observed_vote_share", "")).strip() in {"", "None"}
    )
    if unscored:
        warnings.append(
            f"{unscored} out-of-fold row(s) have no observed vote share and "
            "cannot contribute a residual."
        )
