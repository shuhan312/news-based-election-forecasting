# `data/` —— 选举参考表（第 1A 层）

整个流水线都以之对齐的、小型且权威的选举结果参考表。这里提交的所有内容，要么是从冻结的抽取器工作簿确定性地转换而来，要么是由 `src/` 中的脚本从官方 / 公开来源获取的；原始工作簿、抓取的网页和新闻语料库依据大文件规定存放在 Git 之外（OneDrive / `data/raw/`，已被 git 忽略）。

## 完整文件索引

| 文件 | 生成者 | 内容 |
| --- | --- | --- |
| `elections/2013_scc_results.csv` | `src/convert_2013_extractor_output.py` | 2013 年萨里郡议会选举结果，从经过验证的抽取器工作簿转换而来 |
| `elections/2013_conversion_log.csv` | 同上 | 该次构建的逐行转换日志 |
| `elections/2013_wikipedia_turnout_audit.csv` | `src/add_2013_wikipedia_turnout.py` | 经过审计的维基百科补充数据，用于填补官方页面缺失的 2013 年投票率 |
| `elections/2026_east_surrey_results.csv`、`elections/2026_west_surrey_results.csv` | `src/convert_2026_extractor_output.py`（由 `src/fetch_2026_surrey_results.py` 收集） | 东萨里 / 西萨里分别的 2026 年候选人结果 |
| `elections/2026_conversion_log.csv` | 同上 | 2026 年构建的逐行转换日志 |
| `elections/results_2017_2024.csv` | `src/fetch_election_results.py` | 从选举日历所列维基百科页面中抽取的选区级结果 |
| `elections/official_scc_candidate_results_test.csv` | `src/fetch_official_scc_results.py` | 官方页面候选人结果抽取的核对数据 |
| `elections/election_calendar.csv` | `src/build_election_calendar.py` | 萨里选举日历，新闻时间窗口以它为基准对齐 |
| `elections/ward_winners.csv` | `src/aggregate_results.py` | 每个选区 2017/2021 年的胜选者和胜选差距——预注册选区样本的输入之一 |
| `elections/ward_party_results.csv` | `src/aggregate_results.py` | 来自维基百科结果链的政党级选区结果 |
| `elections/candidate_name_standardisation.csv`、`elections/party_name_standardisation.csv` | `src/build_name_standardisation.py` | 经过人工审核的名称标准化表；英国改革党（Reform UK）与英国独立党（UKIP）从不合并 |
| `elections/turnout_audit.csv` | `src/audit_turnout.py` | 针对缓存选举表的投票率审计 |

## 复现

`convert_*` 构建从冻结的抽取器工作簿出发是确定性的；而 `fetch_*`、日历和维基百科脚本读取外部来源，因此重新运行它们会得到一份新的快照，而不是与已提交表格逐字节一致的副本——已提交的版本才是冻结的参考。所有脚本都在仓库根目录下运行；分组命令见 `src/README.md`（"Top-level collection scripts"一节），`convert_*` 步骤上游的工作簿来源见 `surrey-election-extractor/README.md`。
