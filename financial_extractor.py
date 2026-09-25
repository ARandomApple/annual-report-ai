"""
financial_extractor.py — Deterministic financial data extraction pipeline.

Phase 2, Step 1: Number parsing, heading detection, scope detection,
candidate page identification, and multi-page statement range detection.

No table extraction yet. No LLM. No company-specific rules.
"""

import re
import math

from pdf_parser import PdfDocument, PdfPage
from financial_models import (
    ValueType, Confidence, PeriodType, StatementType, StatementScope,
    ParsedNumber, ReportingPeriod, FinancialValue, FinancialMetric,
    Statement, StatementPageRange, FinancialReport,
)
from metric_aliases import CANONICAL_METRICS


# ======================================================================
# 1. NUMBER PARSING — context-independent
# ======================================================================

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_FULLWIDTH_COMMA = "，"
_FULLWIDTH_PERIOD = "．"

_MISSING_PATTERN = re.compile(
    r"^\s*(—|–|-{1,3}|\.{2,}|N/?A|n/?a|\\-|$\s*)\s*$"
)

_PCT_PATTERN = re.compile(r"[%％]\s*$")

_PER_SHARE_PATTERN = re.compile(
    r"/\s*(?:股|shares?)", re.IGNORECASE
)


def parse_financial_number(raw: str) -> ParsedNumber:
    """
    Parse a financial number string into a ParsedNumber.

    Context-independent: does NOT classify a bare ``0.36`` as EPS —
    that resolution happens later based on the row label.

    Handles:
      - comma-separated numbers: ``523,924`` → 523924.0
      - decimal numbers: ``523,924.7`` → 523924.7
      - parentheses negatives: ``(1,234)`` → -1234.0
      - leading minus: ``-1,234`` → -1234.0
      - percentages: ``7.2%`` → value=7.2, type=PERCENTAGE
      - per-share markers: ``¥3.52/股`` → value=3.52, type=PER_SHARE
      - Chinese full-width digits: ``１２３`` → 123
      - missing-value markers: ``—``, ``–``, ``N/A``, ``---`` → None

    Returns:
        ParsedNumber with .value (float or None), .value_type, .raw_string.
    """
    original = raw.strip()

    # --- Missing value -------------------------------------------------------
    if not original or _MISSING_PATTERN.match(original):
        return ParsedNumber(
            value=None, value_type=ValueType.UNKNOWN, raw_string=original,
        )

    value_type = ValueType.UNKNOWN
    cleaned = original

    # Financial tables may repeat a currency glyph in selected cells.
    cleaned = re.sub(r'^[\$¥￥€£]\s*', '', cleaned)

    # --- Surface type signals ------------------------------------------------
    if _PCT_PATTERN.search(cleaned):
        value_type = ValueType.PERCENTAGE
        cleaned = _PCT_PATTERN.sub("", cleaned).strip()

    if _PER_SHARE_PATTERN.search(cleaned):
        value_type = ValueType.PER_SHARE
        # Strip currency symbols before numeric parse
        cleaned = re.sub(r"[¥￥$€£]", "", cleaned)
        cleaned = re.sub(r"元", "", cleaned)
        # Strip the per-share suffix itself
        cleaned = _PER_SHARE_PATTERN.sub("", cleaned).strip()

    # --- Normalise: full-width → ASCII ---------------------------------------
    cleaned = cleaned.translate(_FULLWIDTH_DIGITS)
    cleaned = cleaned.replace(_FULLWIDTH_COMMA, ",")
    cleaned = cleaned.replace(_FULLWIDTH_PERIOD, ".")

    # Remove thousands separators (commas and spaces between digits)
    cleaned = re.sub(r"(?<!\d\.)(?<=\d)[,\s](?=\d)", "", cleaned)

    # --- Sign detection ------------------------------------------------------
    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()
    if cleaned.startswith("-"):
        is_negative = True
        cleaned = cleaned[1:].strip()

    # --- Parse ---------------------------------------------------------------
    try:
        value = float(cleaned)
    except (ValueError, TypeError):
        return ParsedNumber(
            value=None, value_type=ValueType.UNKNOWN, raw_string=original,
        )

    if is_negative:
        value = -value
    if math.isnan(value) or math.isinf(value):
        return ParsedNumber(
            value=None, value_type=ValueType.UNKNOWN, raw_string=original,
        )

    return ParsedNumber(value=value, value_type=value_type, raw_string=original)


