# `src/normalisation/` —— 文本规范化（第 2 层，第 4 阶段）

清洗层的前半部分：读取收集到的、符合纳入资格的文章，生成干净、结构化的文章文本以供标注。整个过程都是保守的——目标是去除网页模板噪声和编码残留，而不改动文字本身。第 4 阶段的每一步都由一个**纯逻辑模块**加上一个**`build_` 运行器**组成，后者把逻辑应用到每篇文章上（逻辑部分不涉及 IO，可以单独测试）。

## 第 4 阶段的各个步骤

```text
1  normalisation_input   锁定符合资格的文章总体，并为每篇文章选择文本来源
2  html_clean            保守的 HTML / 网页模板清洗
3  char_normalise        保守的 Unicode、编码和字符规范化
4  structure_normalise   空白、换行和段落结构的规范化
5  boundary_resolve      判定标题 / 正文 / 辅助文本的边界 → 结构化文章
6  text_quality          文本质量验证和正文缺失状态
7  final_audit           审计第 1–6 步并运行确定性的语言检查
```

## 完整文件指南

每一步对应一个纯逻辑模块和一个 `build_` 运行器；`tests/test_<step>.py` 覆盖每个逻辑模块。

| 步骤 | 逻辑模块 | 运行器 | 运行器写出的内容 |
| --- | --- | --- | --- |
| 1 | `normalisation_input.py` | `build_normalisation_input.py` | 锁定的符合资格文章总体以及每篇文章选定的文本来源（清单 + 记录 + 审核队列） |
| 2 | `html_clean.py` | `build_html_cleaned_articles.py` | 经过 HTML / 网页模板清洗的文章文本及其日志 |
| 3 | `char_normalise.py` | `build_char_normalised_articles.py` | 经过 Unicode / 编码规范化的文本及其日志 |
| 4 | `structure_normalise.py` | `build_structure_normalised_articles.py` | 经过空白 / 段落结构规范化的文本及其日志 |
| 5 | `boundary_resolve.py` | `build_structured_articles.py` | 标题 / 正文 / 辅助文本的边界 → 结构化文章 |
| 6 | `text_quality.py` | `build_text_quality.py` | 逐篇文章的文本质量判定、处理队列和摘要 |
| 7 | `final_audit.py` | `build_final_layer.py` | 经过审计的最终文本层（`normalised_text_layer_v1_provisional.jsonl`，被 git 忽略），以及已提交的清单、审计和质量报告 |

`_v1_provisional` 是这一冻结中间层的历史版本名称，并不表示最终的仓库还在等待更多的文本清洗工作。下游加载程序锁定的正是这一层及其清单。

## 运行与输出

在仓库根目录下按顺序运行各个 `build_` 步骤，例如：

```bash
python3 -m src.normalisation.build_normalisation_input
python3 -m src.normalisation.build_html_cleaned_articles
python3 -m src.normalisation.build_char_normalised_articles
python3 -m src.normalisation.build_structure_normalised_articles
python3 -m src.normalisation.build_structured_articles
python3 -m src.normalisation.build_text_quality
python3 -m src.normalisation.build_final_layer
```

本阶段是**确定性的**——它读取冻结的符合资格语料库，每次运行都生成相同的已清洗文章。输出（已清洗文章的 `*_articles_v1.jsonl` 各层以及清洗日志 / 审核队列）写入仓库根目录的 `news_collection/` 目录；见该目录的 README。它们随后被 `src/dedup/`（第 5 阶段）使用，再进入标注。

## 交接与验证

下游文章加载程序读取的是第 7 步经过审计的文本层：`src/llm_extraction/run_pilot.py`（生产抽取背后共用的文章加载程序）直接加载 `news_collection/normalised_text_layer_v1_provisional.jsonl`，已提交的清单记录了它的哈希。本包的离线测试套件：

```bash
.venv/bin/python -m pytest tests/test_normalisation_input.py \
    tests/test_html_cleaning.py tests/test_char_normalisation.py \
    tests/test_structure_normalisation.py tests/test_boundary_resolution.py \
    tests/test_text_quality.py tests/test_final_audit.py -q
```

## 规范

清洗是保守的，从不改写内容；每一步都经过审计，正文缺失会被记录为一种状态，而不会被悄悄丢弃。原始文章文本不提交（版权原因）；见 `REPO_MAP.md`。
