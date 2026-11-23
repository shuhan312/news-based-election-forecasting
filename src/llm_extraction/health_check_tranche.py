"""窄批次与全语料库运行之间的关卡。

它的任务是在问题还便宜的时候把它抓住。窄批次有 89 篇文章；完整语料库有
1,638 篇。一个 schema 缺陷、一次截断或一段无法核验的引文，在这里发现几乎
不花什么成本，而在完整运行中则要付出十八倍的代价。

四个阈值。其中三个与批次提交之前所声明的一致；第四个在失败之后被替换，下面
的常量代码块完整地说明了原因，而不是让这一改动不了了之。

* **每层的 schema 失败率最多 5%。** 先例是纳入资格批处理，其中 2,370 个请求
  中有 20 个因 schema 失败——0.8%。百分之五在此之上留有相当大的余量，同时
  仍能抓住提示词真正出了问题的层。框架补救的 Sonnet 组失败率为 8.3%，这个
  阈值正是为拒绝这种情况而校准的。
* **逐字引文核验率至少 95%**，针对需要证据片段的层。试点达到了 98.1%。一段
  在文章中找不到的片段意味着模型重构了引文，而这是唯一一种会使抽取变得无法
  追溯的失败方式。
* **成本在估计值的两倍以内。** 这不是一个严格的界限——它的存在是为了抓住
  失控的情况，例如提示词不再被缓存，或者某一层输出的 token 远多于它的前身。
* **任何一层的空记录率都不得比它自身在 D4 验证样本上的比率高出 15 个百分点
  以上。** 取代了一个没有引用任何先例、而且连 D4 数据本身都无法通过的统一 20%
  门槛——见 `D4_EMPTY_RATE` 代码块。现在的检查寻找的是相对于已测量的先前表现
  的退化，而不是一个绝对水平，因为一篇文章不带有任何框架的频率是语料库本身
  的事实，而不是抽取过程的缺陷。

一次失败会使整条链停止。它不会针对这 89 篇文章调整提示词然后重试——那将是
在评估数据上做选择，而 D4 关卡的全部意义正是为了避免这种做法。

唯一确实改变了的那个阈值，是基于早于该批次的数据改变的，而这一区别正是本
模块值得信任的全部理由。因为批次没有通过门槛就放宽门槛，是在评估数据上做
选择。发现某个门槛从来就与验证这些层的样本不一致，并依据那份先前的样本重新
校准，则是在修正测量工具。记录中写明了做的是哪一种、依据的是什么证据，因此
读者可以不同意这个决定，而不必自己去察觉它。

用法：
    python3 -m src.llm_extraction.health_check_tranche narrow
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.run_corpus_extraction import (EXCLUDED_LAYERS,
                                                      FRAME_KEYS,
                                                      ORIGINAL_LAYERS,
                                                      load_tranche)

MAX_SCHEMA_FAILURE_RATE = 0.05
MIN_QUOTE_VERIFICATION = 0.95
MAX_COST_MULTIPLE = 2.0

# 空记录检查，在失败之后被替换——而这恰恰是整个模块
# 要防止的那种模式，所以这里完整地写出理由，而不是
# 一笔带过。
#
# 原来的门槛是每层统一 20%，而且与其他三个
# 阈值不同，它没有引用任何先例。它没有引用先例是因为根本没有先例：它
# 是凭直觉设定的，理由是如果一个层在五分之一的语料库中
# 什么都没找到，那要么是提示词有问题，要么是它测量的东西过于罕见，
# 不足以构建特征。
#
# 这一论证把抽取过程的缺陷与语料库本身的性质混为一谈。
# 在 D4 样本上测量——也就是这些层据以通过验证并被采纳的
# 同一批 60 篇文章——空记录率为：
#
#     framing_revised   36.4%（Sonnet）   40.0%（Haiku）
#     issues            18.3%（Sonnet）    8.3%（Haiku）
#     stance_revised     0.0%（Sonnet）    0.0%（Haiku）
#
# 所以 20% 的门槛会拒绝掉四个框架中有两个据以被采纳的
# 那批数据本身。一篇在投票前三十天内的文章可能不带有
# 四个叙事框架中的任何一个，也没有可编码的政治议题，却仍然是
# 语料库的合理成员；纳入资格意味着"在范围之内"，而不是"关于
# 这场选举"。
#
# 替代方案把每一层与它自身在实际运行的模型组上的比率
# 进行比较，并在出现实质性退化时判定失败，而不是看一个
# 绝对水平——这与成本检查的形式相同，后者允许不超过估计值的两倍，
# 而不是给出一个具体数字。因此校准所用的数据
# 完全早于该批次。
#
# 没有放宽的部分：schema 阈值和引文阈值——该批次在议题层上
# 也没有通过这两项——保持原值不变。那次失败
# 是通过在收集程序中修复一个可推导的字段来解决的，
# 修复逐篇文章记录在案，并且先测量了它对 D4 数字的影响，
# 而不是通过移动门槛。
D4_EMPTY_RATE = {
    "issues": 0.183,            # Sonnet 组，即这一层运行所用的模型组
    "framing_revised": 0.400,   # Haiku 组
    "stance_revised": 0.000,    # Haiku 组
    "credit_blame": 0.316,      # 为完整起见记录；该层已被排除
    "consequence": 0.438,       # 为完整起见记录；该层已被排除
}
EMPTY_RATE_REGRESSION = 0.15
DEFAULT_D4_EMPTY_RATE = 0.20    # 未见过的层退回使用原来的门槛

# 按模型列出的每百万 token 批处理费率，因为各层不再共用
# 同一个模型：需要逐字证据片段的三个层运行在
# Sonnet 上，它能提供这些片段；两个修订后的层运行在 Haiku 上，
# 它在这些层所要求的判断上既更便宜又更好。
RATES = {
    "claude-haiku-4-5": (0.50, 2.50),
    "claude-sonnet-5": (1.00, 5.00),   # 推广期费率，截至 2026-08-31
}
DEFAULT_RATE = (1.00, 5.00)


def _spans(node, out: list[str]) -> None:
    """收集一条记录中任意深度的每一个 evidence_span 文本。

    之所以递归，是因为各层嵌套片段的方式不同——在议题声明内部、在归因行
    内部、在后果行内部——而一个只认识每种具体结构的检查程序，会悄悄跳过
    一个它没有被教过其结构的层。
    """
    if isinstance(node, dict):
        if "evidence_span" in node and isinstance(node["evidence_span"], dict):
            text = node["evidence_span"].get("text")
            if text:
                out.append(text)
        for v in node.values():
            _spans(v, out)
    elif isinstance(node, list):
        for v in node:
            _spans(v, out)


def _is_empty(layer: str, record: dict) -> bool:
    """一条解析后的记录是否真的带有一项发现。

    空记录并不是失败——一篇没有归因的文章确实就没有归因，而 schema 也提供了
    表达这一点的方式。只有在大量出现时它才值得关注，而这正是阈值所衡量的。"""
    if layer == "issues":
        issues = record.get("issues") or {}
        primary = issues.get("primary_issue")
        if isinstance(primary, dict):
            primary = primary.get("issue_code") or primary.get("code")
        return not primary
    if layer == "credit_blame":
        return not (record.get("attributions") or [])
    if layer == "consequence":
        return not (record.get("consequences") or [])
    if layer == "stance_revised":
        return not (record.get("judgements") or [])
    if layer == "framing_revised":
        frames = {f["frame"]: f.get("present")
                  for f in record.get("frames") or []}
        return not any(frames.get(k) for k in FRAME_KEYS)
    return False


def main() -> None:
    tranche = sys.argv[1] if len(sys.argv) > 1 else "narrow"
    outputs = json.loads(
        Path(f"llm_context/corpus_extraction_outputs_{tranche}.json").read_text())
    batches = json.loads(
        Path(f"llm_context/corpus_extraction_batches_{tranche}.json").read_text())
    # 该批次实际抽取的文章，从它自己的输出中读取，
    # 而不是根据批次规则重新推导。far 抽样器会排除
    # 之前各次 far 抽样用过的文章，所以在收集 `far2` 之后重新推导它
    # 会返回第三个、不同的样本——检查程序随后就在
    # 89 篇 far2 从未见过的文章中寻找 far2 的证据片段，报告 314 个中
    # 0 个通过核验。一个会重新计算其检查对象的关卡，可能会因为
    # 关卡自身的缺陷而判定一次抽取失败。
    extracted_ids = {r["article_id"] for rows in outputs["layers"].values()
                     for r in rows}
    arts, _fallback, _census = load_tranche(tranche, only_ids=extracted_ids)

    report: dict = {"tranche": tranche, "layer_models": outputs.get("layer_models", {}),
                    "articles": batches["articles"],
                    "thresholds": {
                        "max_schema_failure_rate": MAX_SCHEMA_FAILURE_RATE,
                        "min_quote_verification": MIN_QUOTE_VERIFICATION,
                        "max_cost_multiple": MAX_COST_MULTIPLE,
                        "d4_empty_rate_baseline": D4_EMPTY_RATE,
                        "empty_rate_regression_allowance":
                            EMPTY_RATE_REGRESSION},
                    "layers": {}}

    for layer, rows in outputs["layers"].items():
        n = len(rows)
        failed = sum(1 for r in rows
                     if r["record"] is None or r["validation_errors"])
        empty = sum(1 for r in rows if r["record"] is not None
                    and not r["validation_errors"]
                    and _is_empty(layer, r["record"]))
        checked = verified = 0
        if layer in ORIGINAL_LAYERS:
            for r in rows:
                if r["record"] is None:
                    continue
                spans: list[str] = []
                _spans(r["record"], spans)
                article = arts.get(r["article_id"], {})
                haystack = ((article.get("body") or "") + "\n"
                            + (article.get("title") or ""))
                for s in spans:
                    checked += 1
                    if s in haystack:
                        verified += 1
        fail_rate = failed / n if n else 0.0
        empty_rate = empty / n if n else 0.0
        quote_rate = verified / checked if checked else None
        problems = []
        if fail_rate > MAX_SCHEMA_FAILURE_RATE:
            problems.append(f"schema failure {fail_rate:.1%} exceeds "
                            f"{MAX_SCHEMA_FAILURE_RATE:.0%}")
        if quote_rate is not None and quote_rate < MIN_QUOTE_VERIFICATION:
            problems.append(f"quote verification {quote_rate:.1%} below "
                            f"{MIN_QUOTE_VERIFICATION:.0%}")
        baseline = D4_EMPTY_RATE.get(layer, DEFAULT_D4_EMPTY_RATE)
        allowance = baseline + EMPTY_RATE_REGRESSION
        if empty_rate > allowance:
            problems.append(f"empty records {empty_rate:.1%} exceed "
                            f"{allowance:.1%} (D4 rate {baseline:.1%} plus "
                            f"{EMPTY_RATE_REGRESSION:.0%} regression "
                            f"allowance)")
        # 被排除的层仍然会被测量和报告——该批次为它
        # 付了费，这些数字也应当留在记录中——但它不参与
        # 关卡的投票。如果让完整运行不会提交的层阻挡
        # 它会提交的层，就会因为一个已经基于比 89 篇文章
        # 更强的证据做出决定的结果而让整条链停下来。
        report["layers"][layer] = {
            "articles": n, "failed": failed,
            "counts_toward_gate": layer not in EXCLUDED_LAYERS,
            "excluded_reason": EXCLUDED_LAYERS.get(layer),
            "schema_failure_rate": round(fail_rate, 4),
            "empty_records": empty,
            "empty_record_rate": round(empty_rate, 4),
            "empty_rate_d4_baseline": baseline,
            "empty_rate_allowance": round(allowance, 4),
            "quote_spans_checked": checked,
            "quote_spans_verified": verified,
            "quote_verification_rate": (None if quote_rate is None
                                        else round(quote_rate, 4)),
            "problems": problems, "passes": not problems}

    # 每一层按其自身模型的费率计价；如果缺少按层的明细，就退回到
    # 按 Sonnet 费率计算整个批次，这只会
    # 高估而不会低估，因此不可能让一次失控的运行
    # 看起来负担得起。
    by_layer = outputs.get("usage_by_layer") or {}
    usage = outputs.get("usage", {})
    if by_layer:
        cost = 0.0
        for layer, u in by_layer.items():
            rin, rout = RATES.get(u.get("model"), DEFAULT_RATE)
            cost += (u.get("input_tokens", 0) / 1e6 * rin
                     + u.get("output_tokens", 0) / 1e6 * rout)
    else:
        rin, rout = DEFAULT_RATE
        cost = (usage.get("input_tokens", 0) / 1e6 * rin
                + usage.get("output_tokens", 0) / 1e6 * rout)
    per_article = cost / batches["articles"] if batches["articles"] else 0
    # 根据该批次实际的每篇文章成本进行推算，这
    # 比任何事先的猜测都是更好的估计——D4 的数字来自
    # 使用不同提示词的六个层。
    full_articles = _full_corpus_size()
    report["cost"] = {
        "tranche_usd": round(cost, 4),
        "per_article_usd": round(per_article, 5),
        "projected_full_corpus_usd": round(per_article * full_articles, 2),
        "full_corpus_articles": full_articles,
        "note": ("projected from this tranche's measured cost per article, "
                 "at each layer's own batch rate; the full run reuses these 89 "
                 "extractions rather than repeating them"),
    }

    # 一个从未被收集的关卡层，不得因为缺席而通过。
    # 收集程序现在可以在缺少某个被排除的层的情况下继续运行，这意味着
    # 输出文件不再必然包含每一个被提交过的
    # 层——而对现有各层执行 `all()` 会放行一个
    # 检查对象根本不存在的关卡。
    required = sorted(set(batches["layers"]) - set(EXCLUDED_LAYERS))
    missing = [l for l in required if l not in report["layers"]]
    report["required_layers"] = required
    report["missing_layers"] = missing
    if missing:
        report["layers"].setdefault("__completeness__", {
            "articles": 0, "counts_toward_gate": True, "excluded_reason": None,
            "problems": [f"gating layers not collected: {missing}"],
            "passes": False, "quote_verification_rate": None,
            "schema_failure_rate": 0.0, "empty_record_rate": 0.0,
            "failed": 0, "empty_records": 0, "quote_spans_checked": 0,
            "quote_spans_verified": 0})

    report["overall_pass"] = all(v["passes"] for v in report["layers"].values()
                                 if v["counts_toward_gate"])
    report["verdict"] = (
        "PASS - the full-corpus run may proceed on this model and these prompts"
        if report["overall_pass"] else
        "FAIL - stop. Do not submit the full corpus. Fix the named layer and "
        "re-validate on a fresh tranche; do not tune against these 89 articles")

    out = Path(f"llm_context/tranche_health_check_{tranche}.json")
    out.write_text(json.dumps(report, indent=2))

    print(f"# Tranche health check ({tranche})\n")
    print("| layer | articles | schema fail | empty | quotes verified | verdict |")
    print("|---|---|---|---|---|---|")
    for layer, v in report["layers"].items():
        q = ("n/a" if v["quote_verification_rate"] is None
             else f"{v['quote_verification_rate']:.1%}")
        verdict = ("pass" if v["passes"] else "; ".join(v["problems"]))
        if not v["counts_toward_gate"]:
            verdict = f"[not gating: {v['excluded_reason']}] {verdict}"
        print(f"| {layer} | {v['articles']} | {v['schema_failure_rate']:.1%} "
              f"| {v['empty_record_rate']:.1%} | {q} | {verdict} |")
    print(f"\ncost: ${report['cost']['tranche_usd']} for this tranche, "
          f"${report['cost']['per_article_usd']}/article, projected "
          f"${report['cost']['projected_full_corpus_usd']} for "
          f"{full_articles} articles")
    print(f"\n**{report['verdict']}**")
    print(f"-> {out}")


def _full_corpus_size() -> int:
    _arts, _fb, census = load_tranche("all")
    return sum(census["by_window"].values())


if __name__ == "__main__":
    main()
