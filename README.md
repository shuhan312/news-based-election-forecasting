# 从语境到后果——AI 驱动的新闻分类与事件预测

独立研究项目（Independent Research Project，伦敦帝国理工学院 MSc ACSE）。

**研究问题：** 在经过调整的、仅基于历史数据的基线之上，选举前的新闻能否为地方选举得票率的预测带来额外价值？
案例研究：2026 年萨里郡议会（Surrey County Council）选举，并特别关注英国改革党（Reform UK）——一个几乎没有选举历史的政党。

**一句话概括设计：** 第一阶段（Stage 1）仅用历史选举数据预测候选人得票率（LightGBM）；第二阶段（Stage 2）用 LLM 抽取的新闻特征对剩余误差建模（按时间窗口分别拟合的岭回归）；所有预测都在读取 2026 年选举结果之前冻结，新闻的效果与一个重新校准过的无新闻对照组进行比较。核心结果：在扩充后的训练集（v2）下，31–90 天窗口中合并新闻特征将 MAE 从 4.445 个百分点降低到 4.205 个百分点（ΔMAE +0.240，95% 置信区间 [+0.078, +0.387]）；扩充之前的 v1 在任何窗口中都没有带来改进。

## 仓库与复现

- **正式仓库：** [github.com/ese-ada-lovelace-2025/irp-sl1425](https://github.com/ese-ada-lovelace-2025/irp-sl1425)
- **复现指南：** [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
- **仓库地图：** [REPO_MAP.md](REPO_MAP.md)
- **最终报告：** [deliverables/sl1425-final-report.pdf](deliverables/sl1425-final-report.pdf)

## 仓库结构

本仓库是一个分阶段的流水线。生产步骤遵循声明好的数据流；而验证、审计和展示代码可以读取明确指名的上游产物。`tests/test_artefact_citations.py` 守护表格包和应用所使用的机器可读引用接口；它并不声称会解析每一处行文中的引用。
完整的导览——各目录的用途、报告章节与代码的对应关系，以及一份"追溯任意数字"的示例步骤——见 [REPO_MAP.md](REPO_MAP.md)。如需复现最终报告中的任何图、表或核心数字——包括环境、数据获取、重建顺序以及每张图 / 每张表对应的脚本——请参照 [REPRODUCIBILITY.md](REPRODUCIBILITY.md)。

| 位置 | 内容 |
| --- | --- |
| `src/` | 流水线本体：选举结果的收集与验证（顶层），以及 `news_collection/`、`dedup/`、`normalisation/`、`llm_extraction/`、`news_features/`、`news_modelling/` |
| `surrey-election-no-news-baseline/` | 第一阶段子项目：仅基于历史数据的基线（有独立的 README） |
| `surrey-election-extractor/` | 将官方选举结果页面转换为结构化记录的子项目（有独立的 README） |
| `news_features/`、`news_collection/`、`llm_context/`、`news_protocol/` | 冻结的证据：每个实验一个目录（结果 JSON + 发现记录）、实验协议与预注册、LLM 运行记录 |
| `outputs/report_tables_v1/` | 报告表格包：23 个 CSV + `manifest.json`（表格包输入的 sha256）+ 生成的、供报告使用的 LaTeX 表格 |
| `outputs/report_figures_v1/` | 报告图表包（10 张图） |
| `report/` | 最终报告的自包含 LaTeX 源码；其中的 16 份表格副本从 `outputs/report_tables_v1/latex/` 同步而来 |
| `app/` | 基于冻结产物的 Streamlit 浏览 / 情景分析层 |
| `demo/` | 答辩（viva）演示程序（有独立的 README）；不属于证据链的一部分 |
| `tests/` | 守护流水线、盲化、表格重新生成和产物引用的测试 |
| `logbook/`、`deliverables/`、`title/`、`scripts/` | 课程管理文件与工具脚本 |
| [`audit_leakage_provenance.py`](audit_leakage_provenance.py) | 仓库根目录下的泄漏与来源审计——见下一节 |

## 验证"无泄漏"的声明

一条离线命令即可端到端地重新检查整条审计链：每一次实际执行的搜索都能对应到冻结的、带版本号的查询计划；正式语料库中的每篇文章都早于其选举前时间窗口的截止日期；没有文章在语料库中被重复计数；新闻特征表只包含预测变量，没有任何结果列；第一阶段模型包的哈希、预测变量的使用许可以及按日期划定的训练 / 测试划分彼此一致，并且"无人竞选"仍作为单独的审计记录保留，而不是被处理成一个零得票的虚构候选人；英国改革党（Reform UK）从未与英国独立党（UKIP）合并；盲化的 v1/v2 预测冻结完好无损——已提交的冻结清单、一次性揭盲记录在评分时绑定的哈希，以及今天磁盘上的字节内容必须三者一致，并且 Git 历史显示每次冻结都在揭盲之前提交、此后从未改动；17 个本地搜索区域完全由选举结果确定性地生成——选择脚本不读取任何新闻，并且日志中每一次针对选区的搜索都是在样本提交之后才执行的。

```bash
python3 -m audit_leakage_provenance
```

该审计是确定性的，不调用任何 API，不修改任何研究输入，并将其机器可读的结论写入 [`outputs/leakage_provenance_audit_v1.json`](outputs/leakage_provenance_audit_v1.json)（已提交的副本是最近一次审计运行的结论）。它还会写出 [`outputs/provenance_audit_v1.csv`](outputs/provenance_audit_v1.csv)，这是一份精简的事件台账，其中未知的结果发布时间戳和预测创建时间戳被刻意留空，而不是推测填入；`tests/test_leakage_provenance_audit.py` 会在测试套件中运行它。

## 快速开始

需要 Python 3.14（开发环境为 3.14.6）。第一阶段子项目在 `surrey-election-no-news-baseline/requirements.txt` 中声明了自己的依赖。

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m pytest tests -q
```

## 复现报告中的产物

报告中的每张表和每张图都可以从其声明的、已提交或已恢复的冻结边界重新生成，并且构建时带有断言，一旦出现偏差就会失败。完整的命令列表见 `REPRODUCIBILITY.md`；精简版的报告包生成顺序如下：

```bash
PYTHONPATH=src .venv/bin/python -m news_modelling.build_report_tables
PYTHONPATH=src .venv/bin/python -m news_modelling.report_appendix_tables
PYTHONPATH=src .venv/bin/python -m news_modelling.stage2_fitting_cells_table
make -C report sync-tables
PYTHONPATH=src .venv/bin/python -m news_modelling.make_report_figures
PYTHONPATH=src .venv/bin/python -m news_modelling.study_design_figure
PYTHONPATH=src .venv/bin/python -m news_modelling.corpus_funnel_figure
PYTHONPATH=src .venv/bin/python -m news_modelling.pipeline_overview_figure
PYTHONPATH=src .venv/bin/python -m news_modelling.framework_figure
PYTHONPATH=src .venv/bin/python -m news_modelling.reform_party_split_figure
.venv/bin/python demo/build_viva_pack.py   # 离线答辩材料包（见 demo/README.md）
```

报告 PDF 直接从已提交的仓库目录树编译，需要带有 `latexmk` 的 TeX 发行版：

```bash
make -C report       # 生成 report/report.pdf
```

`report/report.tex` 读取 `report/` 下 16 份同步过来的 LaTeX 表格副本，从而保证提交的 Overleaf 源码是自包含的。这些表格的权威生成版本位于 `outputs/report_tables_v1/latex/`；`make -C report sync-tables` 会刷新这些副本，测试要求两者逐字节一致。

基于冻结产物的 Streamlit 浏览器可在仓库根目录下运行：

```bash
.venv/bin/streamlit run app/news_app.py
```

上游各阶段（收集、抽取、特征、建模）由 `src/` 下的 `run_*` 模块运行；`news_features/` 下每个冻结产物目录都记录了生成它的确切命令和输入。

## 本地大型产物（依据 IRP 大文件规定）

以下大型或涉及版权的产物刻意没有纳入版本管理。可重新生成的产物可以重建；而历史 API 数据、LLM 输出和冻结的预测证据则应当恢复，并与已提交的哈希进行核对。副本存放在学校的 OneDrive 文件夹 [`irp-sl1425-large-files`](https://imperiallondon-my.sharepoint.com/:f:/g/personal/sl1425_ic_ac_uk/IgBi8ECozK1UT6t7z3t8-CRpASvOBLyw6FIXgyId6DA35TY?e=Drejw9) 中（伦敦帝国理工学院账号持有者可以查看）。

下面每个 `.tar.gz` 都是在仓库根目录下以相对路径创建的，因此把它下载到仓库根目录并运行 `tar -xzf <archive>`，即可将其内容恢复到原来的位置。

| OneDrive 项目 | 大小 | 恢复位置 / 方式 | 重新生成方式 |
| --- | --- | --- | --- |
| v1 `blinded_predictions.csv` | 约 20 MB | 放入 `news_features/blinded_2026_predictions_v1/` | 历史冻结的预测字节；其完整性由旁边已提交的清单保证 |
| v2 `blinded_predictions.csv` | 约 10 MB | 放入 `news_features/blinded_2026_predictions_v2/` | 历史冻结的预测字节；其完整性由旁边已提交的清单保证 |
| `d4_llm_outputs.json`、`d4_llm_outputs_haiku.json` | 1.3 + 1.6 MB | 放入 `llm_context/` | 冻结的 LLM 原始响应（包含文章文本，因版权原因未纳入 git）；用已提交的 `d4_llm_output_manifest.json` 核验 |
| `corpus_extraction_outputs_*.json`（九个批次） | 约 16 MB | 放入 `llm_context/` | 重建相应特征版本所需的原始抽取边界；用已提交的批次摘要 / 清单核验 |
| `model_bundle_v1/` | 约 15 MB | 放入 `surrey-election-no-news-baseline/outputs/` | 由子项目中已纳入版本管理的第一阶段工作流生成 |
| `data-batch1-small.tar.gz` | 91 MB | 在仓库根目录解压——恢复 `data/raw/news/{records,api_raw,quarantine}`、`data/raw/{guardian,wikipedia,newsapi,news_pilot,surrey_county_council,surrey_2026}`、`data/processed`、`data/elections` | 恢复或重新获取原始输入；已纳入版本管理的代码会重建下游版本 |
| `data-batch2-text.tar.gz` | 430 MB | 在仓库根目录解压——恢复 `data/raw/news/text/` | 恢复冻结的文章文本；下游构建程序无法逐字节重新生成它 |
| `data-batch3-html.tar.gz` | 812 MB | 在仓库根目录解压——恢复 `data/raw/news/html/` | 恢复冻结的源页面抓取 |
| `pdf/`（592 个文件） | 3.2 GB | 将该文件夹下载到 `data/raw/news/pdf/` | 恢复原始来源 PDF；常规的报告复现不会再次处理它们 |
| `excluded_sidecars_20260726.tar.gz` | 3.3 GB | 放入 `data/archives/` | 排除决策的归档，作为证据保留 |

`tests/test_artefact_citations.py` 守护表格包和应用的引用接口，以及那些被指名的、按设计仅保存在本地的例外。报告表格的测试会将全部 16 张收录的 LaTeX 表格（包括单独推导的第二阶段时间线表）与 `report/` 下的自包含副本进行核对。

## AI 使用声明

在代码开发和仓库整理过程中，我通过 [Anthropic API 和 Claude 工具](https://www.anthropic.com/) 使用了 Anthropic 的 Claude Sonnet 5 和 Claude Haiku 4.5，并使用了 OpenAI 的 [ChatGPT](https://chatgpt.com/) 和 [Codex](https://openai.com/codex/)（包括 GPT-5.6 Sol），用于有针对性的辅助。Claude Sonnet 5 和 Claude Haiku 4.5 也是已声明的研究流水线的一部分，用于议题、立场和框架的分类。开发方面的辅助包括：讨论流水线的组织方式；起草或完善部分 Python 代码和单元测试的框架；审阅 Markdown 文档、JSON 元数据和清单文件；以及协助调试、可复现性检查和泄漏 / 来源审计。

研究问题、方法论、特征定义、纳入与排除决策、结果解读和结论均由我本人确定。我在采纳 AI 辅助的建议之前都对其进行了审阅、修改和测试，拒绝了没有仓库证据支持的建议，并对提交的工作承担全部责任。最终的仓库体现了我本人的实现决策和理解，我能够解释所提交各组件的目的和运行方式。

## 模块事务说明（IRP 原有说明）

请熟悉并遵守 [GitHub 仓库使用说明](https://ese-msc.github.io/irp/repos/)。

严禁删除或修改本仓库中原有的 GitHub Actions 工作流或目录结构。IRP 文件应与原有文件"共存"。

定时工作流会定期检查 `main` 分支上的 `logbook/logbook.md` 最近是否有更新，以及仓库（任意分支）是否有定期提交。如果检测到不活跃，系统会自动以 issue 的形式发出警告。这些 issue 不得关闭。
