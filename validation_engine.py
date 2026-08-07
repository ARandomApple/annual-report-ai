"""
validation_engine.py — Deterministic accounting validations.

Validates extracted financial data using scale-aware tolerances.
Values are compared ONLY within the same ReportingPeriod.
Never modifies extracted numbers — it detects problems, not hides them.
"""

from financial_models import (
    Confidence,
    FinancialReport,
    FinancialValue,
    ReportingPeriod,
    Statement,
    StatementType,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Scale-aware tolerance
# ---------------------------------------------------------------------------


def balance_sheet_tolerance(
    assets: float,
    liabilities: float,
    equity: float,
    reported_unit_multiplier: float,
) -> float:
    """
    Compute a scale-aware tolerance for the balance-sheet equation.

    Uses the larger of:
      - Half the smallest reported unit (rounding tolerance)
      - 0.1 % of the larger side (relative tolerance)

    Args:
        assets: Total assets (normalized to base units).
        liabilities: Total liabilities (normalized to base units).
        equity: Total equity (normalized to base units).
        reported_unit_multiplier: The multiplier that converts one reported
            unit to base currency (e.g. 1_000_000 for "百万元").

    Returns:
        The maximum acceptable absolute difference.
    """
    rounding_tolerance = reported_unit_multiplier * 0.5
    larger_side = max(abs(assets), abs(liabilities + equity))
    relative_tolerance = larger_side * 0.001  # 0.1 %
    return max(rounding_tolerance, relative_tolerance)


# ---------------------------------------------------------------------------
# Period-aware value selection
# ---------------------------------------------------------------------------


def _period_key(period: ReportingPeriod) -> tuple:
    """Return a sortable key that uniquely identifies a reporting period."""
    return (period.year, period.period_type.value, period.end_date or "")


def _find_common_periods(
    assets_values: list[FinancialValue],
    liabilities_values: list[FinancialValue],
    equity_values: list[FinancialValue],
) -> list[tuple[ReportingPeriod, FinancialValue, FinancialValue, FinancialValue]]:
    """
    Find periods for which all three balance-sheet metrics exist.

    Returns a list of (period, assets_fv, liabilities_fv, equity_fv) tuples,
    sorted from best (most-recent year, best confidence) to worst.
    """
    # Group each metric's values by period key
    by_period: dict[tuple, dict[str, FinancialValue]] = {}

    for fv in assets_values:
        if fv.parsed_number.value is not None:
            k = _period_key(fv.period)
            by_period.setdefault(k, {})["assets"] = fv

    for fv in liabilities_values:
        if fv.parsed_number.value is not None:
            k = _period_key(fv.period)
            by_period.setdefault(k, {})["liabilities"] = fv

    for fv in equity_values:
        if fv.parsed_number.value is not None:
            k = _period_key(fv.period)
            by_period.setdefault(k, {})["equity"] = fv

    # Keep only periods that have all three
    common: list[tuple[ReportingPeriod, FinancialValue, FinancialValue, FinancialValue]] = []
    for k, groups in by_period.items():
        if "assets" in groups and "liabilities" in groups and "equity" in groups:
            fv_a = groups["assets"]
            fv_l = groups["liabilities"]
            fv_e = groups["equity"]
            common.append((fv_a.period, fv_a, fv_l, fv_e))

    # Sort: most-recent year first, then best worst-case confidence
    def _sort_key(tup):
        period, fv_a, fv_l, fv_e = tup
        conf_order = {
            Confidence.HIGH: 0,
            Confidence.MEDIUM: 1,
            Confidence.LOW: 2,
            Confidence.UNKNOWN: 3,
        }
        worst_conf = max(
            conf_order.get(fv_a.confidence, 3),
            conf_order.get(fv_l.confidence, 3),
            conf_order.get(fv_e.confidence, 3),
        )
        return (-period.year, worst_conf)

    common.sort(key=_sort_key)
    return common


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------


def validate_balance_sheet_equation(
    statement: Statement,
    reported_unit_multiplier: float = 1.0,
) -> ValidationResult | None:
    """
    Check: Total Assets ≈ Total Liabilities + Total Equity.

    Only validates values belonging to the SAME ReportingPeriod.
    Selects the most-recent common period that has all three metrics.

    Args:
        statement: The extracted balance sheet Statement.
        reported_unit_multiplier: Unit multiplier for the balance sheet.

    Returns:
        ValidationResult, or None if required metrics are missing.
    """
    # Collect all values for the three required metrics
    assets_values: list[FinancialValue] = []
    liabilities_values: list[FinancialValue] = []
    equity_values: list[FinancialValue] = []

    for metric in statement.metrics:
        if metric.canonical_name == "total_assets":
            assets_values.extend(metric.values)
        elif metric.canonical_name == "total_liabilities":
            liabilities_values.extend(metric.values)
        elif metric.canonical_name == "total_equity":
            equity_values.extend(metric.values)

    if not assets_values:
        return ValidationResult(
            rule="balance_sheet_equation",
            passed=False, absolute_difference=None, relative_difference=None,
            tolerance_used=0.0,
            detail="Missing: total_assets not found in balance sheet.",
        )
    if not liabilities_values:
        return ValidationResult(
            rule="balance_sheet_equation",
            passed=False, absolute_difference=None, relative_difference=None,
            tolerance_used=0.0,
            detail="Missing: total_liabilities not found in balance sheet.",
        )
    if not equity_values:
        return ValidationResult(
            rule="balance_sheet_equation",
            passed=False, absolute_difference=None, relative_difference=None,
            tolerance_used=0.0,
            detail="Missing: total_equity not found in balance sheet.",
        )

    # Find the best common period
    common = _find_common_periods(assets_values, liabilities_values, equity_values)

    if not common:
        return ValidationResult(
            rule="balance_sheet_equation",
            passed=False, absolute_difference=None, relative_difference=None,
            tolerance_used=0.0,
            detail=(
                "Required metrics (total_assets, total_liabilities, total_equity) "
                "were found but no common ReportingPeriod exists — they belong to "
                "different periods and cannot be compared."
            ),
        )

    # Use the best common period
    period, fv_a, fv_l, fv_e = common[0]

    a = fv_a.normalized_value
    l = fv_l.normalized_value
    e = fv_e.normalized_value

    # mypy: we filtered out None values in _find_common_periods
    assert a is not None and l is not None and e is not None

    diff = a - (l + e)
    abs_diff = abs(diff)
    tol = balance_sheet_tolerance(a, l, e, reported_unit_multiplier)
    larger = max(abs(a), abs(l + e))
    rel_diff = abs_diff / larger if larger != 0 else 0.0
    passed = abs_diff <= tol

    pages = list({fv_a.source_page, fv_l.source_page, fv_e.source_page})

    if passed:
        detail = (
            f"Period: {period.label or period.year}. "
            f"Assets ({a:,.2f}) ≈ Liabilities ({l:,.2f}) + Equity ({e:,.2f}) "
            f"= {l+e:,.2f}. Diff = {abs_diff:,.2f}, tolerance = {tol:,.2f} "
            f"(rel = {rel_diff:.6f}). PASS."
        )
    else:
        detail = (
            f"Period: {period.label or period.year}. "
            f"Assets ({a:,.2f}) vs Liabilities ({l:,.2f}) + Equity ({e:,.2f}) "
            f"= {l+e:,.2f}. Diff = {abs_diff:,.2f} exceeds tolerance {tol:,.2f} "
            f"(rel = {rel_diff:.6f}). FAIL."
        )

    return ValidationResult(
        rule="balance_sheet_equation",
        passed=passed,
        absolute_difference=round(abs_diff, 2),
        relative_difference=round(rel_diff, 6),
        tolerance_used=round(tol, 2),
        detail=detail,
        source_pages=pages,
    )


# ---------------------------------------------------------------------------
# Run-all entry point
# ---------------------------------------------------------------------------


def run_all_validations(
    report: FinancialReport,
    reported_unit_multiplier: float = 1.0,
) -> list[ValidationResult]:
    """
    Run all applicable accounting validations on a FinancialReport.

    Args:
        report: The extracted FinancialReport.
        reported_unit_multiplier: Unit multiplier (e.g. 1_000_000 for millions).

    Returns:
        List of ValidationResult objects.
    """
    results: list[ValidationResult] = []

    if report.balance_sheet is not None:
        bs_result = validate_balance_sheet_equation(
            report.balance_sheet, reported_unit_multiplier
        )
        if bs_result is not None:
            results.append(bs_result)

    return results
