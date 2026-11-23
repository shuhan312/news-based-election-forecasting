# 萨里无新闻基线（Surrey no-news baseline）

IRP 的第一阶段：**只使用投票日之前就已存在的信息**、不使用任何新闻，预测萨里郡每个选区中每位候选人的得票率。英国改革党（Reform UK）是本研究关注的政党，自始至终单独报告；英国改革党和英国独立党（UKIP）从不合并，任何 UKIP 的观测都不会被当作关于改革党的证据。

这是导师要求的核心比较基准——新闻层必须超越它。它的输出是一个带版本号的**模型包**，其中的折外（out-of-fold）预测就是新闻阶段的输入。

它是 `surrey-election-extractor` 的同级目录，而不是一个独立的 Git 仓库。两者职责不同：

- `surrey-election-extractor` 负责官方来源的抽取、来源追溯、派生 / 分析字段的治理，以及模型输入契约的发布；
- `surrey-election-no-news-baseline` 负责特征、数据划分、模型、评估指标以及导出的模型包。

建模层从不编辑官方选举数据，也从不导入抽取器的内部模块。它读取已发布的 JSON 契约，特征和目标分别保存在不同的文件中，作为一种结构上的防泄漏控制：

```text
surrey-election-extractor/outputs/no_news_candidate_contests/
├── no_news_candidate_contest_features.json
└── no_news_candidate_contest_targets.json
```

---

## 1. 主线

在仓库根目录下、激活项目虚拟环境后运行。如果仓库根目录下共用的 `.venv` 还不存在，请先按照 `surrey-election-extractor/README.md` 中的说明创建（`python3 -m venv .venv`，然后对每个子项目的 `requirements.txt` 执行 `pip install -r`）：

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train
```

该命令读取 `config/baseline_model.yaml`，在每一个按时间顺序划分的折上为三种架构打分，选出其中一种，进行拟合，并把模型包写入 `outputs/model_bundle_v1/`。整个过程需要几分钟。

在长时间运行之前，先检查它将要做什么——下面两条命令都是即时完成的：

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli config
```

`config` 打印应用配置文件和所有命令行参数之后**最终生效**的设置，因此在拟合任何东西之前就能看出某个覆盖设置是否没有生效。`validate` 检查一个文件后退出。

### 六页界面

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m streamlit run surrey-election-no-news-baseline/app/streamlit_app.py
```

包括上传与验证、模型配置、训练、结果、可解释性和导出。该应用**读取模型包并调用命令行工具**；它从不从工作簿中抽取数据，也从不在进程内拟合模型，因此它展示的每个数字都来自一条可以重新运行的命令。训练作为子进程启动，其日志以流式方式显示在页面上。

如果契约缺失或已过期，先重新生成它：

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python surrey-election-extractor/scripts/generate_no_news_candidate_contests.py
```

依赖：`numpy`、`lightgbm`、`pyyaml`、`pytest`，以及界面所需的 `streamlit`、`pandas` 和 `openpyxl`。LightGBM 是必需的——架构 B 是任务要求的比较对象之一，如果缺少这个比较对象而程序又悄无声息地失败，比较报告就会在只比较了两种架构的情况下声称尝试了三种。

### 从零复现模型包

在仓库根目录下、激活 `.venv` 后，按顺序执行：

```bash
# 1) 重新生成本包读取的候选人契约（来自抽取器）
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_candidate_contests.py

# 2) 输出模型包要复制进去的划分清单和泄漏审计
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/build_candidate_split_and_leakage.py

# 3) 拟合并导出模型包（需要几分钟）
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train

# 4) 确认没有任何东西被破坏
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m pytest surrey-election-no-news-baseline/tests -q
```

当第 3 步的日志显示折外 MAE 为 9.85、留出集 MAE 为 4.53，并且第 4 步报告整个测试套件全部通过时，即确认复现成功。在全新克隆的仓库中第 2 步很重要：模型包构建器会在 `split_manifest.csv` 和 `leakage_audit.csv` 存在时把它们复制进模型包，不存在时则发出警告，因此先生成它们可以保证模型包是完整的。

---

## 2. 按功能分组的完整文件指南

### 2.1 交付的候选人模型——核心路径

命令行工具是公开入口；它把完整的训练运行委托给模型包构建器。理解最终报告中的第一阶段需要看的就是下面这些文件。

