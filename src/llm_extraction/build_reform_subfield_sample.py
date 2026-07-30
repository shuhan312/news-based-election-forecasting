"""Build the reform_uk sub-field validation workbook: the 14 D4 articles
the model marked applicable=true, plus 8 controls it marked false, hash-
shuffled together so the reviewer cannot tell which is which. Blind by
construction: no model output appears on the sheet.

Why controls at all: scoring only the model's positives would hand the
human an all-yes applicable column, a constant marginal, and a kappa
that collapses to 0 regardless of real agreement - the prevalence
problem already documented in eligibility_manual_review_methodology.md
section 8.1. Controls are drawn in sha256(article_id) order from the
applicable=false pool, reform-mentioning ones first (they are the near
misses that actually test the boundary), so the draw is reproducible
and unsteerable."""

import csv
import hashlib
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

csv.field_size_limit(10_000_000)
REPO = Path("/Users/sl1425/irp-sl1425")
OUT_DIR = REPO / "outputs" / "d4_validation_labelling_2026-07-29"
OUT = OUT_DIR / "D4_ReformUK_Subfields_Labelling.xlsx"

llm = json.loads((REPO / "llm_context/d4_llm_outputs.json").read_text())
sample = {r["article_id"]: r for r in csv.DictReader(
    open(REPO / "llm_context/d4_validation_sample_v1.csv"))}

N_CONTROLS = 8

applicable_true, false_mentioning, false_other = [], [], []
for r in llm["layers"]["consequence"]:
    rec = r.get("record")
    if not rec:
        continue
    aid = r["article_id"]
    if (rec.get("reform_uk") or {}).get("applicable"):
        applicable_true.append(aid)
    elif sample.get(aid, {}).get("mentions_reform") == "true":
        false_mentioning.append(aid)
    else:
        false_other.append(aid)


def hash_order(ids):
    return sorted(ids, key=lambda a: hashlib.sha256(a.encode()).hexdigest())


# Near misses first: an article that mentions Reform but which the model
# judged not materially about it is the case that actually tests the
# applicable boundary. Top up from the rest only if there aren't enough.
controls = (hash_order(false_mentioning) + hash_order(false_other))[:N_CONTROLS]
rows = sorted(applicable_true + controls,
              key=lambda a: hashlib.sha256(a.encode()).hexdigest())
print(f"{len(applicable_true)} applicable + {len(controls)} controls "
      f"= {len(rows)} rows")

ARIAL = "Arial"
F_HDR = Font(name=ARIAL, size=10, bold=True, color="FFFFFF")
F_BODY = Font(name=ARIAL, size=10)
F_TITLE = Font(name=ARIAL, size=13, bold=True)
FILL_HDR = PatternFill("solid", fgColor="1F4E79")
FILL_YELLOW = PatternFill("solid", fgColor="FFFF00")
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")

wb = Workbook()
ws = wb.active
ws.title = "读我"
ws.sheet_view.showGridLines = False
for i, w in enumerate([3, 30, 108], 1):
    ws.column_dimensions[get_column_letter(i)].width = w
ws.cell(row=1, column=2, value="Reform UK 子字段验证 — 22 篇 × 6 字段").font = F_TITLE
lines = [
    ("这是什么", "consequence 层整体没过门,但它上面搭着的 reform_uk 独立子字段块从没被验证过。这 22 篇里有的涉及 Reform UK、有的只是提到了 reform 一词——你逐篇判断,与模型对分。过门则 Reform 专属特征保留,不过则同样弃用。"),
    ("ru_applicable", "文章是否实质性地关于 Reform UK 这个政党(不是一笔带过、不是 reform 普通词义)?yes/no。选 no 时后面五列全部留空。"),
    ("ru_growth_suggested", "文章有没有暗示 Reform 支持度在增长?yes/no"),
    ("ru_credible_challenger", "文章有没有把 Reform 呈现为可信的挑战者(而非边缘小党)?yes/no"),
    ("ru_established_support_affected", "文章暗示哪些老党的支持可能被 Reform 侵蚀?从 conservative / labour / liberal_democrat 里选,逗号分隔,没有填 none"),
    ("ru_switching_directions", "文章有没有提到选民转向?从 con_to_reform / lab_to_reform / ld_to_reform 里选,逗号分隔,没有填 none"),
    ("ru_signal_nature", "信号的性质:national_momentum(全国势头) / local_campaign_strength(本地竞选实力) / protest_voting(抗议性投票) / anti_incumbent_sentiment(反在任情绪),逗号分隔,没有填 none"),
    ("红线", "只记录文章说了/暗示了什么;报道量绝不自动等于选票;拿不准 boolean 选 no(诚实保守)。预计 20 分钟。"),
]
r = 3
for label, text in lines:
    ws.cell(row=r, column=2, value=label).font = Font(name=ARIAL, size=11, bold=True)
    c = ws.cell(row=r, column=3, value=text)
    c.font = F_BODY
    c.alignment = WRAP
    r += 2

ws = wb.create_sheet("RU标注-22篇")
head = ["article_id", "election_id", "headline", "正文摘录(截1000字)", "全文路径",
        "ru_applicable", "ru_growth_suggested", "ru_credible_challenger",
        "ru_established_support_affected", "ru_switching_directions",
        "ru_signal_nature", "notes"]
for c, h in enumerate(head, 1):
    cell = ws.cell(row=1, column=c, value=h)
    cell.font = F_HDR
    cell.fill = FILL_HDR
    cell.alignment = WRAP
for i, w in enumerate([30, 13, 40, 70, 32, 13, 16, 18, 28, 26, 30, 24], 1):
    ws.column_dimensions[get_column_letter(i)].width = w

fcr = {r["article_id"]: r["headline"] for r in csv.DictReader(
    open(REPO / "news_collection/full_corpus_review.csv"))}
for i, aid in enumerate(rows, start=2):
    txt_path = REPO / "data/raw/news/text" / f"{aid}.txt"
    excerpt = txt_path.read_text(encoding="utf-8", errors="replace")[:1000]
    vals = [aid, sample[aid]["election_id"], fcr.get(aid, ""), excerpt,
            str(txt_path)] + [""] * 7
    for c, v in enumerate(vals, 1):
        cell = ws.cell(row=i, column=c, value=v)
        cell.font = F_BODY
        cell.alignment = WRAP if c in (3, 4) else TOP
    for c in range(6, 12):
        ws.cell(row=i, column=c).fill = FILL_YELLOW

n = len(rows) + 1
dv = DataValidation(type="list", formula1='"yes,no"', allow_blank=True)
ws.add_data_validation(dv)
for col in ("F", "G", "H"):
    dv.add(f"{col}2:{col}{n}")
ws.freeze_panes = "C2"

wb.active = 0
wb.save(OUT)
print(f"saved {OUT}")
