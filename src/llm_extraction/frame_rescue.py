"""使用立场层的方法，对未通过验证的框架层进行的一次补救尝试。

## 原始层为什么失败，以及为什么同样的修正可能适用

`framing_detection.py` 要求从十六个类别中选出一个 `primary_frame`。它在两把
"尺子"上都没有通过——与人工编码的 kappa 为 0.483，两个模型组之间为 0.502——
而把十六个类别归并为三个主题系列的粗化重新测试仍然没有通过（0.496 / 0.523），
所以问题并不在于粒度。

诊断借鉴了立场层。那一层失败有两个原因，两者都是把一个没有指引的选择交给了
模型：哪些实体值得占一行，以及兜底类别 `mixed` 的边界在哪里。修正这两点后，
它的模型组间一致性从 0.316 提高到了 0.848。

`primary_frame` 是同一类问题。问"这十六个框架中哪一个是*主要*框架"是一个
十六选一的排序判断，而提示词中没有任何内容说明如何排序。一篇既评判议会的
能力、*又*把选民描绘成已经受够了的文章，确实包含两个框架；哪一个是"主要"的，
是文章本身并没有回答的问题，因此两个模型会以不同方式处理它并产生分歧——尽管
它们对文章包含什么内容完全一致。

粗化重新测试无法发现这一点，因为把已经记录的 `primary_frame` 归并到某个系列，
仍然继承了产生它的那次排序。你无法从一个只存储过一个胜出者的字段中，恢复出
"两者都存在"这一信息。

## 这一层改变了什么

**一次排序变成了四个独立的"是否存在"问题。** 对四个框架中的每一个，模型只回答：
这个框架是否存在于这篇文章中，是或否。各框架之间并不互斥，没有哪个是"主要"
的，一篇文章可以同时带有全部四个框架，也可以一个都没有。不再剩下任何可供
产生分歧的排序。

**四个框架在这里固定下来，是根据研究问题而不是根据什么得分高来选择的。** 它们
在任何输出存在之前就已声明。每个框架都对应原来十六个类别中的一组，所以并没有
测量任何新的东西——只是以一种两个评分者能够达成一致的形式，询问同样的内容：

* `incumbent_judgement` —— 文章对执政当局的表现做出评判。来自原来的
  government_performance、governance_failure、financial_pressure、
  public_service_quality、accountability、competence、integrity、leadership。
* `challenger_emergence` —— 文章把既有秩序之外的某个政党呈现为一股正在崛起
  或可信的力量。来自 challenger_emergence、electoral_competition、
  national_political_momentum。这是研究问题最直接关心的框架：英国改革党
  （Reform UK）正是所研究的新兴挑战者。
* `voter_discontent` —— 文章把选民描绘为不满、愤怒或想要惩罚某人。来自
  anti_incumbent_sentiment、voter_dissatisfaction。与上一个框架配对，是因为
  关于挑战者投票的标准理论是"不满加上一个可用的替代选项"，把两者分开可以让
  数据说明是否两者都是必需的。
* `local_impact` —— 文章通过对居民的具体本地影响来框定事件。来自
  local_community_impact、policy_conflict。之所以保留，是因为本地与全国的
  比较是导师指名的对比之一。

原来十六个类别中有四个不对应其中任何一个——`other`，以及另外三个描述文章
体裁而不是框架的类别。它们的缺席是刻意的并已记录在案：这一层测量的是四个
指名的框架，而不是对所有可能框架的一个划分。

**不要求逐字证据片段**，原因与在立场补救中取消它的原因相同：它压低了召回率，
迫使一个能看出某个框架、却无法分离出一句干净可引用句子的模型回答"不存在"。
改为要求一句话的自由文本理由。

## 如实的状态说明

这是这一系列中第二次、也是最后一次补救尝试。如果通过，框架将以四个二元的
"是否存在"指示变量进入特征集——而不是作为一个十六类的分类，并且会如实这样
报告。如果失败，框架就是在四次独立尝试（原始版、粗化版、本次重新设计，每次
都在两个模型组上）之后被排除的，这比"与一位编码者有一次分歧"要有力得多的
排除依据。

再继续迭代就意味着针对验证样本调整提示词直到它通过为止，这只是换了个名字的、
在评估数据上做选择。两次有原则的尝试是事先设定的上限。

用法：
    python3 -m src.llm_extraction.frame_rescue submit [arm]
    python3 -m src.llm_extraction.frame_rescue collect [arm]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.run_d4_validation import ARMS, load_d4_articles
from src.llm_extraction.run_pilot import MODEL

RESCUE_VERSION = "frame-rescue-v1.0-2026-07-30"

# 必须超过 Haiku 组固定的 4,000 token 思考预算，因为
# API 要求 budget_tokens < max_tokens。立场补救的第一次
# 提交把这个值设为 2,000，结果每个 Haiku 请求都报错，而每个
# Sonnet 请求都成功了——Sonnet 使用自适应思考，没有可以超出的
# 固定预算。记录在这里，以免第二次掉进同一个陷阱。
MAX_TOKENS = 6000

# 四个框架，以及每个框架向模型提出的问题。
# 措辞比平常更重要：这些就是模型可依据的全部规格说明，
# 因此每一条都写成关于文章的一个可检验的单一论断，
# 而不是一个需要解读的类别标签。
FRAMES = {
    "incumbent_judgement": (
        "Does the article pass judgement on how the governing administration "
        "has performed - its competence, its finances, the quality of the "
        "services it runs, its integrity, or its leadership? This includes "
        "criticism and defence alike; the question is whether the article "
        "puts the administration's record on trial, not whether it approves."
    ),
    "challenger_emergence": (
        "Does the article present a party outside the established order as a "
        "rising or credible force - gaining support, worth taking seriously, "
        "or capable of winning where it previously could not?"
    ),
    "voter_discontent": (
        "Does the article portray voters as dissatisfied, angry, or wanting "
        "to punish someone - fed up with how things are, or looking for an "
        "alternative? The discontent must be attributed to voters or "
        "residents, not merely expressed by a politician."
    ),
    "local_impact": (
        "Does the article frame the matter through concrete consequences for "
        "local residents - a road, a school, a development, a service they "
        "use - rather than as politics in the abstract?"
    ),
}


def build_prompt() -> str:
    """系统提示词。

    在每篇文章之间都是逐字节稳定的，这与立场补救的不同——这里的问题集
    不依赖于文章内容，所以整个提示词在每个批次中只缓存一次，其余请求都
    按缓存读取的费率计费。
    """
    questions = "\n\n".join(
        f'{i}. "{key}": {text}'
        for i, (key, text) in enumerate(FRAMES.items(), start=1))
    keys = ", ".join(f'"{k}"' for k in FRAMES)
    return f"""You identify narrative frames in news articles, for an academic study \
