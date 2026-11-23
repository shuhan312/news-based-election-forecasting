# 萨里选举结果抽取器（Surrey Election Results Extractor）

本子项目构建 IRP 所使用的、保留原始来源的萨里郡议会选举数据库（流水线第 1A 层）。它为无新闻的第一阶段基线提供历史选举数据，项目以此为基准，检验选举前的新闻能否在以往选举结果之外提供额外的预测信息。该流水线保留来源证据、验证抽取出的数值，并为下游建模生成可供审计的特征和目标数据集；模型的拟合与评估属于下游工作，不在本子项目的范围之内。并不是每个文件都在生产路径上：下面的完整文件指南按功能对所有模块分组，主线列在最前面。

当前版本概要：

- 24 个选举事件：2013、2017 和 2021 年的主要选举，分别举行的东萨里和西萨里 2026 年选举，以及 19 场补选。
- 1,992 行候选人数据，343 行选区（division）或分区（ward）数据。
- 24 条经过审核的 2021→2026 地理对应关系，以及 205 条经过批准的历史参照。
- 官方数值从不被修改；补充层、派生层和分析层各自保留独立的来源和状态字段，官方未公布的空缺保持可见。

## 1. 主线

`run_extraction_workflow` 按顺序分阶段处理一个主要选举页面、区域索引页面或单个结果页面的 URL：验证 URL，运行一次不消耗配额的预检，发现所有区域以固定官方公布的分母（每场已配置的 2013–2021 年选举都必须找到全部 81 个选区），为每个区域抽取候选人表格和投票汇总，验证记录并构建工作簿。对于每个官方页面，获取顺序为：(1) 议会官方的实时页面，(2) 互联网档案馆（Internet Archive）中归档的官方副本，(3) 搜索引擎索引的证据。搜索摘要从不覆盖官方数据行，缺失的来源数值也从不靠推断填补。

已发布的数据集可以根据已提交的审计离线重建，无需下载选举页面，也不需要 API key。首先创建一次环境（`python3 -m venv .venv && source .venv/bin/activate && pip install -r surrey-election-extractor/requirements.txt`），然后在仓库根目录（`irp-sl1425`）下按以下顺序运行：

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_master_election_database.py
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_final_position_qa.py
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_final_election_data_release_audit.py
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_electoral_baseline.py
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_candidate_contests.py
```

最后一条命令写出 `outputs/no_news_candidate_contests/`——这是第一阶段基线（`surrey-election-no-news-baseline/`）读取的输入契约。

端到端交接：

```text
官方页面 / 存档 / 搜索索引
    -> run_extraction_workflow（经过验证的工作簿）
    -> 已提交的 config/ 证据 + 审计
    -> generate_master_election_database.py（分析用数据载荷）
    -> generate_no_news_candidate_contests.py
    -> surrey-election-extractor/outputs/no_news_candidate_contests/
    -> surrey-election-no-news-baseline/（第一阶段读取这一版本）
