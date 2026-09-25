"""Visual overview using only compatible, source-linked financial inputs."""
import streamlit as st
from financial_models import StatementType as ST, PeriodType
from financial_inputs import statements_for, periods_for, select_value, money_unit
from financial_engine import compute_metrics
from dashboard_component import dashboard_html
from diagnostics import metric_issue
from change_decomposition import gross_profit_bridge, revenue_segment_bridge

def apply_theme():
    st.markdown('''<style>
    :root {--ink:#24223A;--purple:#7655F7;}
    .stApp {background:#F7F7FC;color:var(--ink);}
    [data-testid="stHeader"] {background:rgba(247,247,252,.9);}
    [data-testid="stSidebar"] {background:#FFFFFF;border-right:1px solid #E9E7F3;}
    .block-container {padding-top:2rem;max-width:1450px;padding-bottom:3rem;}
    h1,h2,h3 {color:#24223A;letter-spacing:-.035em;}
    [data-testid="stFileUploader"] {background:#fff;border:1px solid #E7E2F8;border-radius:20px;padding:12px;}
    [data-testid="stFileUploaderDropzone"] {background:#F4F0FF;border:1px dashed #AC99F4;border-radius:14px;}
    button[kind="primary"], [data-testid="stBaseButton-primary"] {background:#7655F7!important;border-color:#7655F7!important;border-radius:12px!important;}
    button[kind="secondary"] {border-radius:12px;}
    [data-testid="stExpander"] {background:white;border:1px solid #E8E5F0;border-radius:16px;}
    [data-testid="stMetric"] {background:white;border:1px solid #E8E5F0;border-radius:18px;padding:16px;}
    [data-baseweb="tab-list"] {gap:22px;}
    [data-baseweb="tab-highlight"] {background:#7655F7;}
    [data-testid="stPlotlyChart"] {border-radius:20px;overflow:hidden;border:1px solid #ECE9F5;}
    .brand {font-size:25px;font-weight:850;letter-spacing:-1px;margin:6px 0 26px;}
    .brand b {background:#7655F7;color:#fff;padding:8px 11px;border-radius:14px;margin-right:10px;}
    .eyebrow {font-size:11px;letter-spacing:2px;font-weight:750;color:#726A8A;margin-bottom:10px;}
    .hero {background:#EDE7FF;border-radius:26px;display:flex;align-items:center;justify-content:space-between;padding:34px 40px;margin:10px 0 26px;overflow:hidden;}
    .hero h1 {font-size:38px;line-height:1.25;margin:0 0 14px;max-width:650px;}
    .hero p {color:#665D7A;line-height:1.8;margin:0;max-width:650px;}
    .hero-art {width:240px;min-width:180px;height:155px;margin-left:20px;}
    .pill {display:inline-block;background:white;color:#675389;border-radius:30px;padding:5px 12px;font-size:12px;margin:0 8px 18px 0;}
    .kpi {min-height:157px;border-radius:22px;padding:23px;margin:8px 0 18px;background:#fff;border:1px solid #E8E5F0;}
    .kpi.purple {background:#7655F7;color:white;border-color:#7655F7;}
    .kpi.orange {background:#FFF0E9;} .kpi.mint {background:#E3F7F1;} .kpi.yellow {background:#FFF7D9;}
    .kpi-label {font-size:13px;opacity:.85;margin-bottom:12px;}
    .kpi-value {font-size:32px;line-height:1.2;font-weight:780;letter-spacing:-1px;}
    .kpi-note {font-size:11px;margin-top:12px;opacity:.85;line-height:1.6;}
    .feature {background:white;border:1px solid #E8E5F0;border-radius:22px;padding:28px;min-height:182px;}
    .feature .icon {font-size:26px;margin-bottom:15px;} .feature h3 {font-size:19px;}
    .feature p {color:#777186;font-size:14px;line-height:1.8;}
    @media(max-width:760px) {.hero{padding:24px}.hero h1{font-size:28px}.hero-art{display:none}.kpi-value{font-size:27px}}
    </style>''',unsafe_allow_html=True)


