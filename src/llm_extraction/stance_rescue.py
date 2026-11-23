"""第 6 阶段 / D4 增补——针对未通过验证的立场层的一次补救尝试。

## 原始层为什么失败

`stance_classification.py` 在两把"尺子"上都没有通过：与人工编码的 kappa 为
0.482-0.490，两个模型组之间为 0.316。对 60 篇 D4 文章上模型间分歧的诊断
找到了两个原因，它们是设计缺陷，而不是模型的失败。在 61 个政党层面的比较中，
只有 30 个一致：

* **16 个（26%）是纳入争议**——一个模型组为某个政党创建了一行，而另一个没有。
  这一层把"评估哪些实体"的选择完全交给了模型（"one row per political
  entity that the article represents in any evaluative way"，即文章以任何
  评价性方式呈现的每个政治实体一行），并附加了两个主观条件：这种呈现必须
  是评价性的，并且必须带有一段逐字引用的证据。Sonnet 输出了 168 行，而
  Haiku 输出了 140 行——在完全相同的输入上多纳入了 20%。两个模型组回答的
  是不同的问题集。

* **15 个（25%）是方向争议，其中 11 个涉及 `mixed`**——`mixed vs negative`、
  `mixed vs positive`、`negative vs mixed`。这并不是关于报道是否带有敌意的
  分歧；而是关于一个阈值的分歧：当一篇文章中同时存在两种倾向时，到什么
  程度它就不再是"以负面为主"而变成"mixed"。`mixed` 起到了一个兜底类别的
  作用，而每个模型划定其边界的方式各不相同。

61 个比较中只有 4 个是实质性的方向冲突（negative vs neutral、positive vs
neutral）。去掉这两个设计缺陷，一致率将接近 93%。

## 这一层改变了什么，以及刻意不改变什么

两项改动，各自针对一个诊断出的缺陷：

1. **政党列表由代码确定，而不是由模型选择。** 政党是否出现由针对文章文本
   的确定性别名匹配决定（`parties_present`），然后只就这些政党向模型提问。
   因此两个模型组回答的是完全相同的问题集，纳入边界按构造就是可复现的，
   而不是一个可能漂移的判断。

2. **去掉 `mixed`；模型必须做出明确选择。** 只有三个取值——`unfavourable`、
   `favourable`、`neither`——并明确指示：当一篇文章同时带有两种倾向时，要
   指出占主导的方向。这正是 `test_coarsened_agreement.py` 那次运行事后无法
   实现的粗化，因为把已经记录下来的 `mixed` 合并起来，无法恢复出哪个方向
   占主导。

仅在这一层取消了逐字证据片段的要求。在原始版本中，它压低了召回率：一个能够
看出敌意框架、却无法分离出一段干净可引用片段的模型，会被规则 3 推向完全省略
这一行。改为要求一个简短的自由文本理由，这既保持了输出的可审计性，又不会
把引文作为报告一项判断的前提条件。

## 保持不变的部分，以使比较保持公平

相同的 60 篇 D4 文章、相同的两个模型组、相同的批处理定价、相同的关卡
（kappa >= 0.60，并带有预注册的 AC1 后备标准），以及作为次要参照的相同人工
金标准标签。这里以模型间一致性为主要标准，原因见
`d4_gate_outcome_and_decisions.md` 第 3b 节：人工标签是单轮标注的，而且是在
一条与这一层本身相矛盾的指示下收集的，因此它们无法单独对这一层做出裁决。

## 如实的状态说明

这是对一个失败的层所做的事后重新设计，因此如果在这里通过，会被报告为
"在修订后的层下，以降低的粒度恢复了立场"，而绝不会被说成原始层通过了。
重新设计是由对分歧*为什么*发生的诊断驱动的，而不是靠搜寻一个得分高的表述——
上述两项改动在任何补救输出存在之前就已经确定。

用法：
    python3 -m src.llm_extraction.stance_rescue submit [arm]
    python3 -m src.llm_extraction.stance_rescue collect [arm]
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.run_d4_validation import ARMS, load_d4_articles
from src.llm_extraction.run_pilot import MODEL

RESCUE_VERSION = "stance-rescue-v1.0-2026-07-30"

# 必须超过最大的那个模型组的思考预算：API 要求
# budget_tokens < max_tokens，而 Haiku 组为思考预留了 4,000 个 token。
# 第一次提交把这个值设为 2,000，结果每个 Haiku 请求
# 都因此报错，而 Sonnet——它使用自适应思考，
# 因此没有可以超出的固定预算——在全部 34 个请求上都成功了。之所以记录下来
# 而不是悄悄修正，是因为这种不对称对于今后
# 任何添加固定预算模型组的人来说都是一个真实的陷阱。
MAX_TOKENS = 6000

# 用于确定性地检测政党是否出现的政党别名。刻意
# 保守：只有在出现明确无歧义的表面形式时，才算该政党出现，
# 因此问题集仅凭文本就可以复现。改革党的
# 别名不包括单独的 "reform" 一词——那是普通的英语
# 单词，E6 纳入资格规则正是为了区分它而存在的，在这里接受它
# 会重新引入 E6 所消除的那种混淆。
PARTY_ALIASES = {
    "conservative": [r"\bconservatives?\b", r"\btor(?:y|ies)\b",
                     r"\bconservative party\b"],
    "labour": [r"\blabour\b"],
    "liberal_democrat": [r"\bliberal democrats?\b", r"\blib dems?\b",
                         r"\bliberal democrat party\b"],
    "green": [r"\bgreen party\b", r"\bthe greens\b", r"\bgreens\b"],
    "reform_uk": [r"\breform uk\b", r"\breform party\b"],
    "ukip": [r"\bukip\b", r"\buk independence party\b"],
}

PARTY_LABELS = {
    "conservative": "the Conservative Party",
    "labour": "the Labour Party",
    "liberal_democrat": "the Liberal Democrats",
    "green": "the Green Party",
    "reform_uk": "Reform UK",
    "ukip": "UKIP",
}

DECISIONS = ("unfavourable", "favourable", "neither")


def parties_present(title: str, body: str) -> list[str]:
    """文章明确无歧义地提到了哪些研究所关注的政党。

    确定性的，并且对每个模型组都完全相同——正是这项改动把纳入判断从模型
    手中拿走。返回稳定的顺序，使渲染出的提示词逐字节稳定并可被缓存。
    """
    text = f"{title}\n{body}".lower()
    return [p for p in PARTY_ALIASES
            if any(re.search(pat, text) for pat in PARTY_ALIASES[p])]


def build_prompt(parties: list[str]) -> str:
    """系统提示词，按问题集渲染。

    在不同文章之间不是逐字节稳定的，因为政党列表不同——所以只有在提到相同
    政党的文章之间才会命中缓存。这是固定问题集的代价，而且值得付出：一个把
    政党列表交给模型决定的共享提示词，正是导致原始层无法复现的原因。
    """
    named = "\n".join(f"- {PARTY_LABELS[p]}" for p in parties)
    return f"""You judge how a news article portrays named political parties, for an \
