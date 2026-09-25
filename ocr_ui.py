"""Server-side OCR with bounded page selection and original-page review."""
import hashlib
import pymupdf
import streamlit as st
from ocr_engine import available,parse_page_selection,recognize_pdf
from pdf_parser import parse_pdf
from table_extractor import extract_financial_report
from financial_models import StatementType


@st.cache_data(show_spinner=False,max_entries=8)
def page_preview(data,number):
    with pymupdf.open(stream=data,filetype='pdf') as doc:
        return doc[number-1].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False).tobytes('png')


def render_ocr(data,name,document,report,prefix='single'):
    identity=hashlib.sha256(data).hexdigest()[:16]
    key=f'ocr_{prefix}_{identity}'
    # At most one OCR document per upload slot is retained in this session.
    slot=f'ocr_result_{prefix}'
    saved=st.session_state.get(slot)
    if saved and saved['identity']!=identity:
        del st.session_state[slot];saved=None
    if saved:
        statements=[saved['report'].income_statement,saved['report'].balance_sheet,saved['report'].cash_flow_statement]
        if any(s is not None and not isinstance(s.statement_type,StatementType) for s in statements):
            # A Streamlit code reload may replace Enum classes while session state
            # still holds old objects. Rebuild from cached OCR text, not images.
            saved['document']=parse_pdf(data,name,ocr_pages=saved['pages'])
            saved['report']=extract_financial_report(data,name,ocr_pages=saved['pages'])
    missing=report is None or not any((report.income_statement,report.balance_sheet,report.cash_flow_statement))
    with st.expander('▤ 文字识别与原图核对 · 服务器端 OCR',expanded=missing or saved is not None):
        st.caption('扫描件或乱码 PDF 可使用此工具。文件在本网站服务器上处理，不调用 GPT。一次最多识别 20 页；空白页码会先自动定位报表。')
        ready=available()
        if not ready:st.warning('OCR 组件未就绪，请联系网站维护者检查依赖与模型。')
        selected=st.text_input('财务报表的 PDF 页码（可留空自动定位）',placeholder='例如：270-274,278-279',key=key+'_range')
        if st.button('识别财务报表',key=key+'_run',disabled=not ready,type='primary'):
            try:
                pages=parse_page_selection(selected,document.page_count)
                progress=st.progress(0,text='正在准备本地 OCR…')
                with st.spinner('正在服务器识别文字，请稍候…'):
                    recognized=recognize_pdf(data,pages,lambda ratio,text:progress.progress(ratio,text=text))
                    progress.progress(1.0,text='文字识别完成，正在重新定位财务报表…')
                    parsed=parse_pdf(data,name,ocr_pages=recognized)
                    extracted=extract_financial_report(data,name,ocr_pages=recognized)
                saved={'identity':identity,'document':parsed,'report':extracted,'pages':recognized}
                st.session_state[slot]=saved
                st.session_state[key+'_verified']=False
                st.session_state[key+'_preview']=min(recognized)
                st.success(f'已识别 {len(recognized)} 页；请核对原图。')
                if not any((extracted.income_statement,extracted.balance_sheet,extracted.cash_flow_statement)):
                    st.warning('文字识别已完成，但所选页没有找到完整财务报表。请核对页码是否包含报表标题及年份列，再缩小范围重试。')
            except (ValueError,RuntimeError,ImportError) as exc:
                st.error(str(exc))
            except Exception:
                st.error('OCR 未完成。请缩小页码范围后重试；原文件和现有结果已保留。')
        if saved:
            document=saved['document'];report=saved['report']
            st.warning('OCR 数据为待核对结果。请特别检查数字、括号负号、年份、单位；资产负债平衡并不代表所有数字均正确。')
            st.caption('已识别 PDF 页码：'+', '.join(map(str,sorted(saved['pages']))))
        default=min(saved['pages']) if saved else 1
        if saved and st.session_state.get(key+'_preview') not in saved['pages']:
            st.session_state[key+'_preview']=default
        page=int(st.number_input('原图预览 · PDF 页码',min_value=1,max_value=max(1,document.page_count),value=default,step=1,key=key+'_preview'))
        # Rendering only on request avoids spending time on every dashboard rerun.
        show=st.checkbox('显示该页原图',key=key+'_show')
        if show:
            left,right=st.columns([1.1,1])
            try:
                with left:st.image(page_preview(data,page),caption=f'{name} · PDF 第 {page} 页',width='stretch')
                with right:
                    text=saved['pages'][page].raw_text if saved and page in saved['pages'] else document.pages[page-1].text
                    st.text_area('识别文字',text,height=550,disabled=True,key=key+f'_text_{page}')
            except Exception:st.info('此页暂时无法预览。')
        if saved:
            document.ocr_verified=st.checkbox('我已核对 OCR 财务报表的金额、正负号、年份与单位',key=key+'_verified')
            st.caption('核对前可查看试算与图表；GPT 分析需核对后才能使用。')
    return document,report
