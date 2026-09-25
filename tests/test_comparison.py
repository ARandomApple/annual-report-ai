from copy import deepcopy
from io import BytesIO
from unittest.mock import patch
import unittest
from decimal import Decimal
from streamlit.testing.v1 import AppTest
from comparison_engine import ReportSource,compare_reports,comparison_evidence
from financial_models import FinancialReport,StatementScope as Scope,StatementType as ST,ValueType
from pdf_parser import PdfDocument,PdfPage
from test_financial_analysis import statement
from ai_analyst import Settings,analysis_key


def sources():
    result=[]
    for index,(name,years) in enumerate([('2025.pdf',{2025:120,2024:100}),('2024.pdf',{2024:100,2023:80})],1):
        doc=PdfDocument(name,page_count=5,pages=[PdfPage(5,'Source '+name,15)])
        r=FinancialReport(income_statement=statement(ST.INCOME_STATEMENT,{'revenue':years}))
        result.append(ReportSource('D'+str(index),doc,r,'hash'+str(index)))
    return result


def compare(items=None):return compare_reports(items or sources(),Scope.CONSOLIDATED,True)


class ComparisonTests(unittest.TestCase):
    def test_three_years_no_double_count(self):
        c=compare();self.assertEqual([p.year for p in c.points],[2023,2024,2025])
        self.assertEqual([p.value for p in c.points],[80,100,120])
        self.assertEqual(c.points[1].status,'matched');self.assertEqual(len(c.points[1].sources),2)
        self.assertEqual(c.points[1].growth_percent,25);self.assertEqual(c.points[2].growth_percent,20)

    def test_order_independent(self):
        a=compare();b=compare(list(reversed(sources())))
        self.assertEqual([(p.year,p.value,p.status) for p in a.points],[(p.year,p.value,p.status) for p in b.points])

    def test_conflict_blocks_adjacent_growth(self):
        items=sources();items[1].report.income_statement.metrics[0].values[0].parsed_number.value=99
        c=compare(items);self.assertIsNone(c.points[1].value);self.assertEqual(c.points[1].status,'conflict')
        self.assertIsNone(c.points[1].growth_percent);self.assertIsNone(c.points[2].growth_percent)

    def test_restated_same_value_not_merged(self):
        items=sources();items[1].report.income_statement.metrics[0].values[0].period.is_restated=True
        self.assertEqual(compare(items).points[1].status,'conflict')

    def test_currency_conflict(self):
        items=sources();items[1].report.income_statement.metrics[0].values[0].unit='USD'
        self.assertEqual(compare(items).points[1].status,'incompatible')

    def test_scale_normalization(self):
        items=sources();v=items[1].report.income_statement.metrics[0].values[0]
        v.parsed_number.value=.1;v.multiplier=1000
        self.assertEqual(compare(items).points[1].value,100)

    def test_missing_not_zero(self):
        items=sources();items[1].report.income_statement.metrics[0].values[0].parsed_number.value=None
        self.assertEqual(compare(items).points[1].status,'missing')

    def test_unknown_scale(self):
        items=sources();items[1].report.income_statement.metrics[0].values[0].multiplier=None
        self.assertEqual(compare(items).points[1].status,'incompatible')

    def test_no_scope_mixing(self):
        items=sources();items[1].report.income_statement.scope=Scope.PARENT
        c=compare(items);self.assertEqual([p.year for p in c.points],[2024,2025]);self.assertTrue(c.warnings)

    def test_confirmation_required(self):
        with self.assertRaises(ValueError):compare_reports(sources(),Scope.CONSOLIDATED)

    def test_known_company_mismatch(self):
        items=sources();items[0].report.company_name='A';items[1].report.company_name='B'
        with self.assertRaises(ValueError):compare(items)

    def test_duplicate_content(self):
        items=sources();items[1].content_hash=items[0].content_hash
        with self.assertRaises(ValueError):compare(items)

    def test_period_date_conflict(self):
        items=sources();items[1].report.income_statement.metrics[0].values[0].period.end_date='2024-06-30'
        self.assertEqual(compare(items).points[1].status,'incompatible')

    def test_nonconsecutive_no_growth(self):
        items=sources();items[1].report.income_statement.metrics[0].values[1].period.year=2022
        self.assertIsNone(compare(items).points[1].growth_percent)

    def test_negative_base(self):
        items=sources();items[1].report.income_statement.metrics[0].values[1].parsed_number.value=-80
        c=compare(items);self.assertEqual(c.points[1].change,180);self.assertIsNone(c.points[1].growth_percent)

    def test_unknown_scope(self):
        items=sources()
        for source in items:source.report.income_statement.scope=Scope.UNKNOWN
        self.assertTrue(all(p.value is None for p in compare_reports(items,Scope.UNKNOWN,True).points))

    def test_no_mutation(self):
        items=sources();before=deepcopy(items);compare(items);self.assertEqual(before,items)

    def test_citations_distinguish_same_page(self):
        p=comparison_evidence(compare())
        entry=next(e for e in p['evidence'] if e.get('year')==2024)
        self.assertEqual({s['document_id'] for s in entry['source_locations']},{'D1','D2'})
        self.assertEqual({s['page'] for s in entry['source_locations']},{5})
        ids=[e['id'] for e in p['evidence']];self.assertEqual(len(ids),len(set(ids)))

    def test_payload_identity_changes_with_file(self):
        a=comparison_evidence(compare());items=sources();items[0].content_hash='different'
        b=comparison_evidence(compare(items));self.assertNotEqual(analysis_key(a,Settings()),analysis_key(b,Settings()))