```

## 2. 按功能分组的完整文件指南

整个子项目贯穿一条命名约定：`election_extractor/X.py` 存放纯逻辑，`scripts/generate_X.py`（或 `run_X.py`）是它的运行器，写出一项输出或审计，`tests/test_X.py` 对其进行测试。下面的表格列出各逻辑模块；除非另有说明，每个模块都有配对的运行器和测试。

### 2.1 抽取引擎（主线）

| 文件 | 作用 |
|---|---|
| `workflow.py` | 针对一次抽取请求的应用层编排 |
| `discovery.py` | 以官方存档优先的方式发现选举区域 |
| `extraction.py` | 从索引证据中抽取候选人级别的结果 |
| `validation.py` | 对抽取出的结果记录进行只读验证 |
| `completeness.py` | 选举、选区和候选人层面的完整性评估 |
| `workbook.py` | 为经过验证的结果生成 Excel 工作簿 |
| `election_config.py` | 声明式的选举配置，负责加载和验证 |
| `official_source.py` | 针对官方结果页面的公开 HTTP 诊断 |
| `official_archive_fallback.py` | 官方页面被拦截时，合法地退回使用归档副本 |
| `url_utils.py` | 官方 URL 的验证与规范化 |
| `models.py` | 各阶段共用的、与提供方无关的记录模型 |
| `search_providers/` | `base.py` 接口、`serpapi.py` 生产适配器、`mock_provider.py`（用于无需 API key 的测试） |
| `app.py` | 轻量的 Streamlit 外壳；收集输入并调用 `run_extraction_workflow`，所有规则都在库中实现 |
| `scripts/run_configured_election_pipeline.py` | 为一场已配置的选举运行流水线 |
| `scripts/run_2026_east_west_extraction.py` | 为东萨里和西萨里 2026 年选举分别运行经过验证的流水线 |

### 2.2 兼容性审计（运行前的结构检查）

| 文件 | 作用 |
|---|---|
| `compatibility_audit.py` | 兼容性审计用的只读证据辅助函数 |
| `election_compatibility.py` | 针对已配置选举的兼容性检查 |
| `election_2026_compatibility.py` | 针对已发布的 2026 年萨里地图索引的检查 |
| `scripts/run_2013_compatibility_audit.py`、`run_2026_compatibility_audit.py` | 范围受限的只读审计运行器；已提交的 2026 年审计输出记录了东 / 西萨里页面在抽取之前就通过了结构检查和多席位检查 |

### 2.3 主数据库与版本审计

| 文件 | 作用 |
|---|---|
| `master_database.py` | 组装保留原始来源的多场选举分析数据载荷 |
| `election_history.py` | 以证据为准入条件的选举事件时间线和补充层 |
| `election_structure_metadata.py` | 单独审计的选举结构元数据 |
| `supplementary_metadata.py` + `supplementary_metadata_audit.py` | 附加的补充证据层及其政策 |
| `derived_metadata.py` | 与官方证据分开保存的计算值 |
| `division_supplementary_audit.py` | 2013 年选区证据审计（不修补官方数据） |
| `final_data_release_audit.py` | 主数据库的发布就绪审计 |
| `scripts/generate_layered_completeness_report.py`、`generate_2021_data_quality_report.py`、`generate_election_event_timeline.py`、`generate_2013_*` | 每场选举的完整性、质量和时间线报告（提交在 `outputs/` 下） |

### 2.4 政党与候选人身份

| 文件 | 作用 |
|---|---|
| `party_lookup.py` | 明确的、保留原始来源的政党名称查找表；英国改革党（Reform UK）和英国独立党（UKIP）从不合并 |
| `candidate_name_standardisation.py` | 生成展示用的标准名称，但不据此断言身份 |
| `candidate_continuity_evidence.py` | 关于候选人历史和现任身份的明确证据 |
| `candidate_continuity_review.py` | 针对重复出现的已公布姓名的审核队列；不做模糊匹配 |

### 2.5 派生的分析字段（结果侧，绝不作为预测变量）

| 文件 | 作用 |
|---|---|
| `analysis_vote_share.py` | 带来源标签的、用于分析的候选人得票率 |
| `analysis_voting_summary.py` | 可直接用于分析的投票汇总数值；官方字段保持不变 |
| `derived_final_position.py` + `final_position_qa.py` | 透明的得票排名及其质量检查版本 |
| `derived_winning_margin.py` | 根据官方数据行计算的单席位胜选差距 |
| `change_in_vote_share.py` | 仅作为结果的、按确切标签计算的政党得票率变化；按政策被排除在无新闻预测变量之外 |

### 2.6 地理对照（输入选区样本和历史参照）

| 文件 | 作用 |
|---|---|
| `geographic_overlap_audit.py` | 基于官方公开图层的、可审核的 GIS 重叠候选 |
| `geographic_mapping_review.py` + `geographic_mapping_decision.py` + `geographic_mapping_audit.py` | 历史区域到 2026 年区域映射的审核数据集、分析可比性决策以及证据审计 |
| `geographic_crosswalk_resolution.py` | 把 GIS 关系判定为直接、部分和受阻三类输出；其已提交的 `final_direct_mapping_dataset.json` 是本地新闻选区样本所引用的地理证据 |
| `population_weighted_crosswalk.py` | 按人口加权的 2021→2026 对照估计（仅用于审计；从不重新分配选票） |

### 2.7 历史参照与新闻之前的基线

| 文件 | 作用 |
|---|---|
| `historical_reference_permissions.py` | 关于把历史区域用作 2026 年参照的明确许可审计（即 205 条经过批准的参照） |
| `principal_election_continuity.py` | 针对 2024 年之前主要选举的单独法律延续性审计 |
| `historical_baseline.py` | 以证据为准入条件的历史基线层，在任何新闻建模之前构建 |

### 2.8 补选

| 文件 | 作用 |
|---|---|
| `by_election_results.py` | 有证据支撑的补选候选人结果 |
| `by_election_historical_reference.py` | 针对以往按确切标签计算的政党得票率基线的资格审计 |
| `by_election_source_recovery.py` | 只读的官方来源恢复审计，针对那些页面需要借助新闻存档来核实的补选 |
| `scripts/generate_by_election_integration_audit.py` | 对组装好的补选记录进行整合与验证审计 |

### 2.9 无新闻版本——通往第一阶段的桥梁

| 文件 | 作用 |
|---|---|
| `no_news_baseline.py` | 带来源标签的选举基线，在任何新闻特征出现之前构建 |
| `no_news_candidate_contest.py` | 候选人竞选建模版本；`surrey-election-no-news-baseline/` 把 `outputs/no_news_candidate_contests/` 作为其输入契约读取 |

### 2.10 证据与政策输入（`config/`）

以 JSON 形式保存的、冻结并经过核实的输入证据和政策；每条记录都保留其来源 URL 和验证状态。这些文件包含人工判断，无法由代码重新生成。

| 文件 | 内容 |
|---|---|
| `elections.json` | 声明式的选举配置，包括每场主要选举必须发现的 81 个选区的定义 |
| `party_standardisation.json` | 明确的政党名称查找表；英国改革党（Reform UK）和英国独立党（UKIP）保持分开 |
| `historical_reference_permissions.json` | 经过批准的历史区域参照，附其法定来源和 GIS 来源 |
| `principal_election_continuity_permissions.json` | 2024 年之前主要选举的法律延续性许可 |
| `geographic_crosswalk_resolution_policy.json`、`geographic_mapping_decision_policy.json` | 判定 GIS 关系和决定分析可比性的政策 |
| `geographic_overlap_audit.json`、`geographic_mapping_audit.json` | 经过审核的 GIS 重叠候选和映射证据记录 |
| `candidate_continuity_evidence.json` | 关于候选人历史和现任身份的明确证据 |
| `2013_division_turnout_evidence.json` | 填补 2013 年官方未公布空缺的人工投票率证据 |
| `supplementary_metadata.json`、`derived_metadata.json` | 附加的补充证据层，以及与官方字段分开保存的计算值 |
| `final_missing_field_evidence_index.json`、`final_position_second_source_reviews.json` | 官方页面从未公布的字段的证据索引，以及针对派生排名的第二来源审核 |
| `by_election_event_catalogue.json`、`by_election_official_results.json`、`by_election_historical_reference_permissions.json`、`by_election_source_recovery_audit.json` | 19 场补选事件、其有证据支撑的结果、参照许可以及来源恢复决策 |

### 2.11 已提交的审计输出（`outputs/`）

每个目录都是由其生成脚本写出的一份已提交、人类可读的审计；流水线中没有任何环节会读回它们。

| 目录 | 生成者 | 证明的内容 |
|---|---|---|
| `2013/2017/2021_layered_completeness/`、`2026_east/west_layered_completeness/` | `generate_layered_completeness_report.py` | 每场选举的抽取相对于固定区域分母的完整性 |
| `2021_data_quality_report/` | `generate_2021_data_quality_report.py` | 针对已完成的 2021 年审计的数据质量结论 |
| `2013_supplementary_metadata_audit/` | `generate_2013_supplementary_metadata_audit.py` | 范围受限的 2013 年补充元数据政策审计 |
| `2026_compatibility_audit/` | `run_2026_compatibility_audit.py` | 东 / 西萨里 2026 年页面在抽取之前就通过了结构检查和多席位检查（时间顺序证据） |
| `by_election_source_recovery/` | `generate_by_election_source_recovery_audit.py` | 页面缺失的补选的官方来源恢复记录 |
| `election_event_timeline/` | `generate_election_event_timeline.py` | 以证据为准入条件的事件时间线及其数据字典 |
| `final_position_provenance_audit/` | `audit_final_position_provenance.py` | 官方页面不公布排名，因此最终名次是一个带标签的派生字段 |
| `geographic_mapping_audit/`、`geographic_mapping_decision/`、`geographic_mapping_review/`、`geographic_crosswalk_resolution/`、`population_weighted_crosswalk/` | 对应的 `generate_geographic_*` / `generate_population_*` 脚本 | 经过审核的 2021→2026 地理链条；`geographic_crosswalk_resolution/final_direct_mapping_dataset.json` 是本地新闻选区样本所引用的已提交证据 |
| `historical_baseline_features/` | `generate_historical_baseline_features.py` | 历史基线特征字典与方法论 |

### 2.12 来源审计与政策（`docs/`）

| 文件 | 作用 |
|---|---|
| `election_data_readiness_audit.md` | 权威的当前状态版本概要（字段覆盖、计数、边界） |
| `historical_longitudinal_field_provenance_audit.md` | 每个滞后 / 派生字段的逐字段来源和证据边界 |
| `supervisor_field_coverage_matrix.md` | 导师要求的当前字段覆盖矩阵，由 `test_release_documentation.py` 与版本绑定 |
| `2013_byfleets/epsom_ewell_issued_ballots_audit.md`、`2013_elmbridge_issued_ballots_recovery_audit.md`、`2013_runnymede_archived_declarations_audit.md`、`2017_reigate_rejected_ballots_audit.md` | 针对特定缺失选票数值的人工来源恢复审计——已提交配置条目背后独一无二的人工证据 |
| `by_election_supplementary_metadata_audit.md`、`supplementary_metadata_governance.md` | 补充元数据证据审计，以及链接各项选票审计的治理总览 |
| `candidate_and_incumbency_evidence_audit.md` | 候选人历史和现任身份字段背后的官方证据审计 |
| `change_in_vote_share_policy.md`、`winning_margin_derivation_policy.md` | 结果侧分析字段的派生政策，包括它们被排除在无新闻预测变量之外的规定 |
| `historical_reference_permission_audit.md`、`principal_election_continuity_audit.md` | 授予历史参照许可和 2024 年之前延续性许可的审计 |
| `historical_baseline_feature_layer.md`、`no_news_electoral_baseline.md`、`final_election_data_release_protocol.md` | 历史基线组件说明、无新闻基线版本说明，以及最终发布协议 |
| `streamlit_extractor_release_verification.md`、`technical_notes.md` | 干净环境下的应用验证记录，以及关于解析器 / 分页 / 提供方的技术说明 |

## 3. 来源恢复与审计策略

议会的实时网站部署在 Imperva Incapsula 反爬虫防护之后，经常返回一个验证挑战页面，而不是公布的表格。出现这种情况时，应用**不会**尝试绕过防护：它会退回使用互联网档案馆 Wayback Machine 中合法归档的官方副本；只有当议会页面被拦截、*并且*不存在可用的归档副本时，才会切换到仅使用搜索索引的模式。每个归档数值都记录其抓取时间戳、确切的 `web.archive.org` 快照 URL 以及抽取证据，因此归档数值始终可审计，并且能与实时获取的数值区分开。逐区域的审计会保留尝试时间、查询、结果数量、选中的 URL 和验证警告；它们从不保留提供方的原始响应或凭据。

## 4. Streamlit 应用

这个单页应用接受一个主要选举的入口页面、一个区域索引 URL 或一个官方分区 / 选区结果 URL，并生成一个工作簿，其中包含一个索引页、每个区域一个工作表以及一份抽取日志：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r surrey-election-extractor/requirements.txt
cd surrey-election-extractor && streamlit run app.py
```