# ======================================================================
# 2. STATEMENT HEADING DETECTION — top-of-page only
# ======================================================================

_STATEMENT_HEADINGS: dict[StatementType, list[str]] = {
    StatementType.BALANCE_SHEET: [
        "资产负债表", "合并资产负债表", "财务状况表", "合并财务状况表",
        "概要合并财务状况表",
        "Balance Sheet", "Consolidated Balance Sheet",
        "Consolidated Balance Sheets",
        "Statement of Financial Position",
        "Consolidated Statement of Financial Position",
    ],
    StatementType.INCOME_STATEMENT: [
        "利润表", "合并利润表", "损益表", "合并损益表",
        "概要合并利润及其他综合收益表",
        "综合收益表", "合并综合收益表",
        "Income Statement", "Consolidated Income Statement",
        "Statement of Operations", "Statement of Income",
        "Consolidated Statements of Operations",
        "Statement of Profit or Loss",
        "Consolidated Statement of Profit or Loss",
        "Statement of Comprehensive Income",
        "Consolidated Statement of Comprehensive Income",
    ],
    StatementType.CASH_FLOW: [
        "现金流量表", "合并现金流量表", "概要合并现金流量表",
        "Cash Flow Statement", "Statement of Cash Flows",
        "Consolidated Statement of Cash Flows",
        "Consolidated Statements of Cash Flows",
    ],
}

# Compiled heading regexes — searched against top portion of page text only
_HEADING_REGEX: dict[StatementType, list[re.Pattern]] = {
    stype: [re.compile(re.escape(h), re.IGNORECASE) for h in headings]
    for stype, headings in _STATEMENT_HEADINGS.items()
}

# Scope detection — strong signals only
# CONSOLIDATED: 合并 or "Consolidated" + recognised statement heading phrase
_CONSOLIDATED_PATTERN = re.compile(
    r"合并"
    r"|Consolidated\s+(?:Balance\s+Sheets?|Income\s+Statements?"
    r"|Statements?\s+of\s+(?:Operations|Financial\s+Position|Cash\s+Flows"
    r"|Profit\s+or\s+Loss|Comprehensive\s+Income))",
    re.IGNORECASE,
)

# PARENT: 母公司 or "Company" + recognised statement heading phrase
_PARENT_PATTERN = re.compile(
    r"母公司(?:的)?"
    r"|Company\s+(?:Balance\s+Sheet|Income\s+Statement"
    r"|Statement\s+of\s+(?:Financial\s+Position|Cash\s+Flows"
    r"|Profit\s+or\s+Loss|Comprehensive\s+Income))",
    re.IGNORECASE,
)

# TOC / table-of-contents rejection
_TOC_INDICATORS = re.compile(
    r"(?:目\s*录|Table\s+of\s+Contents|CONTENTS|Index)",
    re.IGNORECASE,
)
_DOT_LEADER = re.compile(r"\.{4,}|\-{4,}")    # TOC dot leaders
_PAGE_REF = re.compile(r"\.+\s*\d{1,4}\s*$")  # "....... 123"

# Fraction of page text (from start) searched for statement headings.
# This is extracted-text order, NOT physical PDF coordinate order.
_TOP_FRACTION = 0.40


def _normalize(text: str) -> str:
    """Collapse whitespace to single spaces and strip."""
    return re.sub(r"\s+", " ", text).strip()


def _extract_line(text: str, offset: int) -> str:
    """Return the full line containing the given character offset."""
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end]


