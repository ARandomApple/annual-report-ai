import unittest
from unittest.mock import Mock
from copy import deepcopy
from table_extractor import _recover_revenue_total, _positional_rows
from test_table_extractor_step2 import assemble
from test_financial_analysis import report, statement, metric, ST


class EnglishReportRegression(unittest.TestCase):
    def test_wrapped_label_notes_and_footer(self):
        page=Mock()
        page.get_text.return_value=[(190,10,210,20,'2025'),(290,10,310,20,'2024'),
            (10,30,100,40,'Purchase of equipment,'),
            (10,45,120,55,'construction in progress'),(190,45,210,55,'(50)'),(290,45,310,55,'(40)'),
            (10,65,100,75,'Income tax expense'),(120,65,140,75,'12(a)'),(190,65,210,75,'(5)'),(290,65,310,75,'(4)'),
            (10,100,100,110,'Annual Report'),(190,100,210,110,'2025')]
        rows=_positional_rows(page)
        self.assertEqual(rows[1][0],'Purchase of equipment, construction in progress')
        self.assertEqual(rows[2][0],'Income tax expense')
        self.assertEqual(len(rows),3)

    def test_section_total_is_verified_for_every_year(self):
        rows=[['Revenues','',''],['Service A','60','50'],['Service B','40','30'],['6','100','80']]
        result=_recover_revenue_total(rows,{1:None,2:None})
        self.assertEqual(result[-1],['Revenues','100','80'])
        self.assertEqual(rows[-1][0],'6')
        bad=deepcopy(rows); bad[-1][2]='81'
        self.assertEqual(_recover_revenue_total(bad,{1:None,2:None}),bad)

    def test_no_heading_no_inferred_revenue(self):
        rows=[['A','60','50'],['B','40','30'],['','100','80']]
        self.assertEqual(_recover_revenue_total(rows,{1:None,2:None}),rows)

    def test_missing_segment_never_becomes_zero(self):
        rows=[['Revenues','',''],['A','60','50'],['B','—','30'],['','60','80']]
        self.assertEqual(_recover_revenue_total(rows,{1:None,2:None}),rows)

    def test_english_names_and_attribution_are_distinct(self):
        s=assemble([['','2025','2024'],['Profit for the year','20','18'],
                    ['Cost of revenues','(40)','(30)'],['Equity holders of the Company','19','17']])
        self.assertEqual([m.canonical_name for m in s.metrics],['net_income','cost_of_revenue',None])
        self.assertEqual(s.metrics[1].values[0].parsed_number.value,-40)

    def test_cash_flow_is_net_after_tax(self):
        s=assemble([['','2025','2024'],['Cash generated from operations','50','40'],
                    ['Net cash flows generated from operating activities','45','35']],stype=ST.CASH_FLOW)
        self.assertEqual([m.canonical_name for m in s.metrics],[None,'operating_cash_flow'])

    def test_reported_gross_profit_handles_expense_sign(self):
        r=report(); r.income_statement=statement(ST.INCOME_STATEMENT,{
            'revenue':{2025:100},'cost_of_revenue':{2025:-40},'gross_profit':{2025:60}})
        self.assertEqual(metric(r,'gross_margin').value,60)
        self.assertIn('gross_profit',metric(r,'gross_margin').formula)

    def test_conflicting_gross_profit_does_not_fall_back(self):
        r=report(); r.income_statement.metrics.extend(statement(ST.INCOME_STATEMENT,{'gross_profit':{2025:30}}).metrics)
        r.income_statement.metrics.extend(statement(ST.INCOME_STATEMENT,{'gross_profit':{2025:31}}).metrics)
        self.assertIsNone(metric(r,'gross_margin').value)
        self.assertIn('冲突',metric(r,'gross_margin').reason)