academic study of pre-election coverage in Surrey, England.

You will be asked about EXACTLY these parties, all of which the article names:

{named}

For each one, answer the single question: does this article portray that party \
favourably, unfavourably, or neither?

Rules:
1. JUDGE THE PORTRAYAL, NOT THE PARTY. You are reading how the article \
represents the party - not whether you agree with it, and not the party's own \
opinions quoted in the article.
2. UNFAVOURABLE INCLUDES UNFAVOURABLE FACTS. An article reporting that a party \
lost heavily, is falling in the polls, faces a scandal, or is blamed for a \
failure portrays that party unfavourably - even when the reporting is entirely \
neutral in tone. You are not judging whether the journalist editorialised; you \
are judging whether a reader finishes the article thinking better or worse of \
that party.
3. COMMIT TO A DIRECTION. There is no "mixed" option. When an article carries \
both favourable and unfavourable material about the same party, name the \
direction that predominates. Use "neither" only when the article genuinely \
does not move the reader either way - a bare mention in a candidate list, a \
procedural notice, a passing reference with no evaluative weight.
4. ONE ANSWER PER PARTY LISTED. Do not add parties, do not omit any.
5. GIVE A SHORT REASON. One sentence per party saying what in the article \
drives the answer. No verbatim quotation is required.
6. Output ONLY a JSON object of this exact shape, no markdown fences:

{{"judgements": [{{"party": "<one of the keys below>", \
"portrayal": "unfavourable|favourable|neither", "reason": "<one sentence>"}}]}}

