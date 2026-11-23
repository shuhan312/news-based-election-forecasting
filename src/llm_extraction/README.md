# `src/llm_extraction/` —— 经过验证的 LLM 语境抽取（第 3 层）

本目录把正式新闻文章转换成结构化的语境标签，用人工编码和独立的模型运行来检验这些标签，并且只把经过验证的字段准入最终的特征流水线。并不是每个文件都在生产路径上：下面的完整文件指南按功能对所有模块分组，主线列在最前面。

生成的输出和决策记录位于 [`llm_context/`](../../llm_context/README.md)。逐篇文章的模型原始响应保存在本地，因为其中复述了受版权保护的文章引文。

## 1. 主线

最终报告使用三个经过验证的抽取层，由一个权威的生产运行器运行：

| 最终层 | 定义 | 生产模型 | 最终用途 |
|---|---|---|---|
| 议题分类 | `issue_classification.py` | Claude Sonnet 5 | 探索性的议题特征 |
| 修订后的政党立场 | `stance_rescue.py` | Claude Haiku 4.5 | 政党文章占比和立场平衡度 |
| 修订后的框架 | `frame_rescue.py` | Claude Haiku 4.5 | 用于探索性分析的、经过验证的框架 |

`run_corpus_extraction.py` 负责为这些层提交、收集、验证、重试请求，并记录提示词指纹，结果保存在名为 `llm_context/corpus_extraction_outputs_<tranche>.json` 的分批文件中。`health_check_tranche.py` 在一个批次被接受之前执行事先声明的运行检查，`write_batch_manifest_digest.py` 则把本地的批次清单精简为已提交的来源摘要。

```bash
python3 -m src.llm_extraction.run_corpus_extraction submit <tranche>
python3 -m src.llm_extraction.run_corpus_extraction collect <tranche>
python3 -m src.llm_extraction.health_check_tranche <tranche>
```

被接受的标签有两个冻结的下游版本：

| 版本 | 构建器 | 输出 | 在最终报告中的角色 |
|---|---|---|---|
| v1 | [`src/news_features/build_feature_table.py`](../news_features/build_feature_table.py) | `news_features/news_feature_table_v1.csv`、`news_feature_table_v1_metadata.json` | 冻结的、扩充之前的参照 |
| v2 | [`src/news_features/build_feature_table_v2.py`](../news_features/build_feature_table_v2.py) | `news_features/news_feature_table_v2.csv`、`news_feature_table_v2_metadata.json` | 扩充后的验证性版本，包含补选语料库 |

端到端流程：

```text
run_corpus_extraction.py
    -> llm_context/corpus_extraction_outputs_<tranche>.json
    -> build_feature_table.py / build_feature_table_v2.py
    -> news_features/news_feature_table_v1.csv / news_feature_table_v2.csv
    -> src/news_modelling/run_blinded_2026_predictions.py / _v2.py
    -> news_features/blinded_2026_predictions_v1/ / _v2/
    -> src/news_modelling/unblind_2026.py
    -> news_features/unblinding_2026_v1/
```

## 2. 按功能分组的完整文件指南

### 2.1 生产流水线（主线）

| 文件 | 作用 |
|---|---|
| `run_corpus_extraction.py` | 权威运行器：对通过验证关卡的三个层进行全语料库抽取 |
| `issue_classification.py` | 议题 / 话题层的定义：提示词、schema 和逐条记录验证器 |
| `stance_rescue.py` | 修订后的三级政党立场层的定义（取代了未通过验证的原始版本） |
| `frame_rescue.py` | 修订后的框架层的定义（取代了未通过验证的原始版本） |
| `health_check_tranche.py` | 一个批次的标签被接受之前必须通过的运行关卡 |
| `write_batch_manifest_digest.py` | 把一个批次的本地批次清单精简为已提交的来源摘要 |

### 2.2 被上述代码导入的共享辅助模块

| 文件 | 作用 |
|---|---|
| `pilot_sample.py` | 抽样和提示词构造函数；D4 验证样本也是用它抽取的 |
| `run_pilot.py` | 文章加载和模型常量，被生产运行器和每个重新设计层复用 |
| `validate_context.py` | 对抽取记录进行 schema 验证 |

### 2.3 报告一致性表格背后的验证证据

这些脚本生成了最终报告（附录，LLM 抽取验证）中报告的 kappa 值和通过 / 未通过决定。

| 文件 | 作用 |
|---|---|
| `build_d4_sample.py` | 抽取确定性的人工验证文章样本 |
| `run_d4_validation.py` | 让两个模型分别在该样本上运行六个被比较的抽取层 |
| `compare_d4_agreement.py` | 将模型输出与人工标签比较评分；定义了 kappa >= 0.60 的判定标准，其他所有评分程序都复用它 |
| `compare_model_to_model.py` | 被比较各层上模型之间（Sonnet vs Haiku）的一致性 |
| `compare_stance_rescue.py` | 为修订后的立场层评分（先模型之间，再对照人工参照） |
| `compare_frame_rescue.py` | 为修订后的框架层评分（先模型之间，再对照人工参照） |
| `test_coarsened_agreement.py` | 事先声明的检查：未通过的字段在更粗的标签粒度下能否通过 |

### 2.4 负面结果证据（被排除的层）

功过归因层和预期影响层即使在重新设计之后仍未通过关卡。它们的代码之所以保留，是因为最终报告报告了这些负面结果，而这些结果必须保持可复现；它们是证据，而不是生产层。

