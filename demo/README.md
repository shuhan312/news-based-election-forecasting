# 答辩演示程序（`demo/`）

一个本地、离线的研究演示程序，为答辩（viva）而制作，服务于研究课题 **"Context to Consequence — AI-Driven News Categorisation and Event Prediction"（从语境到后果——AI 驱动的新闻分类与事件预测）**（2026 年萨里地方选举，重点关注英国改革党 Reform UK）。

## 隔离声明

本目录**不属于报告结果所依赖的工作**。这里的任何内容都不会输入流水线、冻结的预测、报告表格或报告图表。它*只是一个浏览层*：展示的每个数字都是**在构建时从 `outputs/report_tables_v1/` 中已提交的、冻结的产物读取的**（其 `manifest.json` 锁定了每个上游输入的 sha256），每张图都嵌入自已提交的 `outputs/report_figures_v1/`。如果材料包中任何一个核心数字与冻结产物不一致，构建就会**失败**。没有任何数字是编造的，探索性结果也会如实标注为探索性结果，与报告完全一致。

## 生成的内容

`demo/viva_pack.html` —— 一个单一、自包含的 HTML 文件（不需要服务器、网络或 API key），按照演示要求分为八个部分：

1. 研究概述
2. 数据与代码
3. 方法论
4. 技术结果
5. 研究解读
6. 交互演示（冻结模型的情景分析 + 验证性结果浏览器）
7. 局限性与负责任的使用
8. 导出与来源追溯

此外还内置了**答辩指引**：建议的演示顺序、每一部分的讲解要点，以及预想的问题和基于产物的回答。

还有一个**代码导航器**（第 9 部分：`src/`、`app/`、`tests/` 和 `demo/` 中每个纳入版本管理的 Python 文件都被原样嵌入，支持搜索和带行号查看，因此考官的任何问题都可以通过打开对应的文件来回答），以及导师答辩指引所要求的现场演示配套：静态材料包承载冻结的证据及其代码线索，而 `app/news_app.py`（Streamlit）接受输入——政党、语气、实验组、文章数量、时间窗口——并现场运行冻结的模型；材料包会在构建时核验现场应用所需的输入是否存在于本机上。

整个页面还贯穿了另外两项功能：

- **数字到代码的来源追溯。** 每张表、每张图和每个核心数字都带有一个"这些数字背后的代码"按钮。点击后会展开完整的链条：冻结的输入产物（及其清单中的 sha256）、计算这些数字的流水线模块（模块的 docstring 加上确切的函数，例如 `unblind_2026.py` 中的 bootstrap 和评分代码），以及 `build_report_tables.py` 中写出该 CSV 的函数。所有摘录都在构建时由 `ast` 从仓库中提取——从不手工复制——因此不可能与已提交的代码出现偏差。
- **合成的假设情景（what-if）。** 第 6.2 部分重放了设计中的情景层（`synthetic_news_scenarios.py`）：把假设的新闻报道注入冻结的 v2 模型的特征单元格中，并在已提交的输出旁边展示注入机制、冻结系数断言以及已声明的边界（议题维度无法通过模型传导）。

## 运行说明

在仓库根目录下：

```bash
.venv/bin/python demo/build_viva_pack.py
open demo/viva_pack.html
```

依赖：只需要 `pandas`（已包含在项目的 `requirements.txt` 中）。不需要任何环境变量、密钥或网络访问——材料包是静态的，可以在任何浏览器中离线使用。

测试：

```bash
.venv/bin/python -m pytest demo/test_viva_pack.py -q
```

## 现场模型演示（可选，独立）

仓库中还包含 `app/news_app.py`，这是一个 Streamlit 应用，可以针对*冻结的*第二阶段模型现场运行合成情景（在运行任何内容之前，它都会重新核验冻结的系数）。静态材料包则嵌入的是已提交的情景输出（`t18_synthetic_scenarios.csv`），因此答辩演示无需任何配置即可进行；如果要求现场运行、并且本地存在模型包，则以 Streamlit 应用作为备选。

## 来源追溯

| 输入 | 作用 |
| --- | --- |
| `outputs/report_tables_v1/*.csv` | 所有表格数字（冻结的，通过 `manifest.json` 以 sha256 锁定） |
| `outputs/report_tables_v1/latex/a1_stage1_predictors.tex`、`a5_llm_validation.tex` | 预测变量词典和 LLM 验证证据 |
| `outputs/report_figures_v1/*.png` | 所有图表（已提交） |
| `git ls-files` | 仓库地图和测试数量（计算得出，而非手工填写） |

生成的 `viva_pack.html` 是构建产物，依据仓库关于生成产物的规定已被 git 忽略（见 `demo/.gitignore`）。
