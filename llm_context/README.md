# `llm_context/` —— LLM 抽取输出与决策记录

流水线第 3 层的产物。本目录存放 Claude 语境抽取（`src/llm_extraction/`）的结果：提示词、schema、与人工标注一致性的验证、审计记录，以及冻结的标签清单。它证明了 LLM 标签在使用之前经过了验证，同时记录了下游各层读取的是哪些冻结输出。下面的完整索引按用途对每个已提交的文件分组；最后两个部分明确属于历史记录。

## 哪些已提交、哪些保存在本地

**逐篇文章的 LLM 原始响应会复述文章中的引文**，因此依据版权政策，它们保存在本地 / OneDrive（被 git 忽略）：`d4_llm_outputs*.json`、`corpus_extraction_outputs_*.json` 以及各层的 `*_outputs.json`。已提交的是在没有文本的情况下审计和核验它们所需的全部内容：提示词、schema、一致性评分表、批次摘要和 SHA-256 清单。抽取是分批调用 Claude API 完成的，属于**冻结的产物**，而不是可以确定性重跑的过程；每一个一致性数字都可以从已提交的文件重新计算，批次摘要则精确锁定了特征表使用的是哪些冻结输出。

证据的粒度是：每个抽取层、每个模型组、每道关卡各一条记录（审计、错误分析、schema、批次清单、一致性结论）；因此，最终报告一致性表格中的每一项验证结论都有其可供核查的源文件。

## 1. 生产抽取（主线）

由 `src/llm_extraction/run_corpus_extraction.py`、`health_check_tranche.py` 和 `write_batch_manifest_digest.py` 写出。

| 文件 | 内容 |
|---|---|
| `context_extraction_prompt_v1_final.md` | 冻结的生产提示词 |
| `llm_prompt_version_v1.1.md` | 提示词版本记录 |
| `issue_taxonomy_v1.3.json` | 生产用的议题分类体系（由 `issue_classification.py` 加载） |
| `corpus_extraction_batch_digests.json` | 每个批次的批次 ID、提示词指纹和输出摘要 |
| `tranche_health_check_narrow/far/far2/far3/all.json` | 每个批次在被接受之前所通过的、事先声明的运行关卡 |
| `llm_context_version_manifest.json` | 抽取契约的版本索引 |

## 2. D4 验证——报告一致性表格背后的证据

由 `build_d4_sample.py`、`run_d4_validation.py`、`compare_d4_agreement.py`、`compare_model_to_model.py` 和 `test_coarsened_agreement.py` 生成；这些文件是最终报告 LLM 验证附录中每一个 kappa 值的来源。

| 文件 | 内容 |
|---|---|
| `d4_validation_sample_v1.csv`、`d4_validation_sample_audit.json` | 确定性的人工验证样本及其审计 |
| `d4_human_labels_v1.csv` | 人工标注 |
| `d4_agreement_report.json` / `_haiku.json` | 每个模型组的模型与人工一致性（带 `{SUFFIX}` 的文件名由评分程序写出） |
| `d4_inter_model_agreement.json` | Sonnet 与 Haiku 之间的一致性（信度） |
| `d4_coarsened_agreement.json` / `_haiku.json` | 事先声明的粗粒度检查 |
| `d4_findings_log.md`、`d4_gate_outcome_and_decisions.md` | 发现日志以及已记录的关卡决策 |
| `d4_llm_output_manifest.json` | 本地验证输出的 SHA-256 清单 |

## 3. 被采纳的重新设计（立场与框架）

修订后的三级立场层和修订后的框架层，它们取代了未通过验证的原始版本并进入生产。

| 文件 | 内容 |
|---|---|
| `stance_rescue_batch.json` / `_batch_haiku.json`、`frame_rescue_batch.json` / `_batch_haiku.json` | 重新设计运行的批次清单（按模型加后缀写出） |
| `stance_rescue_outputs.json` / `_haiku.json`、`frame_rescue_outputs.json` / `_haiku.json` | 用于评分的重新设计输出 |
| `stance_rescue_agreement.json` + `.md`、`frame_rescue_agreement.json` + `.md` | 使这两层得以准入的一致性结论 |

