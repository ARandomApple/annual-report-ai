"""Explicit-button AI calls, with session-only results scoped to exact evidence."""
import streamlit as st
from ai_analyst import (AnalysisError, Settings, get_settings, build_evidence, analysis_key,
                        generate_analysis)


def render_ai(report, document, scope, payload_builder=None, key_prefix=""):
    def key(name):
        return f"{key_prefix}_{name}" if key_prefix else name
    st.subheader('GPT 分析 / AI interpretation')
    if document is not None and document.ocr_page_numbers and not document.ocr_verified:
        st.info('请先在 OCR 区域核对财务数据并确认，再生成 GPT 分析。')
        return
    with st.expander('配置我的 OpenAI API Key / My API key',
                     expanded=not bool(st.session_state.get('user_api_key'))):
        st.text_input('OpenAI API Key', type='password', key='user_api_key',
            help='仅保留在当前网页会话中；关闭会话后需重新填写。')
        st.caption('AI 请求使用你自己的 API 账户并由该账户计费。密钥不会写入项目文件或数据库；服务器在请求期间会处理它。')
        st.button('移除本次会话的 Key', key='clear_user_api_key',
            on_click=lambda: st.session_state.__setitem__('user_api_key',''))
    base=get_settings()
    user_key=st.session_state.get('user_api_key','').strip()
    if user_key.lower().startswith(('your_', 'your-', 'sk-your')):
        user_key=''
    # Never use a server-side key for a visitor's paid request.
    settings=Settings(user_key,base.model,base.max_output_tokens)
    st.caption(f'模型：{settings.model} · 仅点击生成时调用付费 API；最多输出 {settings.max_output_tokens} tokens。')
    language=st.selectbox('分析语言 / Output language',['zh','en'],
        format_func=lambda value:'中文' if value=='zh' else 'English',key=key('ai_language'))
    if not settings.api_key:
        st.info('请在上方填写你自己的 OpenAI API Key，才能生成 AI 分析。无需把密钥发到聊天中。')
    try:
        payload=payload_builder(language) if payload_builder else build_evidence(report,document,scope,language)
    except (AnalysisError,ValueError):
        st.warning('当前材料不足或数据异常，暂时无法生成 AI 分析，请先检查提取结果。')
        return
    fingerprint=analysis_key(payload,settings)
    saved=st.session_state.get(key('ai_result'))
    current=saved if saved and saved['fingerprint']==fingerprint else None
    with st.expander('查看将发送的分析材料 / Preview data sent to OpenAI'):
        st.caption('只发送这里列出的财务数据、校验信息和截取原文，不上传完整 PDF。分析材料会发送给 OpenAI。')
        st.json(payload,expanded=False)
    if any(e.get('status')=='failed' for e in payload['evidence']):
        st.warning('当前数据有校验失败项，AI 分析必须结合这些限制阅读。')
    clicked=st.button('已生成本次分析' if current else '生成 AI 分析',key=key('generate_ai'),
        disabled=not settings.api_key or current is not None,type='primary')
    if clicked and current is None:
        with st.spinner('GPT 正在分析，最长等待约 60 秒…'):
            try:
                result=generate_analysis(payload,settings)
                current={'fingerprint':fingerprint,'result':result}
                st.session_state[key('ai_result')]=current
                st.session_state.pop(key('ai_error'),None)
            except AnalysisError as exc:
                st.session_state[key('ai_error')]={'fingerprint':fingerprint,'message':str(exc)}
    error=st.session_state.get(key('ai_error'))
    if error and error['fingerprint']==fingerprint:
        st.error(error['message'])
        st.caption('重新点击将发起一次新请求，并可能再次产生费用。')
    if current:
        result=current['result']
        evidence={entry['id']:entry for entry in payload['evidence']}
        st.caption('AI 生成内容；已检查引用编号有效性，未自动验证每个结论的正确性，请结合原文核对。')
        for claim in result['analysis']['claims']:
            st.markdown('**事实陈述**' if claim['kind']=='fact' else '**分析推测**')
            st.text(claim['topic'])
            st.text(claim['text'])
            pages=sorted({p for identifier in claim['evidence_ids'] for p in evidence[identifier]['pages']})
            locations=[loc for identifier in claim['evidence_ids'] for loc in evidence[identifier].get('source_locations',[])]
            if locations:
                references=list(dict.fromkeys(f"{loc['document_id']} · {loc['file_name']} · PDF {loc['page']} 页" for loc in locations))
                st.caption('依据：'+', '.join(claim['evidence_ids'])+' · '+'；'.join(references))
            else:
                st.caption('依据：'+', '.join(claim['evidence_ids'])+' · PDF 页码：'+(', '.join(map(str,pages)) or '无页码'))
        if result['analysis']['limitations']:
            st.write('分析限制')
            for limitation in result['analysis']['limitations']:st.text('• '+limitation)
        st.caption(f"本次 API 用量：输入 {result['input_tokens']} tokens，输出 {result['output_tokens']} tokens。实际费用以 API 账户账单为准。")
        if st.button('清除本次结果',key=key('clear_ai')):
            st.session_state.pop(key('ai_result'),None)
            st.rerun()
