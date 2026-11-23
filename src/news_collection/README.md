# `src/news_collection/` —— 新闻收集与纳入资格（第 1 层）

流水线第 1 层（新闻部分）：获取选举前的新闻语料库，对其进行纳入资格筛选，并记录每一项保留 / 剔除决策。本目录**只存放代码**。它生成的产物——查询清单、只追加的搜索日志、纳入资格决策和语料库统计——位于仓库根目录的 [`news_collection/`](../../news_collection/README.md)；原始语料库本身位于 `data/raw/news/`，不提交。各阶段和规则的设计依据是 `news_protocol/`。并不是每个文件都在生产路径上：下面的完整文件指南按功能对所有模块分组，主线列在最前面。

## 1. 主线

```text
build_query_inventory      →  冻结的确定性查询清单（2,470 条查询；A–H、M、M2）
run_collection / runner    →  通过适配器（SerpAPI、出版方站内搜索、网页存档）执行查询，
                              每次搜索向 search_log.csv 追加一行（可断点续跑）
resolve_publication_dates  →  阶段 1：确定每篇文章的发布日期及其置信度
assess_eligibility         →  阶段 2：用脚本执行预注册的 I/E 规则
build_manual_review_sample →  阶段 3：针对脚本无法判定的规则生成人工审核表
run_llm_corpus_batch_v2    →  阶段 4：在剩余语料库上运行冻结的、经 κ 验证的 LLM 分类器
assemble_corpus_decisions  →  阶段 5：把脚本、人工和 LLM 的决策合并为最终记录
canonical_corpus_release   →  切出可审计的语料库版本供特征层读取（v2 加入了补选）
```

```bash
python3 -m src.news_collection.run_collection --stage A|B|C|D|E|F|G|H|M|M2
python3 -m src.news_collection.build_query_inventory
python3 -m src.news_collection.make_collection_report
```

两套独立的阶段体系——请勿混淆：

- **收集阶段 A–H、M 和 M2** —— 查询清单的分组，用 `run_collection --stage` 运行。
- **纳入资格流水线阶段 1–5** —— 日期 → 纳入资格 → 审核表 → 冻结的 LLM 批处理 → 合并。主语料库运行一次这套流程；每个案例研究留出样本都在新的路径上用同样冻结的规则复现它。

## 2. 按功能分组的完整文件指南

### 2.1 收集引擎（主线）

| 文件 | 作用 |
|---|---|
| `build_query_inventory.py` | 根据选区样本和选举结果构建确定性的查询清单 |
| `run_collection.py` | 分阶段收集的命令行入口 |
| `runner.py` | 通过适配器执行查询清单，并记录每一次搜索 |
| `adapters.py` | 生产用的来源适配器（SerpAPI、出版方站内搜索、网页存档） |
| `schema.py` | 已收集文章的记录构造与验证 |

### 2.2 日期判定

| 文件 | 作用 |
|---|---|
| `resolve_publication_dates.py` | 发布日期判定阶段（每篇文章的日期、来源和置信度） |
| `build_effective_dates.py` | 把日期判定的各个阶段合并成一张查找表 |
| `recover_pdf_dates.py` | 为存储的页面缺少日期的三条记录恢复日期证据 |

### 2.3 纳入资格规则与人工审核

| 文件 | 作用 |
|---|---|
| `assess_eligibility.py` | 用脚本执行预注册的纳入 / 排除规则 |
| `manual_review_schema.py` | 所有审核表的 schema、理由代码分类体系和验证规则 |
| `build_manual_review_sample.py` | 抽取可复现的分层审核样本（168 篇文章的试点） |
| `finalize_manual_review.py` | 把手工填写的审核表转换为已提交的决策 |
| `compute_review_agreement.py` | 独立审核之间的百分比一致率和 Cohen's kappa（与 `llm_extraction` 共用） |

### 2.4 LLM 纳入资格分类器——v1 试点（验证历史）

已记录的试点，它为在 E4/E5/E6/E8 规则上使用 LLM 提供了依据：它与 168 条人工决策的一致性，就是冻结的 v2 分类器背后的证据。

| 文件 | 作用 |
|---|---|
| `llm_classifier.py` | 针对人工审核规则的 v1 分类器 |
| `run_llm_classification_pilot.py` | 在人工编码过的同一批 168 篇文章上运行 v1 |
| `compare_llm_to_human_agreement.py` | 将试点结果与人工决策比较评分 |
| `audit_llm_pilot_disagreements.py` | 对每一处试点分歧进行逐行审计 |

### 2.5 LLM 纳入资格分类器——冻结的 v2（生产）

| 文件 | 作用 |
|---|---|
| `llm_classifier_v2.py` | 冻结的 v2 分类器定义 |
| `llm_v2_io.py` | 每次冻结 v2 运行共用的确定性 I/O |
| `build_llm_validation_sample.py` | 抽取全新的 128 篇文章盲测验证样本 |
| `run_llm_validation_v2.py` | 在该盲测样本上运行一次冻结的 v2 |
| `compare_llm_validation_agreement.py` | 将冻结的 v2 与 128 篇人工编码文章比较评分 |
| `run_llm_corpus_batch_v2.py` | 冻结的 v2 在剩余语料库上的批量运行 |
| `build_full_corpus_review_sheet.py` | 批处理之后针对剩余语料库的审核表 |

