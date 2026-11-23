"""把抽取出的文章记录转换成模型所连接的新闻特征表。

## 粒度，以及为什么它不是任务说明所设想的那种

任务说明要求按选区（ward）构建特征。但语料库做不到这一点：在当前 1,632 篇
文章的正式版本中，有 46 篇来自针对特定选区的搜索，用 108 个已公布的区域名称
对正文进行匹配又能找回 22 篇——**4.2% 带有明确的区域，94.2% 根本没有提到任何
明确的萨里区域**。覆盖过于稀疏且不均衡，无法构建通用的选区级特征。

因此这张表以 **(election, party, window)** 为键。把它与基线的 (election, area,
party) 行连接时，每个值会被广播到该场选举的所有区域上。这是一个真实的局限，
在这里明确说明，而不是用一个特征名称把它掩盖起来：这张表中的新闻特征可以
解释不同选举之间、不同政党之间的差异，但永远无法解释同一场选举内不同区域
之间的差异。

## 哪些特征能够承载系数——经过测量而不是假定

训练期（2013 + 2017）内的单元格计数，来自 `diagnose_feature_grain`：

    按选举                  2 个单元格  - 无法拟合；两个点恰好确定一条
                                          直线，什么也推广不了
    按 选举 x 政党         10 个单元格  - 可用，每个单元格的文章数中位数为 162

因此每个特征在输出时都附带一个 `training_variation` 判定，选举层面的特征会
标为 `insufficient`，而不是被悄悄提供给一个无法从中学到任何东西的模型。它们
仍然会被计算：如果那条流水线将来真的运行，已收集但尚未处理的 3,122 篇补选
文章会再增加八个选举层面的单元格，而一个已经存在的列以后再填充是没有成本的。

**英国改革党在训练期内的文章数为零**——该党在 2013 年或 2017 年还不存在。
无法估计任何专门针对改革党的新闻系数。任何关系都必须以不区分政党的方式，
从训练期内存在的五个政党中学习，然后应用到改革党身上。这是本项目的核心外推，
它应当写进报告正文，而不是放在脚注里。

## 计数和占比两者都有，理由经过测量

计数会受到某场竞选被搜索得有多深入的影响；占比则不会，因为搜索深度会同时
改变分子和分母。补选的搜索完整度从不到 12% 到 100% 不等，这就是为什么补选
被排除在基于计数的特征之外——所以这里的每个计数都有一个对应的占比，并且在
比较搜索深度不同的竞选时，设定应当优先使用占比。

## 去重，以及守护它的断言

各批次的输出文件有重叠：far2 的文章在完整运行中被重新抽取，而它的立场和框架
记录却保留在原处，因此直接拼接这些文件会重复计数**框架层 98 篇文章、立场层
66 篇文章**——原始行数超过了语料库，框架层 1,730 行对应 1,632 篇文章。因此
记录按 `article_id` 去重，最新批次优先，并且构建过程会断言去重后的文章数
永远不超过语料库的规模。悄无声息的重复计数会抬高受影响选举的每一个数量类
特征。

用法：
    python3 -m src.news_features.build_feature_table
"""

from __future__ import annotations

import csv
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.run_corpus_extraction import (EXCLUDED_LAYERS,
                                                     FRAME_KEYS, LAYER_ARMS)
from src.llm_extraction.stance_rescue import PARTY_ALIASES
from src.news_collection.canonical_corpus_release import (
    OUTPUT as CANONICAL_MANIFEST,
    build_release,
)
from src.news_features.actor_party_attribution import (parties_for_actors,
                                                       publication_date)

OUT_CSV = Path("news_features/news_feature_table_v1.csv")
OUT_META = Path("news_features/news_feature_table_v1_metadata.json")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_relative(path: Path) -> str:
    """以可移植的方式序列化谱系路径，无论包装脚本绑定的是绝对路径还是相对路径。"""

    resolved = path if path.is_absolute() else (REPO_ROOT / path)
    return str(resolved.resolve().relative_to(REPO_ROOT))

# 导师于 2026-07-30 确认的六个时间窗口（"Keep the news windows
# you already implemented... That is fine. No need to change them"，即保留已实现的窗口、无需修改），
# 按从最早到最晚排列，使得每个累积快照都是这个列表的一个前缀。
WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")

