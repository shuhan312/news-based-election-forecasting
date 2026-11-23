# news_collection/ —— 原始新闻收集产物

生产阶段"原始新闻收集"（Raw News Collection）环节的、纳入版本管理的产物。语料库本身（记录、原始 HTML、原始 API 响应、抽取出的文本）位于 `data/raw/news/`，并且刻意不提交；这里的所有内容都是为了让语料库可以被审计和重建。

| 文件 | 内容 |
|---|---|
| `query_inventory.csv` | 冻结的确定性计划：覆盖 A–H、M 和 M2 各阶段共 2,470 条查询。它由已提交的选举输入、17 个选区的样本以及已提交的最终地理对照表重新生成。 |
| `search_log.csv` | 只追加的日志：每执行一次搜索记录一行，包括零结果和失败的搜索（协议 §5.3）。 |
| `query_lineage_v1.csv` | 四个已被取代的 `-ward` slug 查询 ID 及其纠正后的替代 ID，使每一行历史搜索日志仍然可以关联上。 |
| `checkpoints/completed_queries.json` | 断点续跑：已经执行过的查询 ID（仅保存在本地，被 git 忽略——它是运行时状态，完全可以从 `search_log.csv` 推导出来）；删除某个查询 ID 即可强制重新执行（会追加一行新的日志）。 |
| `collection_diagnostics.json` | 语料库统计 + schema 重新验证的结果。用 `python3 -m src.news_collection.make_collection_report` 重新生成。 |
| `../outputs/leakage_provenance_audit_v1.json` | 详细的跨层断言，涵盖查询谱系、文章时间顺序、重复控制、第一阶段划分与预测变量许可、第二阶段结果隔离、政党身份以及预测冻结的完整性。 |
| `../outputs/provenance_audit_v1.csv` | 精简的事件时间线；无法获得的结果发布时间戳和预测创建时间戳保持空白，而不是凭空编造。 |

运行收集：

```
python3 -m src.news_collection.run_collection --stage A|B|C|D|E|F|G|H|M|M2
```

代码：`src/news_collection/`（schema、适配器、运行器、命令行、查询清单构建器、诊断）。设计依据：`news_protocol/`。

查询清单包含完整的 19 场补选的计划。在冻结版本的截止时间点，有 704 条计划中的 E/G/H 查询尚未执行（E 244 条、G 324 条、H 136 条）。它们被记录为未执行，既没有被转换成零结果的搜索，也没有被用来声称覆盖完整。可用 `python3 -m audit_leakage_provenance` 重新生成这一断言。

## 清洗、去重和纳入资格产物

这个文件夹是整个语料库构建过程的共同存放地，而不仅仅是收集：清洗（第 4 阶段，`src/normalisation/`）、去重（第 5 阶段，`src/dedup/`）和纳入资格筛选各阶段也都把它们冻结的决策记录和摘要写到这里。这就是为什么这个目录很大——每一项阶段决策都有一条已提交的记录，这样不需要文章文本也能审计语料库。逐篇文章的文本层本身（`*_articles_v1.jsonl`）被 git 忽略；引用它们的决策记录则已提交。

| 文件 | 内容 |
|---|---|
| `character_normalisation_log_v1.csv`、`*_review_queue_v1.csv` | 第 4 阶段清洗日志以及由此产生的人工审核队列 |
| `article_version_families_v1_provisional.*`、`article_version_relationships/resolutions/temporal_availability_v1_provisional.csv` | 第 5 阶段版本关联：哪些文章是哪些文章的更新版本，以及每篇文章何时可获得 |
| `canonical_article_mapping_v1_provisional.csv`、`canonical_resolutions_v1_provisional.csv`、`duplicate_cluster_conflicts/review_queue_v1_provisional.csv` | 第 5 阶段去重：每个重复项映射到其正式副本，以及被标记待审核的簇 |
| **`canonical_corpus_release_v1.json`、`canonical_corpus_release_v2.json`** | 冻结的正式语料库——特征层读取的、每条新闻只保留一篇的文章集合（`news_features/ARTIFACT_LINEAGE.md` 说明了哪个是生产版本） |
| `corpus_eligibility_decisions.csv`、`byelection_eligibility_decisions*.csv`、`byelection_llm_v2.csv`、`*_review*.csv` | 纳入资格筛选：每篇文章的保留 / 剔除决策，包括补选和案例研究系列 |

命名约定：`_v1_provisional` 表示某一阶段的临时冻结——即生产语料库发布时所处的状态；`_review_queue` 文件是送交人工审核的行；`*_resolutions` 文件记录人工给出的答案。

## 按流水线阶段排列的完整产物索引

### 收集来源追溯（第 1B 层）

| 文件 | 内容 |
|---|---|
| `query_inventory.csv`、`query_lineage_v1.csv`、`search_log.csv` | 冻结的计划、slug 纠正谱系，以及只追加的执行日志（见上文） |
| `sidecar_archive_manifest_20260726.csv` | 为已收集页面保留的归档附属文件（sidecar）副本的清单 |
| `guardian_geographic_relevance_flags.csv`、`serpapi_domain_relevance_flags.csv` | 两项收集审计（`src/news_collection/audit_*.py`）产生的质量检查标记 |
| `pdf_date_recovery.csv` | 为那些存储的页面缺少日期的记录恢复出的日期证据 |

### 日期判定（时间顺序防线）

| 文件 | 内容 |
|---|---|
| `date_resolution_log.csv`、`date_resolution_log_v2.csv` | 逐篇文章的日期判定结果，由 `build_effective_dates.py` 读取 |
| `date_conflicts_queue.csv` | 针对相互矛盾的日期证据的人工裁决队列 |

