"""All GPT tests are offline: mocked clients or HTTP MockTransport only."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import httpx
import openai
from streamlit.testing.v1 import AppTest
from ai_analyst import (Analysis,AnalysisError,Settings,build_evidence,analysis_key,
                        generate_analysis,get_settings)
from financial_models import StatementScope
from pdf_parser import PdfDocument,PdfPage
from test_app import fixture_report


def document():
    return PdfDocument('fixture.pdf',page_count=1,pages=[PdfPage(1,'Revenue 100',11)])


def payload(scope=StatementScope.CONSOLIDATED):
    return build_evidence(fixture_report(),document(),scope)


def output():
    return {'claims':[{'topic':'经营表现','kind':'fact','text':'已识别营业收入。','evidence_ids':['R1']}],
            'limitations':['仅分析提供的数据。']}


def client():
    mock=Mock()
    mock.responses.parse.return_value=SimpleNamespace(status='completed',
        output_parsed=Analysis.model_validate(output()),usage=SimpleNamespace(input_tokens=100,output_tokens=50))
    return mock


class AnalystTests(unittest.TestCase):
    def test_no_key_no_request(self):
        mock=client()
        with self.assertRaises(AnalysisError):generate_analysis(payload(),Settings(),mock)
        mock.responses.parse.assert_not_called()

    def test_evidence_is_scoped_and_contains_checks(self):
        p=payload();raw=[e for e in p['evidence'] if e['type']=='reported_value']
        self.assertEqual(raw[0]['raw_value'],'100')
        self.assertNotIn('60',[e['raw_value'] for e in raw])
        self.assertTrue(any(e['type']=='validation' for e in p['evidence']))
        self.assertTrue(any(e['type']=='source_excerpt' for e in p['evidence']))

    def test_payload_has_no_key(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'secret-never-emit'}):
            p=payload()
            self.assertNotIn('secret-never-emit',json.dumps(p))
            self.assertNotIn('secret-never-emit',repr(get_settings()))

    def test_request_contract(self):
        mock=client();r=generate_analysis(payload(),Settings('test'),mock)
        kwargs=mock.responses.parse.call_args.kwargs
        self.assertFalse(kwargs['store']);self.assertEqual(kwargs['max_output_tokens'],4000)
        self.assertEqual(kwargs['input'][0]['role'],'developer')
        self.assertEqual(r['input_tokens'],100)
        mock.responses.parse.assert_called_once()

    def test_invalid_citation_rejected(self):
        mock=client();mock.responses.parse.return_value.output_parsed.claims[0].evidence_ids=['NOT_IN_INPUT']
        with self.assertRaises(AnalysisError):generate_analysis(payload(),Settings('test'),mock)

    def test_missing_citation_rejected(self):
        mock=client();mock.responses.parse.return_value.output_parsed.claims[0].evidence_ids=[]
        with self.assertRaises(AnalysisError):generate_analysis(payload(),Settings('test'),mock)

    def test_incomplete_output_rejected(self):
        mock=client();mock.responses.parse.return_value.status='incomplete'
        with self.assertRaises(AnalysisError):generate_analysis(payload(),Settings('test'),mock)

    def test_refusal_rejected(self):
        mock=client();mock.responses.parse.return_value.output_parsed=None
        with self.assertRaises(AnalysisError):generate_analysis(payload(),Settings('test'),mock)

    def test_error_sanitized_no_retry(self):
        mock=client();req=httpx.Request('POST','https://api.openai.com/v1/responses')
        mock.responses.parse.side_effect=openai.AuthenticationError('secret-never-emit',response=httpx.Response(401,request=req),body=None)
        with self.assertRaises(AnalysisError) as caught:generate_analysis(payload(),Settings('test'),mock)
        self.assertNotIn('secret-never-emit',str(caught.exception));mock.responses.parse.assert_called_once()

    def test_timeout_no_retry(self):
        mock=client();mock.responses.parse.side_effect=openai.APITimeoutError(request=httpx.Request('POST','https://api.openai.com'))
        with self.assertRaises(AnalysisError) as caught:generate_analysis(payload(),Settings('test'),mock)
        self.assertIn('可能已计费',str(caught.exception));mock.responses.parse.assert_called_once()

    def test_payload_cap(self):
        p=payload();p['huge']='x'*120001;mock=client()
        with self.assertRaises(AnalysisError):generate_analysis(p,Settings('test'),mock)
        mock.responses.parse.assert_not_called()

    def test_session_identity(self):
        p=payload();settings=Settings('test');key=analysis_key(p,settings)
        self.assertNotEqual(key,analysis_key(payload(StatementScope.PARENT),settings))
        changed=deepcopy(p);changed['language']='en'
        self.assertNotEqual(key,analysis_key(changed,settings))
        self.assertNotEqual(key,analysis_key(p,Settings('test',model='other-model')))
        self.assertNotEqual(key,analysis_key(p,Settings('different-user-key')))
        changed=deepcopy(p);changed['evidence'][0]['raw_value']='101'
        self.assertNotEqual(key,analysis_key(changed,settings))

    def test_sdk_parses_structured_output_offline(self):
        requests=[]
        def handler(request):
            body=json.loads(request.content);requests.append(body)
            self.assertEqual(body['text']['format']['type'],'json_schema')
            self.assertTrue(body['text']['format']['strict'])
            return httpx.Response(200,json={'id':'resp_test','object':'response','created_at':0,
                'status':'completed','model':'gpt-5.4-mini',
                'output':[{'id':'msg_test','type':'message','role':'assistant','status':'completed',
                    'content':[{'type':'output_text','text':json.dumps(output()),'annotations':[]}]}],
                'usage':{'input_tokens':100,'output_tokens':50,'total_tokens':150}})
        with openai.OpenAI(api_key='test-offline',max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handler))) as sdk:
            result=generate_analysis(payload(),Settings('test'),sdk)
        self.assertEqual(len(requests),1);self.assertEqual(result['analysis'],output())


UI_CODE='''
import streamlit as st
from ai_ui import render_ai
render_ai(st.session_state.report,st.session_state.document,st.session_state.scope)
'''


class AIUITests(unittest.TestCase):
    def app(self):
        app=AppTest.from_string(UI_CODE)
        app.session_state.report=fixture_report();app.session_state.document=document()
        app.session_state.scope=StatementScope.CONSOLIDATED
        return app

    def test_no_key_button_disabled(self):
        with patch('ai_ui.get_settings',return_value=Settings()),patch('ai_ui.generate_analysis') as generate:
            app=self.app().run();self.assertFalse(app.exception)
            self.assertTrue(app.button(key='generate_ai').disabled);generate.assert_not_called()

    def test_only_click_calls_and_rerun_reuses(self):
        result={'analysis':output(),'model':'gpt-5.4-mini','input_tokens':100,'output_tokens':50}
        with patch('ai_ui.get_settings',return_value=Settings('server-key')),patch('ai_ui.generate_analysis',return_value=result) as generate:
            app=self.app().run();generate.assert_not_called()
            self.assertTrue(app.button(key='generate_ai').disabled)  # Server key is never a visitor fallback.
            app.text_input(key='user_api_key').set_value('user-key').run()
            app.button(key='generate_ai').click().run();self.assertFalse(app.exception)
            generate.assert_called_once()
            self.assertEqual(generate.call_args.args[1].api_key,'user-key')
            app.button(key='generate_ai').click().run()  # A queued click must not repeat a paid call.
            generate.assert_called_once();self.assertTrue(app.button(key='generate_ai').disabled)
            self.assertTrue(any(x.value=='已识别营业收入。' for x in app.text))
            app.selectbox(key='ai_language').set_value('en').run()
            generate.assert_called_once();self.assertFalse(any(x.value=='已识别营业收入。' for x in app.text))
            app.session_state.scope=StatementScope.PARENT;app.run();generate.assert_called_once()
            app.text_input(key='user_api_key').set_value('different-key').run()
            self.assertFalse(app.button(key='generate_ai').disabled)
            self.assertFalse(any(x.value=='已识别营业收入。' for x in app.text))
            app.button(key='clear_user_api_key').click().run()
            self.assertTrue(app.button(key='generate_ai').disabled)
            self.assertEqual(app.session_state['user_api_key'],'')

    def test_api_failure_preserves_page(self):
        with patch('ai_ui.get_settings',return_value=Settings()),patch('ai_ui.generate_analysis',side_effect=AnalysisError('连接超时')) as generate:
            app=self.app().run()
            app.text_input(key='user_api_key').set_value('user-key').run()
            app.button(key='generate_ai').click().run()
            self.assertFalse(app.exception);self.assertEqual(app.error[0].value,'连接超时')
            app.run();generate.assert_called_once()

if __name__=='__main__':unittest.main()
