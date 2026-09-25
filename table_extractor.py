"""Phase 2 Step 2: deterministic table extraction, with no UI or LLM dependency.

Only pages selected by Step 1 are processed. Ambiguous columns are skipped;
unknown units never produce a normalized monetary value.
"""
from dataclasses import dataclass, replace
from decimal import Decimal
import re
import pymupdf

from financial_extractor import (parse_financial_number, identify_financial_pages,
                                 detect_statement_page_ranges)
from financial_models import (Confidence, FinancialMetric, FinancialReport,
    FinancialValue, PeriodType, ReportingPeriod, Statement, StatementScope,
    StatementType, ValueType)
from metric_aliases import CANONICAL_METRICS, resolve_metric
from pdf_parser import parse_pdf, PdfPage


@dataclass
class TableData:
    rows: list[list[str]]
    source_page: int
    method: str
    context: str = ""


@dataclass
class UnitInfo:
    currency: str = ""
    multiplier: float | None = None


def detect_unit(text: str) -> UnitInfo:
    text = re.sub(r'每股[^，,;；\n]*|except[^;\n]*per.share[^;\n]*', '', text, flags=re.I)
    # Share counts can have a different scale from the monetary statement.
    text = re.sub(r'\bexcept\b[^\n]*', '', text, flags=re.I)
    currencies = []
    for code, pattern in [
        ('CNY', r'人民币|人民幣|\bRMB\b|\bCNY\b'),
        ('USD', r'美元|US\$|\bUSD\b|(?<![A-Za-z])\$(?![A-Za-z])'), ('HKD', r'港元|港币|HK\$|\bHKD\b'),
        ('SGD', r'新加坡元|(?<![A-Za-z])S\$|\bSGD\b'), ('EUR', r'欧元|\bEUR\b')]:
        if re.search(pattern, text, re.I): currencies.append(code)
    scales = set()
    # Ordered alternatives prevent 千元/元 from matching inside 百万元.
    for match in re.finditer(r'百万元|千万元|亿元|万元|千元|(?<![万千百亿])元|\bbillions?\b|\bmillions?\b|\bthousands?\b', text, re.I):
        token = match.group().lower()
        scales.add({'百万元':1e6, '千万元':1e7, '亿元':1e8, '万元':1e4,
                    '千元':1e3, '元':1}.get(token, 1e9 if token.startswith('billion') else 1e6 if token.startswith('million') else 1e3))
    return UnitInfo(currencies[0] if len(currencies)==1 else '',
                    scales.pop() if len(scales)==1 else None)


def detect_period(header: str, statement_type: StatementType) -> ReportingPeriod | None:
    years = set(re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)', header))
    if len(years) != 1: return None
    year = int(next(iter(years)))
    kind = PeriodType.POINT_IN_TIME if statement_type == StatementType.BALANCE_SHEET else PeriodType.ANNUAL
    if kind != PeriodType.POINT_IN_TIME:
        if re.search(r'quarter|three months|季度|三个月', header, re.I): kind = PeriodType.QUARTER
        elif re.search(r'half.year|six months|半年度|六个月', header, re.I): kind = PeriodType.HALF_YEAR
    end = None
    date = re.search(r'(?:19|20)\d{2}\s*[年/-]\s*(\d{1,2})\s*[月/-]\s*(\d{1,2})', header)
    if date:
        from datetime import date as calendar_date
        try: end = calendar_date(year, int(date[1]), int(date[2])).isoformat()
        except ValueError: return None
    elif re.search(r'December\s+31|31\s+December', header, re.I): end = f'{year}-12-31'
    return ReportingPeriod(year, kind, end_date=end, label=header,
        is_restated=bool(re.search(r'(?<!un)restated|重述|调整后|重列', header, re.I)))


