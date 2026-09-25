"""Annual Report Intelligence: upload, extract and inspect source financial data."""
import streamlit as st
from pdf_parser import parse_pdf
from table_extractor import extract_financial_report
from report_ui import render_report, all_statements
from dashboard_ui import apply_theme,render_hero,render_empty
from ocr_ui import render_ocr
from diagnostics import pdf_failure_message

st.set_page_config(page_title='Annual Report Intelligence', page_icon='📊', layout='wide')
apply_theme()


@st.cache_data(show_spinner=False, max_entries=3, ttl=3600)
def load_document(data: bytes, name: str):
    return parse_pdf(data, name)


@st.cache_data(show_spinner=False, max_entries=3, ttl=3600)
def load_report(data: bytes, name: str):
    # Extraction revision 2: English subtotals and wrapped labels (invalidates cache).
    report = extract_financial_report(data, name)
    return report


st.sidebar.markdown('<div class="brand"><b>◈</b>年报研究室</div>',unsafe_allow_html=True)
st.sidebar.caption('ANNUAL REPORT STUDIO')
st.sidebar.markdown('从一份年报，看到公司的年度变化。')
st.sidebar.divider()
st.sidebar.markdown('**你的分析工作台**\n\n◈ 经营数据看板\n\n↗ 多年变化对比\n\n▤ OCR 文字识别\n\n✓ 数据校验与溯源')
st.sidebar.divider()
st.sidebar.info('解析、OCR 与指标计算在网站服务器完成。')
st.sidebar.caption('GPT 解读为可选功能：API 单独计费，不包含在 ChatGPT Plus 订阅中。')

render_hero()
mode=st.radio('分析模式',['单份年报','双年报 · 多年对比'],horizontal=True,key='report_mode')
if mode=='双年报 · 多年对比':
    from comparison_ui import render_comparison_upload
    render_comparison_upload(load_document,load_report)
    st.stop()

st.caption('每份 PDF 最多 25 MB。上传文件在网站服务器上处理；只有点击生成 AI 分析时，预览中列出的材料才会发送给 OpenAI。')
uploaded = st.file_uploader('上传年报 / Upload annual report', type=['pdf'],
                            help='支持中英文 PDF；扫描页或乱码页可使用 OCR 文字识别。')
st.caption('如果上传框直接显示 Error 且下方没有处理进度：请刷新网页后重新选择文件。')
if uploaded is None:
    render_empty()
    st.stop()

with st.status('正在处理年报…', expanded=True) as processing:
    try:
        data = uploaded.getvalue()
        processing.write('已接收文件，正在读取 PDF 页面和文字层…')
        document = load_document(data, uploaded.name)
    except Exception as exc:
        processing.update(label='PDF 读取失败', state='error', expanded=True)
        st.error(pdf_failure_message(exc))
        st.stop()

    processing.write(f'已读取 {document.page_count} 页，正在定位财务报表并提取金额…')
    report = None
    extraction_failed = False
    try:
        report = load_report(data, uploaded.name)
    except Exception:
        extraction_failed = True
        processing.write('财务报表提取失败；PDF 原文仍可查看。')
    has_values = report is not None and any(m.values for s in all_statements(report) for m in s.metrics)
    if has_values:
        processing.update(label='PDF 已读取 · 财务数据已提取', state='complete', expanded=False)
    else:
        processing.update(label='PDF 已读取 · 财务数据待处理', state='error', expanded=False)

if document.scanned_warning:
    st.warning(document.scanned_warning)
st.caption(f'{uploaded.name} · {document.page_count} 页 · {document.file_size_kb/1024:.1f} MB · '+{'zh': '中文', 'en': 'English'}.get(document.language, '未知语言'))

if extraction_failed:
    st.error('财务报表提取中断。PDF 已读取，你仍可查看下方原文；可尝试 OCR 文字识别或重新选择文件。')
elif not has_values:
    st.warning('PDF 已读取，但未提取到可用财务金额。若文字不可复制，请展开下方「文字识别」并选择报表页；否则请查看文档信息中的文本预览。')

document,report=render_ocr(data,uploaded.name,document,report)

financial_tab, document_tab = st.tabs(['财务数据 / Financial data', '文档信息 / Document'])
with financial_tab:
    if report is not None:
        render_report(report, document)
    else:
        st.info('当前没有可展示的提取结果。')
with document_tab:
    st.subheader('文档信息 / Document information')
    st.caption(f'语言识别置信度：{document.language_confidence:.0%} · 平均每页 {document.chars_per_page:g} 字符')
    with st.expander('PDF 元数据 / Metadata'):
        st.json(document.metadata)
    st.text_area('文本预览 / Text preview', document.text_preview, height=400, disabled=True)

st.divider()
status = st.columns(3)
status[0].success('PDF 已读取')
if report is not None and any(m.values for s in all_statements(report) for m in s.metrics):
    status[1].success('财务数据已提取 · 请核对来源')
else:
    status[1].warning('财务数据未提取')
status[2].info('GPT 分析：在财务数据页按需生成')
