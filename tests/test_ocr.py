import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch,Mock
import pymupdf
from ocr_engine import parse_page_selection,ocr_page,OCRPage,_heading_kind,recognize_pdf,model_path
from pdf_parser import parse_pdf,assess_text_quality
from table_extractor import extract_financial_report
from financial_models import Confidence


class OCRTests(unittest.TestCase):
    def test_bundled_model_used_without_local_setup(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            bundled=root/'models'/'ch_PP-OCRv5_rec_mobile_infer.onnx'
            bundled.parent.mkdir()
            bundled.write_bytes(b'fixture')
            with patch('ocr_engine.ROOT',root):
                self.assertEqual(model_path(),bundled)

    def test_page_selection(self):
        self.assertEqual(parse_page_selection('3-5,4，7',10),[3,4,5,7])
        self.assertEqual(parse_page_selection('',10),[])
        for bad in ['0','11','5-2','1-10000','one','2;3']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):parse_page_selection(bad,10)

    def test_twenty_page_limit(self):
        with self.assertRaises(ValueError):parse_page_selection('1-20,22',30)

    def test_heading_not_narrative(self):
        self.assertEqual(_heading_kind('合并损益表'),'income')
        self.assertEqual(_heading_kind('合并资产负债表（续）'),'balance')
        self.assertIsNone(_heading_kind('请参阅合并资产负债表'))

    def test_low_confidence_numbers_are_not_usable(self):
        box=[[0,0],[20,0],[20,10],[0,10]]
        results=[[box,'1,234',.6],[box,'[1,200)',.99]]
        with patch('ocr_engine._recognize',return_value=(results,1)),patch('ocr_engine.normalize_text',side_effect=lambda s:s):
            page=ocr_page(Mock(),3)
        self.assertEqual(page.words[0][4],'OCR待核对')
        self.assertEqual(page.words[1][4],'(1,200)')
        self.assertEqual(page.low_confidence_count,1)
        self.assertIn('[1,200)',page.raw_text)

    def test_pdf_override_keeps_page_identity(self):
        doc=pymupdf.open();doc.new_page();doc.new_page();data=doc.tobytes();doc.close()
        page=OCRPage(2,[(0,0,20,10,'Revenue',0,0,0)],'Revenue')
        parsed=parse_pdf(data,'test.pdf',ocr_pages={2:page})
        self.assertEqual(parsed.page_count,2)
        self.assertEqual(parsed.pages[1].text,'Revenue')
        self.assertEqual(parsed.ocr_page_numbers,[2])
        self.assertFalse(parsed.ocr_verified)

    def test_ocr_to_financial_report(self):
        doc=pymupdf.open();doc.new_page();data=doc.tobytes();doc.close()
        def word(x,y,text):return (x,y,x+30,y+8,text,0,0,0)
        words=[word(10,10,'合并损益表'),word(10,25,'人民币千元'),word(200,40,'2025年'),word(300,40,'2024年'),
               word(10,60,'收入'),word(200,60,'120'),word(300,60,'100'),
               word(10,80,'年度利润'),word(200,80,'12'),word(300,80,'10')]
        report=extract_financial_report(data,ocr_pages={1:OCRPage(1,words,'原始 OCR')})
        self.assertIsNotNone(report.income_statement)
        revenue=next(m for m in report.income_statement.metrics if m.canonical_name=='revenue')
        self.assertEqual(revenue.values[0].normalized_value,120000)
        self.assertEqual(revenue.values[0].source_page,1)
        self.assertEqual(revenue.values[0].extraction_method,'local_ocr')
        self.assertEqual(revenue.values[0].confidence,Confidence.LOW)

    def test_scan_and_garbled_warnings(self):
        self.assertIn('OCR',assess_text_quality('',10)['warning'])
        self.assertIn('乱码',assess_text_quality('⏊ἷ㏏䚌堪'*200,1)['warning'])
        self.assertIsNone(assess_text_quality('收入资产负债权益现金流量年度报告'*100,1)['warning'])
