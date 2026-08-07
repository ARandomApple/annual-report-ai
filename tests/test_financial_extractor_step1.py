"""
Tests for financial_extractor.py — Step 1.

Covers: parse_financial_number, heading detection, scope detection,
TOC rejection, body-only rejection, continuation scoring,
different-heading veto, candidate identification.

Run directly:
    PYTHONIOENCODING=utf-8 python tests/test_financial_extractor_step1.py
"""

import sys
sys.path.insert(0, ".")

passed = 0
failed = 0


def check(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} | exp={expected!r} act={actual!r}")


from pdf_parser import PdfPage
from financial_models import ValueType, StatementType, StatementScope
from financial_extractor import (
    parse_financial_number,
    _heading_score,
    identify_financial_pages,
    _page_has_continuation_signals,
    detect_statement_page_ranges,
)

# ====================================================================
# 1. NUMBER PARSING
# ====================================================================
print("--- 1. Number parsing ---")

pn = parse_financial_number("523,924")
check("1a val", (pn.value, pn.value_type.value), (523924.0, "unknown"))
check("1a raw", pn.raw_string, "523,924")

pn = parse_financial_number("523,924.7")
check("1b", (pn.value, pn.value_type.value), (523924.7, "unknown"))

pn = parse_financial_number("(1,234)")
check("1c", (pn.value, pn.raw_string), (-1234.0, "(1,234)"))

pn = parse_financial_number("-1,234")
check("1d", (pn.value, pn.raw_string), (-1234.0, "-1,234"))

pn = parse_financial_number("7.2%")
check("1e val", pn.value, 7.2)
check("1e type", pn.value_type, ValueType.PERCENTAGE)

pn = parse_financial_number("１２３,４５６")
check("1f fullwidth", pn.value, 123456.0)

pn = parse_financial_number("—")
check("1g emdash", pn.value, None)

pn = parse_financial_number("N/A")
check("1h NA", pn.value, None)

pn = parse_financial_number("")
check("1i empty", pn.value, None)

pn = parse_financial_number("---")
check("1j triple", pn.value, None)

pn = parse_financial_number("hello")
check("1l malformed", pn.value, None)

pn = parse_financial_number("1 234 567")
check("1m spaces", pn.value, 1234567.0)

# Per-share forms
p = parse_financial_number("¥3.52/股")
check("PS1 val", p.value, 3.52)
check("PS1 type", p.value_type, ValueType.PER_SHARE)

p = parse_financial_number("￥3.52/股")
check("PS2 val", p.value, 3.52)
check("PS2 type", p.value_type, ValueType.PER_SHARE)

p = parse_financial_number("3.52 元/股")
check("PS3 val", p.value, 3.52)
check("PS3 type", p.value_type, ValueType.PER_SHARE)

p = parse_financial_number("$3.52/share")
check("PS4 val", p.value, 3.52)
check("PS4 type", p.value_type, ValueType.PER_SHARE)

p = parse_financial_number("3.52/share")
check("PS5 val", p.value, 3.52)
check("PS5 type", p.value_type, ValueType.PER_SHARE)

# Negative controls
for label, s in [
    ("NC1", "hello/share"),
    ("NC2", "Revenue/share"),
    ("NC3", "元/股"),
    ("NC4", "/share"),
]:
    p = parse_financial_number(s)
    check(label, p.value, None)

# ====================================================================
# 2a. Chinese heading detection
# ====================================================================
print("--- 2a. Heading (Chinese) ---")

page_zh = PdfPage(
    page_number=10,
    text="\n中国电信股份有限公司\n"
    "合并利润表\n"
    "2025年度\n"
    "项目          2025        2024\n"
    "营业收入    523,924     461,829\n"
    "营业成本    380,000     340,000\n"
    "营业利润     43,924      41,829\n"
    "净利润       33,185      30,000\n",
    char_count=0,
)
h = _heading_score(page_zh)
check("zh: type", h["statement_type"], StatementType.INCOME_STATEMENT)
check("zh: score>0", h["score"] > 0, True)
check("zh: matched", h["matched_heading"], "合并利润表")
check("zh: scope", h["scope"], StatementScope.CONSOLIDATED)

