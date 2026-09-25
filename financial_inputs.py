"""Conservative selection of compatible, auditable financial inputs."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from financial_models import StatementScope, ValueType


def money_unit(currency, scale='亿'):
    names = {'CNY': '元', 'USD': '美元', 'HKD': '港元',
             'SGD': '新加坡元', 'EUR': '欧元'}
    name = names.get(currency, currency or '元')
    return scale + name


def period_key(period):
    return (period.year, period.period_type.value, period.start_date or '',
            period.end_date or '', period.is_restated)


def statements_for(report, scope):
    return [s for s in (report.balance_sheet, report.income_statement,
                       report.cash_flow_statement, *report.alternative_statements)
            if s is not None and s.scope == scope]


def normalized(value):
    if value.parsed_number.value is None or value.multiplier is None:
        return None
    try:
        amount = Decimal(str(value.parsed_number.value)) * Decimal(str(value.multiplier))
        return amount if amount.is_finite() else None
    except InvalidOperation:
        return None


@dataclass
class Input:
    amount: Decimal | None = None
    currency: str = ''
    sources: list = field(default_factory=list)
    reason: str = ''


def select_value(statements, statement_type, name, period):
    candidates = [v for s in statements if s.statement_type == statement_type
                  for m in s.metrics if m.canonical_name == name
                  for v in m.values if period_key(v.period) == period_key(period)]
    if not candidates:
        return Input(reason=f'缺少 {name}（{period.year}）')
    if any(s.scope == StatementScope.UNKNOWN for s in statements):
        return Input(sources=candidates, reason='报表口径未识别')
    if any(not v.unit or v.multiplier is None or v.multiplier <= 0 for v in candidates):
        return Input(sources=candidates, reason=f'{name} 的币种或单位不明')
    if any(v.parsed_number.value is None for v in candidates):
        return Input(sources=candidates, reason=f'{name} 有缺失值，需核对')
    if any(v.parsed_number.value_type != ValueType.MONETARY for v in candidates):
        return Input(sources=candidates, reason=f'{name} 不是已识别的金额类型')
    amounts = {normalized(v) for v in candidates}
    currencies = {v.unit for v in candidates}
    if None in amounts:
        return Input(sources=candidates, reason=f'{name} 包含非有限数值')
    if len(amounts) != 1 or len(currencies) != 1:
        return Input(sources=candidates, reason=f'{name} 存在冲突的重复值或币种')
    return Input(next(iter(amounts)), next(iter(currencies)), candidates)


def compatible(inputs):
    reasons = list(dict.fromkeys(i.reason for i in inputs if i.reason))
    if reasons:
        return '；'.join(reasons)
    if len({i.currency for i in inputs}) != 1:
        return '输入币种不一致，未做汇率转换'
    return ''


def periods_for(statements, statement_type):
    periods = {}
    for s in statements:
        if s.statement_type == statement_type:
            for m in s.metrics:
                for value in m.values:
                    periods[period_key(value.period)] = value.period
    return [periods[k] for k in sorted(periods, reverse=True)]