## 4. 负面结果证据（被排除的层）

功过归因（credit-blame）层和预期影响（expected-impact）层即使在重新设计之后仍未通过关卡；最终报告引用了这些负面结果，因此它们的证据仍保持可复现。

| 文件 | 内容 |
|---|---|
| `attribution_rescue_batch.json` / `_batch_haiku.json`、`attribution_rescue_agreement.json` | 功过归因层的重新设计运行及其低于关卡的结论 |
| `consequence_rescue_batch.json` / `_batch_haiku.json`、`consequence_rescue_outputs_haiku.json`、`consequence_rescue_agreement.json` | 预期影响层的重新设计运行及其低于关卡的结论 |

## 5. schema、规则与分类体系的版本链（解读的钥匙）

这些文件用于解读冻结输出中的版本标记；旧版本之所以保留，是因为带有版本标记的记录引用了它们。

| 文件 | 内容 |
|---|---|
| `llm_context_schema_v1.json` | 强制执行的记录契约，由 `validate_context.py` 加载 |
| `llm_context_validation_rules_v1.md`、`llm_context_validation_rules_v1.1.md` | 验证规则；对于新的抽取，v1.1 取代 v1，而在 v1 下验证的试点输出保持原有记录 |
| `issue_taxonomy_v1.2.json` | v1.3 之前的分类体系——规则 S7 禁止在 v1.3 之前的版本标记下使用全国性代码，因此该文件是读取带版本标记记录的钥匙 |
| `llm_context_schema_documentation_v1.md`、`llm_context_schema_revision_notes.md`、`llm_context_schema_v1.1_to_v1.2_changes.md` | schema 文档及修订历史 |
| `llm_context_changelog.md` | 逐层的变更日志 |
| `issue_layer_decisions_v1.md`、`phase6_research_decisions_v1.md` | 已记录的议题层决策和第 6 阶段研究决策 |

## 6. 试点阶段的记录（历史——八层试点，7 月 26–27 日）

在 D4 关卡削减候选层之前，测试了八个候选层的试点。这些是冻结的决策记录：它们解释了每一层为什么被保留、重新设计或放弃。它们都不在生产路径上。

| 文件 | 内容 |
|---|---|
| `llm_context_pilot_audit.md`、`llm_context_pilot_sample_v1.csv` | 67 篇文章的试点审计及其样本 |
| `llm_context_revalidation_report.md`、`llm_context_revalidation_sample_v1.csv` | 试点的重新验证 |
| `llm_context_error_analysis.md`、`llm_context_example_outputs_v1.json` | 跨层错误分析和示例输出 |
| `issue_classification_audit.md` + `_error_analysis.md` + `_schema_v1.json` | 议题层的试点审计（D4 之后保留用于生产） |
| `stance_classification_*`、`framing_detection_*`（审计、错误分析、schema） | 原始立场 / 框架方案的试点记录，这些方案未通过验证，已被重新设计的版本取代 |
| `credit_blame_*`、`electoral_consequence_*`（审计、错误分析、schema） | 报告中引用了其失败结果的两个层的试点记录 |
| `local_national_relevance_*`、`confidence_evidence_*`、`temporal_horizon_*`（审计、错误分析，以及存在时的 schema） | 未经重新设计即被放弃的三个候选层的试点记录 |

## 7. 旧版冻结系列（历史——分批之前的八层冻结）

| 文件 | 内容 |
|---|---|
| `llm_context_freeze_report.md` | 唯一一次旧版八层冻结的报告（其运行器保留在 Git 历史中；答辩材料包演示的是 `freeze_layer.py` 的证据重新核验） |
| `llm_context_schema_v1_final.json` | 伴随该次冻结的、冻结日期时的 schema 快照；v1/v2 生产路径不读取它 |

## 规范

标签只有在通过人工一致性验证之后才会进入流水线；被放弃的抽取层仍保留其批次 ID 和计算出的一致性（可追溯性），尽管其原始输出不再输入任何地方。英国改革党（Reform UK）和英国独立党（UKIP）自始至终分开处理。代码层面的指南见 `src/llm_extraction/README.md`，冻结标签如何流入 `src/news_features/` 见 `REPO_MAP.md`。