def _detect_scope(heading_text: str) -> StatementScope:
    """
    Detect statement scope from the heading text.

    Only strong signals are used:
      - 合并 / "Consolidated + heading phrase" → CONSOLIDATED
      - 母公司 / "Company + heading phrase"     → PARENT
      - otherwise                               → UNKNOWN
    """
    if _CONSOLIDATED_PATTERN.search(heading_text):
        return StatementScope.CONSOLIDATED
    if _PARENT_PATTERN.search(heading_text):
        return StatementScope.PARENT
    return StatementScope.UNKNOWN


def _is_structural_heading(
    line_text: str,
    match_start: int,
    match_end: int,
) -> bool:
    """
    Return True if the line is a standalone statement heading.

    A valid heading line contains essentially only:
      [optional scope prefix] [heading keyword] [optional year / continuation]

    Narrative mentions (e.g. "这些财务报表包括资产负债表") are rejected
    because substantive words remain in the prefix or suffix after cleaning.
    """
    stripped = line_text.strip()
    if not stripped:
        return False

    # --- Secondary: multiple distinct statement types on one line -> listing ---
    seen_types: set[StatementType] = set()
    for stype, patterns in _HEADING_REGEX.items():
        for pat in patterns:
            if pat.search(stripped):
                seen_types.add(stype)
    if len(seen_types) >= 2:
        return False

    # --- Secondary: narrative / reference trigger words -----------------------
    if re.search(
        r"(?:包括|详见|参见|参照"
        r"|includes?\s+the\s+"
        r"|shown?\s+in"
        r"|discussed?\s+(?:in|below|above)"
        r"|see\s+(?:Note|below|above)"
        r"|refer\s+to)",
        stripped, re.IGNORECASE,
    ):
        return False

    # --- Primary: split line at heading match ---------------------------------
    prefix = stripped[:match_start]
    suffix = stripped[match_end:]

    # Remove recognized Chinese scope qualifiers from prefix
    prefix = re.sub(r'^(?:合并|母公司(?:的)?)\s*', '', prefix)
    # Remove recognized English scope qualifiers
    prefix = re.sub(r'^(?:Consolidated|Company)\s+', '', prefix, flags=re.IGNORECASE)
    # Remove section numbers: "1.", "五、", "一.", "10."
    prefix = re.sub(r'^[一二三四五六七八九十\d]+[、．.\s]*', '', prefix)
    prefix = prefix.strip()

    # Remove harmless trailing material from suffix
    # Years
    suffix = re.sub(r'(?:20[12]\d|19\d\d)\s*(?:年|年度|财年)?', '', suffix)
    # Date ranges (e.g. "2025年12月31日")
    suffix = re.sub(r'(?:20[12]\d|19\d\d)[年/\-]\d{1,2}[月/\-]\d{1,2}[日]?',
                    '', suffix)
    # Continuation markers
    suffix = re.sub(r'[（(]\s*续\s*[）)]', '', suffix)
    suffix = re.sub(r'\bcontinued\b', '', suffix, flags=re.IGNORECASE)
    # Trailing punctuation and whitespace only
    suffix = suffix.strip(' \t\n\r、，,.。;；:：-—')

    # Both sides must be empty after cleaning
    return prefix == '' and suffix == ''


