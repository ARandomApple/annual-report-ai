"""Display deterministic calculations and their supporting source inputs."""
import pandas as pd
import streamlit as st
from financial_engine import compute_metrics
from validation_engine import run_all_validations


def render_analysis(report, scope):
    st.subheader('财务指标与校验 / Metrics & checks')
    st.caption('基于当前报表口径计算；百分比以 % 显示。数据不足或口径不兼容时保留原因。')
    results = compute_metrics(report, scope)
    if results:
        rows = []
        for result in results:
            rows.append({'指标':result.label, '年份':str(result.period.year),
                '期间':result.period.label or str(result.period.year),
                '重述':'是' if result.period.is_restated else '否',
                '结果':'—' if result.value is None else f'{result.value:,.2f}',
                '单位':result.unit, '状态':'可计算' if result.value is not None else '未计算',
                '说明':result.reason or '', '公式':result.formula,
                'PDF页码':', '.join(map(str,sorted({v.source_page for v in result.sources})))})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        st.caption('自由现金流采用经营现金流减资本支出绝对值的简化口径。毛利率优先采用报表毛利÷收入，否则采用（收入−营业成本）÷收入；具体见公式。不代表所有行业都使用同一财务定义。')
        with st.expander('计算依据 / Calculation inputs'):
            inputs = []
            for result in results:
                for value in result.sources:
                    inputs.append({'指标':result.label,'结果年份':str(result.period.year),
                        '原始科目':value.raw_label,'输入年份':str(value.period.year),
                        '输入期间':value.period.label,'原值':value.raw_value_str,
                        '币种':value.unit or '未知','倍数':str(value.multiplier),
                        'PDF页码':value.source_page})
            if inputs: st.dataframe(pd.DataFrame(inputs),hide_index=True,width='stretch')
    else:
        st.info('没有可用于当前年度指标计算的期间数据。')
    checks = run_all_validations(report,scope=scope)
    counts = {status:sum(c.status==status for c in checks) for status in ('passed','failed','skipped')}
    st.write(f"校验通过 {counts['passed']} 项 · 未通过 {counts['failed']} 项 · 无法校验 {counts['skipped']} 项")
    if counts['failed']: st.warning('存在校验失败或输入冲突，请核对原文后再使用相关指标。')
    st.dataframe(pd.DataFrame([{'校验':c.rule,'期间':c.period_label,
        '结果':{'passed':'通过','failed':'未通过','skipped':'无法校验'}[c.status],
        '说明':c.detail,'差额':c.absolute_difference,'容差':c.tolerance_used,
        'PDF页码':', '.join(map(str,c.source_pages))} for c in checks]),hide_index=True,width='stretch')
    st.caption('校验通过仅表示已执行规则一致，不等于完整审计或 AI 分析。')
