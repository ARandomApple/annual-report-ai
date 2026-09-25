"""Streamlit app interaction tests with controlled upload/extraction fixtures."""
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from financial_models import (FinancialReport, Statement, StatementType, StatementScope,
    FinancialMetric, FinancialValue, ParsedNumber, ReportingPeriod, PeriodType, ValueType)
from pdf_parser import PdfDocument, PdfPage
from report_ui import value_rows

APP = Path(__file__).resolve().parents[1] / 'app.py'


def fixture_report():
    def statement(scope, amount):
        value = FinancialValue(ParsedNumber(amount, ValueType.MONETARY, str(amount)),
            ReportingPeriod(2025, PeriodType.ANNUAL), 'CNY', 1, 1, '营业收入', str(amount))
        return Statement(StatementType.INCOME_STATEMENT,
            [FinancialMetric('revenue', '营业收入', [value])], scope=scope)
    return FinancialReport(income_statement=statement(StatementScope.CONSOLIDATED, 100),
        alternative_statements=[statement(StatementScope.PARENT, 60)])


class AppTests(unittest.TestCase):
    def run_uploaded(self, name, report=None, error=None):
        upload = BytesIO(b'fixture'); upload.name = name
        document = PdfDocument(name, page_count=1, full_text='Revenue',
            text_preview='Revenue', pages=[PdfPage(1, 'Revenue 100', 11)])
        patches = [patch('streamlit.file_uploader', return_value=upload),
                   patch('pdf_parser.parse_pdf', return_value=document),
                   patch('table_extractor.extract_financial_report', return_value=report, side_effect=error)]
        return patches

    def test_initial_empty(self):
        app = AppTest.from_file(str(APP)).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('请选择' in x.value for x in app.info))

    def test_checked_change_bridge_renders(self):
        from test_financial_analysis import report
        upload, parser, extractor = self.run_uploaded('bridge.pdf', report())
        with upload, parser, extractor:
            app = AppTest.from_file(str(APP)).run(timeout=20)
            self.assertFalse(app.exception)
            self.assertTrue(any('毛利变化' in element.value for element in app.markdown))

    def test_reconciled_segment_bridge_renders(self):
        from test_financial_analysis import report, statement
        r = report()
        segments = []
        for label, values in [('业务 A', {2025: 70, 2024: 60}),
                              ('业务 B', {2025: 50, 2024: 40})]:
            metric = statement(StatementType.INCOME_STATEMENT, {'segment': values}).metrics[0]
            metric.canonical_name = None
            metric.original_label = label
            segments.append(metric)
        r.income_statement.metrics = segments + r.income_statement.metrics
        upload, parser, extractor = self.run_uploaded('segments.pdf', r)
        with upload, parser, extractor:
            app = AppTest.from_file(str(APP)).run(timeout=20)
            self.assertFalse(app.exception)
            self.assertTrue(any('业务分部贡献' in element.value for element in app.markdown))

    def test_upload_and_scope_switch(self):
        upload, parser, extractor = self.run_uploaded('scopes.pdf', fixture_report())
        with upload, parser, extractor:
            app = AppTest.from_file(str(APP)).run(timeout=20)
            self.assertFalse(app.exception)
            self.assertEqual(next(d.value for d in app.dataframe if '报告原值' in d.value.columns).iloc[0]['报告原值'], '100')
            app.selectbox(key='report_scope').set_value(StatementScope.PARENT).run()
            self.assertFalse(app.exception)
            self.assertEqual(next(d.value for d in app.dataframe if '报告原值' in d.value.columns).iloc[0]['报告原值'], '60')
            self.assertTrue(any('Revenue 100' in x.value for x in app.text_area))

    def test_no_statements_not_success(self):
        upload, parser, extractor = self.run_uploaded('empty.pdf', FinancialReport(extraction_warnings=['No statements found']))
        with upload, parser, extractor:
            app = AppTest.from_file(str(APP)).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('未提取' in x.value for x in app.warning))
            self.assertFalse(any('财务数据已提取' in x.value for x in app.success))

    def test_extraction_error_keeps_document(self):
        upload, parser, extractor = self.run_uploaded('failed.pdf', error=RuntimeError('test'))
        with upload, parser, extractor:
            app = AppTest.from_file(str(APP)).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertTrue(any(x.value == 'Revenue' for x in app.text_area))

    def test_invalid_pdf(self):
        file = BytesIO(b'not pdf'); file.name = 'invalid.pdf'
        with patch('streamlit.file_uploader', return_value=file):
            app = AppTest.from_file(str(APP)).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('无法读取' in x.value for x in app.error))

    def test_display_retains_unknown_missing_and_duplicates(self):
        report = fixture_report(); statement = report.income_statement
        statement.metrics.append(statement.metrics[0])
        value = statement.metrics[0].values[0]
        value.multiplier = None
        rows = value_rows(statement)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['标准化数值'], '—')
        self.assertEqual(rows[0]['报告原值'], '100')
        value.parsed_number.value = None
        value.raw_value_str = '—'
        self.assertEqual(value_rows(statement)[0]['报告原值'], '—')


    def test_metrics_and_check_status_visible(self):
        from copy import deepcopy
        report=fixture_report()
        net=deepcopy(report.income_statement.metrics[0])
        net.canonical_name='net_income';net.original_label='净利润'
        net.values[0].parsed_number.value=10;net.values[0].raw_value_str='10'
        report.income_statement.metrics.append(net)
        upload,parser,extractor=self.run_uploaded('metrics.pdf',report)
        with upload,parser,extractor:
            app=AppTest.from_file(str(APP)).run(timeout=20)
            self.assertFalse(app.exception)
            frame=next(d.value for d in app.dataframe if '指标' in d.value.columns and '结果' in d.value.columns)
            row=frame[frame['指标']=='净利润率'].iloc[0]
            self.assertEqual(row['结果'],'10.00')
            self.assertEqual(row['单位'],'%')
            checks=next(d.value for d in app.dataframe if '校验' in d.value.columns)
            self.assertIn('无法校验',checks['结果'].values)

if __name__ == '__main__': unittest.main()
