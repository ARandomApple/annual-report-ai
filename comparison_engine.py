"""Cross-document comparisons without overwriting overlapping reported values."""
from dataclasses import dataclass,field
from decimal import Decimal
import json
from financial_models import StatementScope,PeriodType,ValueType
from financial_inputs import normalized,statements_for
from validation_engine import run_all_validations


@dataclass
class ReportSource:
    document_id: str
    document: object
    report: object
    content_hash: str = ""


@dataclass
class ComparisonPoint:
    metric: str
    label: str
    statement: str
    year: int
    value: Decimal | None = None
    currency: str = ''
    status: str = 'missing'
    reason: str = ''
    signature: tuple = ()
    sources: list = field(default_factory=list)
    change: Decimal | None = None
    growth_percent: Decimal | None = None
    change_reason: str = ''


@dataclass
class Comparison:
    scope: StatementScope
    documents: list
    points: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _signature(period):
    # Ignore year only, so annual observations across years can be compared.
    return (period.period_type.value,(period.start_date or '')[4:],
            (period.end_date or '')[4:],period.is_restated)


def compare_reports(sources,scope,confirmed_same_company=False):
    if len(sources)!=2:raise ValueError('请选择两份年报。')
    if len({s.document_id for s in sources})!=2:raise ValueError('两份文件必须不同。')
    if sources[0].content_hash and sources[0].content_hash==sources[1].content_hash:
        raise ValueError('两份文件内容相同。')
    if not confirmed_same_company:raise ValueError('请先确认两份年报属于同一家公司。')
    companies={s.report.company_name.strip() for s in sources if s.report.company_name.strip()}
    if len(companies)>1:raise ValueError('报告中的公司名称不一致，不能合并。')
    comparison=Comparison(scope,sources)
    groups={}
    for source in sources:
        statements=statements_for(source.report,scope)
        if not statements:comparison.warnings.append(f'{source.document.file_name} 缺少所选报表口径。')
        for statement in statements:
            for metric in statement.metrics:
                if not metric.canonical_name:continue
                for v in metric.values:
                    if v.period.period_type not in (PeriodType.ANNUAL,PeriodType.POINT_IN_TIME):continue
                    key=(statement.statement_type.value,metric.canonical_name,v.period.year)
                    point=groups.setdefault(key,ComparisonPoint(metric.canonical_name,metric.original_label,key[0],key[2]))
                    point.sources.append({'document_id':source.document_id,'file_name':source.document.file_name,
                        'page':v.source_page,'value':v,'label':metric.original_label})
    for point in groups.values():
        values=[item['value'] for item in point.sources]
        amounts={normalized(v) for v in values}
        currencies={v.unit for v in values}
        signatures={_signature(v.period)+(v.parsed_number.value_type.value,) for v in values}
        types={v.parsed_number.value_type for v in values}
        restated={v.period.is_restated for v in values}
        point.currency=next(iter(currencies)) if len(currencies)==1 else ''
        if scope==StatementScope.UNKNOWN:
            point.status='incompatible';point.reason='报表口径未知'
        elif len(restated)>1:
            point.status='conflict';point.reason='原列与重述口径并存，保留两份数值，不自动选用'
        elif len(signatures)>1:
            point.status='incompatible';point.reason='期间或日期口径不一致'
        elif len(currencies)!=1 or not point.currency:
            point.status='incompatible';point.reason='币种不一致或未知，不进行汇率换算'
        elif len(types)!=1 or ValueType.UNKNOWN in types:
            point.status='incompatible';point.reason='数值类型不一致或未知'
        elif any(v.multiplier is None or v.multiplier<=0 for v in values):
            point.status='incompatible';point.reason='单位倍数未知或无效'
        elif None in amounts:
            point.status='missing';point.reason='来源中存在缺失或无效数值'
        elif len(amounts)>1:
            point.status='conflict';point.reason='同年度数值不一致，请核对是否重述、分类调整或提取错误'
        else:
            point.value=next(iter(amounts));point.signature=next(iter(signatures))
            point.status='matched' if len({x['document_id'] for x in point.sources})==2 else 'single'
            point.reason='两份年报一致' if point.status=='matched' else '仅一份年报提供'
        comparison.points.append(point)
    comparison.points.sort(key=lambda p:(p.statement,p.metric,p.year))
    by_key={(p.statement,p.metric,p.year):p for p in comparison.points}
    for point in comparison.points:
        previous=by_key.get((point.statement,point.metric,point.year-1))
        if previous is None:point.change_reason='缺少相邻上一年度';continue
        if point.value is None or previous.value is None:
            point.change_reason='本年或上年数据存在冲突、缺失或不可比口径';continue
        if point.currency!=previous.currency or point.signature!=previous.signature:
            point.change_reason='跨年币种或期间/重述口径不一致';continue
        # Percentages and EPS remain available as reported values, but growth is
        # restricted to monetary line items to avoid confusing percentage points.
        if point.sources[0]['value'].parsed_number.value_type!=ValueType.MONETARY:
            point.change_reason='仅对金额科目计算同比';continue
        point.change=point.value-previous.value
        if previous.value>0:point.growth_percent=point.change/previous.value*100
        else:point.change_reason='上年基数非正数，常规同比增长率不适用'
    years={p.year for p in comparison.points}
    if len(years)<3:comparison.warnings.append('目前可识别的年度不足三年，不补造缺失年度。')
    if not any(p.status=='matched' for p in comparison.points):
        comparison.warnings.append('未找到两份年报一致的重叠科目；请核对是否为相邻年度报告。')
    return comparison