def classify_columns(rows: list[list[str]], stype: StatementType):
    """Find explicit year columns; never infer years from value order."""
    width = max((len(r) for r in rows), default=0)
    headers = [''] * width
    last_header = -1
    for index, row in enumerate(rows[:15]):
        if any(detect_period(cell, stype) for cell in row):
            # Numeric data rows with values such as 2025 are not headers.
            if row and resolve_metric(row[0], CANONICAL_METRICS)[0]: break
            for col, cell in enumerate(row): headers[col] += ' ' + cell
            last_header = index
        elif last_header >= 0 and any(re.fullmatch(r'\s*(?:restated|重述|调整后|重列|原列|合并|公司|母公司|consolidated|group|company|parent)\s*', c, re.I) for c in row):
            for col, cell in enumerate(row): headers[col] += ' ' + cell
            last_header = index
        elif last_header >= 0: break
    columns = {i: detect_period(h, stype) for i, h in enumerate(headers)
               if i > 0 and not re.search(r'notes?|附注|增减|变动|change|%', h, re.I)}
    return {i:p for i,p in columns.items() if p is not None}, last_header


def _positional_rows(page):
    """Map words to physical year-column bands; preserve empty numeric cells."""
    lines = []
    for word in sorted(page.get_text('words'), key=lambda w: ((w[1]+w[3])/2, w[0])):
        y = (word[1]+word[3])/2
        line = next((line for line in reversed(lines[-4:]) if abs(line[0]-y) <= 3), None)
        if line is None:
            line = [y, []]
            lines.append(line)
        line[1].append(word)
    # Anchor on a physical line with two or more explicit year headers.
    anchor = None
    for index, (_, words) in enumerate(lines):
        years = sorted([w for w in words if re.fullmatch(r'(?:19|20)\d{2}(?:年度|年)?',w[4])],key=lambda w:w[0])
        other = ' '.join(w[4] for w in words if w not in years)
        if len(years) >= 2 and not resolve_metric(other,CANONICAL_METRICS)[0]:
            anchor=(index, years)
            break
    if anchor is None:
        # No reliable column geometry: let the text fallback try explicit separators.
        return []
    index, years = anchor
    centers=[(w[0]+w[2])/2 for w in years]
    gap=min(b-a for a,b in zip(centers,centers[1:]))
    boundaries=[centers[0]-gap/2]+[(a+b)/2 for a,b in zip(centers,centers[1:])]+[centers[-1]+gap/2]
    result=[['']+[w[4] for w in years]]
    for _, words in lines[index+1:]:
        cells=[[] for _ in range(len(years)+1)]
        for w in sorted(words,key=lambda w:w[0]):
            center=(w[0]+w[2])/2
            if center<boundaries[0]: cells[0].append(w[4])
            else:
                for col in range(len(years)):
                    if boundaries[col]<=center<boundaries[col+1]:
                        cells[col+1].append(w[4]); break
        row=[' '.join(c) for c in cells]
        # A note identifier before the year columns is metadata, not part of the label.
        row[0]=re.sub(r'\s+(?:\d{1,3}(?:\s*[,，]\s*\d{1,3})*(?:\([a-z]\))?|[（(][一二三四五六七八九十\d]+[）)])$', '', row[0])
        if re.match(r'^Annual Report\b', row[0], re.I):
            continue
        # Join a wrapped description only with explicit continuation cues.
        if (len(result)>1 and result[-1][0] and not any(result[-1][1:])
                and row[0] and (result[-1][0].endswith(',') or re.match(r'^[a-z]',row[0]))
                and not re.match(r'^(?:Note|Revenues|Attributable to|Cash flows from)\b',result[-1][0],re.I)):
            row[0]=result.pop()[0]+' '+row[0]
        result.append(row)
    return result


def extract_tables(page, page_number: int) -> list[TableData]:
    context = page.get_text()[:1500]
    found=[]
    try:
        for table in page.find_tables().tables:
            rows=[[cell or '' for cell in row] for row in table.extract()]
            if rows: found.append(TableData(rows,page_number,'pymupdf_table',context))
    except (ValueError, RuntimeError, AttributeError):
        pass
    if found and any(classify_columns(t.rows, StatementType.INCOME_STATEMENT)[0] for t in found):
        # Borderless PDFs may merge several row labels into one cell while
        # keeping the amount cells separate; positional text preserves rows.
        merged_labels = any(len((r[0] or '').splitlines()) > 1 and any(c.strip() for c in r[1:])
                            for t in found for r in t.rows if r)
        numeric_rows = [r for t in found for r in t.rows[1:] if r and any(c.strip() for c in r[1:])]
        unlabeled_rows = sum(not r[0].strip() for r in numeric_rows)
        if not merged_labels and not (len(numeric_rows) >= 4 and unlabeled_rows * 2 > len(numeric_rows)):
            return found
        positioned = _positional_rows(page)
        if classify_columns(positioned, StatementType.INCOME_STATEMENT)[0]:
            return [TableData(positioned,page_number,'positional',context)]
        return found
    rows=_positional_rows(page)
    if any(len(r)>1 for r in rows):
        return [TableData(rows,page_number,'positional',context)]
    if found: return found  # May be a continuation table with inherited headers.
    rows=[re.split(r'\t+| {2,}',line.strip()) for line in page.get_text().splitlines() if line.strip()]
    return [TableData(rows,page_number,'text_fallback',context)]


