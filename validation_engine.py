"""All-period, scope-aware accounting checks; no values are altered."""
from dataclasses import dataclass
from decimal import Decimal
import re
from financial_models import (ValidationResult, StatementScope, StatementType as ST,
                              PeriodType)
from financial_inputs import (statements_for, periods_for, select_value, compatible,
                              period_key)


@dataclass
class CheckResult(ValidationResult):
    status: str = 'skipped'
    period_label: str = ''
    scope: str = ''


def balance_sheet_tolerance(assets, liabilities, equity, reported_unit_multiplier):
    """Legacy helper: three independently rounded amounts, half a unit each."""
    return 1.5 * reported_unit_multiplier


def rounding_quantum(value):
    """Reported decimal precision × monetary scale, before normalization."""
    raw = value.raw_value_str.translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    match = re.search(r'\.(\d+)', raw)
    decimals = len(match[1]) if match else 0
    return Decimal(str(value.multiplier)) * Decimal(10) ** -decimals


def _check(rule, status, detail, period=None, scope=None, sources=(), difference=None,
           relative=None, tolerance=0):
    return CheckResult(rule=rule, passed=status=='passed', absolute_difference=difference,
        relative_difference=relative, tolerance_used=float(tolerance), detail=detail,
        source_pages=sorted({v.source_page for v in sources}), status=status,
        period_label=(f'{period.year} / {period.period_type.value}'
                      + (f' / {period.end_date}' if period.end_date else '')
                      + (' / 重述' if period.is_restated else ' / 原列')) if period else '',
        scope=scope.value if scope else '')


def _balance_checks(statements, scope):
    periods = periods_for(statements, ST.BALANCE_SHEET)
    if not periods:
        return [_check('balance_sheet_equation', 'skipped', '缺少资产负债表期间数据', scope=scope)]
    results = []
    for period in periods:
        inputs = [select_value(statements, ST.BALANCE_SHEET, n, period)
                  for n in ('total_assets', 'total_liabilities', 'total_equity')]
        sources = [v for item in inputs for v in item.sources]
        reason = compatible(inputs)
        if period.period_type != PeriodType.POINT_IN_TIME:
            reason = '资产负债表不是明确的时点期间'
        if reason:
            results.append(_check('balance_sheet_equation', 'skipped', reason, period, scope, sources))
            continue
        a, l, e = [item.amount for item in inputs]
        difference = abs(a-l-e)
        # Duplicate sources are the same operand, so only count its uncertainty once.
        tolerance = sum(max(rounding_quantum(v) for v in item.sources) for item in inputs) / 2
        larger = max(abs(a), abs(l+e))
        relative = difference/larger if larger else Decimal(0)
        status = 'passed' if difference <= tolerance else 'failed'
        detail = (f'资产 {a:,.2f}；负债 {l:,.2f}；权益 {e:,.2f} {inputs[0].currency}。'
                  f'差额 {difference:,.4f}；按原文精度计算的容差 {tolerance:,.4f}。')
        results.append(_check('balance_sheet_equation', status, detail, period, scope, sources,
                              float(difference), float(relative), tolerance))
    return results


def validate_balance_sheet_equation(statement, reported_unit_multiplier=1.0):
    """Compatibility entry: latest period only; scale comes from each source value.

    The legacy multiplier argument is accepted, but cannot override provenance.
    Use run_all_validations for every period and scope.
    """
    return _balance_checks([statement], statement.scope)[0]


def run_all_validations(report, reported_unit_multiplier=1.0, scope=None):
    scopes = [scope] if scope is not None else [s for s in StatementScope if statements_for(report,s)]
    if not scopes:
        return [_check('statement_coverage', 'skipped', '未提取到任何财务报表')]
    results = []
    for current_scope in scopes:
        statements = statements_for(report, current_scope)
        for stype in ST:
            if not any(s.statement_type == stype and s.metrics for s in statements):
                results.append(_check('statement_coverage', 'skipped', f'缺少 {stype.value}', scope=current_scope))
        results.extend(_balance_checks(statements, current_scope))
        checked = set()
        for statement in statements:
            for metric in statement.metrics:
                if not metric.canonical_name: continue
                for value in metric.values:
                    key = (statement.statement_type, metric.canonical_name, period_key(value.period))
                    if key in checked: continue
                    checked.add(key)
                    # Non-monetary lines are shown in the raw table but not used in this engine.
                    if metric.canonical_name.startswith('eps_') or metric.canonical_name=='gross_margin': continue
                    item = select_value(statements, statement.statement_type, metric.canonical_name, value.period)
                    if item.reason:
                        status = 'failed' if '冲突' in item.reason or '非有限' in item.reason else 'skipped'
                        results.append(_check('input_quality',status,item.reason,value.period,current_scope,item.sources))
    return results