# 累积时间段，取自 `window_schemes.ORIGINAL_EMAIL.cumulative`，
# 而不是在这里自行编造。该定义引用了导师本人的邮件，
# 内容为"投票前 1 到 N 天的所有内容"——即末尾的 N 天，
# 从投票日往前累积。
#
# 本文件的第一个版本把数量和方向都弄错了：它
# 输出了四个名为 `as_at_90_days` 之类的快照，由
# `WINDOWS[:1]` 构建，而那是 180 到 91 天的区间——即*最早*的覆盖，恰好是
# 定义所要求内容的补集。`previous_90_days` 是投票前最后 90
# 天，即 `90_to_31_days` 及其之后的所有窗口。复用
# 方案自身的标签也意味着这里的特征名与
# 抽取流水线已经分配的名称一致，而不是为同样的时间段
# 引入第二套词汇。
def _cumulative_members() -> dict[str, tuple[str, ...]]:
    """每个累积时间段内包含的窗口名称，取自冻结的方案。"""
    from src.news_modelling.window_schemes import ORIGINAL_EMAIL
    spans = {name: (lo, hi) for name, lo, hi in ORIGINAL_EMAIL.windows}
    out: dict[str, tuple[str, ...]] = {}
    for label, limit in ORIGINAL_EMAIL.cumulative:
        # 当一个窗口完全位于某个累积时间段之内时，它才属于该时间段。
        # 因此 `previous_7_days` 包含 final_72_hours 和 7_to_4_days，
        # 而不包含跨越边界的 14 到 8 天区间。
        out[label] = tuple(w for w in WINDOWS if spans[w][1] <= limit)
    return out


SNAPSHOTS = _cumulative_members()

# 导师规定的按时间顺序的划分。按行记录，使得某个设定可以
# 直接据此筛选而无需重新推导划分，也使得下面的训练变异性
# 判定可以根据表本身计算出来。
SPLIT_ROLE = {"SCC-2013-05": "train", "SCC-2017-05": "train",
              "SCC-2021-05": "validation", "ESWS-2026-05": "test"}

# 两个点恰好确定一条直线。三个点时才第一次出现残差；
# 十个点时系数才值得报告。之所以在这里写明，是因为"足够的
# 变异"否则就是在模型拟合内部悄悄做出的判断。
MIN_CELLS_TO_FIT = 3
MIN_CELLS_TO_REPORT = 10

# 选举网格。None（默认值，也是 v1 的行为）表示从至少有一篇
# 语料库文章的选举中推导网格。如果某个版本的范围登记了
# 那些合理地以零篇符合资格文章告终的选举，就要显式设置它，
# 因为下面的零单元格政策对选举的适用方式与对时间段完全相同：
# 一次已完成但没有符合资格文章的搜索，
# 是对零覆盖的一次观测，而不是一场缺失的选举。
GRID_ELECTIONS: list[str] | None = None

# 同时按 (选举, 政党, 时间窗口) 聚合议题层和框架层，
# 方法是把每篇文章归属到其抽取记录中
# `political_relevance.affected_actors` 所列出的政党。
#
# 默认关闭，而且是刻意如此。仓库中的每一个结果都是
# 用按选举聚合构建的表计算出来的，因此 v1 和 v2
# 必须始终能够逐字节一致地重建；有一个测试正是断言这一点。
# v3party 包装脚本会开启它并写入自己的路径，这是
# 新列出现的唯一地方。
#
# 开启它时，按选举的列仍然会被输出。在一个文件中同时包含两种
# 粒度，正是使这一改动可审计的原因：在任何一个单元格内，
# 选举列按构造在全部六个政党之间都是相同的，而
# 政党列则不是。
PARTY_CONTENT_ATTRIBUTION = False

# 加载记录时要忽略的抽取批次。默认为空，这
# 也是 v1 和 v2 的行为。
#
# `load_records` 会读取磁盘上的每一个 `corpus_extraction_outputs_*.json`，而
# 某个批次中的文章可能合理地不被任何正式版本准入。
# E5 本地扩展正是这种情况：它的分诊验证没有通过——
# kappa 为 0.4762，而门槛是 0.600，所以它的 Farnham Herald 文章从未
# 被准入任何版本——但这个批次还是在 2026-08-02 被抽取了，
# 比特征表 v2 写出的时间晚了九个小时。`main` 中的断言
# 拒绝这种混合是正确的。在这里指名该批次是满足这一断言的
# 有限定范围的方式：它声明一次构建由哪个语料库组成，而不是放松
# 执行检查的那道防线。
EXCLUDED_TRANCHES: set[str] = set()