# ====================================================================
# 2b. English heading detection
# ====================================================================
print("--- 2b. Heading (English) ---")

page_en = PdfPage(
    page_number=20,
    text="\nABCD Corporation\n"
    "Consolidated Statement of Financial Position\n"
    "As at December 31, 2025\n",
    char_count=0,
)
h = _heading_score(page_en)
check("en: type", h["statement_type"], StatementType.BALANCE_SHEET)
check("en: score>0", h["score"] > 0, True)
check("en: scope", h["scope"], StatementScope.CONSOLIDATED)

# ====================================================================
# 2c. Parent scope detection
# ====================================================================
print("--- 2c. Parent scope ---")

page_parent = PdfPage(
    page_number=30,
    text="\n某公司\n"
    "母公司利润表\n"
    "2025年度\n",
    char_count=0,
)
h = _heading_score(page_parent)
check("parent: type", h["statement_type"], StatementType.INCOME_STATEMENT)
check("parent: scope", h["scope"], StatementScope.PARENT)

# ====================================================================
# 2d. Unknown scope detection
# ====================================================================
print("--- 2d. Unknown scope ---")

page_unknown = PdfPage(
    page_number=40,
    text="\nXYZ Ltd\n"
    "Income Statement\n"
    "For the year ended December 31, 2025\n",
    char_count=0,
)
h = _heading_score(page_unknown)
check("unknown: type", h["statement_type"], StatementType.INCOME_STATEMENT)
check("unknown: scope", h["scope"], StatementScope.UNKNOWN)

# ====================================================================
# 3. TOC rejection
# ====================================================================
print("--- 3. TOC rejection ---")

page_toc = PdfPage(
    page_number=1,
    text="\n目  录\n"
    "合并利润表 ......................................... 145\n"
    "合并资产负债表 ......................................... 148\n"
    "合并现金流量表 ......................................... 152\n",
    char_count=0,
)
h = _heading_score(page_toc)
check("TOC: no type", h["statement_type"], None)
check("TOC: score", h["score"], 0.0)

# ====================================================================
# 4. Body-only heading rejection
# ====================================================================
print("--- 4. Body-only rejection ---")

page_body = PdfPage(
    page_number=50,
    text="\n审计报告\n"
    "我们审计了ABC公司的财务报表。\n"
    "这些财务报表包括资产负债表、利润表和"
    "现金流量表。\n\n"
    "第10页\n"
    "审计师签名\n",
    char_count=0,
)
h = _heading_score(page_body)
check("body-only: no type", h["statement_type"], None)
check("body-only: score", h["score"], 0.0)

# ====================================================================
# 5. Continuation scoring
# ====================================================================
print("--- 5. Continuation scoring ---")

page_cont = PdfPage(
    page_number=52,
    text="\n（续）\n"
    "项目          2025        2024\n"
    "营业收入    523,924     461,829\n"
    "营业成本    380,000     340,000\n"
    "营业利润    143,924     121,829\n"
    "销售费用     15,000      14,000\n"
    "管理费用     10,000       9,500\n"
    "研发费用     20,000      18,000\n"
    "财务费用      5,000       4,500\n"
    "投资收益      2,000       1,800\n",
    char_count=0,
)
signals = _page_has_continuation_signals(
    page_cont,
    StatementType.INCOME_STATEMENT,
    [2025, 2024],
)
check("cont: signals >= 3", signals >= 3, True)

# ====================================================================
# 6. Different-heading veto (integration)
# ====================================================================
print("--- 6. Different-heading veto ---")

pg10_text = (
    "\n合并利润表\n2025年度\n"
    "项目          2025        2024\n"
    "营业收入    523,924     461,829\n"
    "营业成本    380,000     340,000\n"
    "营业利润    143,924     121,829\n"
    "销售费用     15,000      14,000\n"
    "管理费用     10,000       9,500\n"
    "净利润       33,185      30,000\n"
)