| 文件 | 作用 |
|---|---|
| `credit_blame.py` | 原始的功过归因层定义 |
| `attribution_rescue.py` | 重新设计的功过归因层（第二次尝试） |
| `compare_attribution_rescue.py` | 将重新设计版本与人工金标准标签比较评分（仍低于关卡；被排除） |
| `electoral_consequence.py` | 原始的预期选举影响层定义 |
| `consequence_rescue.py` | 重新设计的预期影响层（第二次尝试） |
| `compare_consequence_rescue.py` | 将重新设计版本与人工金标准标签比较评分（仍低于关卡；被排除） |

### 2.5 作为验证输入保留的、已被取代的方案

| 文件 | 作用 |
|---|---|
| `stance_classification.py` | 未通过验证的原始立场方案；被 `run_d4_validation.py` 作为一个被比较的组导入 |
| `framing_detection.py` | 未通过验证的原始框架方案；被 `run_d4_validation.py` 作为一个被比较的组导入 |
| `temporal_horizon.py` | 未被采用的 LLM 时间跨度层；被 `run_d4_validation.py` 作为一个被比较的组导入 |

### 2.6 最终报告的扩展

一些轻量的包装脚本，它们在最终报告的额外样本上复用冻结的三层机制；不定义任何新的抽取方法。

| 文件 | 作用 |
|---|---|
| `run_byelection_extraction.py` | 抽取进入 v2 特征表的补选语料库 |
| `run_byelection_issues_resubmit.py` | 恢复用的包装脚本：在 API 额度中断之后重新提交补选的议题层 |
| `run_haslemere_probe_extraction.py` | Haslemere 复现测试的抽取 |
| `run_woking_south_blind_extraction.py` | Woking South 盲测迁移测试的抽取 |

### 2.7 归档的验证支持与揭盲后的扩展

| 文件 | 作用 |
|---|---|
| `freeze_layer.py` | 纯验证辅助函数；之所以保留，是因为归档的八层冻结报告和答辩材料包会演示它的证据重新核验；它不是生产运行器 |
| `run_e5_backlog_v3_extraction.py` | 揭盲之后的 v3exp 谱系：v1/v2 特征表不使用它，但它的标签进入了 v3exp 表，Woking South 盲测的本地实验组（§5.6）就是在这张表上拟合的 |

除此之外的已被取代的开发代码——最初的单层试点运行器、从未通过验证的本地 / 全国相关性层和置信度证据层、过时的八层冻结运行器，以及两个一次性的来源修复工具——已从最终的目录树中移除。Git 历史保留了这些脚本。关于提示词回填的发现（包括无法恢复的 v1.2 提示词）仍记录在 `llm_context/d4_findings_log.md` 中。

## 3. 输出位置与交接

生产代码和它的输出刻意放在不同的目录中：

| 位置 | 内容 | 版本管理状态 |
|---|---|---|
| `src/llm_extraction/` | 抽取、验证和比较代码 | 已提交 |
| `llm_context/corpus_extraction_outputs_<tranche>.json` | 逐篇文章的原始标签和支撑引文 | 本地 / OneDrive；因引文复述了受版权保护的文本而被 git 忽略 |
| `llm_context/*agreement*.json` | 人工–模型以及模型–模型的验证结果 | 已提交 |
| `llm_context/corpus_extraction_batch_digests.json` | 提示词指纹、批次 ID 和输出摘要 | 已提交 |
| `llm_context/d4_llm_output_manifest.json` | 本地验证输出的完整性清单 | 已提交 |
| `news_features/news_feature_table_v1.*` | 冻结的、扩充之前的特征表及元数据 | 已提交 |
| `news_features/news_feature_table_v2.*` | 扩充后的、最终报告使用的特征表及元数据 | 已提交 |

## 4. 不花费 API 额度即可验证本目录

本包的确定性逻辑（提示词构造、记录验证器、一致性评分、关卡规则）由单元测试覆盖，可以在几秒钟内离线运行：

```bash
python -m pytest tests/test_issue_classification.py \
    tests/test_stance_classification.py tests/test_framing_detection.py \
    tests/test_credit_blame.py tests/test_electoral_consequence.py \
    tests/test_temporal_horizon.py tests/test_freeze_layer.py \
    tests/test_llm_context_schema.py tests/test_pilot_pipeline.py \
    tests/test_party_content_attribution.py
```

模型响应本身被视为冻结的产物，而不会被随意重新生成：Claude Batches API 成本较高，而且不能保证逐位确定。已提交的提示词版本、一致性评分表、批次摘要、提示词指纹和 SHA-256 清单共同确定了最终特征表所使用的确切本地输出。

最终的方法论规则很简单：

1. 验证记录结构和证据；
2. 在留出的人工标注文章和独立的模型运行上衡量一致性；
3. 只准入满足已声明规则的字段；
4. 只有当未通过的字段用于支撑一项已报告的负面结果时，才保留它们；
5. 让每个被接受的批次都能追溯到其提示词和批次清单。

从正式文章经过抽取和特征构建到第二阶段模型的完整路径见 [`REPO_MAP.md`](../../REPO_MAP.md)。第二阶段的运行器还会加载 [`surrey-election-no-news-baseline/README.md`](../../surrey-election-no-news-baseline/README.md) 中记录的冻结第一阶段模型包。
