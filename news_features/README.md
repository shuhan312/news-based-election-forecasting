# `news_features/` —— 特征表与冻结的新闻证据

本目录存放两类内容：由已标注语料库构建的**第 4 层特征表输出**，以及报告所引用的每一项新闻结果的**第 6 层冻结证据**——每个实验一个按登记编号命名的子目录，每个子目录包含其结果 JSON 和一份 `findings.md`。（在 `REPO_MAP.md` 中，第 4 层是 `src/news_features/` 中生成这些表的代码，第 6 层是存放在这里的冻结实验证据。）这里是报告中各项新闻事实的归属地。构建它的代码位于 `src/news_features/` 和 `src/news_modelling/`；它读取的语料库位于 `news_collection/`。

## 从这里开始

| 文件 | 提供的内容 |
| --- | --- |
| [`PRODUCTION_NEWS_EVIDENCE_REGISTER.md`](PRODUCTION_NEWS_EVIDENCE_REGISTER.md) | 人类可读的结果登记册：一份 8 月 1 日的基础记录，加上之后就地标注日期的增补，区分冻结版本、负面证据、已被取代的试点和尚未解决的工作 |
| [`ARTIFACT_LINEAGE.md`](ARTIFACT_LINEAGE.md) | 哪个文章集合和哪张特征表是**生产**版本，从而确保两条互不兼容的流水线永远不会被当作同一个分析 |
| [`../REPO_MAP.md`](../REPO_MAP.md) | 每个报告数字的"报告章节 → 产物 → 代码"追溯 |

## 最终报告使用的特征表

最终报告使用两个冻结的特征版本，粒度为**选举 × 政党 × 时间段**，每个版本包含六个互不重叠的时间窗口和六个累积时间段：

| 版本 | 语料库 | 在最终报告中的角色 |
| --- | --- | --- |
| `news_feature_table_v1.csv` + 元数据 | 1,632 篇文章的主要选举语料库 | 冻结的、扩充之前的参照 |
| `news_feature_table_v2.csv` + 元数据 | v1 加上 627 篇补选文章 | 扩充后的验证性版本，也是报告主要正面结果的来源 |

元数据文件记录了构建每张表所使用的确切正式语料库版本。`v3exp` 和 `v3party` 是后来的敏感性分析变体（本地新闻来源谱系和政党粒度的内容）；它们并不取代 v1/v2 这一对验证性版本。

较早的选区级试点表（`article_level_news_features`、`context_aggregated_features` 等）以及揭盲之后的 `v4e5local` 探索性表已从 `main` 中移除；它们仍保留在 git 提交历史中。版本边界见 [`ARTIFACT_LINEAGE.md`](ARTIFACT_LINEAGE.md)。

## 冻结的实验证据——完整索引

每个子目录对应一个实验，在证据登记册中有登记编号，存放冻结的结果和发现记录。除非另有说明，生成模块位于 `src/news_modelling/`。

| 目录 | 生成者 | 支撑的内容 |
| --- | --- | --- |
| `blinded_2026_predictions_v1/`、`blinded_2026_predictions_v2/` | `run_blinded_2026_predictions(_v2).py` | 揭盲前冻结的预测：协议 + sha256 清单（csv 保存在本地；审计检查 4 核验该冻结） |
| `unblinding_2026_v1/` | `unblind_2026.py` | 针对真实结果的一次性评分——§5.1 及验证性表格 |
| `production_news_experiment_v1/`、`production_news_lopo_v1/`、`production_estimability_v1/` | `production_news_*.py` | 冻结的 2017→2021 设计实验、留一政党（LOPO）分析（表 11）以及可估计性审计（§4.6 的阈值） |
| `identity_placebos_v1/`、`placebo_specifications_v1/`、`stance_volume_margins_v1/`、`combined_specification_v1/` | 对应的同名模块 | §5.3/§6.2 的信号分解诊断（表 15） |
| `exploratory_decompositions_v1/`、`reform_decomposition_v1/`、`per_party_bootstrap_v1/` | 对应的同名模块 | §5.4 和图 5：归因、机制，以及带区间的按政党拆分 |
| `stage1_party_sensitivity_v1/`、`byelection_enrichment_v1/` | 对应的同名模块 | §6.2（0.2404→0.3004/0.0428）和 §6.3（可靠性数字） |
| `approach_comparison_v1/` | `compare_news_approaches.py` | 残差法 vs 联合建模，表 4 |
| `local_v3_rerun_v1/`、`minimal_detectable_effect_v1/` | 对应的同名模块 | 表格包中的 t19/t23——已提交，但最终报告正文未引用 |
| `haslemere_probe/`、`woking_south_blind_v1/` | 探测 / 盲测模块 | §5.6 的迁移与复现（表 14）；Woking South 包含密封的协议、盲测预测和启封记录 |
| `synthetic_scenarios_v1/` | `synthetic_news_scenarios.py` | 应用和答辩材料包读取的假设情景 |
| `pipeline_overview_v1/` | `pipeline_overview_figure.py` | 图 2 的源数据 |

### 根目录登记册与诊断记录

| 文件 | 内容 |
| --- | --- |
| `PRODUCTION_NEWS_EVIDENCE_REGISTER.md`、`ARTIFACT_LINEAGE.md` | 结果登记册和版本边界记录（见"从这里开始"） |
| [`CHALLENGE_RESPONSE_FINDINGS.md`](CHALLENGE_RESPONSE_FINDINGS.md) | 对 8 月 5 日导师质询的回应：每个数字都从已提交的产物重新推导，早先的错误被记录下来而不是被替换掉 |
| `PARTY_IDENTITY_AND_DESIGN_POWER.md` | §6.2 背后的政党身份与设计效力分析；其中单独标注的选区粒度部分是已停用的开发诊断，仅作为历史保留 |
| `news_layer_capability_findings.md`、`article_area_attribution_summary.json`、`feature_grain_diagnosis.json` | 带日期的 v1 粒度评估及其仍然有效的 §6.4 证据：1,632 篇文章中有 68 篇可以关联到具体区域，同时记录了训练单元格的计数 |

## 规范与来源追溯

预测变量列与结果列是分开的。表的元数据记录了粒度、可用列和来源；而位于 `outputs/leakage_provenance_audit_v1.json` 的独立跨层审计会检查时间顺序、重复、第一阶段划分与预测变量治理、第二阶段结果隔离以及政党身份；`outputs/provenance_audit_v1.csv` 是其精简的事件台账，未知的时间戳留空。大型二进制文件——冻结的盲化预测文件——依据 IRP 大文件规定保存在本地 / OneDrive，其 sha256 已提交在登记册中和文件旁边，因此即使没有这些大文件，每个数字也都可以核验。缺失的结果会被记录为缺失，而绝不会被记录为负面结果。