def _heading_score(page: PdfPage) -> dict:
    """
    Score a page for statement heading presence.

    Only the top ~40 % of the page's extracted text is searched.
    Earlier matches receive a higher confidence score.

    TOC / table-of-contents pages are vetoed regardless of text content.

    Returns a dict with keys:
        statement_type   — StatementType or None
        score            — float 0.0–1.0 (0.0 if no heading found)
        matched_heading  — the actual heading string matched, or None
        scope            — StatementScope (CONSOLIDATED / PARENT / UNKNOWN)
    """
    result: dict = {
        "statement_type": None,
        "score": 0.0,
        "matched_heading": None,
        "scope": StatementScope.UNKNOWN,
    }

    page_text = page.text
    top_length = max(int(len(page_text) * _TOP_FRACTION), 300)
    top_text = page_text[:top_length]

    # --- Veto: TOC indicators in the first 200 chars -------------------------
    if _TOC_INDICATORS.search(_normalize(top_text)[:200]):
        return result

    # --- Veto: heavy dot-leader / page-reference patterns --------------------
    if len(_DOT_LEADER.findall(top_text)) > 2:
        return result
    if len(_PAGE_REF.findall(top_text)) > 5:
        return result

    # A compact list of several statement titles is a local contents page,
    # even when it lacks the word "Contents" or dotted leaders.
    structural_types = set()
    for stype, patterns in _HEADING_REGEX.items():
        for line in top_text.splitlines():
            for pattern in patterns:
                match = pattern.search(line)
                if match and _is_structural_heading(line, match.start(), match.end()):
                    structural_types.add(stype)
                    break
    if len(structural_types) >= 2:
        return result

    # --- Search for heading patterns in top text -----------------------------
    best_type: StatementType | None = None
    best_heading: str | None = None        # regex match substring (reporting)
    best_line: str | None = None           # full line for scope detection
    best_offset: int = top_length          # smaller = earlier in text

    for stype, patterns in _HEADING_REGEX.items():
        for pattern in patterns:
            match = pattern.search(top_text)
            if match and match.start() < best_offset:
                heading_line = _extract_line(top_text, match.start())
                line_start = top_text.rfind("\n", 0, match.start()) + 1
                m_start = match.start() - line_start
                m_end = match.end() - line_start
                # --- Structural check: skip inline mentions -------------------
                if not _is_structural_heading(heading_line, m_start, m_end):
                    continue
                best_type = stype
                best_heading = match.group()
                best_line = heading_line
                best_offset = match.start()

    if best_type is None:
        return result

    # Score: earlier offset within top_text → higher confidence
    # Range: ~0.70 (end of top portion) to ~1.00 (very start)
    score = 1.0 - (best_offset / top_length) * 0.3
    score = round(max(0.70, min(1.0, score)), 3)

    result["statement_type"] = best_type
    result["score"] = score
    result["matched_heading"] = best_heading
    result["scope"] = _detect_scope(best_line)
    return result


# ======================================================================
# 3. CONTENT SCORING
# ======================================================================


def _content_score(page: PdfPage) -> float:
    """
    Score a page for financial content density.

    Returns float in [0, 1] based on:
      - canonical metric alias density
      - numeric value density
      - year header presence
      - unit/currency markers
      - TOC-signal penalty

    This is a quantitative signal — it does NOT detect headings.
    """
    page_text = page.text
    score = 0.0

    normalized_text = _normalize(page_text).lower()

    # --- Metric alias density ------------------------------------------------
    alias_hits = 0
    for cm in CANONICAL_METRICS:
        for alias in cm.aliases:
            if alias.normalized in normalized_text:
                alias_hits += 1
                break       # count each canonical metric at most once
    if alias_hits >= 5:    score += 0.35
    elif alias_hits >= 3:  score += 0.20
    elif alias_hits >= 1:  score += 0.10

    # --- Numeric density -----------------------------------------------------
    numbers = re.findall(r"\b\d[\d,.\s]*\d\b|\b\d\b", page_text)
    if len(numbers) >= 20:   score += 0.30
    elif len(numbers) >= 10: score += 0.20
    elif len(numbers) >= 5:  score += 0.10

    # --- Year headers --------------------------------------------------------
    year_matches = re.findall(
        r"\b(20[12]\d|19\d\d)\s*(?:年|年度|年12月31日)?\b", page_text,
    )
    if year_matches:
        score += 0.15

    # --- Unit / currency markers ---------------------------------------------
    unit_matches = re.findall(
        r"(?:人民币|美元|港元|新加坡元|RMB|CNY|USD|HKD|SGD"
        r"|千元|百万元|万元|亿元"
        r"|thousands?|millions?|billions?)",
        page_text, re.IGNORECASE,
    )
    if unit_matches:
        score += 0.10

    # --- TOC-signal penalty --------------------------------------------------
    dot_count = len(_DOT_LEADER.findall(page_text))
    page_ref_count = len(_PAGE_REF.findall(page_text))
    if dot_count > 3 or page_ref_count > 5:
        score *= 0.3

    return min(score, 1.0)


