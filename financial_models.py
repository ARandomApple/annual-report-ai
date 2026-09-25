"""
financial_models.py — Core data models for the financial extraction engine.

Every extracted number carries full provenance: source page, raw label,
original value string, extraction method, confidence, detected period,
currency, and multiplier.  This is critical for later AI explainability.
"""

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ValueType(Enum):
    """Classification of a parsed numeric value."""

    MONETARY = "monetary"
    PERCENTAGE = "percentage"
    PER_SHARE = "per_share"
    RATIO = "ratio"
    COUNT = "count"
    UNKNOWN = "unknown"


class Confidence(Enum):
    """Confidence level for an extraction or resolution."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class PeriodType(Enum):
    """Type of reporting period."""

    ANNUAL = "annual"
    HALF_YEAR = "half_year"
    QUARTER = "quarter"
    POINT_IN_TIME = "point_in_time"


class StatementType(Enum):
    """Type of financial statement."""

    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"


class StatementScope(Enum):
    """Scope of a financial statement — consolidated or parent-only."""

    CONSOLIDATED = "consolidated"
    PARENT = "parent"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Value-level models
# ---------------------------------------------------------------------------


@dataclass
class ParsedNumber:
    """A numeric value parsed from financial text, independent of context.

    The *same* ``0.36`` could be EPS or a ratio — the value_type is determined
    by surface signals (%, ¥/share markers), and the final interpretation is
    resolved later by the row label.
    """

    value: float | None          # None only when the value is truly missing
    value_type: ValueType
    raw_string: str              # exactly as it appeared in the source text


@dataclass
class ReportingPeriod:
    """A reporting period for a financial value.

    Supports annual, half-year, quarterly, and point-in-time (balance-sheet)
    periods.  Restated / comparative periods are flagged via ``is_restated``.
    """

    year: int
    period_type: PeriodType
    start_date: str | None = None    # ISO-format date, e.g. "2025-01-01"
    end_date: str | None = None      # ISO-format date, e.g. "2025-12-31"
    label: str = ""                  # original text, e.g. "2025年度"
    is_restated: bool = False


@dataclass
class FinancialValue:
    """A single financial data point with full provenance."""

    parsed_number: ParsedNumber
    period: ReportingPeriod
    unit: str = ""                       # e.g. "CNY", "USD", "SGD"
    multiplier: float | None = 1.0              # e.g. 1_000_000 for "百万元"
    source_page: int = 0
    raw_label: str = ""                  # original label text from the PDF
    raw_value_str: str = ""              # original value string from the PDF
    extraction_method: str = ""          # "pymupdf_table" | "positional" | "text_fallback"
    confidence: Confidence = Confidence.UNKNOWN

    @property
    def normalized_value(self) -> float | None:
        """The value scaled to base units, or None when the scale is unknown."""
        if self.parsed_number.value is None or self.multiplier is None:
            return None
        return self.parsed_number.value * self.multiplier


# ---------------------------------------------------------------------------
# Metric-level models
# ---------------------------------------------------------------------------


@dataclass
class FinancialMetric:
    """A canonical financial metric with values across one or more periods."""

    canonical_name: str | None          # None when no canonical metric could be resolved
    original_label: str                 # the raw label from the PDF
    values: list[FinancialValue] = field(default_factory=list)
    confidence: Confidence = Confidence.UNKNOWN


# ---------------------------------------------------------------------------
# Statement-level models
# ---------------------------------------------------------------------------


@dataclass
class StatementPageRange:
    """A detected financial statement spanning one or more pages."""

    statement_type: StatementType
    anchor_page: int                    # page where the heading was found
    continuation_pages: list[int] = field(default_factory=list)
    start_page: int = 0
    end_page: int = 0
    scope: StatementScope = StatementScope.UNKNOWN
    confidence: Confidence = Confidence.UNKNOWN
    evidence: str = ""                  # human-readable reasoning


@dataclass
class Statement:
    """Extracted data for one financial statement."""

    statement_type: StatementType
    metrics: list[FinancialMetric] = field(default_factory=list)
    source_page_range: StatementPageRange | None = None
    scope: StatementScope = StatementScope.UNKNOWN
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Report-level models
# ---------------------------------------------------------------------------


@dataclass
class FinancialReport:
    """Complete structured financial report from an annual report PDF."""

    company_name: str = ""
    reporting_period: ReportingPeriod | None = None
    currency: str = ""
    unit: str = ""                       # e.g. "thousands", "millions"

    income_statement: Statement | None = None
    balance_sheet: Statement | None = None
    cash_flow_statement: Statement | None = None

    # Alternative statements (e.g. parent-only when consolidated also exists)
    alternative_statements: list[Statement] = field(default_factory=list)

    extraction_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation models
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of a single accounting validation rule."""

    rule: str                           # e.g. "balance_sheet_equation"
    passed: bool
    absolute_difference: float | None
    relative_difference: float | None   # abs_diff / max(abs(A), abs(L+E))
    tolerance_used: float
    detail: str                         # human-readable explanation
    source_pages: list[int] = field(default_factory=list)