def _clean_label(label):
    # Remove numbering/operators only; preserve all financial terminology.
    label=re.sub(r'^\s*(?:[一二三四五六七八九十]+[、.]|[（(][一二三四五六七八九十\d]+[）)]|\d+[、.])\s*', '',label)
    return re.sub(r'^(?:加|减|其中)[：:]\s*', '',label)


def _column_scope(header):
    if re.search(r'合并|consolidated|group',header,re.I): return StatementScope.CONSOLIDATED
    if re.search(r'母公司|公司|parent|company',header,re.I): return StatementScope.PARENT
    return StatementScope.UNKNOWN


def _recover_revenue_total(rows, columns):
    """Recover a blank/note-only subtotal only if every year's segments sum exactly.

    Preserve the printed total, and expose the section context in its label.
    Never infer revenue from an arbitrary blank amount row or a partial sum.
    """
    output=[]; heading=None; segments=[]
    for original in rows:
        row=list(original)
        name, confidence, _=resolve_metric(_clean_label(row[0]),CANONICAL_METRICS) if row else (None,None,None)
        complete=bool(row) and all(c<len(row) for c in columns)
        if complete and name=='revenue' and confidence==Confidence.HIGH and not any(row[c].strip() for c in columns):
            heading=row[0]; segments=[]
        elif heading and complete:
            numbers=[parse_financial_number(row[c]).value for c in columns]
            if re.fullmatch(r'\s*(?:\d{1,3}(?:\([a-z]\))?)?\s*',row[0]):
                if len(segments)>=2 and all(n is not None for n in numbers) and all(
                    sum(Decimal(str(s[i])) for s in segments)==Decimal(str(n)) for i,n in enumerate(numbers)):
                    row[0]=heading
                heading=None; segments=[]
            elif name or not all(n is not None for n in numbers):
                heading=None; segments=[]
            else:
                segments.append(numbers)
        output.append(row)
    return output