def render_hero():
    st.markdown('''<div class="hero"><div><div class="eyebrow">ANNUAL REPORT STUDIO</div>
    <span class="pill">在线解析</span><span class="pill">数据可追溯</span>
    <h1>把厚厚的年报，<br>变成看得懂的图表。</h1>
    <p>从营收到现金流，读懂公司的年度变化。<br>上传 PDF，开始你的财务探索。</p></div>
    <svg class="hero-art" viewBox="0 0 240 155" aria-hidden="true">
    <rect x="12" y="27" width="127" height="110" rx="22" fill="white" transform="rotate(-8 75 80)"/>
    <rect x="35" y="83" width="20" height="37" rx="6" fill="#C7BAFF"/>
    <rect x="63" y="63" width="20" height="57" rx="6" fill="#A68DFF"/>
    <rect x="91" y="43" width="20" height="77" rx="6" fill="#7655F7"/>
    <circle cx="170" cy="69" r="51" fill="#FF784F"/><circle cx="170" cy="69" r="25" fill="#EDE7FF"/>
    <path d="M170 18 A51 51 0 0 1 221 69 L195 69 A25 25 0 0 0 170 44Z" fill="#FFBDA4"/>
    <rect x="150" y="119" width="73" height="27" rx="13.5" fill="#18AA96"/>
    <path d="M168 134L178 125L187 131L205 121" fill="none" stroke="white" stroke-width="3"/>
    </svg></div>''',unsafe_allow_html=True)


def render_empty():
    st.info('请选择一份年报 PDF 开始。')
    for col,(icon,title,body) in zip(st.columns(3),[
        ('◈','数据，一眼看清','用关键指标和年度图表，查看经营表现。'),
        ('▤','难读 PDF，也能识别','OCR 可识别扫描页或乱码页，并逐页核对。'),
        ('↗','变化，有据可查','对比相邻年报，每个数字都保留来源页码。')]):
        with col:st.markdown(f'<div class="feature"><div class="icon">{icon}</div><h3>{title}</h3><p>{body}</p></div>',unsafe_allow_html=True)


KPI_SPECS = [
    ('revenue', '营业收入', ST.INCOME_STATEMENT, 'money'),
    ('net_income', '净利润', ST.INCOME_STATEMENT, 'money'),
    ('operating_cash_flow', '经营现金流', ST.CASH_FLOW, 'money'),
    ('revenue_growth', '收入同比', None, 'percent'),
    ('operating_profit', '营业利润', ST.INCOME_STATEMENT, 'money'),
    ('gross_profit', '毛利', ST.INCOME_STATEMENT, 'money'),
    ('net_income_growth', '净利润同比', None, 'percent'),
    ('gross_margin', '毛利率', None, 'percent'),
    ('net_margin', '净利润率', None, 'percent'),
    ('operating_margin', '营业利润率', None, 'percent'),
    ('total_assets', '总资产', ST.BALANCE_SHEET, 'money'),
    ('total_liabilities', '总负债', ST.BALANCE_SHEET, 'money'),
    ('debt_to_assets', '资产负债率', None, 'percent'),
    ('ocf_margin', '经营现金流／收入', None, 'percent'),
    ('free_cash_flow', '自由现金流', None, 'money'),
]


