"""在扩充语料库上构建新闻特征表 v2。

    python3 -m src.news_features.build_feature_table_v2

表 v1（288 行，4 场选举）保留在原处：它是所有扩充之前的结果据以计算的表。
这个包装脚本在正式版本 v2 上重新运行冻结的构建器，因此每一条聚合规则、占比
定义、零单元格政策、实验组对账断言和训练变异性判定都与 v1 逐字节一致——只有
三个模块级全局变量发生变化：

- 输出路径（``news_feature_table_v2.*``）；
- 语料库来源（``canonical_corpus_release_v2.build_release``）；
- 划分角色映射，其中加入了八场留出期之前的补选。

全部八场补选都被标为 ``train``。这正是扩充的全部意义——它们的存在就是为了
扩大 2026 年之前的拟合一侧——而且按照导师的时间顺序规则，这也是诚实的标签：
它们全都在 2026 年留出集之前投票，而其中五场 2025 年补选还位于 2021 年验证
选举*之后*，这一点只有在针对它们重新运行基于 2021 年的验证时才有影响；v2
模型的协议则是在 2026 年之前的所有数据上拟合，正如 v1 盲化协议已经为其合并
变体所声明的那样。

本次构建打印出的训练变异性判定就是衡量扩充是否成功的指标：在 2 个训练单元格
时为 `insufficient` 的列现在应该能够越过拟合门槛，而元数据会准确记录哪些列
做到了。
"""

from __future__ import annotations

from src.news_collection import canonical_corpus_release_v2 as release_v2
from src.news_features import build_feature_table as frozen

# 输出路径：v2 文件放在 v1 文件旁边，绝不覆盖它们。
frozen.OUT_CSV = frozen.OUT_CSV.with_name("news_feature_table_v2.csv")
frozen.OUT_META = frozen.OUT_META.with_name(
    "news_feature_table_v2_metadata.json")

# 语料库来源：冻结的构建器调用 `build_release()` 并写出
# 它返回的清单；两个名称都是模块级全局变量，因此重新绑定它们
# 就能让完全相同的聚合代码指向 v2 语料库。
frozen.build_release = release_v2.build_release
frozen.CANONICAL_MANIFEST = release_v2.OUTPUT

# 扩展后的导师按时间顺序划分：八场留出期之前的
# 补选加入最终 2026 年之前拟合的训练一侧。
frozen.SPLIT_ROLE.update({
    election_id: "train"
    for election_id in release_v2.BYELECTION_POLLING_DAYS
})

# 完整的 v2 选举网格，显式写出。八场补选中有六场
# 在筛选漏斗末端被准入的全国文章数为零（它们的报道
# 以本地为主，而本地 E5 审核被跳过了）；根据文章是否存在
# 来推导网格会悄悄丢掉这些选举，把"已搜索、
# 没有符合资格的内容"变成"从未搜索"。零覆盖的行带有零计数
# 和空白占比，与冻结的零单元格政策的规定完全一致。
frozen.GRID_ELECTIONS = sorted(
    set(release_v2.BYELECTION_POLLING_DAYS)
    | {"SCC-2013-05", "SCC-2017-05", "SCC-2021-05", "ESWS-2026-05"}
)

# 有三个批次是在这张表写出之后才抽取的，包含 321
# 篇版本 v2 不准入的文章，这会使构建在语料库
# 断言处终止：
#
#     news_feature_table_v2.csv   2026-08-01 16:23
#     haslemere1                  2026-08-01 22:55    20 篇文章
#     e5local1                    2026-08-02 01:31    29 篇文章
#     wokingsouth1                2026-08-02 17:23   272 篇文章
#
# 第一个和第三个是单场竞选的案例研究语料库，各有
# 自己的版本；第二个是 E5 本地扩展，它的分诊验证未通过——
# kappa 为 0.4762，而门槛是 0.600，所以它的文章从未
# 被任何地方准入。它们都不属于这个谱系。
#
# 指名它们恢复了一张已提交的表应当具备的性质：
# 有这一行时，重建结果与已提交的 CSV 逐字节一致；
# 没有这一行时，这张表根本无法重建。
frozen.EXCLUDED_TRANCHES = {"haslemere1", "e5local1", "wokingsouth1"}


def main() -> None:
    frozen.main()


if __name__ == "__main__":
    main()