# ======================================================================
# 4. CANDIDATE PAGE IDENTIFICATION
# ======================================================================


def identify_financial_pages(
    pages: list[PdfPage],
    heading_threshold: float = 0.0,
    content_threshold: float = 0.3,
) -> list[dict]:
    """
    Identify candidate financial statement pages.

    A page is a candidate only when BOTH:
      - A statement heading is found at the top of the page
        (heading_score > heading_threshold).
      - The page has sufficient financial content
        (content_score >= content_threshold).

    This dual-threshold prevents TOC and narrative pages from being
    treated as financial statements.

    Returns a list of dicts, each with:
        page_number, statement_type, heading_score, content_score,
        matched_heading, scope, is_anchor
    """
    candidates: list[dict] = []

    for page in pages:
        h = _heading_score(page)
        c = _content_score(page)

        has_heading = h["score"] > heading_threshold
        has_content = c >= content_threshold

        if has_heading and has_content and h["statement_type"] is not None:
            candidates.append({
                "page_number": page.page_number,
                "statement_type": h["statement_type"],
                "heading_score": h["score"],
                "content_score": round(c, 3),
                "matched_heading": h["matched_heading"],
                "scope": h["scope"],
                "is_anchor": True,
            })

    return candidates


# ======================================================================
# 5. YEAR EXTRACTION (lightweight, for continuation signals)
# ======================================================================

_YEAR_PATTERN = re.compile(
    r"(?:"
    r"(?:Year\s+ended|Fiscal\s+Year|FY[E]?)\s*"
    r"(?:December\s+31|Dec\s+31|31\s+December|31\s+Dec)[,.\s]*"
    r")?"
    r"(20[12]\d|19\d\d)"
    r"(?:\s*(?:年|年度|财年))?"
)


def _detect_years_from_text(text: str) -> list[int]:
    """
    Extract unique years from text, preserving L→R order.

    Used by the continuation-signal detector to test whether a
    candidate continuation page repeats the anchor page's year columns.
    """
    seen: set[int] = set()
    years: list[int] = []
    for match in _YEAR_PATTERN.finditer(text):
        y = int(match.group(1))
        if y not in seen:
            seen.add(y)
            years.append(y)
    return years


# ======================================================================
# 6. MULTI-PAGE CONTINUATION DETECTION
# ======================================================================

_CONTINUATION_MARKERS = re.compile(
    r"(?:续|续表|Continued|\(continued\)|Cont'd)", re.IGNORECASE,
)


def _page_has_continuation_signals(
    page: PdfPage,
    anchor_statement_type: StatementType,
    detected_years: list[int] | None = None,
) -> int:
    """
    Count positive continuation signals for a candidate continuation page.

    Signals (0–5 scale):
      1 pt — Financial metric density: ≥ 3 canonical alias matches
      2 pt — Explicit continuation marker: 续, 续表, Continued, etc.
      1 pt — Repeated year columns: ≥ 2 anchor years present
      1 pt — Statement-specific vocabulary: ≥ 5 alias hits from anchor type
      1 pt — Numeric density: ≥ 10 numbers on page

    A page needs ≥ 3 points to qualify as a continuation.

    Note: "no different heading" is NOT a positive signal — it is a
    separate veto applied by the caller.
    """
    signals = 0
    page_text = page.text
    normalized_text = _normalize(page_text).lower()

    # Signal 1 — Financial metric density (1 pt) -------------------------
    alias_hits = 0
    for cm in CANONICAL_METRICS:
        for alias in cm.aliases:
            if alias.normalized in normalized_text:
                alias_hits += 1
                break
    if alias_hits >= 3:
        signals += 1

    # Signal 2 — Explicit continuation marker (2 pt) ---------------------
    if _CONTINUATION_MARKERS.search(page_text):
        signals += 2

    # Signal 3 — Repeated year columns (1 pt) ----------------------------
    if detected_years:
        year_strs = [str(y) for y in detected_years]
        found = sum(1 for ys in year_strs if ys in page_text)
        if found >= 2:
            signals += 1

    # Signal 4 — Statement-specific vocabulary (1 pt) --------------------
    specific = 0
    for cm in CANONICAL_METRICS:
        if anchor_statement_type.value in cm.statement_types:
            for alias in cm.aliases:
                if alias.normalized in normalized_text:
                    specific += 1
                    break
    if specific >= 5:
        signals += 1

    # Signal 5 — Numeric density (1 pt) ----------------------------------
    numbers = re.findall(r"\b\d[\d,.\s]*\d\b|\b\d\b", page_text)
    if len(numbers) >= 10:
        signals += 1

    return signals


