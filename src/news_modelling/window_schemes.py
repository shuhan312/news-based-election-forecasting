"""导师指定的三种新闻时间窗口方案，并列放在一起。

三份文件给出了三套不同的选举前时间窗口，而且它们彼此无法统一：

* 最初的邮件 —— 六个窗口，最远到 180 天，外加六个累积快照。这是抽取
  流水线目前实现的方案（``src/llm_extraction/temporal_horizon.py``）。
* Prompt 1 的附带说明和 Prompt 2 —— 30 天之内的三个窗口，外加 30 天、
  7 天和 1 天的累积快照。
* 桌面应用规格说明 —— 七个带标签的时间段，把最后三天拆分为"最后 48
  小时"、"前一天"和"选举日"，并要求把超过 30 天的内容从影响力特征中
  *排除*，而不仅仅是放进更早的窗口。

这些差异并不只是表面上的。按照最初的方案，一篇在投票前三天发布的文章
属于 ``final_72_hours``；按照 Prompt 2，它属于"7 到 2 天"窗口；按照桌面
规格说明，它属于"最后一周"。Prompt 2 还要求各窗口严格互不重叠，因此同一篇
文章不能被放进其中两个窗口，而且每个新闻特征都是按窗口计算的 —— 这意味着
方案的选择会改变下游的每一个数字。

与其去猜，不如把三种方案都在这里实现，并把默认值保持为当前已在使用的
那一种，这样在问题得到回答之前什么都不会改变。比较函数的存在，是为了能用
一张由真实文章组成的表来展示差异，而不是抽象地争论。

本模块决定什么、不决定什么
-----------------------------------------
它**只决定时间**：一篇文章在投票前多少天发布、在给定方案下它属于哪个窗口，
以及仅凭时间是否就会使它失去资格。它不决定相关性、地理或重复 —— 这些是
在别处做出的内容判断，一篇文章即使时间完全合适，也仍可能因为其中任何一项
而被排除。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

# 任务说明中默认的时区和投票截止时间。英格兰的投票站在
# 22:00 关闭，投票日当天在此之前发布的文章确实
# 能被选民看到；在此之后发布的则不能。
UK = ZoneInfo("Europe/London")
POLL_CLOSE = time(22, 0)

# 新闻选举标识符带有投票月份；第一阶段标识符带有
# 完整的选举名称。按投票*日期*而不是按任何一个字符串
# 建立映射，可以让两套命名方案彼此独立。这里是
# 该映射的权威存放处；其他模块都从这里导入它。
NEWS_ELECTION_DATES: dict[str, date] = {
    "SCC-2013-05": date(2013, 5, 2),
    "SCC-2017-05": date(2017, 5, 4),
    "SCC-2021-05": date(2021, 5, 6),
    "ESWS-2026-05": date(2026, 5, 7),
}

# 基于时间的排除理由。Prompt 2 要求每一篇被排除的文章
# 都有可审计的理由；这里列出的是仅凭时间就能确定的那些理由。
# 基于内容的理由（地理无关、低置信度匹配、重复、
# 合成数据）在别处指定，这里刻意不去编造。
AFTER_POLLS_CLOSED = "after_polls_closed"
AFTER_POLLING_DATE = "after_polling_date"
BEFORE_COLLECTION_WINDOW = "outside_configured_news_window"
UNKNOWN_DATE = "unknown_publication_date"
ELECTION_DAY_TIME_UNKNOWN = "election_day_publication_time_unknown"


@dataclass(frozen=True)
class WindowScheme:
    """一份文件对选举前时间窗口的定义。

    ``windows`` 是 (label, first_day, last_day) 三元组，天数从投票日往前倒数，
    两端都包含在内，并且不得重叠。``cumulative`` 是 (label, days) 二元组，
    表示"投票前 1 到 N 天的所有内容"，因此同一篇文章可以合理地出现在
    多个累积快照中。

    ``max_days`` 是一个界限，超过它的文章会被排除在影响力特征之外，而不是
    被放进更早的窗口。最初的邮件收集 180 天的内容并对全部内容建模；桌面
    规格说明则明确规定，超过 30 天的任何内容都"must be removed from the
    active influence dataset"（必须从活跃的影响力数据集中移除）。这是
    模型被允许看到什么内容的实质性差异，而不是标签上的差异。
    """

    key: str
    source: str
    windows: tuple[tuple[str, int, int], ...]
    cumulative: tuple[tuple[str, int], ...]
    max_days: int
    includes_election_day: bool = False

    def validate(self) -> None:
        """互不重叠是一项要求，所以要检查而不是想当然。"""

        covered: set[int] = set()
        for label, first, last in self.windows:
            if first > last:
                raise ValueError(f"{self.key}/{label}: first day {first} after last {last}")
            days = set(range(first, last + 1))
            clash = covered & days
            if clash:
                raise ValueError(
                    f"{self.key}/{label} overlaps an earlier window on day(s) "
                    f"{sorted(clash)}. Prompt 2 requires non-overlapping windows."
                )
            covered |= days


# --- 三种方案 ------------------------------------------------------

ORIGINAL_EMAIL = WindowScheme(
    key="original_email_180d",
    source="supervisor's original email: 'Please collect articles individually "
           "with exact publication dates and then assign them to...'",
    windows=(
        ("final_72_hours", 1, 3),
        ("7_to_4_days", 4, 7),
        ("14_to_8_days", 8, 14),
        ("30_to_15_days", 15, 30),
        ("90_to_31_days", 31, 90),
        ("180_to_91_days", 91, 180),
    ),
    cumulative=(
        ("previous_72_hours", 3), ("previous_7_days", 7),
        ("previous_14_days", 14), ("previous_30_days", 30),
        ("previous_90_days", 90), ("previous_180_days", 180),
    ),
    max_days=180,
)

PROMPT_1_AND_2 = WindowScheme(
    key="prompt_1_and_2_30d",
    source="Prompt 1 covering note and Prompt 2: '30-8 days before, 7-2 days "
           "before, final day before'",
    windows=(
        # "投票日之前最后一个完整的日子"只有第 1 天。
        ("final_day", 1, 1),
        ("7_to_2_days", 2, 7),
        ("30_to_8_days", 8, 30),
    ),
    cumulative=(
        ("previous_1_day", 1), ("previous_7_days", 7), ("previous_30_days", 30),
    ),
    max_days=30,
)

DESKTOP_SPEC = WindowScheme(
    key="desktop_spec_30d",
    source="desktop application specification: 'Use the following exact, "
           "non-overlapping periods relative to the target election date'",
    windows=(
        # 在这里，选举日投票截止之前本身就是一个独立的时间段，
        # 另外两种方案都没有这一段。
        ("election_day", 0, 0),
        ("previous_day", 1, 1),
        ("final_48_hours", 2, 2),
        ("final_week", 3, 7),
        ("two_weeks_out", 8, 14),
        ("one_month_out", 15, 30),
    ),
    cumulative=(
        ("previous_1_day", 1), ("previous_7_days", 7), ("previous_30_days", 30),
    ),
    max_days=30,
    includes_election_day=True,
)

SCHEMES: dict[str, WindowScheme] = {
    scheme.key: scheme
    for scheme in (ORIGINAL_EMAIL, PROMPT_1_AND_2, DESKTOP_SPEC)
}

# 流水线当前使用的方案。保持为最初邮件中的方案，这样
# 加入本模块不会改变任何已有的数字；一旦问题得到解决，
# 切换只需要改一行。
DEFAULT_SCHEME = ORIGINAL_EMAIL.key


@dataclass(frozen=True)
class WindowAssignment:
    """一篇文章落在哪里，以及它为什么被纳入或未被纳入。"""

    days_before: int | None
    window: str | None
    cumulative: tuple[str, ...]
    included: bool
    exclusion_reason: str | None
    scheme: str

    def as_record(self) -> dict:
        return {
            "days_before_polling": self.days_before,
            "window": self.window,
            "cumulative_windows": list(self.cumulative),
            "included_in_influence_features": self.included,
            "exclusion_reason": self.exclusion_reason,
            "window_scheme": self.scheme,
        }


def days_before_polling(
    published: date,
    polling_day: date,
) -> int:
    """发布日期与投票日之间相差的日历天数。

    正数表示在投票日之前，零表示投票日当天，负数表示在投票日之后。使用
    日历天而不是 24 小时周期，因为三种方案全都是这样写的（"30 calendar
    days before election day"，即选举日之前 30 个日历天）。
    """

    return (polling_day - published).days


def classify_lag(days: int | None, *, scheme: str = DEFAULT_SCHEME) -> str:
    """按照权威的时间窗口方案对发布时间差进行分类。"""

    if days is None:
        return "undated"
    if days <= 0:
        return "on_or_after_polling_day"

    chosen = SCHEMES[scheme]
    for label, first, last in chosen.windows:
        if first <= days <= last:
            return label
    return "before_the_earliest_window"


def assign(
    published: date | None,
    polling_day: date,
    *,
    scheme: str = DEFAULT_SCHEME,
    published_time: time | None = None,
    poll_close: time = POLL_CLOSE,
) -> WindowAssignment:
    """把一篇文章放进某个窗口，或者记录它为什么不能被使用。

    ``published_time`` 只在投票日当天才有意义。一篇日期为投票日但没有时间的
    文章，*不会*被假定为发布于投票截止之前：桌面规格说明明确规定，除非用户
    确认，否则不得纳入这类文章，而如果作相反的假定，就会让关于选举结果的
    报道进入一个选举前的预测。这正是本函数要防止的那一种泄漏。
    """

    chosen = SCHEMES[scheme]

    if published is None:
        return WindowAssignment(None, None, (), False, UNKNOWN_DATE, scheme)

    days = days_before_polling(published, polling_day)

    if days < 0:
        return WindowAssignment(days, None, (), False, AFTER_POLLING_DATE, scheme)

    if days == 0:
        # 投票日。它是否计入取决于方案和时间。
        if not chosen.includes_election_day:
            return WindowAssignment(days, None, (), False, AFTER_POLLS_CLOSED, scheme)
        if published_time is None:
            return WindowAssignment(
                days, None, (), False, ELECTION_DAY_TIME_UNKNOWN, scheme)
        if published_time >= poll_close:
            return WindowAssignment(days, None, (), False, AFTER_POLLS_CLOSED, scheme)

    if days > chosen.max_days:
        return WindowAssignment(
            days, None, (), False, BEFORE_COLLECTION_WINDOW, scheme)

    window = next(
        (label for label, first, last in chosen.windows if first <= days <= last),
        None,
    )
    if window is None:
        # 只有当某个方案的覆盖范围出现空隙时才会走到这里，
        # 而 validate() 的作用就是防止这种情况。如实报告而不去猜测。
        return WindowAssignment(
            days, None, (), False, BEFORE_COLLECTION_WINDOW, scheme)

    cumulative = tuple(
        label for label, limit in chosen.cumulative if 1 <= days <= limit
    )
    return WindowAssignment(days, window, cumulative, True, None, scheme)


def compare_schemes(
    published: date | None,
    polling_day: date,
    *,
    published_time: time | None = None,
) -> dict[str, dict]:
    """同一篇文章在三种方案下的归属。

    这样写是为了能用一张由真实文章组成的表来展示分歧，而不是从定义出发
    进行争论。其中两种方案会排除超过 30 天的所有内容，而第三种方案会对
    这些内容建模；最后三天在三种方案中的切分方式也各不相同。
    """

    return {
        key: assign(published, polling_day, scheme=key,
                    published_time=published_time).as_record()
        for key in SCHEMES
    }


def scheme_summary() -> list[dict]:
    """对每种方案的简明描述，用于提交给导师的报告。"""

    rows = []
    for scheme in SCHEMES.values():
        scheme.validate()
        rows.append({
            "scheme": scheme.key,
            "source": scheme.source,
            "windows": [f"{label}: day {first}-{last}"
                        for label, first, last in scheme.windows],
            "cumulative": [label for label, _ in scheme.cumulative],
            "modelled_horizon_days": scheme.max_days,
            "includes_election_day": scheme.includes_election_day,
        })
    return rows