pg11_text = (
    "\n（续）\n"
    "项目          2025        2024\n"
    "投资收益      2,000       1,800\n"
    "财务费用      5,000       4,500\n"
    "公允价值变动    500         600\n"
    "营业外收入      800         700\n"
    "营业外支出      300         250\n"
)

pg12_text = (
    "\n合并现金流量表\n2025年度\n"
    "项目          2025        2024\n"
    "经营活动现金流  124,519   110,000\n"
    "投资活动现金流  -80,000   -75,000\n"
    "筹资活动现金流  -30,000   -25,000\n"
    "现金净增加额    14,519    10,000\n"
)

pg13_text = (
    "\n项目          2025        2024\n"
    "所得税费用     8,739       7,829\n"
    "净利润        33,185      30,000\n"
    "基本每股收益     0.36       0.33\n"
    "稀释每股收益     0.36       0.33\n"
)

pages_veto = [
    PdfPage(page_number=10, text=pg10_text, char_count=0),
    PdfPage(page_number=11, text=pg11_text, char_count=0),
    PdfPage(page_number=12, text=pg12_text, char_count=0),
    PdfPage(page_number=13, text=pg13_text, char_count=0),
]

candidates_veto = identify_financial_pages(pages_veto)
ranges = detect_statement_page_ranges(candidates_veto, pages_veto)

# Filter for the income statement range specifically
income_ranges = [
    r for r in ranges
    if r.statement_type == StatementType.INCOME_STATEMENT
]
check("veto: exactly one income range", len(income_ranges), 1)

r = income_ranges[0]
check("veto: IS anchor_page", r.anchor_page, 10)
check("veto: IS continuation_pages", r.continuation_pages, [11])
check("veto: IS start_page", r.start_page, 10)
check("veto: IS end_page", r.end_page, 11)
check("veto: pg12 NOT in IS cont", 12 not in r.continuation_pages, True)
check("veto: pg13 NOT in IS cont", 13 not in r.continuation_pages, True)

# Page 12 may correctly form its own CASH_FLOW range
cf_ranges = [
    r for r in ranges
    if r.statement_type == StatementType.CASH_FLOW
]
if cf_ranges:
    cf = cf_ranges[0]
    check("veto: CF anchor is pg12", cf.anchor_page, 12)
    print(f"  Separate CASH_FLOW range: pages {cf.start_page}-{cf.end_page}")

# ====================================================================
# 7. identify_financial_pages
# ====================================================================
print("--- 7. identify_financial_pages ---")

pages_mix = [
    PdfPage(page_number=1, text="目录 ... 合并利润表 ..... 145", char_count=0),
    PdfPage(page_number=2, text="审计意见 ...", char_count=0),
    PdfPage(
        page_number=3,
        text="合并利润表\n项目 2025 2024\n"
        "营业收入 523 462\n营业成本 380 340\n"
        "营业利润 144 122\n净利润 33 30",
        char_count=0,
    ),
    PdfPage(
        page_number=4,
        text="合并资产负债表\n项目 2025 2024\n"
        "资产总计 1000 900\n负债合计 600 550\n"
        "权益合计 400 350",
        char_count=0,
    ),
]
candidates = identify_financial_pages(pages_mix)
check("identify: count", len(candidates), 2)
check("identify: cand[0] type", candidates[0]["statement_type"], StatementType.INCOME_STATEMENT)
check("identify: cand[0] page", candidates[0]["page_number"], 3)
check("identify: cand[1] type", candidates[1]["statement_type"], StatementType.BALANCE_SHEET)
check("identify: cand[1] page", candidates[1]["page_number"], 4)

# ====================================================================
# 8. REGRESSION: Scope detection with full heading context
# ====================================================================
print("--- 8. Regression: Scope + structural heading ---")

# A. 母公司利润表 → INCOME_STATEMENT + PARENT
page_a = PdfPage(page_number=100, text="母公司利润表\n2025年度\n项目 2025\n收入 100", char_count=0)
h_a = _heading_score(page_a)
check("reg A: type", h_a["statement_type"], StatementType.INCOME_STATEMENT)
check("reg A: scope", h_a["scope"], StatementScope.PARENT)

