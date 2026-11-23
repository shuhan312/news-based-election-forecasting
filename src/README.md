# `src/` —— 新闻流水线代码（第 1–5 层）

## 用途及在 IRP 中的角色

本目录包含为项目新闻部分做准备、并拟合第二阶段新闻模型的代码。它检验选举前的新闻是否能**在仅基于历史数据的第一阶段基线**（`surrey-election-no-news-baseline/`）**之外提供额外的预测信息**。它把原始新闻文章转换成经过验证的"选举–政党–时间窗口"特征，并拟合项目核心比较中所使用的残差模型。

这里**只存放代码**。它的输出和冻结证据位于仓库根目录——`news_collection/`、`llm_context/`、`news_features/`——报告表格位于 `outputs/`。关于完整的八层流水线，以及任何一个报告数字如何追溯到生成它的代码，见 [`../REPO_MAP.md`](../REPO_MAP.md)。

## 编号说明：层（Layer）不是建模阶段（Stage）

本仓库刻意使用两套不同的编号体系：

- **流水线第 1–8 层（Pipeline Layers 1–8）** 描述端到端的数据流和证据流。
- **建模第 1–2 阶段（Modelling Stages 1–2）** 区分仅基于历史数据的基线（第一阶段）和新闻残差模型（第二阶段）。

因此，第二阶段建模位于**流水线第 5 层**。收集过程内部的查询阶段（A–H、M、M2）和纳入资格阶段（1–5）只是局部的工作流标签，既不是建模阶段，也不是流水线层。

部分第 2 层的 README 还保留了最初新闻处理协议中的编号：文本规范化是**第 4 阶段（Phase 4）**，去重是**第 5 阶段（Phase 5）**。这些是层内部的历史工作流标签，并不是额外的流水线层。这两个组件都属于当前的**流水线第 2 层**；保留这些阶段编号只是为了让代码仍能追溯到最初的协议。

## `src/` 中涵盖的层

| 流水线层 | 代码位置 | 职责 |
| --- | --- | --- |
| **1A —— 官方选举输入** | 顶层的 `src/*.py`；`surrey-election-extractor/` | 构建并验证选举结果、日历和名称表，新闻以它们为基准对齐 |
| **1B —— 新闻收集与纳入资格** | `news_collection/` | 获取选举前的语料库，并记录每一项纳入 / 排除决策 |
| **2 —— 清洗与规范化** | `normalisation/`、`dedup/` | 清洗文本、合并重复项并选出一篇正式文章 |
| **3 —— LLM 抽取与验证** | `llm_extraction/` | 抽取议题 / 立场 / 框架标签，执行人工一致性关卡，并冻结被接受的标签 |
| **4 —— 特征构建** | `news_features/` | 把被接受的标签聚合成"选举–政党–时间窗口"特征表，并执行防泄漏检查 |
| **5 —— 建模** | `news_modelling/`；第一阶段的同级项目 | 加载冻结的第一阶段模型包，拟合第二阶段残差模型，冻结预测并执行一次性揭盲 |

第 6–8 层位于 `src/` 之外：冻结证据在 `news_features/` 和 `news_protocol/` 中，报告表格 / 图表在 `outputs/` 中，最终的使用方在 `report/`、`app/` 和 `demo/` 中。权威的八层地图以及从报告到代码的追溯见 [`../REPO_MAP.md`](../REPO_MAP.md)。

## 流水线概览

```text
第 1 层  官方选举输入 + 新闻收集与纳入资格
   ↓
第 2 层  文本规范化 + 文章存储 + 去重
   ↓
第 3 层  LLM 议题 / 立场 / 框架 → 验证关卡 → 冻结标签
   ↓
第 4 层  选举 × 政党 × 时间窗口 特征表
   ↓
第 5 层  第一阶段历史基线 + 第二阶段新闻残差模型
   ↓
第 6–8 层  冻结证据 → 报告包 → 报告 / 应用 / 答辩 使用方
```

## 目录结构

| 位置 | 作用 |
| --- | --- |
| `news_collection/` | 第 1B 层：新闻检索以及纳入资格 / 泄漏筛查 |
| `normalisation/`、`dedup/` | 第 2 层：清洗与规范化 |
| `llm_extraction/` | 第 3 层：LLM 标签、验证与冻结证据 |
| `news_features/` | 第 4 层：确定性的特征构建与防泄漏检查 |
| `news_modelling/` | 第 5 层：第二阶段残差建模、盲化、揭盲与诊断 |
| 顶层脚本 | 第 1A 层：构建新闻据以对齐的选举表和日历 |

