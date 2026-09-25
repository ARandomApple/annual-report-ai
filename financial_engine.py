"""Deterministic metrics from same-scope financial statements; no AI calls."""
from dataclasses import dataclass, field
import math
from financial_models import StatementScope, StatementType as ST, PeriodType
from financial_inputs import (statements_for, select_value, compatible, periods_for,
                              Input)


@dataclass
class MetricResult:
    name: str
    label: str
    period: object
    scope: StatementScope
    formula: str
    value: float | None = None
    unit: str = '%'
    reason: str = ''
    sources: list = field(default_factory=list)


def compute_metrics(report, scope=StatementScope.CONSOLIDATED):
    statements = statements_for(report, scope)
    results = []

    def result(name, label, period, formula, inputs, calc, unit='%'):
        item = MetricResult(name, label, period, scope, formula, unit=unit,
                            sources=[v for i in inputs for v in i.sources])
        item.reason = compatible(inputs)
        if not item.reason:
            item.value, item.reason = calc([i.amount for i in inputs])
            if item.value is not None:
                item.value = float(item.value)
                if not math.isfinite(item.value):
                    item.value = None
                    item.reason = '计算结果超出可显示数值范围'
        results.append(item)

    def ratio(values):
        a, b = values
        if b <= 0: return None, '分母为零或负数，未计算该比率'
        return a / b * 100, ''

    for stype, rows in [
        (ST.INCOME_STATEMENT, [
            ('net_margin', '净利润率', 'net_income', 'revenue'),
            ('operating_margin', '营业利润率', 'operating_profit', 'revenue')]),
        (ST.BALANCE_SHEET, [('debt_to_assets', '资产负债率', 'total_liabilities', 'total_assets')]),
    ]:
        for period in periods_for(statements, stype):
            if stype == ST.INCOME_STATEMENT and period.period_type != PeriodType.ANNUAL: continue
            if stype == ST.BALANCE_SHEET and period.period_type != PeriodType.POINT_IN_TIME: continue
            for name, label, numerator, denominator in rows:
                inputs = [select_value(statements, stype, n, period) for n in (numerator, denominator)]
                result(name, label, period, f'{numerator} / {denominator} × 100%', inputs, ratio)

    income_periods = periods_for(statements, ST.INCOME_STATEMENT)
    for period in income_periods:
        if period.period_type != PeriodType.ANNUAL: continue
        for name, label in [('revenue', '营业收入增长率'), ('net_income', '净利润增长率')]:
            prior = [p for p in income_periods if p.year == period.year-1
                     and p.period_type == period.period_type
                     and (p.start_date or '')[4:] == (period.start_date or '')[4:]
                     and (p.end_date or '')[4:] == (period.end_date or '')[4:]]
            current = select_value(statements, ST.INCOME_STATEMENT, name, period)
            previous = (select_value(statements, ST.INCOME_STATEMENT, name, prior[0]) if len(prior)==1
                        else Input(reason='上一年度缺失或存在多个原列/重述口径，无法确定比较基期'))
            def growth(values):
                current, previous = values
                if previous <= 0: return None, '上年基数为零或负数，常规增长率不适用'
                return (current-previous)/previous*100, ''
            result(name+'_growth', label, period, '(本年值 − 上年值) / 上年值 × 100%',
                   [current, previous], growth)
        revenue = select_value(statements, ST.INCOME_STATEMENT, 'revenue', period)
        cost = select_value(statements, ST.INCOME_STATEMENT, 'cost_of_revenue', period)
        def gross(values):
            revenue, cost = values
            if revenue <= 0 or cost < 0: return None, '收入非正数或营业成本为负，需核对口径'
            return (revenue-cost)/revenue*100, ''
        gross_profit = select_value(statements, ST.INCOME_STATEMENT, 'gross_profit', period)
        if gross_profit.sources:
            result('gross_margin', '毛利率（报表毛利口径）', period,
                   'gross_profit / revenue × 100%', [gross_profit,revenue], ratio)
        else:
            result('gross_margin', '毛利率（收入减营业成本口径）', period,
                   '(revenue − cost_of_revenue) / revenue × 100%', [revenue,cost], gross)
        # Exact period identity prevents accidentally mixing fiscal dates or restatements.
        ocf = select_value(statements, ST.CASH_FLOW, 'operating_cash_flow', period)
        result('ocf_margin', '经营现金流／营业收入', period,
               'operating_cash_flow / revenue × 100%', [ocf,revenue], ratio)

    for period in periods_for(statements, ST.CASH_FLOW):
        if period.period_type != PeriodType.ANNUAL: continue
        ocf = select_value(statements, ST.CASH_FLOW, 'operating_cash_flow', period)
        capex = select_value(statements, ST.CASH_FLOW, 'capital_expenditure', period)
        currency = ocf.currency or capex.currency or '未知币种'
        result('free_cash_flow', '自由现金流（简化口径）', period,
               'operating_cash_flow − abs(capital_expenditure)', [ocf,capex],
               lambda values: (values[0]-abs(values[1]), ''), currency)
    return results


def detect_signals(financial_data, metrics):
    """Reserved for a later stage; not used by the current UI."""
    return [{'status': 'not_implemented', 'message': 'Signal detection is not implemented.'}]
