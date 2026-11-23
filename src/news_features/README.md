# `src/news_features/` —— 特征构建（第 4 层）

流水线第 4 层（新闻部分）：把已标注的文章语料库转换成模型所连接的"选举–政党–时间窗口"**特征表**，并附带泄漏审计。本目录**只存放代码**。它生成的表位于仓库根目录的 [`news_features/`](../../news_features/README.md)；它读取的已标注语料库位于 `llm_context/` 和 `news_collection/`。下面的示意图就是完整的文件指南：一个引擎（主线）、五个轻量包装脚本、一个辅助模块、两个独立的诊断脚本——共九个文件。

## 文件之间的关系（一览）

一个引擎，被五个轻量包装脚本导入；两个诊断脚本独立在一旁。这里的文件之间不存在其他导入关系。

```
llm_context/corpus_extraction_outputs_*.json      （冻结的 LLM 标签）
news_collection/canonical_corpus_release_*.json   （冻结的语料库）
        │
        ▼
build_feature_table.py  ── 引擎 ──────────► news_feature_table_v1.csv
   加载 → 冻结 → 检查 → 累计                       （冻结的、扩充之前的参照）
        → 生成行 → 报告关卡 → 写出
   导入一个辅助模块：actor_party_attribution.py
        │   每个包装脚本 = `import build_feature_table as frozen`，
        │   重新绑定几个全局变量，调用 frozen.main() —— 链条本身从不改变
        ├─ build_feature_table_v2.py       ─► v2.csv     ★ 主要的验证性结果
        ├─ build_feature_table_v3exp.py    ─► v3exp.csv    本地新闻谱系：Woking South 盲测（§5.6）+ 本地重跑（表格包 t19）
        ├─ build_feature_table_v3party.py  ─► v3party.csv  政党粒度 → 安慰剂 / 分解 / 立场
        ├─ build_haslemere_probe_features.py     ─► Haslemere 留出样本   （报告 §5.6）
        └─ build_woking_south_blind_features.py  ─► Woking South 留出样本（报告 §5.6）

diagnose_article_area_attribution.py ─► 4.2% / 94.2% 的区域发现（论证粒度选择，§6.4）
diagnose_feature_grain.py            ─► 训练单元格计数
   （两者都直接读取语料库——不属于构建过程，输出不输入任何表）
```

本 README 的其余部分逐一展开每个方框：引擎、包装脚本、`main()` 内部按顺序执行的七个步骤，以及为什么粒度不是选区级别。

## 生产特征表由一个引擎构建

第二阶段模型所连接的特征表由单一引擎 **`build_feature_table.py`** 构建。它读取冻结的 LLM 抽取批次（`llm_context/corpus_extraction_outputs_*.json`）和冻结的正式语料库版本，对记录去重（最新批次优先），并把它们**直接在文件内**聚合到 `(election, party, window)` 粒度。所有聚合规则、零单元格策略、本地 / 全国实验组的拆分以及训练变异性报告关卡都位于 `build_feature_table.py` 内部——它**并不**编排一串可导入的阶段模块。

运行 `build_feature_table.py` **就是** v1 构建。其他每张生产表都是一个轻量包装脚本：它导入引擎（`import build_feature_table as frozen`），重新绑定几个模块级全局变量（语料库来源、输出路径、划分角色、选举网格），然后调用 `frozen.main()`：

| 文件 | 输出表 | 在最终报告中的角色 |
| --- | --- | --- |
| `build_feature_table.py` | `news_feature_table_v1.csv` | **引擎**；冻结的、扩充之前的参照 |
| `build_feature_table_v2.py` | `news_feature_table_v2.csv` | 扩充后的验证性版本（+8 场补选）——**主要结果** |
| `build_feature_table_v3exp.py` | `news_feature_table_v3exp.csv` | 本地新闻谱系（+29 篇审核者准入的本地文章）；**Woking South 盲测**（§5.6）的本地实验组在其上拟合，探索性的本地重跑（`local_v3_rerun.py`，表格包表 t19，最终报告正文未引用）也读取它 |
| `build_feature_table_v3party.py` | `news_feature_table_v3party.csv` | 政党粒度的内容表（开启 `PARTY_CONTENT_ATTRIBUTION`）；**所有政党层面的探索性 / 安慰剂 / 分解分析都读取它**（`identity_placebos`、`reform_decomposition`、`stance_volume_*`、`stage1_party_sensitivity`、`placebo_specifications` 等） |
| `build_haslemere_probe_features.py` | Haslemere 探测特征 | 案例研究留出样本的特征，复用引擎（为保持盲化而单独存放） |
| `build_woking_south_blind_features.py` | Woking South 特征 | 案例研究留出样本的特征，复用引擎（为保持盲化而单独存放） |

