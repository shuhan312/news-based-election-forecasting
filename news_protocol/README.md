# `news_protocol/` —— 新闻流水线的设计依据

管理本项目新闻部分的规则、方法论、预注册和决策记录。本目录回答"为什么要这样做？"——它是 `src/` 中代码所实现的设计依据，与代码及其输出分开保存，这样不必阅读程序就能读懂一项决策。最终语料库是在该协议**及其有文档记录的修订和纠正性重跑**之下收集的；下面四个部分把当前规则、机器可读证据、纠正记录和历史记录清楚地分开。

## 1. 当前有效的规则

最终语料库和特征实际据以筛选和抽样的文件。

| 文件 | 规定的内容 |
| --- | --- |
| `article_eligibility_rules.md` | 预注册的 I1–I6 / E1–E10 纳入资格规则，报告附录中复述了这些规则 |
| `eligibility_manual_review_codebook.md` | 已记录的人工审核决策背后的人工审核编码手册 |
| `division_sample.md`、`division_sample.csv` | 冻结的 17 个选区的本地搜索样本（由 `src/build_division_sample.py` 生成；它的提交时间是仓库根目录泄漏审计中区域选择检查的时间锚点） |
| `news_source_registry.csv` | 新闻来源登记表，包括其覆盖范围和获取途径 |
| `raw_news_schema.md`、`raw_news_schema.json` | 收集引擎强制执行的原始新闻记录 schema |
| `historical_coverage_audit.csv` | 经过审计的、每个来源的新闻覆盖起始日期 |

## 2. 机器可读的证据

| 文件 | 内容 |
| --- | --- |
| `evidence/coverage_verification_2026-07-22.json` | 覆盖审计背后的、带日期的来源覆盖核验 |
| `evidence/pilot_records.json` | 支撑检索验证试点的记录 |

## 3. 修订与纠正

| 文件 | 记录的内容 |
| --- | --- |
| `collection_faults_and_corrections.md` | 收集过程中发现的每一个问题以及纠正它所付出的代价——如实记录执行过程如何偏离了最初的计划（接口替换、带引号查询和日期限制的重跑、范围扩展） |

## 4. 历史的和已被取代的开发记录

为保留开发轨迹而保存的带日期记录；每份文件顶部都有一条状态说明，指出后来发生了什么。它们都不描述当前状态。

| 文件 | 当时是什么，以及被什么取代 |
| --- | --- |
| `news_research_protocol.md` | 最初的预注册快照；最终的收集遵循了它以及上面有文档记录的修订 |
| `eligibility_manual_review_methodology.md` | 提出 v2 时的审核方法论；冻结的 v2 分类器随后经过了验证并投入使用 |
| `llm_v2_feasibility_plan.md` | v2 分类器冻结前的开发计划 |
| `retrieval_validation_report.md` | 收集前的验证，宣布检索框架已就绪 |
| `source_adapter_framework.md` | 适配器设计，后来在 `src/news_collection/adapters.py` 中实现 |
| `news_analysis_scope_decision.md` | 范围决策，附有截至 2026 年 7 月 30 日的执行计数 |
| `feature_selection_findings.md` | 已移除的选区级试点特征链的发现；其中未解决的划分问题已由第一阶段的划分设计解决 |

关于该协议如何管理收集、清洗、LLM 和特征各层，见 `REPO_MAP.md`。