| 角色 | 主要文件 |
| --- | --- |
| 命令入口 | `no_news_baseline/cli.py` |
| 第一阶段的完整编排与模型包导出 | `scripts/build_candidate_model_bundle.py` |
| 按时间顺序的折与留出集 | `no_news_baseline/candidate_splits.py` |
| 预测变量许可与防泄漏规则 | `no_news_baseline/candidate_leakage_audit.py` |
| 35 个预测变量编码为 127 个输入 | `no_news_baseline/candidate_features.py` |
| 岭回归（Ridge）架构 | `no_news_baseline/candidate_share_model.py` |
| 部分池化（partial pooling）架构 | `no_news_baseline/candidate_hierarchical_model.py` |
| 最终基线所选用的 LightGBM 架构 | `no_news_baseline/candidate_boosted_model.py` |
| 三种架构的比较与选择关卡 | `no_news_baseline/candidate_architecture_selection.py` |
| 候选人、政党和英国改革党的评估指标 | `no_news_baseline/candidate_metrics.py` |
| 竞选内排名与席位预测 | `no_news_baseline/candidate_seat_projection.py` |
| 冻结的建模假设 | `config/baseline_model.yaml` |

执行路径为：

```text
no_news_baseline/cli.py
    -> scripts/build_candidate_model_bundle.py
    -> 数据划分 + 泄漏审计 + 特征编码器
    -> Ridge / 部分池化 / LightGBM 比较
    -> 选中的 LightGBM 拟合
    -> outputs/model_bundle_v1/
```

### 2.2 交付的候选人模型——支撑模块

| 文件 | 作用 |
| --- | --- |
| `candidate_cohort.py` | 估计目标（estimand）、群组成员资格、竞选内归一化、排名和席位分配 |
| `candidate_data_validation.py` | 对建模契约做席位数和投票日期的验证 |
| `candidate_contestation.py` | "无人竞选"记录——没有参选的政党没有对应的行，也从不被记录为零 |
| `candidate_evidence_layers.py` | 每个字段来自哪一个证据层（官方 / 派生 / 分析） |
| `candidate_historical_strength.py` | 郡级的历史政党实力预测变量 |
| `candidate_interactions.py` | 英国改革党的交互项，以及带标签、默认关闭的 UKIP 模块 |
| `candidate_probability_model.py` | 单独拟合的当选概率模型，带席位数约束 |
| `candidate_explainability.py`、`candidate_tree_explainability.py` | SHAP、各折的系数和不稳定特征；针对交付的架构 B 的树模型专用解释 |
| `architecture_paired_bootstrap.py` | 架构比较的配对 bootstrap 不确定性 |
| `election_dates.py` | 共用的选举日期解析器，是按时间顺序划分和防泄漏规则的基础 |
| `configuration.py` | 按"命令行参数 → 文件 → 默认值"解析配置，并把结果记录在模型包中 |
| `logging_setup.py` | 训练运行的日志记录，以及关于哪些内容可以写入日志的那条规则 |
| `scripts/build_candidate_split_and_leakage.py` | 独立的划分清单和泄漏审计输出脚本（复现顺序中的第 2 步） |

### 2.3 界面与支撑

| 位置 | 作用 |
| --- | --- |
| `app/streamlit_app.py`、`app/loaders.py`、`app/views.py` | 六页界面：入口、模型包 / 契约加载以及各个页面；它读取模型包并调用命令行工具，从不在进程内拟合 |
| `config/baseline_model.yaml` | 所有可调整的假设及其理由（见下文"配置"） |
| `outputs/` | 只存放产物——由带版本的代码和抽取器契约重新生成，不纳入 Git |
| `tests/` | 离线测试套件，大致每个源模块对应一个测试模块；最重要的那些测试断言的是某件事*会失败* |

---

## 模型做什么

**目标变量。** `analysis_vote_share` —— 一位候选人的得票数占该竞选中全部投票数的比例。模型在变换后的尺度上拟合，即 `share × candidates ÷ 100`，当一位候选人恰好获得平均份额时该值等于 1.0。否则单席位和双席位竞选处于不同的尺度上，不经变换就同时在两者上拟合的模型学到的会是席位数，而不是政治因素。

**预测。** 先预测候选人得票率，然后在竞选内排名，再取前 *N* 名作为当选（*N* 是选举前已知的席位数），最后得到当选概率——在对数几率（log-odds）上平移，直到每场竞选的概率之和等于其席位数。

