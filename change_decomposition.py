"""Conservative revenue/cost bridge for the change in gross profit."""
from decimal import Decimal

from financial_models import PeriodType, StatementType as ST, ValueType
from financial_inputs import (Input, compatible, money_unit, normalized, period_key, periods_for,
                              select_value, statements_for)


def revenue_segment_bridge(report, scope):
    """Use source rows as revenue segments only when both years sum to the total."""
    statements = statements_for(report, scope)
    periods = [p for p in periods_for(statements, ST.INCOME_STATEMENT)
               if p.period_type == PeriodType.ANNUAL]
    if not periods:
        return None, '未识别到年度利润表。'
    latest = max(p.year for p in periods)
    pair = [[p for p in periods if p.year == year] for year in (latest-1, latest)]
    if any(len(group) != 1 for group in pair):
        return None, '缺少相邻两年的唯一收入列。'
    prior, current = pair[0][0], pair[1][0]
    if ((prior.start_date or '')[4:], (prior.end_date or '')[4:]) != ((current.start_date or '')[4:], (current.end_date or '')[4:]):
        return None, '两年的会计期间不同。'
    totals = [select_value(statements, ST.INCOME_STATEMENT, 'revenue', p)
              for p in (prior, current)]
    if compatible(totals):
        return None, '营业收入缺失或存在冲突。'
    source_pages = {v.source_page for item in totals for v in item.sources}
    if len(source_pages) != 1:
        return None, '收入明细与合计未位于同一可靠表格。'
    source_page = next(iter(source_pages))
    for statement in statements:
        if statement.statement_type != ST.INCOME_STATEMENT:
            continue
        for index, total_metric in enumerate(statement.metrics):
            if total_metric.canonical_name != 'revenue':
                continue
            segment_metrics = []
            for metric in reversed(statement.metrics[max(0,index-8):index]):
                if metric.canonical_name is not None:
                    break
                segment_metrics.insert(0, metric)
            if not 2 <= len(segment_metrics) <= 6:
                continue
            if len({m.original_label.strip() for m in segment_metrics}) != len(segment_metrics):
                continue
            segments = []
            for metric in segment_metrics:
                values = []
                for period in (prior, current):
                    candidates = [v for v in metric.values if period_key(v.period)==period_key(period)]
                    if len(candidates)!=1:
                        break
                    value = candidates[0]
                    amount = normalized(value)
                    if (amount is None or amount < 0 or value.parsed_number.value_type != ValueType.MONETARY
                            or value.source_page != source_page):
                        break
                    values.append(Input(amount, value.unit, [value]))
                if len(values)!=2:
                    break
                segments.append((metric.original_label.strip(), values))
            if len(segments)!=len(segment_metrics):
                continue
            if compatible(totals + [v for _,values in segments for v in values]):
                continue
            # Exact source-unit reconciliation prevents coincidental expense rows
            # from being presented as business segments.
            if any(sum(values[i].amount for _,values in segments) != totals[i].amount for i in (0,1)):
                continue
            effects=[values[1].amount-values[0].amount for _,values in segments]
            if totals[0].amount+sum(effects)!=totals[1].amount:
                continue
            magnitude=max(abs(totals[0].amount),abs(totals[1].amount),*(abs(x) for x in effects))
            if magnitude>=Decimal(1_000_000):divisor,unit=Decimal(100_000_000),money_unit(totals[0].currency,'亿')
            elif magnitude>=Decimal(10_000):divisor,unit=Decimal(10_000),money_unit(totals[0].currency,'万')
            else:divisor,unit=Decimal(1),money_unit(totals[0].currency,'')
            return {
                'kind':'revenue_segments', 'years':(prior.year,current.year),
                'currency':totals[0].currency, 'unit':unit,
                'start':float(totals[0].amount/divisor),
                'end':float(totals[1].amount/divisor),
                'parts':[(label,float(effect/divisor)) for (label,_),effect in zip(segments,effects)],
                'pages':{prior.year:[source_page],current.year:[source_page]},
                'provisional_ocr':any(v.extraction_method=='local_ocr'
                    for item in totals for v in item.sources),
                'restated_previous':prior.is_restated,
            },''
    return None,'未找到同时列示两年、且明细之和能核对到营业收入的业务分部表。'