# v1 谱系所需的集合，单独命名以便测试能够访问它：下面的 `__main__`
# 代码块就是 v1 构建，而只有运行脚本才能触及的配置，
# 是没有任何东西能够检查的配置。
#
# `byelection1` 出现在这里的原因与其他三个不同。它是
# 扩充部分，版本 v2 准入它，而 v1 按定义不准入——这是范围
# 上的差异，而不是一个被拒绝的语料库。另外三个是两个单场
# 竞选的案例研究和 E5 本地扩展，它们不被任何版本准入。
V1_EXCLUDED_TRANCHES = frozenset(
    {"byelection1", "e5local1", "haslemere1", "wokingsouth1"})

# 被聚合为六个预注册议题特征的议题代码。不在
# 这个映射中的任何内容都归入 `issue_other`，它会被报告而不是
# 被丢弃：分类体系没有覆盖到的议题本身就是关于覆盖情况的一个事实。
#
# 已知缺陷，原样保留（2026-08-14）：这些成员是根据
# 特征计划中的简写起草的，而不是根据抽取提示词中的 `issue_code`
# 枚举，因此 `crime_policing`、`planning_housing`、`waste_recycling` 和
# `schools_send` 永远匹配不上，导致 166 条已编码记录被归入 `issue_other`
# （61/50/5/50）。冻结的 v1/v2 表是用这个映射构建的，它们的
# 逐字节一致重建测试锁定了它，而盲化冻结规则禁止
# 重新生成——所以这个缺陷留在这里，记录在案。今后的构建必须
# 显式传入 ISSUE_GROUPS_CORRECTED；`tests/test_issue_group_mapping.py`
# 同时锁定了两种行为。
ISSUE_GROUPS = {
    "immigration": ("immigration", "asylum", "small_boats"),
    "crime_policing": ("crime", "policing", "antisocial_behaviour"),
    "housing_planning": ("housing", "planning", "development", "green_belt"),
    "council_services": ("council_services", "roads_transport", "waste",
                         "social_care", "schools_sen", "council_finance",
                         "council_tax", "council_performance"),
    "national_politics": ("national_politics", "national_economy",
                          "party_leadership", "scandal"),
}

# 用于任何冻结之后（v3 及以后）构建的修正映射：成员字符串直接取自
# 抽取提示词中的 `issue_code` 枚举本身。
ISSUE_GROUPS_CORRECTED = {
    "immigration": ("immigration",),
    "crime_policing": ("crime_policing",),
    "housing_planning": ("planning_housing",),
    "council_services": ("council_finance", "council_tax",
                         "roads_transport", "waste_recycling",
                         "social_care", "schools_send",
                         "council_performance"),
    "national_politics": ("national_politics", "national_economy",
                          "scandal"),
}


def live_layers() -> list[str]:
    return [l for l in LAYER_ARMS if l not in EXCLUDED_LAYERS]


def load_records() -> tuple[dict[str, dict], dict]:
    """每一层去重后被接受的记录，最新批次优先。

    返回 (records, provenance)。`records[layer][article_id]` 是被接受的记录；
    `provenance` 统计每篇文章的记录来自哪个批次和哪个提示词指纹，从而可以把
    一行特征追溯到它背后的提示词。
    """
    paths = sorted(glob.glob("llm_context/corpus_extraction_outputs_*.json"))
    # "all" 是生产运行，必须优先于各个关卡批次，所以文件
    # 按从旧到新的顺序应用，后写入的覆盖先写入的。按名称
    # 排序会把 "all" 按字母顺序排在第一位，这是错误的顺序——因此
    # 使用显式的排序键，而不是依赖文件名。
    order = {"narrow": 0, "far": 1, "far2": 2, "far3": 3, "all": 9}
    def rank(p: str) -> int:
        name = Path(p).stem.replace("corpus_extraction_outputs_", "")
        return order.get(name, 5)

    records: dict[str, dict[str, dict]] = {l: {} for l in live_layers()}
    provenance: Counter = Counter()
    superseded_seen: dict[str, list[str]] = {}

    for path in sorted(paths, key=rank):
        payload = json.loads(Path(path).read_text())
        tranche = payload.get("tranche", Path(path).stem)
        if tranche in EXCLUDED_TRANCHES:
            continue
        superseded = set(payload.get("superseded_layers") or ())
        if superseded:
            superseded_seen[tranche] = sorted(superseded)
        for layer in live_layers():
            if layer in superseded:
                continue
            for r in payload.get("layers", {}).get(layer, []):
                if r.get("record") is None or r.get("validation_errors"):
                    continue
                records[layer][r["article_id"]] = r
                provenance[(layer, tranche,
                            (r.get("prompt_sha256") or "none")[:12])] += 1
    return records, {"per_layer_tranche_prompt": {f"{k[0]}|{k[1]}|{k[2]}": v
                                                  for k, v in provenance.items()},
                     "superseded_layers_honoured": superseded_seen}


