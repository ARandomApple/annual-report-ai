import unittest

from dashboard_ui import dashboard_data
from dashboard_component import dashboard_html
from financial_models import StatementScope as Scope, StatementType as ST
from test_financial_analysis import report, source


class DashboardTests(unittest.TestCase):
    def test_default_order_and_source_linked_values(self):
        data = dashboard_data(report(), Scope.CONSOLIDATED)
        self.assertEqual([c['id'] for c in data['cards'][:4]],
                         ['revenue', 'net_income', 'operating_cash_flow', 'revenue_growth'])
        revenue = data['cards'][0]
        self.assertEqual(revenue['current']['year'], 2025)
        self.assertEqual(revenue['current']['pages'], [5])
        self.assertEqual(revenue['comparison']['previous']['year'], 2024)
        self.assertEqual(revenue['display_unit'], '元')
        self.assertAlmostEqual(revenue['comparison']['delta'], 20)
        self.assertAlmostEqual(revenue['comparison']['rate'], 20)
        self.assertFalse(revenue['can_trend'])
        self.assertAlmostEqual(data['cards'][3]['current']['value'], 20)
        self.assertEqual(len(data['cards']), 15)

    def test_missing_value_is_not_plotted_as_zero(self):
        r = report()
        source(r, ST.INCOME_STATEMENT, 'net_income').parsed_number.value = None
        card = next(c for c in dashboard_data(r, Scope.CONSOLIDATED)['cards']
                    if c['id'] == 'net_income')
        self.assertIsNone(card['current'])
        self.assertNotIn(2025, [p['year'] for p in card['points']])
        self.assertIn('缺失', card['reason'])

    def test_currency_change_excludes_incomparable_year(self):
        r = report()
        source(r, ST.INCOME_STATEMENT, 'revenue', 2024).unit = 'USD'
        card = dashboard_data(r, Scope.CONSOLIDATED)['cards'][0]
        self.assertEqual([p['year'] for p in card['points']], [2025])
        self.assertIsNone(card['comparison'])

    def test_three_consecutive_years_enable_trend(self):
        from copy import deepcopy
        r = report()
        value = deepcopy(source(r, ST.INCOME_STATEMENT, 'revenue', 2024))
        value.period.year = 2023
        value.parsed_number.value = 90
        r.income_statement.metrics[0].values.append(value)
        self.assertTrue(dashboard_data(r, Scope.CONSOLIDATED)['cards'][0]['can_trend'])

    def test_fiscal_period_mismatch_blocks_direct_comparison(self):
        r = report()
        for metric in r.income_statement.metrics:
            for value in metric.values:
                value.period.end_date = f'{value.period.year}-' + ('06-30' if value.period.year == 2024 else '12-31')
        card = dashboard_data(r, Scope.CONSOLIDATED)['cards'][0]
        self.assertIsNone(card['comparison'])

    def test_untrusted_text_is_not_executable_html(self):
        html = dashboard_html({'year': 2025, 'cards': [],
                               'message': '</script><script>alert(1)</script>'})
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertIn('\\u003c/script\\u003e', html)


if __name__ == '__main__':
    unittest.main()