### 清洗（第 4 阶段，`src/normalisation/`）

| 文件 | 内容 |
|---|---|
| `normalisation_input_manifest_v1.csv/.json`、`normalisation_input_records_v1.jsonl`、`normalisation_input_review_queue_v1.csv`、`normalisation_input_summary_v1.md` | 第 1 步：锁定的符合资格的文章总体及文本来源的选择 |
| `html_cleaning_log_v1.csv` + 审核队列 | 第 2 步：HTML 清洗决策 |
| `character_normalisation_log_v1.csv` + 审核队列 | 第 3 步：字符规范化决策 |
| `structure_normalisation_log_v1.csv` + 审核队列、`structure_review_resolutions_v1.csv` | 第 4 步：结构规范化及其人工处理结果 |
| `text_boundary_log_v1.csv` + 审核队列 | 第 5 步：标题 / 正文边界判定 |
| `text_quality_results_v1.csv`、`text_quality_resolutions_v1.csv`、`text_quality_review_queue_v1.csv`、`text_quality_summary_v1.md` | 第 6 步：文本质量判定及人工处理结果 |
| `missing_text_resolutions_v1.csv`、`language_review_resolutions_v1.csv` | 针对正文缺失和语言规则情形的人工处理结果 |
| `normalised_text_audit_v1_provisional.csv`、`normalised_text_manifest_v1_provisional.json`、`normalised_text_quality_report_v1_provisional.md`、`normalised_text_review_queue_v1_provisional.csv` | 第 7 步：最终经过审计的文本层（清单中记录了被 git 忽略的文本文件的哈希） |

### 去重（第 5 阶段，`src/dedup/`）

每个步骤一个文件系列，按步骤顺序排列；每个系列 = 簇 / 配对 + 审核队列 + 处理结果 / 摘要（视情况而定）。

| 文件系列 | 决定的内容 |
|---|---|
| `exact_duplicate_*_v1_provisional` | 内容逐字节相同的重复 |
| `url_groups` / `url_duplicate_mapping` / `url_resolution_*_v1_provisional` | 规范 URL 的判定 |
| `near_duplicate_*_v1_provisional` | 近似重复检测 |
| `syndication_*_v1_provisional` | 转载（联合发稿）副本的识别 |
| `article_version_*_v1_provisional` | 版本关联与时间可获得性 |
| `duplicate_cluster_*` 和 `validated_duplicate_*_v1_provisional` | 簇的验证 |
| `canonical_article_mapping` / `canonical_resolutions` / `canonical_review_queue` / `canonical_selection_report_v1_provisional` | 每条新闻保留一篇正式文章 |
| `duplicate_mapping_layer/audit/manifest/review_queue_v1_provisional` | 合并后的、临时冻结的映射层，由正式版本读取 |

### 纳入资格筛选与 LLM 分类器链

| 文件 | 内容 |
|---|---|
| `manual_review_sample.csv`、`manual_review_decisions.csv`、`manual_review_kappa_subset.csv` | 分层的人工审核试点（168 篇文章）、其决策以及双人编码的 kappa 子集 |
| `manual_review_llm_pilot.csv`、`llm_v1_disagreement_audit.csv` | v1 分类器在同一批文章上的试点及其逐行的分歧审计 |
| `llm_validation_sample.csv`、`manual_review_llm_v2_validation.csv` | 全新的 128 篇文章盲测样本，以及冻结的 v2 在其上的运行结果 |
| `manual_review_llm_v2_corpus.csv`、`manual_review_llm_v2_local_extension.csv` | 冻结的 v2 在剩余语料库和本地积压文章上的批量运行结果 |
| `llm_v2_corpus_batch_state.json`、`llm_v2_byelection_batch_state.json`、`llm_v2_local_extension_batch_state.json`、`llm_v2_local_extension_dry_run.json` | 每次冻结 v2 运行的批次 ID 和状态 |
| `second_review_queue.csv`、`full_corpus_review.csv`、`corpus_eligibility_decisions.csv` | 升级审核队列、全语料库审核表，以及最终的逐篇文章决策 |
| `e5_hard_disagreement_review_data.json`、`e5_local_manual.csv`、`e5_local_risk_review_plan.json`、`e5_local_risk_review_evaluation.json`、`e5_local_review_queue_round2_summary.json` | E5 排除规则审计：48 个严重分歧、本地人工审核，以及基于风险的盲审计划及其评估 |

### 冻结版本与案例研究

| 文件 | 内容 |
|---|---|
| `canonical_corpus_release_v1.json`、`canonical_corpus_release_v2.json` | v1/v2 特征表读取的冻结文章集合 |
| `byelection_review.csv`、`byelection_eligibility_decisions.csv`、`byelection_eligibility_decisions_e5human_v1.csv`、`byelection_llm_v2.csv`、`byelection_second_review_queue.csv` | v2 扩充背后的补选纳入资格文件系列 |
| `byelection_walkthrough_v1/` | 补选语料库在全部六个阶段中的书面走查及其发现 |
| `haslemere_probe/`（10 个文件） | Haslemere 复现：其语料库、日期、纳入资格、冻结的 v2 运行和二次审核处理结果，以及非新闻线索目录 |
| `woking_south_blind/`（10 个文件） | Woking South 盲测：在密封路径上的同一套阶段文件系列 |
| `e5_local_backlog_v3/`（3 个文件） | 揭盲之后的 v3exp 谱系：审核者准入的决策，以及 Woking South 本地实验组读取的 v3exp 语料库版本 |

关于正式语料库如何流入特征层和建模层，见 `REPO_MAP.md`。