def primary_issue(record: dict) -> str | None:
    """议题代码，从 schema 生成的任意一种结构中解包出来。"""
    value = (record.get("issues") or {}).get("primary_issue")
    if isinstance(value, dict):
        value = value.get("issue_code") or value.get("code")
    return value or None


def issue_group(code: str | None, groups: dict = ISSUE_GROUPS) -> str:
    if not code:
        return "none"
    for group, members in groups.items():
        if code in members:
            return group
    return "issue_other"


def main() -> None:
    records, provenance = load_records()
    article_ids = set().union(*(set(v) for v in records.values()))

    # 在连接抽取记录之前先冻结语料库。版本清单
    # 是唯一一个把主语料、试点和验证三路纳入资格数据流合并起来、
    # 再应用日期、主要选举范围、已确认的
    # 六个时间窗口和文本可获得性的地方。这可以防止主表中 120 篇本地文章的
    # 子集与这里使用的 188 篇本地文章的语料库混在一起。
    release, canonical_articles = build_release()
    CANONICAL_MANIFEST.write_text(
        json.dumps(release, indent=2), encoding="utf-8"
    )
    corpus_size = release["usable_feature_corpus"]["articles"]

    # 抽取记录覆盖的文章数可以合理地少于语料库
    # （某一层可能未通过验证），但它们绝不能引入
    # 来自另一个版本的文章。在这里停止，比写出一张看起来合理、
    # 但分母却来自另一个语料库版本的表要安全。
    unexpected_ids = article_ids - set(canonical_articles)
    assert not unexpected_ids, (
        f"{len(unexpected_ids)} extraction article(s) are outside canonical "
        f"release {release['release_id']}; first ids: "
        f"{sorted(unexpected_ids)[:5]}"
    )
    articles = {
        aid: canonical_articles[aid]
        for aid in article_ids
        if aid in canonical_articles
    }

    # 重复计数风险所要求的那道防线。被抬高的文章数
    # 会抬高每一个数量类特征，而且是悄无声息地抬高。
    assert len(articles) <= corpus_size, (
        f"deduplication failed: {len(articles)} unique articles against a "
        f"corpus of {corpus_size}. Concatenating tranche files double-counts, "
        f"which is what this assertion exists to catch.")
    print(f"records: {
        {l: len(v) for l, v in records.items()} }")
    print(f"unique articles: {len(articles)} of a {corpus_size}-article corpus")

    # --- 按 (选举, 政党, 时间窗口) 累计 -------------------------
    # 随政党变化的计数器。政党键来自立场层自身的
    # 判断列表，而该列表由确定性的别名匹配构建，因此
    # 当且仅当文章提到某个政党时，该政党才会出现在这里。
    party_cells: dict[tuple, Counter] = defaultdict(Counter)
    # 同样的计数器，再按收集实验组拆分一次。于 2026-07-30 加入，
    # 用于导师最初邮件中要求的五组比较
    # （基线 / 本地 / 全国 / 合并 / 完整）。
    #
    # 没有这一部分，实验组比较按构造就是空洞的：表中仅有的
    # 区分实验组的列是 `local_article_count`、
    # `national_article_count` 和 `local_share`，它们全都处于
    # 按选举的粒度，因此只有**两个**不同的训练取值。
    # 一个由只有两个训练取值的特征构建出来的"本地新闻模型"
    # 并不是本地新闻模型；它只是换了个名字的选举指示变量。
    # 拆分按政党的形象刻画计数器——这是唯一一个拥有十个
    # 训练单元格的模块——正是使"本地报道是否起到与
    # 全国报道不同的作用"成为一个这张表真正能够回答的问题的原因。
    #
    # 这里的 `arm` 指**收集**实验组：即由哪一路搜索数据流
    # 获取到这篇文章，这与上面 `local_article_count`
    # 已经使用的定义相同，因此新列能与已有的列相互对应，而不是
    # 引入第二种"本地"的概念。另一种定义——
    # LLM 自身的 `scope_classification`——位于文章层面，是
    # 一项内容判断而不是一个来源事实。在一张表中混用两者
    # 会使 `local_article_count` 和 `local_party_article_count`
    # 用同一个词计数不同的东西。
    party_arm_cells: dict[tuple, Counter] = defaultdict(Counter)
    # 选举层面的计数器，单独保存，因为它们的粒度不同，
    # 把它们混为一谈会掩盖这样一个事实：一个只有两个训练单元格，而另一个
    # 有十个。
    election_cells: dict[tuple, Counter] = defaultdict(Counter)
    # 内容归属实际落地的情况，记录在元数据中。
    # 当某个政党层面的内容特征表现异常时，归属率是首先要检查的东西，
    # 而它无法从表中恢复出来。
    attribution: Counter = Counter()

    for aid, article in articles.items():
        election, window, arm = (article["election_id"], article["window"],
                                 article.get("arm") or "unknown")
        ekey = (election, window)
        election_cells[ekey]["article_count"] += 1
        election_cells[ekey][f"{arm}_article_count"] += 1
        election_cells[ekey][f"source__{article.get('source') or 'unknown'}"] += 1
        if article.get("mentions_reform"):
            election_cells[ekey]["reform_named_count"] += 1

        # 这篇文章提到的政党，用于内容层。从
        # 议题（ISSUE）记录中读取，因为那是抽取过程中唯一被赋予
        # `political_relevance` 模块的层；同一篇文章的框架记录
        # 在下面继承这个集合，这使得无需重新运行抽取就能构建
        # 政党层面的框架特征。当
        # PARTY_CONTENT_ATTRIBUTION 关闭时它为空，因此所有对它的循环都不执行任何操作，
        # 按选举的行为也完全不受影响。
        content_parties: set[str] = set()

        issues = records["issues"].get(aid)
        if issues is not None:
            group = issue_group(primary_issue(issues["record"]))
            election_cells[ekey][f"issue_{group}_count"] += 1
            election_cells[ekey]["issues_coded"] += 1
            if PARTY_CONTENT_ATTRIBUTION:
                relevance = issues["record"].get("political_relevance") or {}
                content_parties = parties_for_actors(
                    relevance.get("affected_actors"),
                    publication_date(article))
                attribution["articles_with_issue_record"] += 1
                attribution["articles_attributed" if content_parties
                            else "articles_no_party_found"] += 1
                for party in content_parties:
                    cell = party_cells[(election, party, window)]
                    cell[f"party_issue_{group}_count"] += 1
                    cell["party_issues_coded"] += 1

        framing = records["framing_revised"].get(aid)
        if framing is not None:
            election_cells[ekey]["framing_coded"] += 1
            present = {f["frame"]: bool(f.get("present"))
                       for f in framing["record"].get("frames") or []}
            for frame in FRAME_KEYS:
                if present.get(frame):
                    election_cells[ekey][f"frame_{frame}_count"] += 1
            # 框架记录本身不携带任何行动者，因此它继承
            # 上面为其所属文章确定的集合。一篇有
            # 框架记录但没有议题记录的文章在这里不贡献任何东西——
            # 2,576 篇中有 17 篇——因为没有可供继承的行动者列表。
            for party in content_parties:
                cell = party_cells[(election, party, window)]
                cell["party_framing_coded"] += 1
                for frame in FRAME_KEYS:
                    if present.get(frame):
                        cell[f"party_frame_{frame}_count"] += 1

        stance = records["stance_revised"].get(aid)
        if stance is not None:
            for judgement in stance["record"].get("judgements") or []:
                party, portrayal = judgement["party"], judgement.get("portrayal")
                cell = party_cells[(election, party, window)]
                cell["party_article_count"] += 1
                cell[f"portrayal_{portrayal}"] += 1
                # 同样的增量，再加上按实验组作为键。写成第二个
                # 累加器，而不是从实验组拆分中推导出全实验组的数字，
                # 这样每一个已经发布的列都保持
                # 原来的值完全不变；下面的对账断言
                # 就是证明两者保持一致的依据。
                arm_cell = party_arm_cells[(election, party, arm, window)]
                arm_cell["party_article_count"] += 1
                arm_cell[f"portrayal_{portrayal}"] += 1

    # --- 每个 (选举, 政党, 时间窗口或快照) 输出一行 -----------
    def summed(cells: dict, key_prefix: tuple, windows) -> Counter:
        total = Counter()
        for w in windows:
            total.update(cells.get(key_prefix + (w,), Counter()))
        return total

    parties = sorted({p for (_e, p, _w) in party_cells})
    elections = (sorted(GRID_ELECTIONS) if GRID_ELECTIONS is not None
                 else sorted({e for (e, _w) in election_cells}))
    periods = [(w, (w,)) for w in WINDOWS] + list(SNAPSHOTS.items())

    rows = []
    zero_article_cells = []
    for election in elections:
        for party in parties:
            for period_name, member_windows in periods:
                p = summed(party_cells, (election, party), member_windows)
                e = summed(election_cells, (election,), member_windows)
                by_arm = {
                    arm: summed(
                        party_arm_cells,
                        (election, party, arm),
                        member_windows,
                    )
                    for arm in ("local", "national")
                }
                total = e["article_count"]
                # 保留完整的 选举 x 政党 x 时间段 网格，包括
                # 已完成但没有找到符合资格文章的搜索。旧的
                # 构建丢弃了这些行，把一个真实的零变成了
                # 一个缺失的观测。尤其是，SCC 2017 最后 72 小时的
                # 全部六个政党行都消失了，因此一个按时间顺序的
                # 模型可能会根据所选窗口的不同，悄悄地在不同的选举集合上
                # 训练。
                #
                # 计数类特征是真正的零。占比类特征在其分母为零时
                # 保持空白：零除以零并不是
                # 政党占比为零，而是未定义的。这一区分让
                # 之后的模型可以选择一个明确的缺失值策略，而不是
                # 接收一个捏造出来的比例。
                if not total:
                    zero_article_cells.append({
                        "election_id": election,
                        "standard_party_key": party,
                        "period": period_name,
                    })
                unfav = p["portrayal_unfavourable"]
                fav = p["portrayal_favourable"]
                row = {
                    "election_id": election,
                    "standard_party_key": party,
                    "period": period_name,
                    "period_kind": "window" if period_name in WINDOWS else "snapshot",
                    "split_role": SPLIT_ROLE.get(election, "unknown"),
                    # --- 按 选举 x 政党：可用的粒度 -----------
                    "party_article_count": p["party_article_count"],
                    "party_article_share": round(p["party_article_count"] / total, 6) if total else "",
                    "unfavourable_count": unfav,
                    "favourable_count": fav,
                    "net_portrayal": fav - unfav,
                    "net_portrayal_share": round((fav - unfav) / p["party_article_count"], 6)
                                            if p["party_article_count"] else "",
                    # --- 按选举：两个训练单元格，留待以后使用 --
                    "article_count": total,
                    "local_article_count": e["local_article_count"],
                    "national_article_count": e["national_article_count"],
                    "local_share": round(e["local_article_count"] / total, 6) if total else "",
                    "independent_source_count": sum(
                        1 for k in e if k.startswith("source__")),
                    "reform_named_count": e["reform_named_count"],
                    "reform_share_of_coverage": round(e["reform_named_count"] / total, 6) if total else "",
                }

                # 对本地和全国两个收集实验组分别输出同样的
                # 政党层面信号。这些是导师的
                # 基线 / 本地 / 全国 / 合并 比较所需要的列；
                # 仅靠选举层面的 local_share 只有两个训练取值，
                # 无法识别出本地新闻的系数。
                for arm, arm_party in by_arm.items():
                    arm_total = e[f"{arm}_article_count"]
                    arm_party_count = arm_party["party_article_count"]
                    arm_unfav = arm_party["portrayal_unfavourable"]
                    arm_fav = arm_party["portrayal_favourable"]
                    prefix = f"{arm}_"
                    row[f"{prefix}party_article_count"] = arm_party_count
                    row[f"{prefix}party_article_share"] = (
                        round(arm_party_count / arm_total, 6)
                        if arm_total else ""
                    )
                    row[f"{prefix}unfavourable_count"] = arm_unfav
                    row[f"{prefix}favourable_count"] = arm_fav
                    row[f"{prefix}net_portrayal"] = arm_fav - arm_unfav
                    row[f"{prefix}net_portrayal_share"] = (
                        round((arm_fav - arm_unfav) / arm_party_count, 6)
                        if arm_party_count else ""
                    )

                # 在正式版本中，收集实验组是穷尽的。这些
                # 检查会在错误发生的确切那一行捕获拼写错误 / 新出现的实验组或
                # 聚合错误，在任何模型读取到
                # 被低估的合并计数之前。
                for key in (
                    "party_article_count",
                    "portrayal_unfavourable",
                    "portrayal_favourable",
                    "portrayal_neither",
                ):
                    assert p[key] == sum(block[key] for block in by_arm.values()), (
                        f"arm reconciliation failed for {election}/{party}/"
                        f"{period_name}/{key}: combined={p[key]}, "
                        f"local+national="
                        f"{sum(block[key] for block in by_arm.values())}"
                    )

                for group in list(ISSUE_GROUPS) + ["issue_other", "none"]:
                    n = e[f"issue_{group}_count"]
                    row[f"issue_{group}_count"] = n
                    row[f"issue_{group}_share"] = (
                        round(n / e["issues_coded"], 6) if e["issues_coded"] else "")
                for frame in FRAME_KEYS:
                    n = e[f"frame_{frame}_count"]
                    row[f"frame_{frame}_count"] = n
                    row[f"frame_{frame}_share"] = (
                        round(n / e["framing_coded"], 6) if e["framing_coded"] else "")

                # 同样的两个层，但在政党粒度上，输出在
                # 上面按选举的列旁边，而不是替换它们。
                # 分母是该政党自身被编码的文章，因此该占比
                # 回答的是"在提到这个政党的报道中，有多少是
                # 关于移民的"——这是一种构成，而不是一种数量。正是这一
                # 区分使新特征不至于只是
                # 换了个名字的文章计数，而且在任何设定使用这些列之前
                # 都会检查这一点。
                if PARTY_CONTENT_ATTRIBUTION:
                    coded = p["party_issues_coded"]
                    row["party_issues_coded"] = coded
                    for group in list(ISSUE_GROUPS) + ["issue_other", "none"]:
                        n = p[f"party_issue_{group}_count"]
                        row[f"party_issue_{group}_count"] = n
                        row[f"party_issue_{group}_share"] = (
                            round(n / coded, 6) if coded else "")
                    framed = p["party_framing_coded"]
                    row["party_framing_coded"] = framed
                    for frame in FRAME_KEYS:
                        n = p[f"party_frame_{frame}_count"]
                        row[f"party_frame_{frame}_count"] = n
                        row[f"party_frame_{frame}_share"] = (
                            round(n / framed, 6) if framed else "")
                rows.append(row)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as handle:
        # 固定使用 LF 换行，使生成的 CSV 在不同平台上逐字节稳定，并且
        # 在仓库检查中不会显得包含行尾空白。
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    # --- 训练变异性判定，根据表本身计算 ----------
    # 只有当某个特征在训练行之间存在变化时，才会把它提供给模型。
    # 在这里计算，而不是在 docstring 中声称，这样它就不会过时。
    train_rows = [r for r in rows if r["split_role"] == "train"]
    by_period: dict[str, list] = defaultdict(list)
    for r in train_rows:
        by_period[r["period"]].append(r)

    verdicts = {}
    for column in rows[0]:
        if column in ("election_id", "standard_party_key", "period",
                      "period_kind", "split_role"):
            continue
        # 在一个时间段*内部*计数，而不是跨时间段计数。一个设定只使用一个
        # 窗口或一个快照，因此窗口之间的变化并不是
        # 拟合能看到的变化。跨时间段合并会把 article_count 从 2 个
        # 不同的训练取值抬高到 14 个，并会把它作为可用特征提供给
        # 一个只能看到两个取值的模型——这个判定的第一个版本恰恰就是
        # 这样做的，这也是为什么现在按时间段计算它。
        best = max((len({r[column] for r in group if r[column] != ""})
                    for group in by_period.values()), default=0)
        pooled = len({r[column] for r in train_rows if r[column] != ""})
        verdicts[column] = {
            "distinct_training_values_within_period": best,
            "distinct_training_values_pooled_across_periods": pooled,
            "verdict": ("insufficient" if best < MIN_CELLS_TO_FIT
                        else "fittable_not_reportable" if best < MIN_CELLS_TO_REPORT
                        else "usable"),
        }

    usable = [c for c, v in verdicts.items() if v["verdict"] == "usable"]
    # 当归属功能关闭时，该键不存在，而不是为 null：否则这个
    # 构建器曾经写出的每一个元数据文件都会多出一个键，这会让
    # 五个已提交的产物出现差异，却换不来任何信息。
    #
    # `party_cell_multiplier` 按设计大于 1——一篇提到两个
    # 政党的文章与两者都相关，并且被两者各计一次，因此政党层面的计数
    # 相加不等于选举层面的计数，也不应该期望它们相等。
    # 显式的键顺序：直接展开 Counter 会按插入顺序序列化，
    # 而插入顺序随文章的遍历顺序而变化，曾导致已提交的
    # 元数据在多次重建之间来回翻转。
    attribution_block = {
        "articles_with_issue_record": attribution["articles_with_issue_record"],
        "articles_attributed": attribution["articles_attributed"],
        "articles_no_party_found": attribution["articles_no_party_found"],
        "party_cell_multiplier": round(
            sum(r["party_issues_coded"] for r in rows
                if r["period_kind"] == "window")
            / max(attribution["articles_attributed"], 1), 4),
    } if PARTY_CONTENT_ATTRIBUTION else None

    OUT_META.write_text(json.dumps({
        "rows": len(rows),
        "expected_rows": len(elections) * len(parties) * len(periods),
        "elections": elections,
        "parties": parties,
        "periods": [p for p, _ in periods],
        "unique_articles": len(articles),
        "corpus_size": corpus_size,
        "canonical_corpus_release_id": release["release_id"],
        # 包装脚本会把 CANONICAL_MANIFEST 与 build_release 一起重新绑定。
        # 序列化这个被绑定的路径，而不是把每一张派生表都标注
        # 为 v1，否则 v2 和各案例研究表会在其元数据中声称
        # 错误的语料库谱系。
        "canonical_corpus_manifest": _repo_relative(CANONICAL_MANIFEST),
        "canonical_corpus_by_arm":
            release["usable_feature_corpus"]["by_arm"],
        "terminal_include_articles":
            release["terminal_include_union"]["articles"],
        "excluded_after_terminal_include":
            release["excluded_after_terminal_include"],
        "grain": "election x party x period",
        "empty_cell_policy": (
            "Retain completed election-party-period cells with zero articles. "
            "Counts are 0; shares with a zero denominator are blank."
        ),
        "zero_article_cells": zero_article_cells,
        "grain_note": ("Not area-level: 94.2% of canonical articles carry no "
                       "unambiguous Surrey-area attribution, and the remaining "
                       "coverage is too sparse and uneven to support a general "
                       "ward-level feature."),
        # 只对互不相交的窗口求和。包括累积快照会
        # 把同一篇文章计数多次，而之前的实现
        # 实际上计数的是非空*单元格*，尽管该字段名叫
        # articles（文章数）。
        "reform_training_articles": sum(
            r["party_article_count"] for r in train_rows
            if r["standard_party_key"] == "reform_uk"
            and r["period_kind"] == "window"
        ),
        "training_variation": verdicts,
        "usable_columns": usable,
        **({"party_content_attribution": attribution_block}
           if attribution_block else {}),
        "provenance": provenance,
    }, indent=2))

    print(f"\nrows: {len(rows)}  ({len(elections)} elections x {len(parties)} "
          f"parties x {len(periods)} periods, zero-article cells retained)")
    print(f"columns with usable training variation: {len(usable)} of "
          f"{len(verdicts)}")
    for column, v in sorted(
            verdicts.items(),
            key=lambda kv: -kv[1]["distinct_training_values_within_period"]):
        if v["verdict"] == "insufficient":
            continue
        print(f"    {column:34s} "
              f"{v['distinct_training_values_within_period']:3d} within period"
              f"   ({v['distinct_training_values_pooled_across_periods']:3d} pooled)"
              f"   {v['verdict']}")
    print(f"\n  insufficient: "
          f"{sum(1 for v in verdicts.values() if v['verdict']=='insufficient')} columns")
    print(f"-> {OUT_CSV}\n-> {OUT_META}")


if __name__ == "__main__":
    # 运行本模块就是 v1 构建，而那四个批次会使 948
    # 篇文章落在版本 v1 之外，从而在语料库断言处终止构建——
    # 这是正确的，因为一张混合了多个语料库的表正是该断言
    # 要防止的失败。
    #
    # 在这里应用而不是作为模块默认值，因为导入这个
    # 模块必须保持无副作用：`build_haslemere_probe_features` 和
    # `build_woking_south_blind_features` 会导入它，并且恰恰需要
    # 这个集合所移除的那些批次。
    EXCLUDED_TRANCHES = set(V1_EXCLUDED_TRANCHES)
    main()