SerpAPI key 在一个遮蔽输入框中输入，只在本次请求期间保存在内存中，从不写入项目文件或工作簿；本仓库中不包含任何真实的 key。区域状态分为：`Complete`（所有必需数值都存在并通过验证）、`Incomplete`（官方公布的数值缺失或正在审核中；空白项会在审计中列出，从不被填补）、`Failed`（无法抽取到可靠数据）。干净环境下的发布检查记录在 [`docs/streamlit_extractor_release_verification.md`](docs/streamlit_extractor_release_verification.md) 中。

## 5. 输出与可复现性

主要的生成文件包括：主数据库数据载荷、schema 和审计摘要，最终版本审计，以及无新闻基线版本和竞选版本（路径位于 `outputs/` 下）。生成的工作簿和大型研究输出保存在 Git 之外的学校 OneDrive 上；代码、配置、测试和精简的审计文档仍纳入版本管理，并且版本可以根据已提交的审计离线重建，因此复现时并不需要这些工作簿。这里链接了一个有代表性的完整抽取作为示例：

[有代表性的 2017 年完整抽取，仅为样例（OneDrive）](https://imperiallondon-my.sharepoint.com/:f:/r/personal/sl1425_ic_ac_uk/Documents/IRP%20Surrey%20Election%20Extractor/2017%20Full%20Extraction?csf=1&web=1&e=DFwaAb)

## 6. 不需要 API key 即可验证本目录

测试套件针对模拟的官方页面和索引结果离线运行——不需要、也不会消耗真实的 SerpAPI key。在 `surrey-election-extractor/` 目录下、激活项目环境后运行：

```bash
python -m pytest -q
```

397 个测试覆盖了每个逻辑模块、各运行器以及应用的验收路径；验收测试会用 `openpyxl` 重新打开生成的工作簿字节，核验预期的工作表、数值、空白单元格、超链接和审计结构。

## 7. 局限性以及来源与推断政策

官方结果字段从不使用较低证据层的数据填补；只有当某个派生值或分析值的输入、公式、范围和来源都被保留时，才会发布它。禁止模糊匹配候选人、合并英国独立党（UKIP）与英国改革党（Reform）、未经批准的边界转移以及选票重新分配。官方页面可能会遗漏某个数值（导出时会把该字段留空并把该区域标记为 Incomplete，而不是写入一个计算出的零）；索引的标题和摘要可能不完整或被截断；只有当选举、区域和结果 URL 都匹配时才会合并证据；归档副本按抓取时的样子再现官方页面，包括其中的空缺。预测变量和目标选举的结果分开存储：无新闻输入版本包括 343 行的选区历史表，以及 1,992 行的候选人竞选版本，后者被第一阶段基线作为其输入契约使用。
