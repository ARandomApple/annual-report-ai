"""Actionable, non-technical explanations for local parsing and metric gaps."""
import re


FIELD_NAMES = {
    'revenue': '营业收入', 'net_income': '净利润',
    'operating_cash_flow': '经营现金流', 'operating_profit': '营业利润',
    'gross_profit': '毛利', 'cost_of_revenue': '营业成本',
    'total_assets': '总资产', 'total_liabilities': '总负债',
    'capital_expenditure': '资本支出',
}


def pdf_failure_message(error):
    detail = str(error).lower()
    if any(term in detail for term in ('password', 'encrypted', 'authenticate')):
        return '此 PDF 需要密码。请先在本机打开并导出无密码副本，再重新上传。'
    if any(term in detail for term in ('empty', 'broken', 'invalid', 'not a pdf', 'format')):
        return '文件不是可读取的 PDF，或内容已损坏。请重新下载原年报后上传。'
    return '无法读取此 PDF。请确认文件能在电脑上打开；若上传框直接显示 Error，请刷新网页后重新上传。'


def metric_issue(reason):
    if not reason:
        return ''
    result = reason
    for key, label in FIELD_NAMES.items():
        result = re.sub(rf'\b{re.escape(key)}\b', label, result)
    if '缺少' in reason or '缺失' in reason:
        action = '请核对下方报表是否识别了该科目；扫描件或乱码页可尝试 OCR 文字识别。'
    elif '币种' in reason or '单位' in reason:
        action = '请核对原报表的币种和金额单位；系统不会猜测或自动换汇。'
    elif '冲突' in reason or '多个' in reason or '重述' in reason:
        action = '请在详细数据中检查原列、重述列及重复行，系统暂不替你选用。'
    elif '分母' in reason or '基数' in reason:
        action = '该百分比不适合按常规方式计算，可直接查看两年的原值和差额。'
    else:
        action = '请在下方详细数据中核对来源、年份和计算口径。'
    return result.rstrip('。') + '。' + action


def report_warning_guidance(warnings):
    """Collapse repetitive parser warnings into a few user-actionable issues."""
    joined = '\n'.join(warnings).lower()
    items = []
    if any(term in joined for term in ('no financial statement', 'no financial rows', 'missing income_statement')):
        items.append('未找到完整财务报表。请先检查 PDF 是否可复制文字；扫描件可在「文字识别」中选择报表页。')
    if 'missing balance_sheet' in joined:
        items.append('未找到资产负债表，资产与负债类指标可能无法计算。请核对对应 PDF 页码。')
    if 'missing cash_flow_statement' in joined:
        items.append('未找到现金流量表，经营现金流类指标可能无法计算。请核对对应 PDF 页码。')
    if any(term in joined for term in ('unknown currency', 'unknown unit', 'unit; monetary')):
        items.append('部分金额的币种或单位不明确，相关指标不会计算。请核对报表标题附近的单位说明。')
    if any(term in joined for term in ('ambiguous/missing year', 'duplicate period columns')):
        items.append('部分表格的年份列无法可靠区分，已跳过这些行。请核对原表或尝试 OCR。')
    if any(term in joined for term in ('conflicting duplicate', 'restatement')):
        items.append('发现重复或重述口径，请在详细数据中核对，系统未自动选取其中一个数值。')
    if 'ocr' in joined:
        items.append('OCR 识别结果需与原图核对金额、正负号、年份和单位后再使用。')
    if warnings and not items:
        items.append('部分表格未能完整识别；已保留原始提示供核对。')
    return items
