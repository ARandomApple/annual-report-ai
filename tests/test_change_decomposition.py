import unittest

from change_decomposition import gross_profit_bridge, revenue_segment_bridge
from diagnostics import metric_issue, pdf_failure_message, report_warning_guidance
from financial_models import StatementScope as Scope, StatementType as ST
from test_financial_analysis import report, source, statement


class DecompositionTests(unittest.TestCase):
    def test_gross_profit_bridge_reconciles(self):
        bridge, reason = gross_profit_bridge(report(), Scope.CONSOLIDATED)
        self.assertEqual(reason, '')
        self.assertEqual(bridge['kind'], 'gross_profit')
        self.assertEqual((bridge['start'], bridge['revenue_effect'], bridge['cost_effect'], bridge['end']),
                         (20, 20, -10, 30))
        self.assertFalse(bridge['reported_gross_profit_verified'])

    def test_gross_profit_mismatch_blocks_chart(self):
        r = report()
        r.income_statement.metrics.extend(statement(ST.INCOME_STATEMENT, {
            'gross_profit': {2025: 50, 2024: 20}}).metrics)
        bridge, reason = gross_profit_bridge(r, Scope.CONSOLIDATED)
        self.assertIsNone(bridge)
        self.assertIn('不一致', reason)

    def test_missing_and_currency_conflicts_block_chart(self):
        r = report()
        source(r, ST.INCOME_STATEMENT, 'cost_of_revenue', 2024).parsed_number.value = None
        self.assertIsNone(gross_profit_bridge(r, Scope.CONSOLIDATED)[0])
        r = report()
        source(r, ST.INCOME_STATEMENT, 'cost_of_revenue', 2024).unit = 'USD'
        self.assertIsNone(gross_profit_bridge(r, Scope.CONSOLIDATED)[0])

    def test_exact_segment_totals_enable_revenue_bridge(self):
        r = report()
        segments = []
        for label, amounts in [('业务 A', {2025: 70, 2024: 60}),
                               ('业务 B', {2025: 50, 2024: 40})]:
            metric = statement(ST.INCOME_STATEMENT, {'segment': amounts}).metrics[0]
            metric.canonical_name = None
            metric.original_label = label
            segments.append(metric)
        r.income_statement.metrics = segments + r.income_statement.metrics
        bridge, reason = revenue_segment_bridge(r, Scope.CONSOLIDATED)
        self.assertEqual(reason, '')
        self.assertEqual(bridge['kind'], 'revenue_segments')
        self.assertEqual(bridge['parts'], [('业务 A', 10), ('业务 B', 10)])
        segments[1].values[0].parsed_number.value = 49
        self.assertIsNone(revenue_segment_bridge(r, Scope.CONSOLIDATED)[0])


class GuidanceTests(unittest.TestCase):
    def test_metric_reason_uses_readable_name_and_action(self):
        message = metric_issue('缺少 cost_of_revenue（2025）')
        self.assertIn('营业成本', message)
        self.assertIn('OCR', message)

    def test_pdf_and_report_failure_guidance(self):
        self.assertIn('密码', pdf_failure_message(ValueError('document encrypted')))
        self.assertIn('年份列', report_warning_guidance(['Page 5: ambiguous/missing year columns'])[0])


if __name__ == '__main__':
    unittest.main()