of pre-election coverage in Surrey, England.

For each of the four frames below, answer one question: is this frame present \
in this article, yes or no.

{questions}

Rules:
1. THE FRAMES ARE INDEPENDENT. They are not alternatives and none is \
"primary". An article may carry all four, some, or none. Judge each one \
separately, as if it were the only question asked.
2. PRESENT MEANS THE ARTICLE DOES THIS, not that the topic could be read that \
way. A frame is present when the article actually organises some of its \
material that way - through what it emphasises, whom it quotes, or how it \
explains why something matters. A single passing clause is not a frame.
3. DO NOT INFER FROM THE SUBJECT. A story about a school is not automatically \
"local_impact"; it is local_impact when the article dwells on what this means \
for the people who use that school. A story mentioning a party's poll rating \
is not automatically "challenger_emergence"; it is that frame when the article \
presents the party as rising or credible.
4. JUDGE THE ARTICLE, NOT THE POLITICS. You are not assessing whether the \
framing is fair, and not supplying your own view of the parties involved.
5. GIVE A SHORT REASON per frame - one sentence naming what in the article \
drives the answer. No verbatim quotation is required.
6. Output ONLY a JSON object of this exact shape, with all four frames \
present, no markdown fences:

{{"frames": [{{"frame": "<one of {keys}>", "present": true, \
"reason": "<one sentence>"}}]}}

