"""Focused regression fixtures; no generated PDFs or network calls."""
import unittest
from unittest.mock import Mock, patch
from table_extractor import (TableData, detect_unit, detect_period, classify_columns,
    assemble_statement, extract_tables, extract_financial_report, detect_extraction_ranges)
from financial_models import StatementPageRange,StatementType as ST, StatementScope,PeriodType,ValueType


def span(stype=ST.INCOME_STATEMENT):
    return StatementPageRange(stype,1,scope=StatementScope.CONSOLIDATED)


def assemble(rows,context='人民币百万元',stype=ST.INCOME_STATEMENT):
    return assemble_statement([TableData(rows,1,'pymupdf_table',context)],span(stype))


class Step2Tests(unittest.TestCase):
    def test_chinese_units(self):
        for text,scale in [('人民币元',1),('人民币千元',1000),('人民币百万元',1e6),('人民币万元',1e4)]:
            with self.subTest(text=text):
                unit=detect_unit(text); self.assertEqual((unit.currency,unit.multiplier),('CNY',scale))

    def test_english_units(self):
        for text,currency,scale in [('USD thousands','USD',1000),('US$ million','USD',1e6),('SGD million','SGD',1e6),('HK$ million','HKD',1e6)]:
            with self.subTest(text=text):
                unit=detect_unit(text); self.assertEqual((unit.currency,unit.multiplier),(currency,scale))

    def test_unknown_and_conflicting_units(self):
        self.assertIsNone(detect_unit('Revenue').multiplier)
        self.assertEqual(detect_unit('USD and SGD million').currency,'')
        self.assertIsNone(detect_unit('USD million / thousands').multiplier)

    def test_periods(self):
        period=detect_period('2024年12月31日（重述）',ST.BALANCE_SHEET)
        self.assertEqual(period.period_type,PeriodType.POINT_IN_TIME)
        self.assertEqual(period.end_date,'2024-12-31'); self.assertTrue(period.is_restated)
        self.assertEqual(detect_period('Six months ended 2025',ST.INCOME_STATEMENT).period_type,PeriodType.HALF_YEAR)
        self.assertEqual(detect_period('2025 第三季度',ST.INCOME_STATEMENT).period_type,PeriodType.QUARTER)
        self.assertIsNone(detect_period('2025 / 2024',ST.INCOME_STATEMENT))
        self.assertIsNone(detect_period('2025年13月40日',ST.BALANCE_SHEET))

    def test_reversed_years_notes_and_change(self):
        s=assemble([['项目','附注','2024年度','2025年度','2025变动%'],['营业收入','12','100','120','20%']])
        v=s.metrics[0].values
        self.assertEqual([(x.period.year,x.parsed_number.value) for x in v],[(2024,100),(2025,120)])
        self.assertEqual(v[1].normalized_value,120e6)
        self.assertEqual((v[1].raw_label,v[1].raw_value_str,v[1].source_page),('营业收入','120',1))

    def test_missing_negative_eps_percentage(self):
        s=assemble([['项目','2025','2024'],['净利润','(123)','—'],['基本每股收益','0.36','0.30'],['毛利率','7.2%','6%']])
        net,eps,pct=s.metrics
        self.assertEqual(net.values[0].normalized_value,-123e6)
        self.assertIsNone(net.values[1].normalized_value)
        self.assertEqual(eps.values[0].normalized_value,.36)
        self.assertEqual(eps.values[0].parsed_number.value_type,ValueType.PER_SHARE)
        self.assertEqual(pct.values[0].normalized_value,7.2)

    def test_no_year_means_skip(self):
        s=assemble([['Revenue','123','456']],context='USD million')
        self.assertFalse(s.metrics); self.assertTrue(s.warnings)

    def test_unknown_unit_not_normalized(self):
        s=assemble([['','2025'],['Revenue','123']],context='')
        self.assertIsNone(s.metrics[0].values[0].normalized_value)
        self.assertEqual(s.metrics[0].values[0].raw_value_str,'123')

    def test_ambiguous_label_kept_unmapped(self):
        s=assemble([['','2025'],['Revenue growth','10'],['Revenue','100']],context='USD million')
        self.assertIsNone(s.metrics[0].canonical_name)
        self.assertEqual(s.metrics[1].canonical_name,'revenue')

    def test_duplicate_conflict_preserved(self):
        s=assemble([['','2025'],['Revenue','100'],['Revenue','200']],context='USD million')
        self.assertEqual(len(s.metrics),2)
        self.assertTrue(any('Conflicting' in w for w in s.warnings))

    def test_continuation_inherits_headers(self):
        tables=[TableData([['','2025','2024'],['Revenue','100','90']],1,'pymupdf_table','USD million'),
                TableData([['Net income','10','9']],2,'pymupdf_table','')]
        s=assemble_statement(tables,span())
        self.assertEqual(s.metrics[1].values[0].source_page,2)
        self.assertEqual(s.metrics[1].values[0].normalized_value,10e6)
        self.assertTrue(any('inherited' in w for w in s.warnings))

    def test_changed_width_not_inherited(self):
        tables=[TableData([['','2025','2024'],['Revenue','100','90']],1,'pymupdf_table','USD million'),
                TableData([['Net income','5','10','9']],2,'pymupdf_table','')]
        self.assertEqual(len(assemble_statement(tables,span()).metrics),1)

    def test_restated_columns_separate(self):
        s=assemble([['','2024','2024'],['','原列','重述'],['Revenue','100','110']],context='USD million')
        a,b=s.metrics[0].values
        self.assertFalse(a.period.is_restated); self.assertTrue(b.period.is_restated)

    def test_table_layer(self):
        page=Mock(); page.get_text.return_value='USD million'
        table=Mock(); table.extract.return_value=[['','2025'],['Revenue','100']]
        page.find_tables.return_value.tables=[table]
        result=extract_tables(page,7)
        self.assertEqual(result[0].method,'pymupdf_table'); self.assertEqual(result[0].source_page,7)

    def test_positional_layer(self):
        page=Mock(); page.find_tables.return_value.tables=[]
        words=[(200,10,230,20,'2025'),(300,10,330,20,'2024'),
               (10,30,60,40,'Revenue'),(200,30,220,40,'100'),(300,30,320,40,'90')]
        page.get_text.side_effect=lambda *args: words if args else 'USD million'
        result=extract_tables(page,2)
        s=assemble_statement(result,span())
        self.assertEqual(s.metrics[0].values[0].parsed_number.value,100)
        self.assertEqual(s.metrics[0].values[1].period.year,2024)
        self.assertEqual(result[0].method,'positional')

    def test_text_layer(self):
        page=Mock(); page.find_tables.side_effect=RuntimeError('unsupported')
        page.get_text.side_effect=lambda *args: [] if args else 'USD million\nItem\t2025\t2024\nRevenue\t100\t90'
        result=extract_tables(page,2)
        self.assertEqual(result[0].method,'text_fallback')
        self.assertEqual(len(assemble_statement(result,span()).metrics),1)


    def test_unknown_currency_no_normalization(self):
        s=assemble([['','2025'],['Revenue','123']],context='Amounts in millions')
        self.assertIsNone(s.metrics[0].values[0].normalized_value)

    def test_eps_exception_does_not_conflict_with_scale(self):
        u=detect_unit('人民币百万元，每股收益为人民币元')
        self.assertEqual(u.multiplier,1e6)

    def test_new_page_overrides_years_and_units(self):
        tables=[TableData([['','2025','2024'],['Revenue','100','90']],1,'pymupdf_table','USD million'),
                TableData([['','2024','2025'],['Net income','9000','10000']],2,'pymupdf_table','USD thousands')]
        s=assemble_statement(tables,span())
        self.assertEqual(s.metrics[1].values[0].period.year,2024)
        self.assertEqual(s.metrics[1].values[0].normalized_value,9e6)

    def test_positional_blank_preserved(self):
        page=Mock(); page.find_tables.return_value.tables=[]
        words=[(200,10,230,20,'2025'),(300,10,330,20,'2024'),
               (10,30,60,40,'Revenue'),(300,30,320,40,'90')]
        page.get_text.side_effect=lambda *args: words if args else 'USD million'
        s=assemble_statement(extract_tables(page,1),span())
        self.assertIsNone(s.metrics[0].values[0].normalized_value)
        self.assertEqual(s.metrics[0].values[1].normalized_value,90e6)

    def test_irregular_row_skipped(self):
        s=assemble([['','Notes','2025','2024'],['Revenue','100','90']])
        self.assertFalse(s.metrics)

    def test_no_ranges_reports_failure(self):
        from pdf_parser import PdfDocument
        with patch('table_extractor.parse_pdf',return_value=PdfDocument('bad.pdf',full_text='\ufffd')):
            report=extract_financial_report(b'unused')
        self.assertIsNone(report.income_statement)
        self.assertTrue(any('No financial statement' in w for w in report.extraction_warnings))
        self.assertTrue(any('encoding' in w for w in report.extraction_warnings))

    def test_report_assembly_keeps_parent_separate(self):
        from pdf_parser import PdfDocument
        consolidated=span()
        parent=StatementPageRange(ST.INCOME_STATEMENT,2,scope=StatementScope.PARENT)
        doc=Mock(); doc.__enter__=Mock(return_value=doc); doc.__exit__=Mock(return_value=False)
        doc.__getitem__=Mock(return_value=Mock())
        tables=[TableData([['','2025'],['Revenue','100']],1,'pymupdf_table','USD million')]
        with patch('table_extractor.parse_pdf',return_value=PdfDocument('sample.pdf')), \
             patch('table_extractor.detect_statement_page_ranges',return_value=[parent,consolidated]), \
             patch('table_extractor.pymupdf.open',return_value=doc), \
             patch('table_extractor.extract_tables',return_value=tables):
            report=extract_financial_report(b'unused')
        self.assertEqual(report.income_statement.scope,StatementScope.CONSOLIDATED)
        self.assertEqual(len(report.alternative_statements),1)
        self.assertEqual(report.alternative_statements[0].scope,StatementScope.PARENT)
        self.assertTrue(any('Missing balance_sheet' in w for w in report.extraction_warnings))


    def test_mixed_scope_columns_not_merged(self):
        table=TableData([['','2025 合并','2024 合并','2025 公司','2024 公司'],
                         ['一、营业收入','100','90','60','50']],1,'pymupdf_table','人民币元')
        group=assemble_statement([table],span(),StatementScope.CONSOLIDATED)
        parent=assemble_statement([table],span(),StatementScope.PARENT)
        self.assertEqual([v.normalized_value for v in group.metrics[0].values],[100,90])
        self.assertEqual([v.normalized_value for v in parent.metrics[0].values],[60,50])
        self.assertFalse(assemble_statement([table],span()).metrics)

    def test_ambiguous_duplicate_year_columns_skipped(self):
        s=assemble([['','2025','2025'],['Revenue','100','60']],context='USD million')
        self.assertFalse(s.metrics)

    def test_combined_heading_adapter_is_structural(self):
        from pdf_parser import PdfPage
        text='2025 年度合并及公司利润表\n2025 年 2024 年\n营业收入 100 90\n净利润 20 10\n营业成本 80 80\n人民币元'
        pages=[PdfPage(1,text,len(text))]
        ranges=detect_extraction_ranges(pages)
        self.assertEqual(len(ranges),1)
        self.assertEqual(ranges[0].statement_type,ST.INCOME_STATEMENT)
        narrative=text.replace('2025 年度合并及公司利润表','根据合并及公司利润表我们可以发现收入增长')
        self.assertFalse(detect_extraction_ranges([PdfPage(1,narrative,len(narrative))]))
        self.assertEqual(pages[0].text,text)

    def test_unknown_unit_validation_does_not_crash(self):
        from validation_engine import validate_balance_sheet_equation
        s=assemble([['','2025'],['Total assets','100'],['Total liabilities','60'],['Total equity','40']],context='',stype=ST.BALANCE_SHEET)
        result=validate_balance_sheet_equation(s)
        self.assertFalse(result.passed)

    def test_balance_sheet_validation(self):
        from validation_engine import validate_balance_sheet_equation
        s=assemble([['','2025'],['Total assets','100'],['Total liabilities','60'],['Total equity','40']],context='USD million',stype=ST.BALANCE_SHEET)
        self.assertTrue(validate_balance_sheet_equation(s,1e6).passed)


    def test_scope_on_separate_header_row(self):
        table=TableData([['','2025','2024','2025','2024'],['','合并','合并','公司','公司'],
                         ['营业收入','100','90','60','50']],1,'pymupdf_table','人民币元')
        result=assemble_statement([table],span(),StatementScope.CONSOLIDATED)
        self.assertEqual([v.normalized_value for v in result.metrics[0].values],[100,90])


    def test_empty_section_heading_not_a_duplicate_metric(self):
        s=assemble([['','2025','2024'],['基本每股收益','',''],['其中：基本每股收益','0.36','0.30']])
        self.assertEqual(len(s.metrics),1)
        self.assertEqual(s.metrics[0].canonical_name,'eps_basic')
        self.assertFalse(any('Conflicting' in w for w in s.warnings))

if __name__=='__main__': unittest.main()
