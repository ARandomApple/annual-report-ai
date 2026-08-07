"""
metric_aliases.py — Canonical financial metric dictionary with bilingual aliases.

Each canonical metric carries a list of Chinese and English aliases.
Resolution uses a three-tier precedence strategy:

  Tier 1 — Exact normalized-label match                         → HIGH confidence
  Tier 2 — Longest-alias substring match (unambiguous)          → MEDIUM confidence
  Tier 3 — Conservative regex fallback                          → LOW confidence
  No match                                                      → UNKNOWN confidence

Ambiguous Tier-2 matches (two aliases of equal length) remain unresolved.
"""

import re
from dataclasses import dataclass, field
from typing import ClassVar

from financial_models import Confidence


# ---------------------------------------------------------------------------
# Single alias entry
# ---------------------------------------------------------------------------


@dataclass
class MetricAlias:
    """One alias belonging to a canonical metric."""

    pattern: str           # human-readable form for Tier 1 & 2 matching
    normalized: str        # whitespace-collapsed, lowercased for comparison
    length: int            # character length of normalized form
    regex: re.Pattern | None = None  # optional compiled regex for Tier 3 fallback

    @classmethod
    def from_pattern(cls, pattern: str, regex: re.Pattern | None = None) -> "MetricAlias":
        """Create a MetricAlias, computing normalized form and length."""
        normalized = re.sub(r"\s+", "", pattern).lower()
        return cls(
            pattern=pattern,
            normalized=normalized,
            length=len(normalized),
            regex=regex,
        )


# ---------------------------------------------------------------------------
# Canonical metric definition
# ---------------------------------------------------------------------------


@dataclass
class CanonicalMetric:
    """One canonical financial metric with all its aliases."""

    name: str
    aliases: list[MetricAlias] = field(default_factory=list)
    statement_types: list[str] = field(default_factory=list)
    # ^ "income_statement", "balance_sheet", "cash_flow"


