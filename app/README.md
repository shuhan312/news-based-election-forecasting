# `app/` —— 新闻层的 Streamlit 界面

一个第 8 层（Layer 8）的消费者：在流水线已经生成的产物之上的一层轻量、**只读**的浏览层。它不做任何处理、拟合或重新驱动——新闻层已经通过可审计的命令行流水线运行完毕，其输出已被冻结，所以这个应用只负责展示它们。如果在这里重新驱动处理流程，要么会重复命令行的工作，要么更糟——会诱使人去读取设计上一直保持盲化的结果。

## 三个页面

`news_app.py` 提供：

- **Status（状态）** —— 哪些步骤已经运行、加载了哪些冻结产物（第一阶段模型包、特征表、语料库版本），每一项都显示其版本号和 `sha256`，以便确信应用读取的正是已提交的证据。
- **Results（结果）** —— 新闻层的验证性结果，并带有设计要求在任何结果展示界面上都必须附带的统计解读警示。
- **Scenarios（情景）** —— 拟合好的模型对一条假设新闻报道会作出怎样的响应；情景页面会重新核验它所使用的输入。

## 读取的内容（只读）

| 产物 | 来源 |
| --- | --- |
| 第一阶段模型包 | `surrey-election-no-news-baseline/outputs/model_bundle_v1/` |
| 新闻特征表 | `news_features/news_feature_table_v2.csv` |
| 语料库版本 | `news_collection/canonical_corpus_release_v2.json` |
| 盲化预测清单 | 预测文件旁已提交的 `sha256_manifest.json` |

它展示的所有内容都已经作为冻结的、以哈希锁定的产物存在；这个应用只增加一个视图，从不产生新的数字。

## 运行

在仓库根目录下、激活项目的 `.venv` 后运行：

```bash
streamlit run app/news_app.py
```

这是**新闻层**的应用。第一阶段基线有自己的六页应用（`surrey-election-no-news-baseline/app/`），抽取器也有自己的应用（`surrey-election-extractor/app.py`）；两者都是独立的，不受本应用影响。关于第 8 层的消费者如何建立在冻结的报告包之上，见 [`../REPO_MAP.md`](../REPO_MAP.md)。