**数据划分。** 严格按时间顺序并以日期为界，从不随机划分。分组单位是 `election_id + division_id`，因此同一场竞选的候选人永远不会被拆开。包括四个命名的开发折、十二个滚动起点折、一个**主留出集**（2026 年 5 月 7 日投票的所有内容，被视为同一个时间段，因此同一天的事件不会互相用作训练），以及一个**次留出集**（Haslemere，2026 年 7 月 7 日），后者分别在包含和不包含 5 月结果的情况下评估。

**泄漏。** `candidate_leakage_audit.py` 对每一列进行分类，并标明使该列首次可获得的事件。凡是从被预测的那场选举派生出来的内容——得票数、得票率、投票率、胜选差距、得票率变化——一律禁止使用，如果有一项进入了特征矩阵，测试就会失败。

---

## 配置

`config/baseline_model.yaml` 保存所有可调整的假设，并在旁边写明理由。每个值同时也是代码中的默认值，因此这个文件可以精简到只包含你想修改的项；之所以完整地发布，是因为一份需要读者从源代码中重建的配置算不上配置。有一个测试断言该文件仍然与代码默认值一致，所以两者不会悄无声息地出现偏差。

**无法识别的键会使运行停止。** 被悄悄忽略的拼写错误是配置文件最糟糕的失败方式：运行报告成功，设置却从未生效，而且没有任何东西记录下这个差异。

优先级为**命令行参数 → 文件 → 代码默认值**，最终生效的结果会写入模型包，因此模型包总会记录它实际是用什么设置构建的。

### 选择架构

`selection.mode: auto` 按复杂度从低到高、先简单后复杂的顺序执行两道关卡。挑战者必须把英国改革党得票率的 MAE 改善 5% 以上，*并且*最多只在一个开发折上落败。把 `mode` 设为某个架构的名称则直接交付该架构——即任务所要求的手动模式：

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train --architecture C_partial_pooling --output surrey-election-no-news-baseline/outputs/model_bundle_manual_c
```

手动选择**并不会**取消比较。所有架构仍然会被打分，`architecture_comparison.csv` 仍然会被写出，`architecture.json` 会记录 `"overridden": true`，并在旁边写明关卡本来会得出的结论。如果一次覆盖抹去了它所覆盖的内容，那就与一次正常的选择无从区分了。

### UKIP 敏感性运行

任务允许把 UKIP 作为一个单独的背景特征：标注清楚、默认关闭，并与不使用它的模型进行比较。

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train --ukip-interactions --output surrey-election-no-news-baseline/outputs/model_bundle_ukip
```

这只会加入 UKIP 自己的交互列，别无其他。它不会把 UKIP 合并进英国改革党。

---

## 模型包

`outputs/model_bundle_v1/` —— 29 个由清单跟踪的产物，加上清单本身以及只追加的训练日志。最先应该阅读的是：

| 文件 | 回答的问题 |
| --- | --- |
| `model_card.md` | 这个模型是什么，以及它不得被用于什么 |
| `metrics.json` | 所有评估指标，按选举、政党和竞选类型细分 |
| `reform_metrics.json` | 单独列出的英国改革党指标，以及每个被淘汰架构在改革党上的数字 |
| `architecture.json` | 选了哪个架构、如何选出、基于多少证据 |
| `architecture_comparison.csv` | 三种架构在每个折上的结果，因此被淘汰的架构依然可见 |
| `leakage_audit.csv` | 每个字段，无论被允许还是被排除，以及原因 |
| `split_manifest.csv` | 每一行属于哪个折 |
| `out_of_fold_predictions.csv` | **第二阶段训练输入**：用于构造残差目标的历史折外预测 |
| `holdout_predictions.csv` | **第二阶段预测输入**：冻结的 2026 年第一阶段基线，新闻调整量将叠加在它之上 |
| `holdout_seat_projection.csv` | 每场竞选预测的获胜政党，与实际结果对照 |
| `holdout_party_seat_totals.csv` | 每个政党预测的席位数，与实际结果对照 |
| `explainability.json` | SHAP、各折的系数、不稳定特征、示例 |
| `data_quality_report.json` | 按字段和选举统计的缺失情况，以及按选举统计的政党数量 |
| `training_config.yaml` | 构建该模型包时最终生效的配置 |
| `bundle_manifest.json` | 每个文件的 SHA-256，使后续阶段能够证明它加载的是哪一个模型包 |