UI='''
import streamlit as st
from comparison_ui import render_comparison_upload
render_comparison_upload(st.session_state.loader_doc,st.session_state.loader_report)
'''


class ComparisonUITests(unittest.TestCase):
    def setup_app(self):
        entries=sources();files=[]
        for i,source in enumerate(entries):
            file=BytesIO(str(i).encode());file.name=source.document.file_name;files.append(file)
        app=AppTest.from_string(UI,default_timeout=20)
        app.session_state.loader_doc=lambda data,name:next(s.document for s in entries if s.document.file_name==name)
        app.session_state.loader_report=lambda data,name:next(s.report for s in entries if s.document.file_name==name)
        return app,files

    def test_two_uploads_require_confirmation_then_render(self):
        app,files=self.setup_app()
        with patch('streamlit.file_uploader',side_effect=lambda label,**kw:files[0] if kw['key']=='report_a' else files[1]),patch('ai_ui.get_settings',return_value=Settings()),patch('ai_ui.generate_analysis') as generate:
            app.run();self.assertFalse(app.exception);self.assertEqual(len(app.dataframe),0)
            next(c for c in app.checkbox if '同一家公司' in c.label).check().run();self.assertFalse(app.exception)
            frame=app.dataframe[0].value;self.assertEqual(set(frame['年份']),{'2023','2024','2025'})
            self.assertEqual(frame[frame['年份']=='2024'].iloc[0]['重叠核对'],'两份一致')
            self.assertTrue(app.button(key='comparison_generate_ai').disabled);generate.assert_not_called()

    def test_duplicate_upload_rejected(self):
        app,files=self.setup_app()
        with patch('streamlit.file_uploader',return_value=files[0]):
            app.run();self.assertFalse(app.exception)
            self.assertTrue(any('内容相同' in x.value for x in app.warning))


    def test_comparison_ai_cites_both_documents(self):
        app,files=self.setup_app()
        result={'analysis':{'claims':[{'topic':'重叠年度','kind':'fact','text':'两份重叠收入一致。','evidence_ids':['T2']}],
            'limitations':[]},'model':'test','input_tokens':10,'output_tokens':10}
        with patch('streamlit.file_uploader',side_effect=lambda label,**kw:files[0] if kw['key']=='report_a' else files[1]),patch('ai_ui.get_settings',return_value=Settings('test')),patch('ai_ui.generate_analysis',return_value=result) as generate:
            app.run();next(c for c in app.checkbox if '同一家公司' in c.label).check().run()
            app.text_input(key='user_api_key').set_value('comparison-user-key').run()
            app.button(key='comparison_generate_ai').click().run()
            self.assertFalse(app.exception);generate.assert_called_once()
            self.assertEqual(generate.call_args.args[1].api_key,'comparison-user-key')
            captions=' '.join(x.value for x in app.caption)
            self.assertIn('D1 · 2025.pdf · PDF 5 页',captions)
            self.assertIn('D2 · 2024.pdf · PDF 5 页',captions)
            request=generate.call_args.args[0]
            self.assertEqual(request['mode'],'two_reports_multi_year')

    def test_full_app_dual_upload_route(self):
        from pathlib import Path
        entries=sources();files=[]
        for i,source in enumerate(entries):
            file=BytesIO(('route'+str(i)).encode());file.name=source.document.file_name;files.append(file)
        def upload(label,**kw):
            return {'report_a':files[0],'report_b':files[1]}.get(kw.get('key'))
        with patch('streamlit.file_uploader',side_effect=upload), \
             patch('pdf_parser.parse_pdf',side_effect=lambda data,name:next(s.document for s in entries if s.document.file_name==name)), \
             patch('table_extractor.extract_financial_report',side_effect=lambda data,name:next(s.report for s in entries if s.document.file_name==name)), \
             patch('ai_ui.get_settings',return_value=Settings()):
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run()
            app.radio(key='report_mode').set_value('双年报 · 多年对比').run()
            self.assertFalse(app.exception);next(c for c in app.checkbox if '同一家公司' in c.label).check().run()
            self.assertFalse(app.exception);self.assertEqual(set(app.dataframe[0].value['年份']),{'2023','2024','2025'})

if __name__=='__main__':unittest.main()
