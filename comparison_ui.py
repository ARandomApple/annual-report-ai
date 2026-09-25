"""Two-report upload, reconciliation and multi-year trend review."""
import hashlib
import pandas as pd
import streamlit as st
from comparison_engine import ReportSource,compare_reports,comparison_evidence
from financial_models import StatementScope,ValueType
from financial_inputs import statements_for
from report_ui import SCOPE_LABELS,TYPE_LABELS
from ai_ui import render_ai
from diagnostics import pdf_failure_message, report_warning_guidance

STATUS={'matched':'两份一致','single':'单份来源','conflict':'数值/重述冲突',
        'incompatible':'口径不可比','missing':'缺失'}
NAMES={'revenue':'营业收入','net_income':'净利润','net_income_attributable_to_parent':'归母净利润',
       'total_assets':'总资产','total_liabilities':'总负债','total_equity':'股东权益',
       'operating_cash_flow':'经营现金流','capital_expenditure':'资本支出',
       'cost_of_revenue':'营业成本','eps_basic':'基本每股收益'}


def _fmt(value):
    return '—' if value is None else f'{value:,.6f}'.rstrip('0').rstrip('.')


def render_comparison_upload(load_document,load_report):
    st.caption('例如：2025 年报与 2024 年报，可覆盖 2023—2025 年。实际年度取决于文件内容。')
    st.caption('上传框若直接显示 Error 且没有处理进度，请刷新网页、确认本地服务仍在运行后重试。')
    a,b=st.columns(2)
    with a:first=st.file_uploader('年报 A',type=['pdf'],key='report_a')
    with b:second=st.file_uploader('年报 B',type=['pdf'],key='report_b')
    if first is None or second is None:
        st.info('请分别上传两份同一公司的年报。');return
    files=[first,second]
    data=[f.getvalue() for f in files]
    fingerprints=[hashlib.sha256(content).hexdigest() for content in data]
    if fingerprints[0]==fingerprints[1]:
        st.warning('两份上传内容相同，请选择另一年度的年报。');return
    sources=[]
    with st.status('正在处理两份年报…', expanded=True) as processing:
        for index,(file,content) in enumerate(zip(files,data),1):
            processing.write(f'年报 {index}/2：正在读取 PDF…')
            try:
                document=load_document(content,file.name)
            except Exception as exc:
                processing.update(label=f'年报 {index} 读取失败',state='error',expanded=True)
                st.error(f'年报 {index}：'+pdf_failure_message(exc));return
            processing.write(f'年报 {index}/2：已读取 {document.page_count} 页，正在提取财务表格…')
            try:
                report=load_report(content,file.name)
            except Exception:
                processing.update(label=f'年报 {index} 提取失败',state='error',expanded=True)
                st.error(f'年报 {index}：PDF 已读取，但财务表格提取中断。可先核对文本预览，或使用本地 OCR。');return
            sources.append(ReportSource(f'D{index}',document,report,fingerprints[index-1]))
        processing.update(label='两份年报已读取 · 正在核对公司和数据口径',state='complete',expanded=False)
    for source in sources:
        from ocr_ui import render_ocr
        index=int(source.document_id[1:])-1
        source.document,source.report=render_ocr(data[index],files[index].name,source.document,source.report,prefix=source.document_id)
        st.write(f'{source.document_id} · {source.document.file_name} · {source.document.page_count} 页')
        with st.expander(f'{source.document_id} 首页文字 · 核对公司名称'):
            st.text(source.document.pages[0].text[:1000] if source.document.pages else '无可提取文字')
        for message in report_warning_guidance(source.report.extraction_warnings):
            st.warning(f'{source.document_id}：{message}')
        if source.report.extraction_warnings:
            with st.expander(f'{source.document_id} 识别详情'):
                for warning in dict.fromkeys(source.report.extraction_warnings):st.caption(warning)
    confirm_key='same_company_'+hashlib.sha256(''.join(fingerprints).encode()).hexdigest()[:20]
    if not st.checkbox('我已核对，两份年报属于同一家公司',key=confirm_key):
        st.info('尚未可靠自动识别公司身份，请核对后启用对比。');return
    scopes=[scope for scope in SCOPE_LABELS if any(statements_for(s.report,scope) for s in sources)]
    if not scopes:st.warning('两份年报均未提取到财务报表。');return
    scope=st.selectbox('对比口径',scopes,format_func=SCOPE_LABELS.get,key='comparison_scope')
    try:comparison=compare_reports(sources,scope,confirmed_same_company=True)
    except ValueError as exc:st.error(str(exc));return
    for warning in comparison.warnings:st.warning(warning)
    if not comparison.points:st.info('当前口径没有可对比的年度金额。');return
    years=sorted({p.year for p in comparison.points})
    st.subheader('多年变化 / Multi-year comparison')
    st.caption('已识别年度：'+', '.join(map(str,years))+'。金额统一为基础货币单位；重叠年度不一致时不自动选用。')
    points=comparison.points
    table=[]
    for p in points:
        table.append({'科目':NAMES.get(p.metric,p.metric),'年份':str(p.year),'金额/数值':_fmt(p.value),
            '币种':p.currency or '未知','类型':TYPE_LABELS[p.sources[0]['value'].parsed_number.value_type],
            '重叠核对':STATUS[p.status],'同比变化额':_fmt(p.change),'同比增长率%':_fmt(p.growth_percent),
            '说明':p.reason+('；'+p.change_reason if p.change_reason else ''),
            '来源':'；'.join(f"{s['document_id']} · PDF {s['page']} 页" for s in p.sources)})
    st.dataframe(pd.DataFrame(table),hide_index=True,width='stretch')
    conflicts=[p for p in points if p.status in ('conflict','incompatible')]
    if conflicts:st.warning(f'发现 {len(conflicts)} 个冲突或不可比年度科目，相关同比和趋势已暂停。')
    with st.expander('两份来源原值 / Original values',expanded=bool(conflicts)):
        originals=[]
        for p in points:
            for source in p.sources:
                v=source['value']
                originals.append({'科目':NAMES.get(p.metric,p.metric),'年份':str(p.year),
                    '文档':source['document_id'],'文件名':source['file_name'],'PDF页码':source['page'],
                    '原始科目':source['label'],'原值':v.raw_value_str,'币种':v.unit or '未知',
                    '倍数':str(v.multiplier),'期间':v.period.label,'重述':'是' if v.period.is_restated else '否'})
        st.dataframe(pd.DataFrame(originals),hide_index=True,width='stretch')
    choices=list(dict.fromkeys((p.statement,p.metric) for p in points))
    chosen=st.selectbox('趋势科目',choices,format_func=lambda item:NAMES.get(item[1],item[1]),key='trend_metric')
    selected=sorted([p for p in points if (p.statement,p.metric)==chosen],key=lambda p:p.year)
    if (len(selected)>=3 and all(p.value is not None for p in selected)
            and len({p.currency for p in selected})==1 and len({p.signature for p in selected})==1
            and all(b.year==a.year+1 for a,b in zip(selected,selected[1:]))):
        st.caption(f'{NAMES.get(chosen[1],chosen[1])} · {selected[0].currency} · {TYPE_LABELS[selected[0].sources[0]["value"].parsed_number.value_type]}')
        st.line_chart(pd.DataFrame({'年度':[str(p.year) for p in selected],
                                   '数值':[float(p.value) for p in selected]}).set_index('年度'))
    else:st.info('至少需要三个连续、同口径的可比年度才展示趋势线；两年变化请查看上方数值和同比。')
    with st.expander('按文件与页码核对原文'):
        doc_id=st.selectbox('来源文件',[s.document_id for s in sources],
            format_func=lambda identity:next(s.document.file_name+' ('+identity+')' for s in sources if s.document_id==identity),key='compare_source_doc')
        source=next(s for s in sources if s.document_id==doc_id)
        pages=sorted({s['page'] for p in points for s in p.sources if s['document_id']==doc_id})
        if pages:
            page=st.selectbox('PDF 页码',pages,key='compare_source_page')
            text=next((p.text for p in source.document.pages if p.page_number==page),'原文不可用')
            st.text_area('来源页原文',text,height=300,disabled=True,key='compare_source_text')
    st.divider()
    if any(s.document.ocr_page_numbers and not s.document.ocr_verified for s in sources):
        st.info('对比包含待核对 OCR 数据，请先逐份核对并确认，再生成 GPT 分析。')
        return
    render_ai(None,None,scope,payload_builder=lambda language:comparison_evidence(comparison,language),key_prefix='comparison')
