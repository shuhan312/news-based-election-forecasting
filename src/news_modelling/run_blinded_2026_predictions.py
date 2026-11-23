"""冻结盲化的 2026 年新闻层预测。

在仓库根目录下的用法：

    PYTHONPATH=src .venv/bin/python -m news_modelling.run_blinded_2026_predictions

这是新闻层唯一一次被许可打开第一阶段留出集文件的地方。模型包通过带验证的
只读加载器加载，在形成任何预测之前先剥离观测列，并且输出目录一旦写入就
拒绝被覆盖。在单独的、唯一一次的揭盲步骤之前，这里以及其他任何地方都
不会与 2026 年的结果进行比较。
"""

from pathlib import Path

from news_modelling.blinded_2026_predictions import (
    build_blinded_predictions,
    write_outputs,
)
from news_modelling.production_news_experiment import _read_csv
from news_modelling.stage1_bundle import load_stage1_bundle

import json

FEATURES = Path("news_features/news_feature_table_v1.csv")
AUDIT = Path("news_features/production_estimability_v1/estimability_report.json")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUTPUT = Path("news_features/blinded_2026_predictions_v1")


def main() -> None:
    # 带验证的加载器会根据模型包自身的哈希清单进行检查，
    # 因此可以证明冻结读取的就是第一阶段指标所描述的那些文件
    # —— 而不是一个被悄悄重新生成的基线。
    bundle = load_stage1_bundle(BUNDLE)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    features = _read_csv(FEATURES)

    protocol, predictions = build_blinded_predictions(
        oof_rows=[dict(row) for row in bundle.out_of_fold],
        holdout_rows=[dict(row) for row in bundle.holdout],
        features=features,
        audit=audit,
    )
    manifest = write_outputs(
        protocol, predictions, OUTPUT,
        input_paths={
            "news_feature_table_v1.csv": FEATURES,
            "estimability_report.json": AUDIT,
            "out_of_fold_predictions.csv": BUNDLE / "out_of_fold_predictions.csv",
            "holdout_predictions.csv": BUNDLE / "holdout_predictions.csv",
        },
    )

    # 刻意只输出计数和哈希：预测值保留在
    # 冻结文件中，而观测值在剥离步骤之后从未被加载。
    print(f"blinded candidate rows : {protocol['blinded_candidate_rows']}")
    print(f"specifications frozen  : {len(protocol['specifications'])}")
    print(f"prediction rows        : {manifest['prediction_rows']}")
    print(f"predictions sha256     : {manifest['blinded_predictions.csv']}")
    print(f"protocol sha256        : {manifest['frozen_protocol.json']}")
    print(f"written to             : {OUTPUT}")
    print("2026 outcomes read     : no")


if __name__ == "__main__":
    main()
