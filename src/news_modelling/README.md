# `src/news_modelling/` —— 第二阶段新闻建模（第 5 层）

IRP 的核心检验：选举前的新闻能否在仅基于历史数据的第一阶段基线之外改善预测？本目录拟合新闻层估计器，冻结其**盲化的** 2026 年预测，针对真实结果执行**一次性揭盲**，并承载揭盲之后的所有诊断。它读取冻结的第一阶段模型包（`surrey-election-no-news-baseline/outputs/model_bundle_v1/`）以及 `news_features/` 中的 v1/v2 特征表。并不是每个文件都在预测路径上：下面的完整文件指南按功能对所有模块分组，主线列在最前面。

## 1. 主线

```text
surrey-election-no-news-baseline/outputs/model_bundle_v1/
    |- out_of_fold_predictions.csv  -> 第二阶段残差的训练目标
    `- holdout_predictions.csv      -> 冻结的 2026 年第一阶段基线

news_features/news_feature_table_v1.csv / news_feature_table_v2.csv
    + 第一阶段模型包
    -> stage1_bundle.py（验证与加载）
    -> news_estimator.py（按时间窗口拟合的残差岭回归）
    -> run_blinded_2026_predictions.py / _v2.py
    -> news_features/blinded_2026_predictions_v1/ / _v2/
    -> unblind_2026.py
    -> news_features/unblinding_2026_v1/