# B. 合并利润表 → INCOME_STATEMENT + CONSOLIDATED
page_b = PdfPage(page_number=101, text="合并利润表\n2025年度\n项目 2025\n收入 100", char_count=0)
h_b = _heading_score(page_b)
check("reg B: type", h_b["statement_type"], StatementType.INCOME_STATEMENT)
check("reg B: scope", h_b["scope"], StatementScope.CONSOLIDATED)

# C. Narrative listing → no heading
page_c = PdfPage(page_number=102,
    text="这些财务报表包括资产负债表、利润表和现金流量表。\n审计师签名", char_count=0)
h_c = _heading_score(page_c)
check("reg C: no heading", h_c["statement_type"], None)
check("reg C: score", h_c["score"], 0.0)

# D. Reference sentence → no heading
page_d = PdfPage(page_number=103,
    text="详见合并利润表附注。\n其他内容", char_count=0)
h_d = _heading_score(page_d)
check("reg D: no heading", h_d["statement_type"], None)
check("reg D: score", h_d["score"], 0.0)

# E. English narrative → no heading
page_e = PdfPage(page_number=104,
    text="The financial statements include the Balance Sheet and Income Statement.\nAuditor signature", char_count=0)
h_e = _heading_score(page_e)
check("reg E: no heading", h_e["statement_type"], None)
check("reg E: score", h_e["score"], 0.0)

# F. English standalone → BALANCE_SHEET + CONSOLIDATED
page_f = PdfPage(page_number=105,
    text="Consolidated Statement of Financial Position\nAs at December 31, 2025\nAssets 1000", char_count=0)
h_f = _heading_score(page_f)
check("reg F: type", h_f["statement_type"], StatementType.BALANCE_SHEET)
check("reg F: scope", h_f["scope"], StatementScope.CONSOLIDATED)

# G. 根据资产负债表 → no heading (structural suffix)
page_g = PdfPage(page_number=106,
    text="根据资产负债表我们可以发现公司资产增长明显\n其他内容", char_count=0)
h_g = _heading_score(page_g)
check("reg G: no heading", h_g["statement_type"], None)
check("reg G: score", h_g["score"], 0.0)

# H. 资产负债表显示 → no heading (structural suffix)
page_h = PdfPage(page_number=107,
    text="资产负债表显示公司的流动资产增加\n其他内容", char_count=0)
h_h = _heading_score(page_h)
check("reg H: no heading", h_h["statement_type"], None)
check("reg H: score", h_h["score"], 0.0)

# I. Income Statement with narrative suffix → no heading
page_i = PdfPage(page_number=108,
    text="Income Statement analysis shows improved profitability\nOther", char_count=0)
h_i = _heading_score(page_i)
check("reg I: no heading", h_i["statement_type"], None)
check("reg I: score", h_i["score"], 0.0)

# J. Simple 合并资产负债表 → BALANCE_SHEET + CONSOLIDATED
page_j = PdfPage(page_number=109,
    text="合并资产负债表\n项目 2025 2024\n资产 1000 900", char_count=0)
h_j = _heading_score(page_j)
check("reg J: type", h_j["statement_type"], StatementType.BALANCE_SHEET)
check("reg J: scope", h_j["scope"], StatementScope.CONSOLIDATED)

# K. Simple Income Statement → INCOME_STATEMENT + UNKNOWN
page_k = PdfPage(page_number=110,
    text="Income Statement\nYear ended December 31, 2025\nRevenue 100", char_count=0)
h_k = _heading_score(page_k)
check("reg K: type", h_k["statement_type"], StatementType.INCOME_STATEMENT)
check("reg K: scope", h_k["scope"], StatementScope.UNKNOWN)

# L. 利润表 (bare, no scope prefix) → INCOME_STATEMENT + UNKNOWN
page_l = PdfPage(page_number=111,
    text="利润表\n2025年度\n收入 100", char_count=0)
h_l = _heading_score(page_l)
check("reg L: type", h_l["statement_type"], StatementType.INCOME_STATEMENT)
check("reg L: scope", h_l["scope"], StatementScope.UNKNOWN)

# ====================================================================
print(f"\nTOTAL: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
