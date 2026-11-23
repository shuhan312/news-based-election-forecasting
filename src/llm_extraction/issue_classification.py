"""第 6 阶段 / 第 3 步——议题 / 话题分类（纯逻辑；运行器负责 IO，
本模块中没有任何 API 调用）。

一个聚焦的层，而不是重新运行完整的 11 层契约：对每篇正式文章，确定它讨论的是
什么政治议题（一个主要议题 + 最多五个次要议题，依据已批准的 issues-v1.2 分类
体系），每一项分配都带有一段逐字引文、一段解释和一个置信度分数——外加政治相关性
判定（与选举竞争的联系、受影响的行动者、对选民认知可能产生的影响）。按规格
说明，立场、框架、归咎 / 归功以及后果都*不*在这里的范围之内。

验证规则（S 系列；确定性的，输出经过排序）：

    S1  每一段证据都必须*逐字*出现在文章正文中
        （若 from_title 则出现在标题中）——防幻觉关卡，
        其精神与试点的 R1 相同；
    S2  任何置信度 < 0.5 都会强制 review_status = flagged；
    S3  主要 / 次要议题分离：主要代码不得
        再次出现在 secondary_issues 中，并且次要代码必须
        唯一——每篇文章每个代码只分配一次；
    S4  政治相关性声明需要支撑：如果任一布尔值
        为真，就必须提供一段证据——不允许没有支撑的
        解读；
    S5  空分类（没有主要议题，也没有次要议题）不能
        声称 extraction_status 为 "extracted"，并且必须带有一条
        歧义说明——"没有政治议题"是一项明确陈述的发现；
    S6  not_attempted 记录必须为空；
    S7  v1.3 的全国性代码（national_politics、
        national_economy）只有在记录标记为分类体系
        issues-v1.3 时才有效——标记为 v1.2 的试点记录早于
        它们，并以 v1.2 的身份保持可追溯（与
        主 schema 的 R9 是同样的规范）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("llm_context/issue_classification_schema_v1.json")
# v1.3：在试点显示全国组的文章在面向本地的分类体系下
# 无法编码之后，加入了全国性代码（见
# llm_context/issue_layer_decisions_v1.md；导师批准
# 尚待确认，暂时采用）
TAXONOMY_PATH = Path("llm_context/issue_taxonomy_v1.3.json")

CLS_SCHEMA_VERSION = "issue-cls-v1.1-2026-07-27"
CLS_PROMPT_VERSION = "issue-cls-prompt-v1.1-2026-07-27"
CLS_RULES_VERSION = "issue-cls-rules-v1.1-2026-07-27"
TAXONOMY_CURRENT = "issues-v1.3"
NATIONAL_CODES = {"national_politics", "national_economy"}
LOW_CONFIDENCE = 0.5


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _issues(record: dict) -> list[dict]:
    iss = record.get("issues") or {}
    return ([iss["primary_issue"]] if iss.get("primary_issue")
            else []) + (iss.get("secondary_issues") or [])


def validate_structure(record: dict) -> list[str]:
    validator = Draft202012Validator(load_schema())
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: "
                  f"{e.message}" for e in validator.iter_errors(record))


def validate_rules(record: dict, body: str, title: str = "") -> list[str]:
    errors: list[str] = []
    iss = record.get("issues") or {}
    claims = _issues(record)

    # ---- S1 逐字检查 + S2 置信度分流 ------------------------
    rel = record.get("political_relevance") or {}
    spans = [("issues", c.get("evidence_span"), c.get("confidence"))
             for c in claims]
    if rel.get("evidence_span"):
        spans.append(("political_relevance", rel["evidence_span"], None))
    for section, span, conf in spans:
        if not isinstance(span, dict):
            continue
        haystack = title if span.get("from_title") else body
        text = span.get("text", "")
        if text and text not in haystack:
            errors.append(f"S1 {section}: evidence span not found "
                          f"verbatim: {text[:60]!r}")
        if isinstance(conf, (int, float)) and conf < LOW_CONFIDENCE \
                and record.get("review_status") != "flagged":
            errors.append(f"S2 {section}: confidence {conf} below "
                          f"{LOW_CONFIDENCE} but record not flagged")

    # ---- S3 主要 / 次要议题分离 ----------------------------
    primary = (iss.get("primary_issue") or {}).get("issue_code")
    secondary = [c.get("issue_code")
                 for c in iss.get("secondary_issues") or []]
    if primary and primary in secondary:
        errors.append(f"S3 issues: primary code {primary!r} repeated "
                      "in secondary_issues")
    dupes = sorted({c for c in secondary if secondary.count(c) > 1})
    if dupes:
        errors.append(f"S3 issues: duplicate secondary codes {dupes}")

    # ---- S4 相关性声明需要支撑 ---------------------------
    if (rel.get("election_competition_related")
            or rel.get("may_influence_voter_perceptions")) \
            and not rel.get("evidence_span"):
        errors.append("S4 political_relevance: relevance asserted "
                      "without an evidence span")

    # ---- S5 / S6 状态一致性 ---------------------------------
    if not claims:
        if record.get("extraction_status") == "extracted":
            errors.append("S5: no issues assigned yet status is "
                          "'extracted' - empty must be partial/failed "
                          "with a note")
        if record.get("extraction_status") in ("partial", "failed") \
                and not record.get("ambiguity_notes"):
            errors.append("S5: empty classification requires an "
                          "ambiguity note")
    if record.get("extraction_status") == "not_attempted" and claims:
        errors.append("S6: not_attempted record carries issue claims")

    # ---- S7 全国性代码受分类体系版本限制 ----------------
    codes = {c.get("issue_code") for c in claims}
    used_national = sorted(codes & NATIONAL_CODES)
    if used_national and iss.get("taxonomy_version") != "issues-v1.3":
        errors.append(f"S7 issues: {used_national} require "
                      "taxonomy_version issues-v1.3")
    return sorted(errors)


def validate_issue_record(record: dict, body: str,
                          title: str = "") -> list[str]:
    errors = validate_structure(record)
    if errors:
        return errors
    return validate_rules(record, body, title)


def build_issue_prompt() -> str:
    """聚焦的系统提示词——来自已批准的 v1.2 产物的分类体系定义，
    加上精简的 schema。逐字节稳定（不含时钟），
    因此批处理会缓存它，重跑时渲染结果完全相同。"""
    taxonomy = json.loads(TAXONOMY_PATH.read_text())
    tax_lines = "\n".join(f"- {code}: {desc}"
                          for code, desc in taxonomy["codes"].items())
    schema = SCHEMA_PATH.read_text().strip()
    return f"""You are an issue-classification system for an academic study of \