def dashboard_data(report, scope):
    """Build a source-linked, single-scope view without inventing missing values."""
    statements=statements_for(report,scope)
    periods=[p for p in periods_for(statements,ST.INCOME_STATEMENT) if p.period_type==PeriodType.ANNUAL]
    if not periods:return None
    latest=max(p.year for p in periods)
    annual_by_year={y:[p for p in periods if p.year==y] for y in sorted({p.year for p in periods})}
    if len(annual_by_year[latest])!=1:return {'error':'最新年度存在多个期间或重述口径，请在详细数据中核对后比较。'}
    balance=[p for p in periods_for(statements,ST.BALANCE_SHEET) if p.period_type==PeriodType.POINT_IN_TIME]
    balance_by_year={y:[p for p in balance if p.year==y] for y in sorted({p.year for p in balance})}
    metrics=compute_metrics(report,scope)
    cards=[]

    def comparable_periods(mapping, years, require_same_restatement=False):
        """Require the same fiscal dates; disclose comparative restatements."""
        selected=[mapping.get(year,[]) for year in years]
        if any(len(group)!=1 for group in selected):return False
        periods=[group[0] for group in selected]
        def fiscal_signature(period):
            return ((period.start_date or '')[4:], (period.end_date or '')[4:])
        return (len({fiscal_signature(period) for period in periods})==1 and
                (not require_same_restatement or len({p.is_restated for p in periods})==1))

    for name,label,kind,format_ in KPI_SPECS:
        points=[]
        reasons=[]
        period_map=balance_by_year if kind==ST.BALANCE_SHEET or name=='debt_to_assets' else annual_by_year
        for year in sorted(set(annual_by_year)|set(balance_by_year)):
            candidates=period_map.get(year,[])
            if len(candidates)!=1:
                if year==latest:reasons.append('期间缺失或存在多个原列／重述口径')
                continue
            period=candidates[0]
            if kind is None:
                matches=[m for m in metrics if m.name==name and m.period==period]
                if len(matches)!=1:
                    if year==latest:reasons.append('指标缺失或口径不唯一')
                    continue
                item=matches[0]
                amount=item.value
                reason=item.reason
                currency=item.unit if format_=='money' else '%'
                sources=item.sources
            else:
                item=select_value(statements,kind,name,period)
                amount=float(item.amount) if item.amount is not None else None
                reason=item.reason
                currency=item.currency
                sources=item.sources
            if reason or amount is None:
                if year==latest:reasons.append(reason or '数据缺失')
                continue
            points.append({'year':year,'value':amount/1e8 if format_=='money' else amount,
                           'currency':currency,'restated':period.is_restated,
                           'pages':sorted({s.source_page for s in sources if s.source_page>0})})
        # A currency change across years is not a comparable trend.
        if format_=='money' and len({p['currency'] for p in points})>1:
            current_currency=next((p['currency'] for p in points if p['year']==latest),None)
            points=[p for p in points if p['currency']==current_currency]
            reasons.append('其他年度币种不同，未进行换算')
        current_currency=next((p['currency'] for p in points if p['year']==latest),
                              next((p['currency'] for p in points), 'CNY'))
        display_unit='%' if format_=='percent' else money_unit(current_currency,'亿')
        if format_=='money' and points:
            largest=max(abs(p['value']) for p in points)
            if largest<0.0001:
                display_unit=money_unit(current_currency,'')
                factor=1e8
            elif largest<0.01:
                display_unit=money_unit(current_currency,'万')
                factor=1e4
            else:
                factor=1
            for p in points:p['value']*=factor
        current=next((p for p in points if p['year']==latest),None)
        previous=next((p for p in points if p['year']==latest-1),None)
        comparison=None
        fiscal_match=comparable_periods(period_map,[latest-1,latest])
        if current and previous and fiscal_match:
            delta=current['value']-previous['value']
            comparison={'previous':previous,'delta':delta,
                        'rate':delta/previous['value']*100 if format_=='money' and previous['value']>0 else None}
        if current is None:
            comparison_reason=metric_issue('；'.join(dict.fromkeys(reasons))) or '当前年度金额尚未可靠识别，请查看下方详细数据。'
        elif previous is None:
            comparison_reason='缺少上一年度可用数值。请在详细数据中核对上一年列；扫描件可尝试 OCR 文字识别。'
        elif not fiscal_match:
            comparison_reason='两年报表期间或重述口径无法可靠匹配，请核对原始年份列。'
        else:
            comparison_reason=''
        consecutive=[p['year'] for p in points]
        can_trend=(current is not None and len(consecutive)>=3 and consecutive[-1]==latest
                   and consecutive==list(range(consecutive[0],consecutive[-1]+1))
                   and comparable_periods(period_map,consecutive,require_same_restatement=True))
        cards.append({'id':name,'label':label,'format':format_,'display_unit':display_unit,'points':points,
                      'current':current,'comparison':comparison,'can_trend':can_trend,
                      'reason':metric_issue('；'.join(dict.fromkeys(reasons))),
                      'comparison_reason':comparison_reason})
    return {'year':latest,'scope':scope.value,'cards':cards}


