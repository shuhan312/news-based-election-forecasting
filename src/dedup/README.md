# `src/dedup/` —— 去重（第 2 层，第 5 阶段）

清洗层的后半部分：识别同一篇文章的重复副本、转载副本和更新副本，并选出一个正式版本，使语料库中每条新闻只被计数一次。第 5 阶段的每一步都由一个**纯逻辑模块**加上一个**`build_` 运行器**组成，后者把逻辑应用到冻结的文章上。

## 第 5 阶段的各个步骤

```text
1  exact_duplicates    完全相同内容的重复检测
2  url_canonical       规范 URL 判定以及 URL 分组判定
3  near_duplicates     近似重复检测
4  syndication         转载副本识别
5  versioning          更新文章与版本关联、时间可获得性
6  cluster_validation  重复簇验证
7  canonical_selection 正式文章选择（每个簇保留一篇）
8  mapping_layer       合并第 1–7 步并冻结重复映射
```

## 完整文件指南

每一步对应一个纯逻辑模块和一个 `build_` 运行器；`tests/test_<step>.py` 覆盖每个逻辑模块。

| 步骤 | 逻辑模块 | 运行器 | 运行器写出的内容 |
| --- | --- | --- | --- |
| 1 | `exact_duplicates.py` | `build_exact_duplicates.py` | 逐字节相同的重复簇、映射、审核队列和摘要 |
| 2 | `url_canonical.py` | `build_url_resolution.py` | 规范 URL 分组以及 URL 级别的重复映射 |
| 3 | `near_duplicates.py` | `build_near_duplicates.py` | 近似重复的配对 / 簇、处理结果和审核队列 |
| 4 | `syndication.py` | `build_syndication.py` | 转载副本系列及其关系 |
| 5 | `versioning.py` | `build_versioning.py` | 文章版本系列、版本关系和时间可获得性 |
| 6 | `cluster_validation.py` | `build_cluster_validation.py` | 经过验证的簇、冲突及其审核队列 |
| 7 | `canonical_selection.py` | `build_canonical_selection.py` | 每个簇一篇正式文章，并附选择报告 |
| 8 | `mapping_layer.py` | `build_mapping_layer.py` | 合并后的、临时冻结的重复映射（审计 + 清单） |

名称中的 `_v1_provisional` 记录的是这一冻结中间层在生成时所处的状态；它并不表示最终的仓库还在等待另一项去重决策。正式的 v1/v2 语料库版本使用这一锁定的映射，并记录它们自己的版本标识。

## 运行与输出

在仓库根目录下按顺序运行各个 `build_` 步骤，例如：

```bash
python3 -m src.dedup.build_exact_duplicates
python3 -m src.dedup.build_url_resolution
python3 -m src.dedup.build_near_duplicates
python3 -m src.dedup.build_syndication
python3 -m src.dedup.build_versioning
python3 -m src.dedup.build_cluster_validation
python3 -m src.dedup.build_canonical_selection
python3 -m src.dedup.build_mapping_layer
```

本阶段是**确定性的**——它读取冻结的已清洗文章，每次运行都生成相同的重复映射。输出（版本系列、正式文章映射、审核队列以及冻结的 `canonical_corpus_release_*.json`）写入仓库根目录的 `news_collection/` 目录；见该目录的 README。第 8 步冻结的映射供下游各层使用，使它们基于每条新闻的一份正式副本开展工作。

## 交接与验证

语料库版本使用的是第 8 步冻结的映射和第 7 步的正式选择：`src/news_collection/canonical_corpus_release(_v2).py` 据此构建每条新闻一篇的文章集合，而特征表和 LLM 抽取读取的就是这个版本。本包的离线测试套件：

```bash
.venv/bin/python -m pytest tests/test_exact_duplicates.py \
    tests/test_url_resolution.py tests/test_near_duplicates.py \
    tests/test_syndication.py tests/test_versioning.py \
    tests/test_cluster_validation.py tests/test_canonical_selection.py \
    tests/test_mapping_layer.py -q
```

## 规范

重复项从不被删除——它被映射到其正式副本，因此分组是可审计、可撤销的。近似重复和转载的判定在映射冻结（第 8 步）之前会先经过验证（第 6 步）。见 `REPO_MAP.md`。