pre-election news coverage in Surrey, England. For each article, produce ONE \
JSON object conforming exactly to the JSON Schema below: the article's PRIMARY \
political issue, up to five SECONDARY issues, and the political-relevance \
determination. Prompt version: {CLS_PROMPT_VERSION}.

The taxonomy (issues-v1.3; set taxonomy_version to "issues-v1.3") - use ONLY \
these codes, never invent one. The two national_* codes are for NATIONAL \
politics/economy coverage that fits no local code - prefer a specific code \
(healthcare, immigration, scandal...) whenever one applies:
{tax_lines}

Hard rules:
1. EVIDENCE OR NOTHING. Every issue assignment and any asserted political \
relevance must carry evidence_span.text copied CHARACTER-FOR-CHARACTER from \
the article body (or title, with from_title true). NEVER shorten a quote \
with "..." or any ellipsis, NEVER splice passages, NEVER reconstruct from \
memory; choose a shorter contiguous span instead. A validator string-matches \
every span and rejects anything that is not an exact copy.
2. EXPLAIN EVERY ASSIGNMENT. Each issue carries a one-or-two sentence \
explanation of why the code applies.
3. DO NOT GUESS. An article with no political issue gets primary_issue null, \
empty secondary_issues, extraction_status "partial" and an ambiguity note. \
Never force a code.
4. PRIMARY vs SECONDARY. Exactly one main issue (or null); secondary issues \
are genuinely present additional topics, most relevant first, no repeats of \
the primary code, maximum five.
5. RELEVANCE NEEDS PROOF. Set election_competition_related and \
may_influence_voter_perceptions honestly; if either is true, provide the \
supporting evidence_span. List affected_actors only when the article names \
them. Do NOT predict election outcomes.
6. CONFIDENCE IS HONEST. Confidence in [0,1] per assignment; if any is \
below 0.5, set review_status to "flagged".
7. NO PROPERTY THE SCHEMA DOES NOT DEFINE. Every key you emit must appear in \
the schema below, at the level the schema puts it. The top-level object \
permits exactly: schema_version, article_id, canonical_article_id, \
extraction_status, review_status, issues, political_relevance, \
ambiguity_notes. Each issue object permits exactly: issue_code, \
issue_other_label, explanation, evidence_span, confidence. Nothing else, at \
either level. Do not invent a key for a note, a label or a caveat, and do not \
move a property to a level the schema does not declare it at. If something \
needs saying, put it in top-level ambiguity_notes; if an issue falls outside \
the taxonomy, use issue_other_label inside that issue object. The validator \
rejects the whole record for one undeclared key, so a volunteered note costs \
the entire extraction.
8. Output ONLY the JSON object - no markdown fences, no commentary.

The JSON Schema (contract {CLS_SCHEMA_VERSION}):

{schema}"""