```

```bash
PYTHONPATH=src .venv/bin/python -m news_modelling.run_blinded_2026_predictions      # 冻结 v1 预测
PYTHONPATH=src .venv/bin/python -m news_modelling.run_blinded_2026_predictions_v2   # 冻结 v2（扩充后）预测
PYTHONPATH=src .venv/bin/python -m news_modelling.unblind_2026                      # 针对真实结果的一次性评分
```

v1 是冻结的、扩充之前的参照。v2 保留了相同的特征和模型设定，同时加入了补选语料库和训练单元格；它是扩充后的验证性版本，最终报告的主要正面结果来自于它。`news_estimator.py` 实现了两种已声明的方法——**A（残差法）**：对冻结的第一阶段基线的残差误差建模，这也是 v1/v2 所冻结的方法；以及 **B（联合法）**：在揭盲之后于 `compare_news_approaches.py` 中进行比较（附录表 4）。

## 2. 按功能分组的完整文件指南

### 2.1 核心估计与盲化冻结（主线）

| 文件 | 作用 |
|---|---|
| `stage1_bundle.py` | 加载并验证冻结的第一阶段模型包 |
| `news_estimator.py` | 新闻层估计器：方法 A（残差法）和方法 B（联合法） |
| `window_schemes.py` | 已声明的新闻时间窗口方案，在收集、抽取和特征各环节共用 |
| `blinded_2026_predictions.py` / `blinded_2026_predictions_v2.py` | 构造盲化的预测记录（v1 / v2） |
| `run_blinded_2026_predictions.py` / `run_blinded_2026_predictions_v2.py` | 可执行的冻结入口；绑定输入哈希，并在**读取任何 2026 年结果之前**写出冻结产物 |
| `unblind_2026.py` | 主要 2026 年验证性工作流中权威的**一次性**揭盲；在揭盲后的诊断运行之前，将冻结的预测与真实结果比较评分 |

### 2.2 2026 年之前的生产实验（设计验证）

在 2026 年冻结之前确定第二阶段设计的、冻结的 2017→2021 实验，及其可估计性审计和稳健性检查。

| 文件 | 作用 |
|---|---|
| `production_estimability.py` + `run_production_estimability.py` | 审计生产新闻表能否支撑计划中的模型（§4.6 中的变异性阈值） |
| `production_news_experiment.py` + `run_production_news_experiment.py` | 冻结的 2026 年之前的新闻比较 |
| `production_news_lopo.py` + `run_production_news_lopo.py` | 留一政党（leave-one-party-out）稳健性检验（§5.2，附录表 11） |

### 2.3 揭盲之后的诊断（每项都支撑报告中的某个指名章节）

全部读取冻结的输入；预测路径不导入其中任何一个。

| 模块 | 回答的问题 | 在报告中的用途 |
|---|---|---|
| `identity_placebos.py` | 新闻层是否仅仅相当于政党的名字？ | §5.3/§6.2 |
| `stage1_party_sensitivity.py` | 去掉每个政党的平均残差之后，改进是否依然存在？（0.2404 → 0.3004 / 0.0428） | §6.2（唯一来源） |
| `stance_volume_margins.py` | 立场 vs 数量，按边际效应而不是按符号计数比较 | §5.3 |
| `placebo_specifications.py` | LLM 层是否胜过简单地数文章？ | §5.3，附录表 15 |
| `combined_specification.py` | 在一次拟合中同时控制政党身份和文章数量后，政党内部的语气效应是否依然存在？ | §6.2 |
| `exploratory_decompositions.py` | 归因分解与机制分解 | §5.4 |
| `reform_decomposition.py` | 按政党的 ΔMAE 分解；其 JSON 驱动拆分图 | §5.4，图 5（唯一来源） |
| `per_party_bootstrap.py` | 按政党拆分结果的、基于竞选单元 bootstrap 的不确定性 | §5.4（表格包表 t22） |
| `byelection_enrichment.py` | 新增补选单元格在数量与质量之间的权衡 | §6.3（可靠性数字） |
| `minimal_detectable_effect.py` | 归档的设计能够检测到多大的效应量 | 设计分辨率记录（表格包表 t23）；最终报告正文未引用 |
| `compare_news_approaches.py` | 揭盲之后比较残差法（A）与联合法（B） | 附录表 4 |
| `local_v3_rerun.py` | 探索性的本地 vs 全国重跑（v3exp 谱系） | 表格包表 t19；最终报告正文未引用 |
| `haslemere_probe_prediction.py` | 使用冻结 v2 设定进行的 2026 年 7 月 7 日迁移探测 | §5.6 |
| `descriptive_2026_targets.py` | 重新计算报告表格包读取的描述性目标值 | 表格包输入 |

### 2.4 Woking South 盲测协议

| 文件 | 作用 |
|---|---|
| `woking_south_blind_protocol.py` | 在接触任何结果之前冻结协议 |
| `woking_south_blind_predict.py` | 生成盲测预测（不读取任何结果）；在以哈希锁定的 v3exp 表上拟合本地实验组 |
| `woking_south_unseal.py` | 协议中**唯一**被授权读取结果的程序 |

### 2.5 报告包与图表

供报告使用的表格和图表由已提交的 `outputs/report_tables_v1/` 和 `outputs/report_figures_v1/` 包构建；自包含报告源码所使用的 16 个表格文件是同步过来的副本。如果某个数字偏离了其冻结来源，构建时的断言就会失败。

| 文件 | 作用 |
|---|---|
| `build_report_tables.py` | 从已提交的结果产物构建报告表格包（以 sha256 锁定的清单） |
| `report_appendix_tables.py` | 从表格包生成 LaTeX 格式的附录表 |
| `stage2_fitting_cells_table.py` | 根据冻结的 v2 协议和第一阶段模型包，推导出 45 个第二阶段拟合单元格（选举、投票日期、新闻截止日期、政党、第一阶段行数、角色），再加上冻结的 2026 年测试行，作为附录表 a20 |
| `make_report_figures.py` | 从归档结果生成报告的核心图表 |
| `study_design_figure.py` | 图 1：24 个选举事件如何被使用 |
| `pipeline_overview_figure.py` | 图 2：端到端的新闻流水线 |
| `framework_figure.py` | 图 3：两阶段框架及冻结线 |
| `reform_party_split_figure.py` | 图 5：按时间窗口的改革党 vs 非改革党 ΔMAE |
| `corpus_funnel_figure.py` | 语料库图的比例漏斗变体（位于已提交的图表包中；最终报告正文未收录） |

### 2.6 演示

| 文件 | 作用 |
|---|---|
| `synthetic_news_scenarios.py` | 针对冻结 v2 模型的假设新闻情景；由 Streamlit 应用和答辩材料包读取 |

## 3. 不花费 API 额度即可验证本目录

评分是确定性的：建模读取冻结的输入（第一阶段模型包和特征表），因此重跑会得到相同的数字；盲化预测是冻结的产物，其 sha256 已提交在文件旁边。离线测试套件覆盖了估计器、冻结 / 揭盲路径以及每一项诊断：

```bash
python -m pytest tests/test_news_stage1_bundle.py tests/test_news_window_schemes.py \
    tests/test_blinded_2026_predictions.py tests/test_blinded_2026_predictions_v2.py \
    tests/test_unblind_2026.py tests/test_identity_placebos.py \
    tests/test_combined_specification.py tests/test_placebo_specifications.py \
    tests/test_production_estimability.py tests/test_production_news_experiment.py \
    tests/test_production_news_lopo.py tests/test_per_party_bootstrap.py \
    tests/test_minimal_detectable_effect.py tests/test_artefact_citations.py
```

## 4. 规范

预测在看到结果之前就已冻结；揭盲只进行一次并被记录下来；设计的最小可检测效应已归档（表格包表 t23），因此某个时间窗口的零结果永远不会被解读为"没有效应"的证明；英国改革党（Reform UK）单独报告，从不与英国独立党（UKIP）合并。关于每个产物支撑报告的哪个章节，见 `REPO_MAP.md` 和 `news_features/PRODUCTION_NEWS_EVIDENCE_REGISTER.md`。