`training.log` 在每次运行时都会追加内容，并且不计入清单哈希，因为它是在计算清单的同时写入的。

清单**只对本次运行实际写出的文件**计算哈希。输出目录在多次重建之间会被复用，否则旧版本遗留下来的文件会被当作当前代码生成的文件计入哈希——导致模型包声称包含一些重建时无法再生成的文件。目录中发现的其他文件都会以警告形式记录，并列在 `files_not_written_by_this_run` 之下。

### 交接给新闻阶段

第一阶段止于模型包。第二阶段在本子项目之外的 `src/news_modelling/` 中实现：

```text
outputs/model_bundle_v1/out_of_fold_predictions.csv
    -> 第二阶段拟合所用的历史残差目标

outputs/model_bundle_v1/holdout_predictions.csv
    -> 冻结的 2026 年无新闻基线

两个文件
    -> src/news_modelling/stage1_bundle.py
    -> run_blinded_2026_predictions.py / run_blinded_2026_predictions_v2.py
    -> news_features/blinded_2026_predictions_v1/ / _v2/
```

`stage1_bundle.py` 在新闻模型使用这些文件之前，会先验证必需的文件、划分角色和模型包的完整性。模型包是本地生成的输出，而它的代码、配置和文档都纳入了版本管理。

---

## 测试

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m pytest surrey-election-no-news-baseline/tests -q
```

测试套件中最重要的测试断言的是某件事*会失败*：被禁止的字段进入设计矩阵、一场竞选被拆分到不同的折、2026 年 5 月 7 日的数据行进入训练、未知值被悄悄变成零或 "No"、UKIP 模块缺少其对应的改革党基础项、配置中出现不存在的键、席位数大于候选人数、一场选举有两个投票日期、一个已发布的列没有对应的证据层。每次运行时，全部六个 Streamlit 页面都会以无界面方式渲染。

---

## 文档

`docs/` 包含最终方法的文档，以及保留下来的验证证据和负面结果证据：

- [`candidate_level_estimand.md`](docs/candidate_level_estimand.md) —— 为什么分析单位是候选人而不是政党
- [`candidate_split_and_leakage.md`](docs/candidate_split_and_leakage.md) —— 数据划分设计与泄漏审计
- [`candidate_model_card.md`](docs/candidate_model_card.md) —— 交付模型的模型卡
- [`historical_strength_features.md`](docs/historical_strength_features.md) —— 郡级历史数据，以及在引入交互项修复之前它对线性架构造成的损害
- [`reform_interaction_terms.md`](docs/reform_interaction_terms.md) —— 交互项实验，以及它暴露出的统计效力不足的选择设计
- [`ukip_contextual_sensitivity.md`](docs/ukip_contextual_sensitivity.md) —— UKIP 模块的运行，与不使用它的模型的比较，以及为什么没有选用它
- [`architecture_selection_evidence.md`](docs/architecture_selection_evidence.md) —— 三种架构在每个划分角色上的表现，选择 B 带来了什么、付出了什么代价
- [`data_validation_and_evidence_layers.md`](docs/data_validation_and_evidence_layers.md) —— 席位和日期验证，以及为什么模型三分之二的输入是派生的而不是官方的

`outputs/` 下的所有内容都由带版本的代码和抽取器契约重新生成，不纳入 Git。代码、测试、配置、文档和研究决策都纳入了版本管理。

---

## 在阅读任何数字之前值得了解的局限性

- **英国改革党在 2026 年之前的样本只有十四个不同的行**，分布在各个开发折中。每一个针对改革党的开发阶段数字都以此为基础，`reform_metrics.json` 为此带有一个 `small_sample_warning` 标记。
- **模型选择与留出集的结论不一致。** 合并的开发折选择了架构 B；而在主留出集上架构 C 明显更好。这一点如实报告而没有加以"解决"——如果依据留出集来选择，就等于把留出集用掉了。这意味着开发阶段的证据无法可靠地区分这两种架构。
- **留出集不是盲的。** 它的指标在开发过程中被读取过。虽然没有任何 2026 年的数据行进入训练，也没有任何超参数是针对它选择的，但这种纪律比设计初衷要弱。模型卡中已披露这一点。
- 该模型预测的是汇总结果中的统计规律。它并不能说明任何个人为什么会那样投票。