def assemble_statement(tables: list[TableData], page_range, scope_filter=None) -> Statement:
    statement=Statement(page_range.statement_type, source_page_range=page_range, scope=scope_filter or page_range.scope)
    aliases=[m for m in CANONICAL_METRICS if page_range.statement_type.value in m.statement_types]
    inherited_columns={}; inherited_width=0; inherited_unit=UnitInfo()
    for table in tables:
        columns, header_end=classify_columns(table.rows, page_range.statement_type)
        width=max((len(r) for r in table.rows),default=0)
        if columns:
            headers={col:' '.join(row[col] for row in table.rows[:header_end+1] if col<len(row)) for col in columns}
            scopes={col:_column_scope(header) for col,header in headers.items()}
            has_scopes=any(scope!=StatementScope.UNKNOWN for scope in scopes.values())
            if has_scopes:
                if scope_filter is None:
                    statement.warnings.append(f'Page {table.source_page}: explicit scope columns require a scope filter; skipped.')
                    continue
                columns={col:period for col,period in columns.items() if scopes[col]==scope_filter}
            period_keys=[(p.year,p.period_type,p.end_date,p.is_restated) for p in columns.values()]
            if len(period_keys)!=len(set(period_keys)):
                statement.warnings.append(f'Page {table.source_page}: duplicate period columns without distinct scopes/restatement; skipped.')
                continue
            if not columns: continue
            inherited_columns=columns; inherited_width=width
        elif inherited_columns and width==inherited_width:
            columns=inherited_columns
            statement.warnings.append(f'Page {table.source_page}: inherited period columns from preceding table; verify alignment.')
        else:
            statement.warnings.append(f'Page {table.source_page}: ambiguous/missing year columns; table skipped.')
            continue
        unit=detect_unit(table.context)
        # Only inherit when no explicit unit/currency declaration is present.
        if not unit.currency and unit.multiplier is None and not re.search(r'单位|币种|currency|RMB|USD|HKD|SGD|million|thousand', table.context,re.I):
            unit=inherited_unit
        else: inherited_unit=unit
        if not unit.currency or unit.multiplier is None:
            statement.warnings.append(f'Page {table.source_page}: unknown currency or unit; monetary normalization unavailable.')
        data_rows=table.rows[header_end+1:]
        if page_range.statement_type==StatementType.INCOME_STATEMENT:
            recovered=_recover_revenue_total(data_rows,columns)
            if recovered!=data_rows:
                statement.warnings.append(f'Page {table.source_page}: revenue subtotal label recovered from section heading; segment sums verified for all year columns.')
            data_rows=recovered
        for row in data_rows:
            if not row or not row[0].strip(): continue
            if len(row) != width:
                statement.warnings.append(f'Page {table.source_page}: irregular row width; skipped {row[0]!r}.')
                continue
            if not any(row[col].strip() for col in columns if col < len(row)):
                continue  # Empty section headings are not financial value rows.
            label=row[0]
            canonical, match_confidence, _=resolve_metric(_clean_label(label),aliases)
            # Substring matching can turn a subtotal or growth row into a different metric.
            if match_confidence != Confidence.HIGH: canonical=None
            # In US statements "Gross margin" is often a monetary subtotal.
            if canonical=='gross_margin' and label.strip().lower()=='gross margin' and not any('%' in row[c] for c in columns):
                canonical='gross_profit'
            values=[]
            for col, period in columns.items():
                if col>=len(row): continue
                raw=row[col]; parsed=parse_financial_number(raw)
                missing=bool(re.fullmatch(r'\s*(?:—|–|-{1,3}|N/?A)?\s*',raw,re.I))
                if parsed.value is None and not missing: continue
                multiplier=unit.multiplier if unit.currency else None
                if canonical in ('eps_basic','eps_diluted') or re.search(r'每股|per.share',label,re.I):
                    parsed.value_type=ValueType.PER_SHARE; multiplier=1
                elif parsed.value_type==ValueType.PERCENTAGE or (re.search(r'率|margin|百分比|%',label,re.I) and canonical!='gross_profit'):
                    parsed.value_type=ValueType.PERCENTAGE; multiplier=1
                else: parsed.value_type=ValueType.MONETARY
                confidence=Confidence.MEDIUM if canonical and unit.currency and multiplier is not None else Confidence.LOW
                if table.method=='local_ocr':confidence=Confidence.LOW
                values.append(FinancialValue(parsed,period,unit.currency,multiplier,table.source_page,label,raw,table.method,confidence))
            if values and (canonical or any(v.parsed_number.value is not None for v in values)):
                metric=FinancialMetric(canonical,label,values, Confidence.MEDIUM if canonical else Confidence.LOW)
                # Keep duplicates separately, so contradictory source rows cannot overwrite one another.
                for old in statement.metrics:
                    if canonical and old.canonical_name==canonical:
                        for a in old.values:
                            for b in values:
                                if (a.period.year,a.period.period_type,a.period.end_date,a.period.is_restated)==(b.period.year,b.period.period_type,b.period.end_date,b.period.is_restated) and (a.parsed_number.value,a.unit,a.multiplier)!=(b.parsed_number.value,b.unit,b.multiplier):
                                    statement.warnings.append(f'Conflicting duplicate {canonical} for {b.period.year}; retained both source rows.')
                statement.metrics.append(metric)
    if not statement.metrics: statement.warnings.append('No financial rows extracted.')
    return statement