def detect_statement_page_ranges(
    candidates: list[dict],
    pages: list[PdfPage],
    max_continuation_scan: int = 8,
    min_continuation_signals: int = 3,
) -> list[StatementPageRange]:
    """
    Group anchor pages with their continuation pages.

    For each anchor candidate, scans forward up to ``max_continuation_scan``
    pages.  A page is included as a continuation when:
      - It accumulates ≥ ``min_continuation_signals`` positive signals.
      - No different statement heading appears at its top (veto).
      - It is not itself an anchor page.

    Returns a list of ``StatementPageRange`` objects.
    """
    anchors = [c for c in candidates if c["is_anchor"]]
    anchors.sort(key=lambda c: c["page_number"])

    page_by_num: dict[int, PdfPage] = {p.page_number: p for p in pages}
    ranges: list[StatementPageRange] = []
    used_pages: set[int] = set()

    for anchor in anchors:
        anchor_page = anchor["page_number"]
        if anchor_page in used_pages:
            continue

        stype = anchor["statement_type"]
        scope = anchor.get("scope", StatementScope.UNKNOWN)
        continuation_pages: list[int] = []

        # Extract anchor-page years for continuation signal 3
        anchor_text = page_by_num.get(
            anchor_page, PdfPage(anchor_page, "", 0),
        ).text
        detected_years = _detect_years_from_text(anchor_text)

        for offset in range(1, max_continuation_scan + 1):
            next_page_num = anchor_page + offset
            if next_page_num not in page_by_num:
                break
            next_page = page_by_num[next_page_num]

            # --- Veto 1: next page is itself an anchor -----------------------
            if any(c["page_number"] == next_page_num and c["is_anchor"]
                   for c in candidates):
                break

            # --- Veto 2: different statement heading at top of page ----------
            next_heading = _heading_score(next_page)
            if (next_heading["statement_type"] is not None
                    and next_heading["statement_type"] != stype):
                break

            # --- Count positive signals --------------------------------------
            signals = _page_has_continuation_signals(
                next_page, stype, detected_years,
            )
            if signals >= min_continuation_signals:
                continuation_pages.append(next_page_num)
            else:
                # Stop at first page without enough signals
                break

        all_pages = [anchor_page] + continuation_pages
        start_page = min(all_pages)
        end_page = max(all_pages)
        used_pages.update(all_pages)

        # --- Build evidence string -------------------------------------------
        if continuation_pages:
            evidence = (
                f"Anchor page {anchor_page} ({stype.value}, {scope.value}); "
                f"{len(continuation_pages)} continuation page(s) "
                f"({min(continuation_pages)}–{max(continuation_pages)}); "
                f"threshold {min_continuation_signals} signals."
            )
        else:
            evidence = (
                f"Single-page statement at page {anchor_page} "
                f"({stype.value}, {scope.value})."
            )

        ranges.append(StatementPageRange(
            statement_type=stype,
            anchor_page=anchor_page,
            continuation_pages=continuation_pages,
            start_page=start_page,
            end_page=end_page,
            scope=scope,
            confidence=Confidence.MEDIUM if continuation_pages else Confidence.HIGH,
            evidence=evidence,
        ))

    return ranges
