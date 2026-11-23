# 最终报告源码

`report.tex` 是最终报告的权威源文件。它收录的 16 张 LaTeX 表格保存在本目录中，使提交的 Overleaf 源码是自包含的；`make -C report sync-tables` 会从 `../outputs/report_tables_v1/latex/` 中权威的生成副本刷新这些表格。报告中使用的六张图位于 `figures/`。

在仓库根目录下构建 PDF：

```bash
make -C report sync-tables
make -C report
```

这会生成 `report/report.pdf`，它是本地构建产物，不纳入版本管理。按照仓库的提交材料命名规则，提交的版本应放在 `deliverables/sl1425-final-report.pdf`。完整的表格、图表和输入重建顺序记录在 `../REPRODUCIBILITY.md` 中。

## 源码历史

报告自 2026 年 8 月初起在名为 `Final Report` 的 Overleaf 项目中起草。本目录中的两张截图保存了截至 2026 年 8 月 16 日的 Overleaf 历史面板。带标签的 Overleaf 里程碑按时间顺序导入了 Git；它们的提交信息记录了对应的标签和日期。自 2026 年 8 月 16 日起，`report.tex` 直接在本仓库中维护，Git 就是最终源码的版本历史。
