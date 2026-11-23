# `outputs/` —— 生成的产物与审计记录

本目录包含下游产物。它不是原始数据来源，但其中各项的角色并不相同：报告包是生成的展示产物，机器可读的审计台账记录了一个经过验证的仓库状态，而体积较大的工作文件则保留在本地。

## 报告包（第 7 层）——已提交并以哈希锁定

### 表格

`report_tables_v1/` 包含：

- 23 张机器可读的表格（`t01`–`t23`），由 `news_modelling.build_report_tables` 写出；
- `manifest.json`，锁定该表格包构建程序读取的每一个输入；
- 权威的生成 LaTeX 目录，它被镜像到自包含的 `report/` 源码中。

`news_modelling.report_appendix_tables` 把表格包以及明确指名的冻结证据格式化为 LaTeX 表格；`stage2_fitting_cells_table` 则单独推导第二阶段的时间线表。报告收录了 16 个生成的 / 静态的视图，它们被镜像到 `report/` 下，并由测试逐字节锁定。其余的 LaTeX 表格是组件视图或仅存在于表格包中的视图。见 [`report_tables_v1/README.md`](report_tables_v1/README.md)。

### 图表

`report_figures_v1/` 包含 10 张生成的图表。它们由多个模块生成，而不是一个：

- `make_report_figures.py` 写出六张核心分析图；
- `study_design_figure.py`、`corpus_funnel_figure.py` 和 `framework_figure.py` 写出三张结构图；
- `reform_party_split_figure.py` 写出改革党拆分图。

书面报告读取的是 `report/figures/` 中已提交的、供报告使用的副本。它使用了本图表包中的五张图，再加上在 `news_features/pipeline_overview_v1/` 下构建的流水线总览图；图表包中其余的图是补充材料。确切的六个文件的对应关系见 [`../REPRODUCIBILITY.md`](../REPRODUCIBILITY.md)。

构建时的断言和表格重新生成测试会在数值或展示出现偏差时失败。完整的"报告章节 → 产物 → 代码"追溯见 [`../REPO_MAP.md`](../REPO_MAP.md)。

## 已提交的审计与保留的证据

本目录还存放一些小型的已提交输出，它们的价值在于所记录的结论或项目证据，包括泄漏 / 来源审计的 JSON 和 CSV。这些文件并不会仅仅因为位于 `outputs/` 下就成为报告包的输入；生成它们的命令及其权威性记录在文件旁边或根目录的复现指南中。

## 研究工作簿与标注队列——本地、可重新生成

其他目录可能是体积较大的工作产物——综合研究工作簿、主工作簿和新闻工作簿、D4 及人工标注队列、时间窗口方案比较以及进度汇报幻灯片。依据 IRP 大文件规定，它们**被 git 忽略**并保存在 OneDrive 上；构建每一个文件的代码都纳入了版本管理（见 `scripts/` 和 `src/`），因此可以按需重新生成。这里唯一提交的叙述性文档是 `IRP_Surrey_Election_Experiment_Log_*.md`。

## 规则

只有当生成的输出是报告的依赖、精简的机器可读审计结论，或明确保留的最终证据时，才提交它。体积较大的便利性输出保留在本地。一个文件的权威性来自其有文档记录的生成者、输入和哈希——而不是来自它位于 `outputs/` 之下这一事实。