`actor_party_attribution.py` 是引擎导入的唯一辅助模块。它**只有**在开启 `PARTY_CONTENT_ATTRIBUTION`（即 `v3party` 包装脚本）时才会生效；在 v1/v2 验证性构建中它虽被导入，但处于休眠状态。

生产表的命名与对应关系见 [`news_features/ARTIFACT_LINEAGE.md`](../../news_features/ARTIFACT_LINEAGE.md)。报告**并列评估 v1 和 v2；v2 提供主要的正面验证性结果。**

## 逻辑链条（按顺序）

第 4 层是 `build_feature_table.py`（`main()`）内部的一次确定性处理：它读取冻结的上游文件，写出一张特征表。不存在需要运行的阶段脚本链——下面的步骤是那*一个文件内部*按顺序执行的操作。

1. **加载标签** —— `load_records()` 读取每个 `llm_context/corpus_extraction_outputs_*.json`，只保留仍然有效（未被排除）的抽取层，按 `article_id` 去重并且**最新批次优先**，同时遵循所有的 `superseded_layers`。
   → 得到每一层被接受的记录，以及来源信息（每条记录来自哪个批次和哪个提示词）。
2. **冻结语料库** —— `build_release()` 合并主语料、试点和验证三路纳入资格数据流，并应用日期、主要选举范围、六个时间窗口和文本可获得性。
   → 得到正式文章集合以及 `corpus_size`。
3. **两道检查** —— 每篇抽取文章都必须位于该版本之内（出现 `unexpected_ids` 会终止构建），并且去重后的文章数不得超过 `corpus_size`（悄无声息的重复计数会抬高每一个数量类特征）。
4. **累计** —— 对文章遍历一次，填充三个计数器：`election_cells`（每个选举 × 时间窗口的文章数、议题数和框架数）、`party_cells`（政党文章数和形象刻画，取自**立场层自身对每个政党的判断**），以及 `party_arm_cells`（同上，但按本地 / 全国收集实验组拆分）。
5. **生成行** —— 在六个时间窗口和六个累积快照上，每个 `(election, party, period)` 生成一行：计算 `party_article_share`、`net_portrayal` 和 `net_portrayal_share`，**保留零文章单元格**（计数为 `0`，占比留空），生成本地 / 全国列，并在每一行上断言 `local + national == combined`。
6. **报告关卡** —— `training_variation` 统计每一列*在一个时间段内*不同训练取值的个数：`< 3` 为不足（insufficient），`< 10` 为可拟合但不可报告（fittable-not-reportable），`>= 10` 为可用（usable）。在 v1/v2 中，恰好是 **12 个政党层面的列**通过。
7. **写出** —— `news_feature_table_*.csv`（固定使用 LF 换行，逐字节稳定）及其 `*_metadata.json`。

`__main__` 代码块设置 `EXCLUDED_TRANCHES = V1_EXCLUDED_TRANCHES` 并调用 `main()`——这就是 v1 构建。每个包装脚本都在不同的语料库或留出样本上重复这条**完全相同**的链条；链条中的任何东西都不会改变。

### 其他文件的作用

- **包装脚本**（`_v2`、`_v3exp`、`_v3party`、`build_haslemere_probe_features`、`build_woking_south_blind_features`）——导入引擎，重新绑定几个全局变量，重新运行第 1–7 步。每个脚本输入哪一项报告结果见上表。
- **`actor_party_attribution.py`** —— 引擎导入的辅助模块；只在 `v3party` 包装脚本中生效（开启 `PARTY_CONTENT_ATTRIBUTION`），在 v1/v2 中处于休眠状态。
- **诊断脚本** —— `diagnose_feature_grain.py` 和 `diagnose_article_area_attribution.py`（报告引用的粒度决策证据；两者都直接读取语料库，独立于构建过程）。

## 粒度，以及为什么不是选区级别