每个子目录都有自己的 README，列出其中的文件以及内部的执行步骤顺序。

## 如何运行代码

并不是每个 `.py` 文件都是可执行程序。受支持的入口是有文档说明的 `run_*` 和 `build_*` 模块；schema、验证器、估计器和比较辅助模块通常由这些入口导入。直接运行辅助模块既不是必需的，也不构成一个单独的复现步骤。

| 层 | 受支持命令的文档位置 | 执行规则 |
| --- | --- | --- |
| 1A | 下面的顶层脚本指南 | 只在仓库根目录下运行所需的独立构建器或验证器 |
| 1B | [`news_collection/README.md`](news_collection/README.md) | 查询阶段使用收集命令行工具，纳入资格 / 版本发布工作使用有文档说明的构建器 |
| 2 | [`normalisation/README.md`](normalisation/README.md)、[`dedup/README.md`](dedup/README.md) | 按顺序运行 `build_*` 链 |
| 3 | [`llm_extraction/README.md`](llm_extraction/README.md) | 使用生产批处理运行器和健康检查；验证模块用于支撑已记录的证据，API 调用不应随意重复运行 |
| 4 | [`news_features/README.md`](news_features/README.md) | 运行所需的 v1/v2 或明确指名的扩展构建器 |
| 5 | [`news_modelling/README.md`](news_modelling/README.md) | 使用指名的冻结 / 揭盲运行器；其余模块是报告诊断、图表构建器或被导入的建模逻辑 |

每一层的 README 也都给出了其离线验证命令。完整的仓库复现顺序记录在 `REPO_MAP.md` 中；某个文件出现在文件指南中，并不意味着它必须被单独运行。

### 第 1A 层：顶层的官方选举输入脚本

直接位于 `src/` 下的零散脚本是第 1 层中官方选举数据的分支：每个脚本构建一项供流水线其余部分对齐的共享输入（`data/elections/` 中的结果表、选举日历、名称标准化表）。它们是独立脚本，而不是多步骤的子流水线，因此放在顶层而不是放在一个包里。按用途分组：

- **官方结果 → `data/elections/` 中的表** —— `fetch_official_scc_results.py`、`fetch_2026_surrey_results.py`、`convert_2013_extractor_output.py`、`convert_2026_extractor_output.py`、`add_2013_wikipedia_turnout.py`（填补官方页面缺失的 2013 年投票率）、`fetch_election_results.py`、`aggregate_results.py`（写出 `ward_party_results.csv` 和 `ward_winners.csv`，预注册的选区样本会读取它们）、`build_election_calendar.py`、`audit_turnout.py`、`validate_election_results.py`
- **名称标准化与抽样** —— `build_name_standardisation.py`、`build_division_sample.py`
- **新闻覆盖检查** —— `check_newsapi_coverage.py`、`pilot_news_retrieval.py`、`verify_news_coverage_audit.py`

已被取代的早期代码——`build_model_dataset.py` 原型、导师介入之前的新闻脚本（`legacy_pre_supervisor_news/`）以及研究工作簿构建器（`build_research_workbook.py`，其规格早于当前的结果 schema）——已从工作目录树中移除，保留在 Git 历史中。

**输出与复现。** 这些脚本写出已提交的 `data/elections/` 参考表（`2013_scc_results.csv`、`2026_east/west_surrey_results.csv`、`election_calendar.csv`、`candidate_name_standardisation.csv` 及其日志），因此这些表已经在仓库中，无需重新生成。`convert_*` 脚本读取冻结的抽取器输出，可以确定性地复现；`fetch_*`、日历和维基百科投票率脚本读取外部来源，因此重新运行它们会得到一份新的快照，而不是与已提交表格逐位一致的副本。请在仓库根目录下运行脚本（部分脚本，例如 `build_name_standardisation.py`，会导入同级模块，需要设置 `PYTHONPATH=src`）。

## 可复现性与防泄漏控制

生产路径是分阶段的；验证、审计和展示模块也可以读取明确指名的上游产物。预测变量和结果变量保持分离，缺失值会被标记而不是被填补，LLM 标签只有在通过 κ ≥ 0.60 的人工一致性关卡之后才会进入第 4 层并随即冻结，第二阶段对冻结的第一阶段基线的残差建模，以检验新闻特征能否在历史数据之外提供额外的预测信息。报告中的数字都可以追溯到已提交的产物，报告表格包锁定了它读取的每个输入的 sha256（见 `REPO_MAP.md` 和根目录的 `REPRODUCIBILITY.md`）。依据 IRP 大文件规定，`data/` 下的大型原始输入按设计只保存在本地。