# ---------------------------------------------------------------------------
# Helper — build the normalized input
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Collapse whitespace and lower-case for comparison."""
    return re.sub(r"\s+", "", text).lower()


# ---------------------------------------------------------------------------
# Three-tier resolution
# ---------------------------------------------------------------------------


def resolve_metric(
    raw_label: str,
    metrics: list[CanonicalMetric],
) -> tuple[str | None, Confidence, str]:
    """
    Resolve a raw financial label to a canonical metric name.

    Args:
        raw_label: The label text extracted from the PDF (e.g. "营业收入").
        metrics: The list of all canonical metrics with their aliases.

    Returns:
        (canonical_name, confidence, detail) tuple.
        canonical_name is None when no match could be made.
        detail is a human-readable string explaining the resolution.
    """
    if not raw_label or not raw_label.strip():
        return (None, Confidence.UNKNOWN, "empty label")

    normalized_input = _normalize(raw_label)

    # -- Tier 1: exact normalized match ------------------------------------
    exact_matches: list[CanonicalMetric] = []
    for metric in metrics:
        for alias in metric.aliases:
            if alias.normalized == normalized_input:
                exact_matches.append(metric)
                break  # one match per metric is enough

    if len(exact_matches) == 1:
        m = exact_matches[0]
        return (m.name, Confidence.HIGH, f"Tier 1 exact match → {m.name}")
    elif len(exact_matches) > 1:
        names = ", ".join(m.name for m in exact_matches)
        return (None, Confidence.LOW, f"Tier 1 ambiguous: matched {names}")

    # -- Tier 2: longest-alias substring match -----------------------------
    # Collect (metric, alias, match_length) for every alias that is a
    # substring of the normalized input.
    tier2_candidates: list[tuple[CanonicalMetric, MetricAlias, int]] = []
    for metric in metrics:
        for alias in metric.aliases:
            if alias.normalized in normalized_input:
                tier2_candidates.append((metric, alias, alias.length))

    if tier2_candidates:
        # Sort by match length descending
        tier2_candidates.sort(key=lambda x: x[2], reverse=True)
        best_length = tier2_candidates[0][2]

        # Check for ties at the best length
        best = [(m, a) for m, a, l in tier2_candidates if l == best_length]

        if len(best) == 1:
            m, a = best[0]
            return (m.name, Confidence.MEDIUM,
                    f"Tier 2 longest match → {m.name} via '{a.pattern}' (len={best_length})")
        else:
            names = ", ".join(m.name for m, _ in best)
            return (None, Confidence.LOW,
                    f"Tier 2 ambiguous: equal-length matches for {names} (len={best_length})")

    # -- Tier 3: regex fallback --------------------------------------------
    tier3_candidates: list[tuple[CanonicalMetric, MetricAlias]] = []
    for metric in metrics:
        for alias in metric.aliases:
            if alias.regex is not None and alias.regex.search(raw_label):
                tier3_candidates.append((metric, alias))

    if len(tier3_candidates) == 1:
        m, a = tier3_candidates[0]
        return (m.name, Confidence.LOW,
                f"Tier 3 regex match → {m.name} via '{a.pattern}'")
    elif len(tier3_candidates) > 1:
        names = ", ".join(m.name for m, _ in tier3_candidates)
        return (None, Confidence.LOW,
                f"Tier 3 ambiguous: regex matched {names}")

    return (None, Confidence.UNKNOWN, "no match in any tier")


# ---------------------------------------------------------------------------
# The canonical metric dictionary
# ---------------------------------------------------------------------------


def build_canonical_metrics() -> list[CanonicalMetric]:
    """
    Build and return the full canonical metric dictionary.

    Returns:
        List of CanonicalMetric objects covering income statement,
        balance sheet, and cash flow statement line items.
    """
    return [
        # ==================================================================
        # Income Statement
        # ==================================================================
        CanonicalMetric(
            name="revenue",
            statement_types=["income_statement"],
            aliases=[
                MetricAlias.from_pattern("营业收入"),
                MetricAlias.from_pattern("营业总收入"),
                MetricAlias.from_pattern("营收"),
                MetricAlias.from_pattern("经营收入"),
                MetricAlias.from_pattern("收入"),
                MetricAlias.from_pattern("Revenue"),
                MetricAlias.from_pattern("Operating Revenue"),
                MetricAlias.from_pattern("Total Revenue"),
                MetricAlias.from_pattern("Sales"),
                MetricAlias.from_pattern("Net Sales"),
                MetricAlias.from_pattern("Turnover"),
                MetricAlias.from_pattern("Revenues"),
                MetricAlias.from_pattern("Operating Revenues"),
                # Tier 3 regex — 收入 preceded by 营业/经营/销售,
                # NOT followed by 成本/税金
                MetricAlias.from_pattern(
                    "营业(总)?收入",
                    regex=re.compile(
                        r"(?:营业\s*(?:总)?\s*收入|经营\s*收入|销售\s*收入)"
                        r"(?!\s*成本|\s*税金)"
                    ),
                ),
            ],
        ),
        CanonicalMetric(
            name="cost_of_revenue",
            statement_types=["income_statement"],
            aliases=[
                MetricAlias.from_pattern("营业成本"),
                MetricAlias.from_pattern("Cost of Revenue"),
                MetricAlias.from_pattern("Cost of Sales"),
                MetricAlias.from_pattern("Cost of Goods Sold"),
            ],
        ),
        CanonicalMetric(
            name="gross_profit",
            statement_types=["income_statement"],
            aliases=[
                MetricAlias.from_pattern("毛利"),
                MetricAlias.from_pattern("毛利润"),
                MetricAlias.from_pattern("Gross Profit"),
            ],
        ),
        CanonicalMetric(
            name="gross_margin",
            statement_types=["income_statement"],
            aliases=[
                MetricAlias.from_pattern("毛利率"),
                MetricAlias.from_pattern("Gross Margin"),
                MetricAlias.from_pattern("Gross Profit Margin"),
            ],
        ),
        CanonicalMetric(
            name="operating_profit",
            statement_types=["income_statement"],
            aliases=[
                MetricAlias.from_pattern("营业利润"),
                MetricAlias.from_pattern("Operating Profit"),
                MetricAlias.from_pattern("Operating Income"),
                MetricAlias.from_pattern("Income from Operations"),
            ],
        ),
        CanonicalMetric(
            name="profit_before_tax",
            statement_types=["income_statement"],
            aliases=[
                MetricAlias.from_pattern("利润总额"),
                MetricAlias.from_pattern("税前利润"),
                MetricAlias.from_pattern("Profit Before Tax"),
                MetricAlias.from_pattern("Income Before Tax"),
                MetricAlias.from_pattern("Profit before taxation"),
            ],
        ),
        CanonicalMetric(
            name="net_income",
            statement_types=["income_statement"],
            aliases=[
                MetricAlias.from_pattern("净利润"),
                MetricAlias.from_pattern("Net Income"),
                MetricAlias.from_pattern("Net Profit"),
                MetricAlias.from_pattern("Net Earnings"),
            ],
        ),
        CanonicalMetric(
            name="net_income_attributable_to_parent",
            statement_types=["income_statement"],
            aliases=[
                MetricAlias.from_pattern("归属于母公司股东的净利润"),
                MetricAlias.from_pattern("归属于母公司所有者的净利润"),
                MetricAlias.from_pattern("归属于上市公司股东的净利润"),
                MetricAlias.from_pattern("归属母公司股东净利润"),
                MetricAlias.from_pattern(
                    "Net income attributable to shareholders of the parent"
                ),
                MetricAlias.from_pattern(
                    "Net income attributable to owners of the parent"
                ),
                MetricAlias.from_pattern(
                    "Net income attributable to equity holders"
                ),
                MetricAlias.from_pattern("Profit attributable to shareholders"),
                # Tier 3 regex: 归属 + 母/上市/控股 + 净利润
                MetricAlias.from_pattern(
                    "归属于母公司净利润",
                    regex=re.compile(
                        r"归属.*?(?:母公[司]?|上市公[司]?|控股).*?净利润"
                        r"|Net\s+income\s+attributable\s+to\s+"
                        r"(?:shareholders|owners|parent|equity\s+holders)",
                        re.IGNORECASE,
                    ),
                ),
            ],
        ),
        CanonicalMetric(
            name="eps_basic",
            statement_types=["income_statement"],
            aliases=[
                MetricAlias.from_pattern("基本每股收益"),
                MetricAlias.from_pattern("每股收益"),
                MetricAlias.from_pattern("Basic Earnings Per Share"),
                MetricAlias.from_pattern("Basic EPS"),
                MetricAlias.from_pattern("Earnings Per Share"),
            ],
        ),
        CanonicalMetric(
            name="eps_diluted",
            statement_types=["income_statement"],
            aliases=[
                MetricAlias.from_pattern("稀释每股收益"),
                MetricAlias.from_pattern("Diluted Earnings Per Share"),
                MetricAlias.from_pattern("Diluted EPS"),
            ],
        ),

        # ==================================================================
        # Balance Sheet
        # ==================================================================
        CanonicalMetric(
            name="total_assets",
            statement_types=["balance_sheet"],
            aliases=[
                MetricAlias.from_pattern("资产总计"),
                MetricAlias.from_pattern("总资产"),
                MetricAlias.from_pattern("Total Assets"),
                MetricAlias.from_pattern("Total assets"),
            ],
        ),
        CanonicalMetric(
            name="total_liabilities",
            statement_types=["balance_sheet"],
            aliases=[
                MetricAlias.from_pattern("负债合计"),
                MetricAlias.from_pattern("总负债"),
                MetricAlias.from_pattern("Total Liabilities"),
                MetricAlias.from_pattern("Total liabilities"),
            ],
        ),
        CanonicalMetric(
            name="total_equity",
            statement_types=["balance_sheet"],
            aliases=[
                MetricAlias.from_pattern("股东权益合计"),
                MetricAlias.from_pattern("所有者权益合计"),
                MetricAlias.from_pattern("权益合计"),
                MetricAlias.from_pattern("归属母公司股东权益合计"),
                MetricAlias.from_pattern("Total Equity"),
                MetricAlias.from_pattern("Total equity"),
                MetricAlias.from_pattern("Shareholders' Equity"),
                MetricAlias.from_pattern("Stockholders' Equity"),
                MetricAlias.from_pattern("Total shareholders' equity"),
            ],
        ),
        CanonicalMetric(
            name="cash_and_cash_equivalents",
            statement_types=["balance_sheet"],
            aliases=[
                MetricAlias.from_pattern("货币资金"),
                MetricAlias.from_pattern("现金及现金等价物"),
                MetricAlias.from_pattern("Cash and Cash Equivalents"),
                MetricAlias.from_pattern("Cash and cash equivalents"),
                MetricAlias.from_pattern("Cash & Cash Equivalents"),
            ],
        ),
        CanonicalMetric(
            name="accounts_receivable",
            statement_types=["balance_sheet"],
            aliases=[
                MetricAlias.from_pattern("应收账款"),
                MetricAlias.from_pattern("应收款项"),
                MetricAlias.from_pattern("Accounts Receivable"),
                MetricAlias.from_pattern("Trade Receivables"),
                MetricAlias.from_pattern("Trade and Other Receivables"),
            ],
        ),
        CanonicalMetric(
            name="inventory",
            statement_types=["balance_sheet"],
            aliases=[
                MetricAlias.from_pattern("存货"),
                MetricAlias.from_pattern("库存"),
                MetricAlias.from_pattern("Inventory"),
                MetricAlias.from_pattern("Inventories"),
            ],
        ),
        CanonicalMetric(
            name="short_term_debt",
            statement_types=["balance_sheet"],
            aliases=[
                MetricAlias.from_pattern("短期借款"),
                MetricAlias.from_pattern("短期债务"),
                MetricAlias.from_pattern("Short-term Debt"),
                MetricAlias.from_pattern("Short-term Borrowings"),
                MetricAlias.from_pattern("Current Debt"),
            ],
        ),
        CanonicalMetric(
            name="long_term_debt",
            statement_types=["balance_sheet"],
            aliases=[
                MetricAlias.from_pattern("长期借款"),
                MetricAlias.from_pattern("长期债务"),
                MetricAlias.from_pattern("Long-term Debt"),
                MetricAlias.from_pattern("Long-term Borrowings"),
                MetricAlias.from_pattern("Non-current Debt"),
            ],
        ),

        # ==================================================================
        # Cash Flow Statement
        # ==================================================================
        CanonicalMetric(
            name="operating_cash_flow",
            statement_types=["cash_flow"],
            aliases=[
                MetricAlias.from_pattern("经营活动产生的现金流量净额"),
                MetricAlias.from_pattern("经营活动现金流量净额"),
                MetricAlias.from_pattern("经营活动现金流净额"),
                MetricAlias.from_pattern("Net cash flows from operating activities"),
                MetricAlias.from_pattern("Net cash provided by operating activities"),
                MetricAlias.from_pattern("Net cash generated from operating activities"),
                MetricAlias.from_pattern("Operating cash flow"),
                MetricAlias.from_pattern("Cash flows from operating activities"),
            ],
        ),
        CanonicalMetric(
            name="investing_cash_flow",
            statement_types=["cash_flow"],
            aliases=[
                MetricAlias.from_pattern("投资活动产生的现金流量净额"),
                MetricAlias.from_pattern("投资活动现金流量净额"),
                MetricAlias.from_pattern("Net cash flows from investing activities"),
                MetricAlias.from_pattern("Net cash used in investing activities"),
                MetricAlias.from_pattern("Cash flows from investing activities"),
            ],
        ),
        CanonicalMetric(
            name="financing_cash_flow",
            statement_types=["cash_flow"],
            aliases=[
                MetricAlias.from_pattern("筹资活动产生的现金流量净额"),
                MetricAlias.from_pattern("融资活动产生的现金流量净额"),
                MetricAlias.from_pattern("Net cash flows from financing activities"),
                MetricAlias.from_pattern("Net cash used in financing activities"),
                MetricAlias.from_pattern("Cash flows from financing activities"),
            ],
        ),
        CanonicalMetric(
            name="capital_expenditure",
            statement_types=["cash_flow"],
            aliases=[
                MetricAlias.from_pattern("资本支出"),
                MetricAlias.from_pattern("资本性支出"),
                MetricAlias.from_pattern("购建固定资产、无形资产和其他长期资产支付的现金"),
                MetricAlias.from_pattern("Capital Expenditure"),
                MetricAlias.from_pattern("Capital Expenditures"),
                MetricAlias.from_pattern("CapEx"),
                MetricAlias.from_pattern("Purchase of property, plant and equipment"),
                MetricAlias.from_pattern("Purchases of PP&E"),
            ],
        ),
        CanonicalMetric(
            name="free_cash_flow",
            statement_types=["cash_flow"],
            aliases=[
                MetricAlias.from_pattern("自由现金流"),
                MetricAlias.from_pattern("Free Cash Flow"),
                MetricAlias.from_pattern("FCF"),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

# Pre-built list — import this directly
CANONICAL_METRICS: list[CanonicalMetric] = build_canonical_metrics()

# Lookup dict: canonical_name → CanonicalMetric
METRIC_BY_NAME: dict[str, CanonicalMetric] = {
    m.name: m for m in CANONICAL_METRICS
}