def gross_profit_bridge(report, scope):
    """Return a checked bridge, or a short reason why it cannot be drawn."""
    statements = statements_for(report, scope)
    periods = [p for p in periods_for(statements, ST.INCOME_STATEMENT)
               if p.period_type == PeriodType.ANNUAL]
    if not periods:
        return None, '未识别到当前口径的年度利润表。'
    latest = max(p.year for p in periods)
    current = [p for p in periods if p.year == latest]
    previous = [p for p in periods if p.year == latest - 1]
    if len(current) != 1 or len(previous) != 1:
        return None, '缺少相邻两年的唯一年度利润表，或存在原列／重述列冲突。'
    current, previous = current[0], previous[0]
    dates = lambda p: ((p.start_date or '')[4:], (p.end_date or '')[4:])
    if dates(current) != dates(previous):
        return None, '两年的会计期间不一致，不能拆解变化。'

    selected = {}
    for year, period in ((previous.year, previous), (current.year, current)):
        for name in ('revenue', 'cost_of_revenue'):
            selected[year, name] = select_value(statements, ST.INCOME_STATEMENT, name, period)
    inputs = list(selected.values())
    reason = compatible(inputs)
    if reason:
        return None, reason + '。请在详细数据中核对营业收入和营业成本。'
    costs = [selected[year, 'cost_of_revenue'].amount for year in (previous.year, current.year)]
    if not (all(cost >= 0 for cost in costs) or all(cost <= 0 for cost in costs)):
        return None, '两年的营业成本正负记法不同，不能可靠拆解。'

    start = selected[previous.year, 'revenue'].amount - abs(costs[0])
    end = selected[current.year, 'revenue'].amount - abs(costs[1])
    revenue_effect = (selected[current.year, 'revenue'].amount -
                      selected[previous.year, 'revenue'].amount)
    cost_effect = abs(costs[0]) - abs(costs[1])
    if start + revenue_effect + cost_effect != end:
        return None, '收入与成本的变化无法对齐毛利差额。'

    reported = []
    for year, period, derived in ((previous.year, previous, start),
                                  (current.year, current, end)):
        gross = select_value(statements, ST.INCOME_STATEMENT, 'gross_profit', period)
        if not gross.sources:
            continue
        if gross.reason:
            return None, '报表毛利存在缺失或冲突，已暂停拆解。'
        if gross.currency != inputs[0].currency:
            return None, '报表毛利与收入／成本的币种不一致。'
        scale = max(Decimal(str(v.multiplier)) for item in inputs for v in item.sources)
        tolerance = max(Decimal(1), scale * 2)
        if abs(gross.amount - derived) > tolerance:
            return None, '报表毛利与「收入－营业成本」不一致，不能使用这张拆解图。'
        reported.append((year, gross))

    magnitude = max(abs(v) for v in (start, end, revenue_effect, cost_effect))
    if magnitude >= Decimal(1_000_000):
        divisor, unit = Decimal(100_000_000), money_unit(inputs[0].currency,'亿')
    elif magnitude >= Decimal(10_000):
        divisor, unit = Decimal(10_000), money_unit(inputs[0].currency,'万')
    else:
        divisor, unit = Decimal(1), money_unit(inputs[0].currency,'')
    pages = {}
    for year in (previous.year, current.year):
        sources = (selected[year, 'revenue'].sources + selected[year, 'cost_of_revenue'].sources +
                   next((gross.sources for y, gross in reported if y == year), []))
        pages[year] = sorted({value.source_page for value in sources if value.source_page > 0})
    provisional = any(value.extraction_method == 'local_ocr'
                      for item in inputs for value in item.sources)
    return {
        'kind': 'gross_profit',
        'years': (previous.year, current.year),
        'currency': inputs[0].currency,
        'unit': unit,
        'start': float(start / divisor),
        'revenue_effect': float(revenue_effect / divisor),
        'cost_effect': float(cost_effect / divisor),
        'end': float(end / divisor),
        'pages': pages,
        'reported_gross_profit_verified': len(reported) == 2,
        'provisional_ocr': provisional,
        'restated_previous': previous.is_restated,
    }, ''
