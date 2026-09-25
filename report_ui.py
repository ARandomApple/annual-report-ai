"""Read-only views of extracted financial data. No financial calculations."""
import pandas as pd
import streamlit as st
from financial_models import StatementScope, StatementType, ValueType
from diagnostics import report_warning_guidance

SCOPE_LABELS = {
    StatementScope.CONSOLIDATED: '合并报表 / Consolidated',
    StatementScope.PARENT: '母公司报表 / Parent company',
    StatementScope.UNKNOWN: '口径未识别 / Unknown scope',
}
STATEMENT_LABELS = {
    StatementType.BALANCE_SHEET: '资产负债表 / Balance sheet',
    StatementType.INCOME_STATEMENT: '利润表 / Income statement',
    StatementType.CASH_FLOW: '现金流量表 / Cash flow',
}
TYPE_LABELS = {ValueType.MONETARY: '金额', ValueType.PER_SHARE: '每股',
               ValueType.PERCENTAGE: '百分比', ValueType.RATIO: '比率',
               ValueType.COUNT: '数量', ValueType.UNKNOWN: '未知'}


def all_statements(report):
    return [s for s in (report.balance_sheet, report.income_statement,
                       report.cash_flow_statement, *report.alternative_statements)
            if s is not None]


def value_rows(statement):
    """One row per source value, retaining duplicate labels and missing values."""
    rows = []
    for metric in statement.metrics:
        for value in metric.values:
            period = value.period
            normalized = value.normalized_value
            rows.append({
                '原始科目': metric.original_label,
                '年份': str(period.year),
                '期间': period.label or str(period.year),
                '期间类型': period.period_type.value,
                '重述': '是' if period.is_restated else '否',
                '报告原值': value.raw_value_str or '—',
                '币种': value.unit or '未知',
                '数值类型': TYPE_LABELS[value.parsed_number.value_type],
                '单位倍数': '未知' if value.multiplier is None else f'{value.multiplier:g}',
                '标准化数值': '—' if normalized is None else f'{normalized:,.8f}'.rstrip('0').rstrip('.'),
                'PDF页码': value.source_page,
                '标准科目': metric.canonical_name or '未映射',
                '可信度': value.confidence.value,
                '提取方式': value.extraction_method,
            })
    return rows


def render_report(report, pdf_doc):
    statements = all_statements(report)
    st.subheader('财务报表 / Financial statements')
    st.caption('金额保留年报原值；单位倍数表示换算到基础货币单位的系数。缺失值不等于零。')
    if report.extraction_warnings:
        for message in report_warning_guidance(report.extraction_warnings):
            st.warning(message)
        with st.expander(f'识别详情 / Technical details ({len(set(report.extraction_warnings))})'):
            for warning in dict.fromkeys(report.extraction_warnings):
                st.caption(warning)
    available = [s for s in statements if any(m.values for m in s.metrics)]
    if not available:
        st.warning('未提取到可展示的财务数据。请检查 PDF 文字能否复制；扫描件或乱码页请展开上方「文字识别」，选择财务报表页后重试。')
        return

    scopes = [scope for scope in SCOPE_LABELS if any(s.scope == scope for s in available)]
    if st.session_state.get('report_scope') not in scopes:
        st.session_state.pop('report_scope',None)
    scope = st.selectbox('报表口径 / Scope', scopes, format_func=SCOPE_LABELS.get, key='report_scope')
    from dashboard_ui import render_dashboard
    if pdf_doc.ocr_page_numbers:
        st.warning('当前看板含 OCR 数据 · '+('已由用户确认核对' if pdf_doc.ocr_verified else '待核对试算'))
    render_dashboard(report,scope)
    from analysis_ui import render_analysis
    with st.expander('财务指标与数据校验 / Metrics & validation', expanded=False):
        render_analysis(report, scope)
    for tab, stype in zip(st.tabs(list(STATEMENT_LABELS.values())), STATEMENT_LABELS):
        with tab:
            selected = [s for s in statements if s.scope == scope and s.statement_type == stype]
            if not selected:
                st.info('此口径下未识别到该报表。')
                continue
            for index, statement in enumerate(selected):
                rows = value_rows(statement)
                if not rows:
                    st.info('已定位报表，但未提取到有效行。')
                    continue
                pages = sorted({row['PDF页码'] for row in rows})
                st.caption(f'{SCOPE_LABELS[scope]} · PDF 页码：' + ', '.join(map(str, pages)))
                if statement.warnings:
                    with st.expander(f'此报表的识别详情（{len(set(statement.warnings))} 条）'):
                        for warning in dict.fromkeys(statement.warnings):
                            st.caption(warning)
                frame = pd.DataFrame(rows)
                visible = ['原始科目', '年份', '报告原值', '币种', '单位倍数', '数值类型', 'PDF页码']
                st.dataframe(frame[visible], hide_index=True, width='stretch', height=440)
                with st.expander('数据来源与识别详情 / Provenance'):
                    st.dataframe(frame, hide_index=True, width='stretch')
                    st.caption('未映射科目仍保留原文；标准化数值为空表示缺失或单位不明。百分比保持百分点值，每股数值不乘金额倍数。')
                with st.expander('核对原文 / Source text'):
                    number = st.selectbox('PDF 页码', pages, key=f'page_{scope.value}_{stype.value}_{index}')
                    source = next((p for p in pdf_doc.pages if p.page_number == number), None)
                    st.text_area('该页提取原文', source.text if source else '原文不可用', height=300,
                                 disabled=True, key=f'text_{scope.value}_{stype.value}_{index}_{number}')

    from ai_ui import render_ai
    st.divider()
    render_ai(report, pdf_doc, scope)