任务要求按选区构建特征。但语料库做不到这一点：只有约 **4.2%** 的正式文章带有明确的萨里区域，而 **94.2%** 根本没有提到任何明确的区域。因此这张表以 `(election, party, window)` 为键；把它与基线的 `(election, area, party)` 行连接时，每个值会被广播到该场选举的所有区域上。这里的新闻特征可以解释**不同选举之间、不同政党之间**的差异，**但永远无法解释同一场选举内不同区域之间**的差异——这一局限在构建器的 docstring 中明确说明，而不是隐藏在某个特征名称背后。

由此产生两个后果，都在引擎内部处理：

- **计数和占比两者都有。** 计数会受到某场竞选被搜索得有多深入的影响；占比则不会。每个计数列都配有一个对应的占比列。
- **显式保留零文章单元格。** 一次已完成但没有找到任何符合资格文章的搜索，会被保留为一行，计数为 `0`，占比**留空**（分母为零时占比是未定义的，而不是零）——缺失的覆盖会被如实表示，从不被悄悄填补或丢弃。

每个特征还带有一个根据表本身计算出的 `training_variation` 判定（`insufficient` / `fittable_not_reportable` / `usable`），因此只有在训练行之间确实存在变化的列才会提供给模型。在 v1/v2 中，这使得 **12 个政党层面的占比 / 净形象刻画列**被判定为 `usable`；选举层面的议题列和框架列为 `insufficient`/`fittable`，被排除在报告的模型之外。

## 已从 main 中移除：选区级试点和揭盲之后的探测

较早的 **67 篇文章的选区级试点**（`alignment` / `time_windows` / `scope_classification` / `article_features` / `context_aggregation` / `recency_weighting` / `missing_news` 及其 `run_*` 运行器）、它的下游（`feature_selection_v1`、`ward_party_election_features_v1`、`specification_coverage`、`residual_feasibility`、`ward_resolution_v1`），以及揭盲之后的 `build_feature_table_v4e5local` / `e5_local_triage` 探索性构建，都已**从最终的 `main` 中移除**。`build_feature_table.py` 没有导入其中任何一个，也没有任何报告结果引用它们的输出。它们保留在 git 提交历史中以备审计；上述复现路径上的任何东西都不依赖它们。

## 诊断

- `diagnose_feature_grain.py` —— 构建器所引用的训练单元格计数。
- `diagnose_article_area_attribution.py` —— 论证"选举–政党–时间窗口"粒度选择的 4.2% / 94.2% 区域归属发现（直接读取语料库，独立于构建过程）。

## 运行与输出

构建是**确定性的**：它读取冻结的文件，因此重新运行会逐位复现相同的表（一个重建测试锁定了 v1 和 v2）。在仓库根目录下：

```bash
python3 -m src.news_features.build_feature_table       # news_feature_table_v1.csv
python3 -m src.news_features.build_feature_table_v2     # news_feature_table_v2.csv（主要结果）
python3 -m src.news_features.build_feature_table_v3exp  # 本地新闻谱系
python3 -m src.news_features.build_feature_table_v3party # 政党粒度的内容表
```

每个命令都会把各自的 `news_feature_table_*.csv` 和 `*_metadata.json`（行数、语料库指纹、粒度、`empty_cell_policy`、`zero_article_cells`、`training_variation`、`usable_columns`、来源信息）写入仓库根目录的 `news_features/` 目录。

## 不花费 API 额度即可验证本目录

构建过程由离线单元测试覆盖——重建测试逐字节锁定 v1 和 v2 表，归属辅助模块和议题分组映射有各自的测试套件，版本契约则进行端到端检查：

```bash
python -m pytest tests/test_feature_table_rebuild.py \
    tests/test_party_content_attribution.py tests/test_issue_group_mapping.py \
    tests/test_news_feature_release.py
```

需要被 git 忽略的冻结批次文件（`llm_context/corpus_extraction_outputs_*.json`）的测试，会在全新克隆的仓库中自动跳过；跳过原因中会写明需要从 OneDrive 恢复的文件。

## 规范

预测变量列与结果变量列保持分离；缺失的新闻会被显式表示，而不是被填补。每张表的元数据记录了其粒度、可用列和来源信息。独立的跨层审计（`outputs/leakage_provenance_audit_v1.json`）检查时间顺序、重复、结果隔离和政党身份。关于这些表如何输入第二阶段建模，见 `REPO_MAP.md`。