Prompt version: {RESCUE_VERSION}."""


def build_user_message(title: str, body: str, date: str, source: str) -> str:
    return (f"SOURCE: {source}\nPUBLISHED: {date}\n\nTITLE: {title}\n\n"
            f"BODY:\n{body}")


def _paths(arm: str) -> tuple[Path, Path]:
    suffix = "" if arm == "sonnet" else f"_{arm}"
    return (Path(f"llm_context/frame_rescue_batch{suffix}.json"),
            Path(f"llm_context/frame_rescue_outputs{suffix}.json"))


def cmd_submit(arm_name: str = "haiku") -> None:
    arm = ARMS[arm_name]
    model = arm["model"] or MODEL
    arts, _fallback = load_d4_articles()
    client = anthropic.Anthropic()

    # 每篇文章都会被问到全部四个框架——这与立场
    # 补救不同，后者的政党列表取决于文章提到了谁。框架
    # 是文章本身的属性，所以没有什么需要筛选，
    # 也不会跳过任何文章。这也使比较的基数为
    # 完整的 60 篇文章 x 4 个框架 = 240 对。
    system = [{"type": "text", "text": build_prompt(),
               "cache_control": {"type": "ephemeral"}}]
    requests = [Request(
        custom_id=aid,
        params=MessageCreateParamsNonStreaming(
            model=model, max_tokens=MAX_TOKENS, thinking=arm["thinking"],
            system=system,
            messages=[{"role": "user", "content": build_user_message(
                a["title"], a["body"], a.get("publication_datetime", ""),
                a.get("source", ""))}]))
        for aid, a in sorted(arts.items())]

    batch = client.messages.batches.create(requests=requests)
    batch_path, _ = _paths(arm_name)
    batch_path.write_text(json.dumps({
        "version": RESCUE_VERSION, "arm": arm_name, "model": model,
        "thinking": arm["thinking"], "batch_id": batch.id,
        "articles": len(requests), "frames": list(FRAMES)}, indent=2))
    print(f"{arm_name}: batch {batch.id} ({len(requests)} articles x "
          f"{len(FRAMES)} frames)")
    print(f"-> {batch_path}")


def cmd_collect(arm_name: str = "haiku") -> None:
    batch_path, out_path = _paths(arm_name)
    meta = json.loads(batch_path.read_text())
    client = anthropic.Anthropic()

    while True:
        b = client.messages.batches.retrieve(meta["batch_id"])
        print(f"{arm_name}: {b.processing_status} {b.request_counts}")
        if b.processing_status == "ended":
            break
        time.sleep(120)

    rows, usage_in, usage_out = [], 0, 0
    for result in client.messages.batches.results(meta["batch_id"]):
        entry: dict = {"article_id": result.custom_id,
                       "batch_result": result.result.type}
        if result.result.type == "succeeded":
            msg = result.result.message
            usage_in += msg.usage.input_tokens
            usage_out += msg.usage.output_tokens
            text = "".join(b.text for b in msg.content if b.type == "text")
            try:
                parsed = json.loads(text.strip().removeprefix("```json")
                                    .removeprefix("```").removesuffix("```"))
                judged = {f["frame"]: bool(f["present"])
                          for f in parsed.get("frames", [])}
                # 一个只回答了三个框架、或者编造出第五个框架的模型，
                # 没有回答所问的问题。记录为
                # 验证错误，而不是部分采用：对重叠部分
                # 评分会因为它碰巧覆盖到的部分而给它加分。
                errors = []
                if set(judged) != set(FRAMES):
                    errors.append(f"answered about {sorted(judged)}, "
                                  f"asked about {sorted(FRAMES)}")
                entry["frames"] = judged
                entry["reasons"] = {f["frame"]: f.get("reason")
                                    for f in parsed.get("frames", [])}
                entry["validation_errors"] = errors
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                entry["frames"] = None
                entry["validation_errors"] = [f"unparseable: {e}"]
        else:
            entry["frames"] = None
            entry["validation_errors"] = [f"batch: {result.result.type}"]
        rows.append(entry)

    ok = sum(1 for r in rows if r["frames"] and not r["validation_errors"])
    out_path.write_text(json.dumps({
        "version": RESCUE_VERSION, "arm": arm_name, "model": meta["model"],
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
        "articles_ok": ok, "articles_total": len(rows),
        "frames": list(FRAMES), "results": rows}, indent=2))
    print(f"{ok}/{len(rows)} clean -> {out_path}")


if __name__ == "__main__":
    _cmd = sys.argv[1]
    _arm = sys.argv[2] if len(sys.argv) > 2 else "haiku"
    {"submit": cmd_submit, "collect": cmd_collect}[_cmd](_arm)