### 2.6 E5（相关性）排除规则审计

证明数量最多的排除规则被正确执行的证据。

| 文件 | 作用 |
|---|---|
| `build_e5_local_queue.py` | 通过了所有机械规则的 1,060 篇本地文章 |
| `build_e5_risk_review_plan.py` | 针对本地 E5 的、基于风险的盲审人工审核计划 |
| `build_e5_disagreement_review_data.py` | 汇总 48 个 E5 严重分歧，以便透明地审核 |
| `run_llm_local_extension_v2.py` | 冻结的 v2 分类器在新的本地积压文章上的运行 |

### 2.7 语料库合并与版本发布

| 文件 | 作用 |
|---|---|
| `assemble_corpus_decisions.py` | 把脚本、人工和 LLM 的决策合并为最终的纳入资格记录 |
| `canonical_corpus_release.py` | 切出可审计的 v1 语料库版本，供特征层读取 |
| `canonical_corpus_release_v2.py` | v2 版本：主语料库加上补选 |

### 2.8 收集诊断与质量审计

| 文件 | 作用 |
|---|---|
| `make_collection_report.py` | 重新生成本地语料库诊断，并重新验证已存储记录的 schema |
| `audit_guardian_geographic_relevance.py` | 标记在修复 production-office 问题之前收集的《卫报》（Guardian）记录（已提交标记 CSV） |
| `audit_serpapi_domain_relevance.py` | 标记域名不可能与英国相关的 SerpAPI 记录（已提交标记 CSV） |
| [`audit_leakage_provenance.py`](../../audit_leakage_provenance.py)（仓库根目录） | 跨层断言，涵盖查询谱系、时间顺序、重复、第一阶段划分 / 预测变量治理、第二阶段结果隔离、政党身份以及盲化预测冻结；写出详细的 JSON 以及一份精简的时间线 CSV |

### 2.9 案例研究复现（冻结的规则，新的路径）

每个时间留出样本都原封不动地重放纳入资格阶段 1–5，并单独存放，以保证其盲化状态。

| 链条 | 文件 |
|---|---|
| 补选（v2 语料库） | `run_byelection_stages.py`、`run_byelection_llm_batch.py`、`run_byelection_assembly.py`、`build_byelection_second_review_queue.py`、`walk_byelection_pipeline.py`（书面走查，附已提交的发现） |
| Haslemere 复现（§5.6） | `run_haslemere_probe_stages.py`、`run_haslemere_probe_llm_batch.py`、`run_haslemere_probe_assembly.py`、`catalogue_haslemere_nonnews_trail.py`（描述性的非新闻线索） |
| Woking South 盲测（§5.6） | `run_woking_south_blind_stages.py`、`run_woking_south_blind_llm_batch.py`、`run_woking_south_blind_assembly.py` |
| 揭盲之后的 v3exp 谱系 | `run_e5_backlog_v3_assembly.py` —— 并行的 v3 决策；v1/v2 表不使用它，但基于它构建的 v3exp 特征表服务于 Woking South 盲测的本地实验组（§5.6） |

## 3. 运行与可复现性

收集过程查询的是**实时的新闻 API 和存档**，因此无法逐位重跑——之后的运行看到的是已经变化了的新闻网络。因此语料库是一个**冻结的快照**：已提交的是确定性的查询清单、只追加的 `search_log.csv`、纳入资格决策和一份 `sha256` 清单，而不是原始文章。这里的"可复现"指的是查询清单和每一项保留 / 剔除决策都可以从已提交的文件重新生成并审计——而不是说原始语料库可以被完全相同地重新收集。查询清单依赖于已提交的最终地理对照表，如果缺少该输入就会明确报错。`query_lineage_v1.csv` 说明了四条已记录查询的情况，它们旧的 `-ward` URL slug 已被取代。704 条未执行的 E/G/H 查询仍作为明确的计划覆盖保留；它们从不被当作零结果的搜索。

机器可读的审计通过以下命令重建：

```bash
python3 -m audit_leakage_provenance
```

## 4. 不花费 API 额度即可验证本目录

确定性逻辑（schema、审核规则、一致性评分、队列构建、冻结分类器的 I/O）由离线单元测试覆盖：

```bash
python -m pytest tests/test_manual_review.py tests/test_llm_classifier.py \
    tests/test_llm_classifier_v2.py tests/test_llm_local_extension.py \
    tests/test_e5_disagreement_review_data.py tests/test_e5_risk_review_plan.py \
    tests/test_canonical_news_corpus.py tests/test_walk_byelection_pipeline.py
```

少数测试在需要可重新生成的本地收集状态时，会在全新克隆的仓库中自动跳过（跳过原因中会写明重新生成该状态的构建器）。

## 5. 规范

每一次执行的搜索都会被记录，包括零结果和失败的搜索；纳入资格由冻结的规则和经过验证的分类器决定，绝不临时决定；不提交任何文章文本。关于语料库如何输入流水线的其余部分，见 `REPO_MAP.md`。