def render_dashboard(report,scope):
    data=dashboard_data(report,scope)
    if data is None:return
    if 'error' in data:
        st.info(data['error']);return
    st.subheader(f"{data['year']} · 经营概览")
    available=sum(card['current'] is not None for card in data['cards'])
    comparable=sum(card['comparison'] is not None for card in data['cards'])
    st.caption(f'当前年度可展示 {available}/{len(data["cards"])} 项指标 · 可做相邻年度对比 {comparable} 项。点击指标查看原因和计算依据。')
    st.iframe(dashboard_html(data),height=610)
    st.caption('点击指标查看年度对比；仅在至少三个连续可比年度可用时展示趋势图。缺失项不按零展示。')
    bridge, segment_reason = revenue_segment_bridge(report, scope)
    reason = ''
    if bridge is None:
        bridge, reason = gross_profit_bridge(report, scope)
    with st.expander('变化拆解 / Change drivers', expanded=bridge is not None):
        if bridge is None:
            st.info('暂不绘制拆解图。业务分部：' + segment_reason + ' 毛利拆解：' + reason)
        else:
            import plotly.graph_objects as go
            prior, current = bridge['years']
            if bridge['kind'] == 'revenue_segments':
                parts = bridge['parts']
                title = '营业收入变化 · 业务分部贡献'
                explanation = '业务分部明细在两年均与营业收入合计精确相符；各分部变化相加等于总收入变化。'
                endpoint = '营业收入'
            else:
                revenue_label = '收入增加贡献' if bridge['revenue_effect'] > 0 else '收入减少影响' if bridge['revenue_effect'] < 0 else '收入未变'
                cost_label = '成本下降贡献' if bridge['cost_effect'] > 0 else '成本上升影响' if bridge['cost_effect'] < 0 else '成本未变'
                parts = [(revenue_label, bridge['revenue_effect']),
                         (cost_label, bridge['cost_effect'])]
                title = '毛利变化 · 收入与成本影响'
                explanation = ('报表毛利已与收入减营业成本核对。' if bridge['reported_gross_profit_verified']
                               else '报表未同时提供两年毛利，图中毛利按收入减营业成本计算。')
                endpoint = '毛利'
            st.markdown(f'**{title}**')
            total_change = bridge['end'] - bridge['start']
            left, middle, right = st.columns(3)
            left.metric(f'{prior} {endpoint}', f"{bridge['start']:,.2f} {bridge['unit']}")
            middle.metric(f'{current} {endpoint}', f"{bridge['end']:,.2f} {bridge['unit']}")
            right.metric('合计变化', f"{total_change:+,.2f} {bridge['unit']}")
            labels = [label for label,_ in parts] + ['合计变化']
            values = [value for _,value in parts] + [total_change]
            both_pages = ', '.join(map(str, sorted(set(bridge['pages'][prior]+bridge['pages'][current]))))
            fig = go.Figure(go.Waterfall(
                x=labels, measure=[*['relative']*len(parts), 'total'],
                y=[*values[:-1], 0],
                text=[f'{value:+,.2f}' for value in values],
                textposition='outside', customdata=[both_pages]*len(labels),
                hovertemplate='%{x}<br>PDF %{customdata} 页<extra></extra>',
                connector={'line': {'color': '#DAD3EC'}},
                increasing={'marker': {'color': '#7655F7'}},
                decreasing={'marker': {'color': '#FF784F'}},
                totals={'marker': {'color': '#18AA96'}},
            ))
            fig.update_layout(height=345, showlegend=False, paper_bgcolor='white',
                              plot_bgcolor='white', margin=dict(l=30,r=25,t=35,b=45),
                              font=dict(family='Arial, Microsoft YaHei, sans-serif',color='#514A65'))
            fig.update_yaxes(title=f"{bridge['currency']} · {bridge['unit']}",gridcolor='#F0EEF6')
            st.plotly_chart(fig, width='stretch', key='change_drivers_bridge')
            st.caption('拆解图以零为起点，仅表示变化贡献；上方保留两年的完整金额。' + explanation + ' 只使用同口径、同币种且可核对的年度数值。')
            if bridge['provisional_ocr']:
                st.warning('此拆解使用 OCR 识别数据，请先与原图核对。')