def comparison_evidence(comparison,language='zh'):
    from ai_analyst import AnalysisError,MAX_PAYLOAD_CHARS,PROMPT_VERSION
    entries=[]
    points=comparison.points
    # Always retain conflicts ahead of ordinary values if the package is capped.
    ordered=sorted(points,key=lambda p:(p.status not in ('conflict','incompatible'),p.metric,p.year))
    for index,p in enumerate(ordered[:180],1):
        locations=[{'document_id':s['document_id'],'file_name':s['file_name'],'page':s['page']} for s in p.sources]
        entries.append({'id':f'T{index}','type':'multi_report_comparison','metric':p.metric,'label':p.label,
            'statement':p.statement,'year':p.year,'currency':p.currency,'status':p.status,'reason':p.reason,
            'value':str(p.value) if p.value is not None else None,
            'change':str(p.change) if p.change is not None else None,
            'growth_percent':str(p.growth_percent) if p.growth_percent is not None else None,
            'change_reason':p.change_reason,'source_locations':locations,
            'pages':sorted({s['page'] for s in p.sources}),
            'reported_sources':[{'document_id':s['document_id'],'file_name':s['file_name'],
                'page':s['page'],'raw_value':s['value'].raw_value_str,'currency':s['value'].unit,
                'multiplier':s['value'].multiplier,'period':s['value'].period.label,
                'period_type':s['value'].period.period_type.value,'restated':s['value'].period.is_restated,
                'value_type':s['value'].parsed_number.value_type.value} for s in p.sources]})
    for source in comparison.documents:
        for index,c in enumerate(run_all_validations(source.report,scope=comparison.scope),1):
            entries.append({'id':f'{source.document_id}_C{index}','type':'validation','status':c.status,
                'rule':c.rule,'period':c.period_label,'detail':c.detail,'pages':c.source_pages,
                'source_locations':[{'document_id':source.document_id,'file_name':source.document.file_name,'page':n} for n in c.source_pages]})
        page_numbers=sorted({s['page'] for p in points for s in p.sources if s['document_id']==source.document_id})[:4]
        for page in source.document.pages:
            if page.page_number in page_numbers:
                entries.append({'id':f'{source.document_id}_P{page.page_number}','type':'source_excerpt',
                    'text':page.text[:1200],'truncated':len(page.text)>1200,'pages':[page.page_number],
                    'source_locations':[{'document_id':source.document_id,'file_name':source.document.file_name,'page':page.page_number}]})
    payload={'version':PROMPT_VERSION,'mode':'two_reports_multi_year','language':language,
        'scope':comparison.scope.value,'same_company_confirmed_by_user':True,
        'documents':[{'id':s.document_id,'file_name':s.document.file_name,'content_hash':s.content_hash} for s in comparison.documents],
        'evidence':entries,'comparison_warnings':comparison.warnings,
        'extraction_warnings':[{s.document_id:s.report.extraction_warnings} for s in comparison.documents],
        'coverage':{'omitted_comparison_points':max(0,len(points)-180),'full_reports_not_sent':True,
            'excerpt_limit_per_document':4,'excerpt_chars':1200},
        'comparison_policy':'Never choose or overwrite conflicting overlapping-year values. No trend across conflicted/missing points. Cite document identity AND PDF page.'}
    if len(json.dumps(payload,ensure_ascii=False,allow_nan=False))>MAX_PAYLOAD_CHARS:
        raise AnalysisError('两份年报的对比材料超过当前单次上限。')
    return payload