The permitted party keys are: {", ".join(parties)}.
Prompt version: {RESCUE_VERSION}."""


def build_user_message(title: str, body: str, date: str, source: str) -> str:
    return (f"SOURCE: {source}\nPUBLISHED: {date}\n\nTITLE: {title}\n\n"
            f"BODY:\n{body}")


def _paths(arm: str) -> tuple[Path, Path]:
    suffix = "" if arm == "sonnet" else f"_{arm}"
    return (Path(f"llm_context/stance_rescue_batch{suffix}.json"),
            Path(f"llm_context/stance_rescue_outputs{suffix}.json"))


def cmd_submit(arm_name: str = "haiku") -> None:
    arm = ARMS[arm_name]
    model = arm["model"] or MODEL
    arts, _fallback = load_d4_articles()
    client = anthropic.Anthropic()

    requests, question_sets, skipped = [], {}, []
    for aid, a in sorted(arts.items()):
        parties = parties_present(a["title"], a["body"])
        if not parties:
            # 没有提到任何研究所关注的政党，因此没有什么可判断的。记录
            # 下来而不是悄悄丢弃：一篇没有政党的文章是一个
            # 合理的零，而不是一次缺失的测量。
            skipped.append(aid)
            continue
        question_sets[aid] = parties
        requests.append(Request(
            custom_id=aid,
            params=MessageCreateParamsNonStreaming(
                model=model, max_tokens=MAX_TOKENS,
                thinking=arm["thinking"],
                system=[{"type": "text", "text": build_prompt(parties),
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": build_user_message(
                    a["title"], a["body"], a.get("publication_datetime", ""),
                    a.get("source", ""))}])))

    batch = client.messages.batches.create(requests=requests)
    batch_path, _ = _paths(arm_name)
    batch_path.write_text(json.dumps({
        "version": RESCUE_VERSION, "arm": arm_name, "model": model,
        "thinking": arm["thinking"], "batch_id": batch.id,
        "articles": len(requests),
        "articles_without_any_study_party": skipped,
        "question_sets": question_sets}, indent=2))
    print(f"{arm_name}: batch {batch.id} ({len(requests)} articles, "
          f"{len(skipped)} with no study party named)")
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
        aid = result.custom_id
        entry: dict = {"article_id": aid,
                       "batch_result": result.result.type,
                       "asked_about": meta["question_sets"].get(aid, [])}
        if result.result.type == "succeeded":
            msg = result.result.message
            usage_in += msg.usage.input_tokens
            usage_out += msg.usage.output_tokens
            text = "".join(b.text for b in msg.content if b.type == "text")
            try:
                parsed = json.loads(text.strip().removeprefix("```json")
                                    .removeprefix("```").removesuffix("```"))
                judged = {j["party"]: j.get("portrayal")
                          for j in parsed.get("judgements", [])}
                # 对照所问的集合和封闭词表进行验证。
                # 如果模型回答了一个没有被问到的政党，
                # 或者编造了一个取值，这就是一次需要记录的失败——而不是
                # 可以强行修饰成看起来有效的东西。
                errors = []
                asked = set(entry["asked_about"])
                if set(judged) != asked:
                    errors.append(f"answered about {sorted(judged)}, "
                                  f"asked about {sorted(asked)}")
                bad = {p: v for p, v in judged.items() if v not in DECISIONS}
                if bad:
                    errors.append(f"values outside the vocabulary: {bad}")
                entry["judgements"] = judged
                entry["reasons"] = {j["party"]: j.get("reason")
                                    for j in parsed.get("judgements", [])}
                entry["validation_errors"] = errors
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                entry["judgements"] = None
                entry["validation_errors"] = [f"unparseable: {e}"]
        else:
            entry["judgements"] = None
            entry["validation_errors"] = [f"batch: {result.result.type}"]
        rows.append(entry)

    ok = sum(1 for r in rows if r["judgements"] and not r["validation_errors"])
    out_path.write_text(json.dumps({
        "version": RESCUE_VERSION, "arm": arm_name, "model": meta["model"],
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
        "articles_ok": ok, "articles_total": len(rows),
        "results": rows}, indent=2))
    print(f"{ok}/{len(rows)} clean -> {out_path}")


if __name__ == "__main__":
    _cmd = sys.argv[1]
    _arm = sys.argv[2] if len(sys.argv) > 2 else "haiku"
    {"submit": cmd_submit, "collect": cmd_collect}[_cmd](_arm)