def detect_extraction_ranges(pages):
    """Adapt combined group/company headings without changing frozen Step 1.

    Only whole structural title lines are adapted, never narrative mentions.
    Actual scope is determined separately for each table column.
    """
    adapted=[]
    pattern=re.compile(r'^(?:(?:19|20)\d{2}\s*年\s*(?:度|\d{1,2}\s*月\s*\d{1,2}\s*日)?\s*)?'
        r'合并及(?:母)?公司(资产负债表|利润表|现金流量表|财务状况表)(?:[（(]续[）)])?\s*$')
    for page in pages:
        lines=page.text.splitlines()
        for i,line in enumerate(lines):
            match=pattern.fullmatch(line.strip())
            if match: lines[i]=match[1]
        text='\n'.join(lines)
        adapted.append(PdfPage(page.page_number,text,len(text)))
    ranges=detect_statement_page_ranges(identify_financial_pages(adapted),adapted)
    merged=[]
    for current in ranges:
        if (merged and current.start_page==merged[-1].end_page+1
                and current.statement_type==merged[-1].statement_type
                and current.scope==merged[-1].scope):
            previous=merged[-1]
            merged[-1]=replace(previous,continuation_pages=previous.continuation_pages+[current.anchor_page]+current.continuation_pages,
                end_page=current.end_page,evidence=previous.evidence+' Repeated adjacent statement heading.')
        else: merged.append(current)
    return merged


def _table_scopes(tables, stype):
    scopes=set()
    for table in tables:
        columns,end=classify_columns(table.rows,stype)
        for col in columns:
            scope=_column_scope(' '.join(r[col] for r in table.rows[:end+1] if col<len(r)))
            if scope!=StatementScope.UNKNOWN: scopes.add(scope)
    return sorted(scopes,key=lambda scope:scope.value)


def extract_financial_report(file_bytes: bytes, file_name: str='report.pdf', ocr_pages=None) -> FinancialReport:
    parsed=parse_pdf(file_bytes,file_name,ocr_pages=ocr_pages) if ocr_pages else parse_pdf(file_bytes,file_name)
    ranges=detect_extraction_ranges(parsed.pages)
    report=FinancialReport()
    if '\ufffd' in parsed.full_text:
        report.extraction_warnings.append('PDF text contains replacement characters; text encoding may prevent reliable statement detection. OCR is not enabled.')
    if not ranges:
        report.extraction_warnings.append('No financial statement ranges detected; no data extracted.')
        return report
    slots={StatementType.BALANCE_SHEET:'balance_sheet',StatementType.INCOME_STATEMENT:'income_statement',StatementType.CASH_FLOW:'cash_flow_statement'}
    priority={StatementScope.CONSOLIDATED:2,StatementScope.UNKNOWN:1,StatementScope.PARENT:0}
    with pymupdf.open(stream=file_bytes,filetype='pdf') as doc:
        for span in ranges:
            tables=[]
            for number in [span.anchor_page]+span.continuation_pages:
                try:
                    page_tables=extract_tables(ocr_pages[number],number) if ocr_pages and number in ocr_pages else extract_tables(doc[number-1],number)
                    if ocr_pages and number in ocr_pages:
                        for table in page_tables:table.method='local_ocr'
                    tables.extend(page_tables)
                except (ValueError, RuntimeError) as exc:
                    report.extraction_warnings.append(f'Page {number}: extraction failed ({type(exc).__name__}).')
            scopes=_table_scopes(tables,span.statement_type) or [None]
            for scope in scopes:
                statement=assemble_statement(tables,span,scope)
                slot=slots[span.statement_type]; old=getattr(report,slot)
                if old is None or priority[statement.scope]>priority[old.scope]:
                    if old: report.alternative_statements.append(old)
                    setattr(report,slot,statement)
                else: report.alternative_statements.append(statement)
                report.extraction_warnings.extend(statement.warnings)
    for slot in slots.values():
        if getattr(report,slot) is None: report.extraction_warnings.append(f'Missing {slot}.')
    statements=[getattr(report,slot) for slot in slots.values() if getattr(report,slot) is not None]
    currencies={v.unit for st in statements for m in st.metrics for v in m.values if v.unit}
    if len(currencies)==1: report.currency=next(iter(currencies))
    if ocr_pages:
        report.extraction_warnings.append('使用本地 OCR 识别部分页面；计算为待核对结果。请核对原图中的金额、正负号、年份与单位，低置信度数字不参与计算。')
    return report
