from copy import deepcopy
from decimal import Decimal
import unittest
from financial_models import (FinancialReport, Statement, StatementType as ST,
    StatementScope as Scope, FinancialMetric, FinancialValue, ParsedNumber,
    ReportingPeriod, PeriodType, ValueType)
from financial_engine import compute_metrics
from validation_engine import run_all_validations


def statement(stype, data, scope=Scope.CONSOLIDATED):
    metrics=[]
    for name, years in data.items():
        values=[]
        for year, amount in years.items():
            period=ReportingPeriod(year, PeriodType.POINT_IN_TIME if stype==ST.BALANCE_SHEET else PeriodType.ANNUAL)
            values.append(FinancialValue(ParsedNumber(amount,ValueType.MONETARY,str(amount)),period,
                'CNY',1,5,name,str(amount)))
        metrics.append(FinancialMetric(name,name,values))
    return Statement(stype,metrics,scope=scope)


def report():
    return FinancialReport(
        income_statement=statement(ST.INCOME_STATEMENT,{
            'revenue':{2025:120,2024:100},'net_income':{2025:12,2024:8},
            'operating_profit':{2025:18,2024:15},'cost_of_revenue':{2025:90,2024:80}}),
        balance_sheet=statement(ST.BALANCE_SHEET,{
            'total_assets':{2025:200,2024:180},'total_liabilities':{2025:80,2024:70},
            'total_equity':{2025:120,2024:110}}),
        cash_flow_statement=statement(ST.CASH_FLOW,{
            'operating_cash_flow':{2025:30,2024:20},'capital_expenditure':{2025:-10,2024:8}}))


def source(report,stype,name,year=2025):
    st={ST.INCOME_STATEMENT:report.income_statement,ST.BALANCE_SHEET:report.balance_sheet,
        ST.CASH_FLOW:report.cash_flow_statement}[stype]
    return next(v for m in st.metrics if m.canonical_name==name for v in m.values if v.period.year==year)


def metric(report,name,year=2025,scope=Scope.CONSOLIDATED):
    return next(m for m in compute_metrics(report,scope) if m.name==name and m.period.year==year)


class MetricTests(unittest.TestCase):
    def test_expected_formulas(self):
        r=report()
        for name,expected in [('revenue_growth',20),('net_income_growth',50),('net_margin',10),
            ('operating_margin',15),('gross_margin',25),('debt_to_assets',40),('ocf_margin',25),('free_cash_flow',20)]:
            with self.subTest(name=name): self.assertAlmostEqual(metric(r,name).value,expected)

    def test_positive_and_negative_capex(self):
        r=report(); source(r,ST.CASH_FLOW,'capital_expenditure').parsed_number.value=10
        self.assertEqual(metric(r,'free_cash_flow').value,20)

    def test_missing_value_not_zero(self):
        r=report(); source(r,ST.INCOME_STATEMENT,'net_income').parsed_number.value=None
        self.assertIsNone(metric(r,'net_margin').value)
        self.assertIn('缺失',metric(r,'net_margin').reason)

    def test_zero_denominator(self):
        r=report(); source(r,ST.INCOME_STATEMENT,'revenue').parsed_number.value=0
        self.assertIsNone(metric(r,'net_margin').value)

    def test_negative_growth_base(self):
        r=report(); source(r,ST.INCOME_STATEMENT,'net_income',2024).parsed_number.value=-8
        self.assertIsNone(metric(r,'net_income_growth').value)

    def test_nonconsecutive_year(self):
        r=report(); source(r,ST.INCOME_STATEMENT,'revenue',2024).period.year=2023
        self.assertIsNone(metric(r,'revenue_growth').value)

    def test_unknown_unit(self):
        r=report(); source(r,ST.INCOME_STATEMENT,'revenue').multiplier=None
        self.assertIsNone(metric(r,'net_margin').value)

    def test_currency_mismatch(self):
        r=report(); source(r,ST.INCOME_STATEMENT,'revenue').unit='USD'
        self.assertIsNone(metric(r,'net_margin').value)
        self.assertIn('币种',metric(r,'net_margin').reason)

    def test_scale_conversion(self):
        r=report(); v=source(r,ST.INCOME_STATEMENT,'revenue'); v.parsed_number.value=.12;v.multiplier=1000
        self.assertEqual(metric(r,'net_margin').value,10)

    def test_conflicting_duplicates(self):
        r=report(); duplicate=deepcopy(r.income_statement.metrics[0]);duplicate.values[0].parsed_number.value=121
        r.income_statement.metrics.append(duplicate)
        self.assertIsNone(metric(r,'net_margin').value)
        self.assertTrue(any(c.status=='failed' and c.rule=='input_quality' for c in run_all_validations(r)))

    def test_identical_duplicates_preserve_provenance(self):
        r=report();r.income_statement.metrics.append(deepcopy(r.income_statement.metrics[0]))
        result=metric(r,'net_margin');self.assertEqual(result.value,10);self.assertEqual(len(result.sources),3)

    def test_scope_separation(self):
        r=report();parent=deepcopy(r.income_statement);parent.scope=Scope.PARENT
        parent.metrics[0].values[0].parsed_number.value=60;r.alternative_statements.append(parent)
        self.assertEqual(metric(r,'net_margin').value,10)
        self.assertEqual(metric(r,'net_margin',scope=Scope.PARENT).value,20)
        self.assertIsNone(metric(r,'ocf_margin',scope=Scope.PARENT).value)

    def test_unknown_scope(self):
        r=report();r.income_statement.scope=Scope.UNKNOWN
        self.assertIsNone(metric(r,'net_margin',scope=Scope.UNKNOWN).value)

    def test_restated_and_original_not_blended(self):
        r=report();source(r,ST.INCOME_STATEMENT,'revenue').period.is_restated=True
        self.assertTrue(all(m.value is None for m in compute_metrics(r) if m.name=='net_margin' and m.period.year==2025))

    def test_ambiguous_prior_restatement(self):
        r=report();v=deepcopy(source(r,ST.INCOME_STATEMENT,'revenue',2024));v.period.is_restated=True
        r.income_statement.metrics[0].values.append(v)
        self.assertIsNone(metric(r,'revenue_growth').value)

    def test_cross_statement_different_dates(self):
        r=report();source(r,ST.CASH_FLOW,'operating_cash_flow').period.end_date='2025-06-30'
        self.assertIsNone(metric(r,'ocf_margin').value)

    def test_not_annualizing_quarter(self):
        r=report()
        for m in r.income_statement.metrics:
            for v in m.values:v.period.period_type=PeriodType.QUARTER
        self.assertFalse(any(m.name=='net_margin' for m in compute_metrics(r)))

    def test_calculation_does_not_mutate_report(self):
        r=report();before=deepcopy(r);compute_metrics(r);run_all_validations(r);self.assertEqual(r,before)


class ValidationTests(unittest.TestCase):
    def test_checks_all_years(self):
        checks=[c for c in run_all_validations(report()) if c.rule=='balance_sheet_equation']
        self.assertEqual(len(checks),2);self.assertTrue(all(c.status=='passed' for c in checks))

    def test_failed_old_year_not_hidden(self):
        r=report();v=source(r,ST.BALANCE_SHEET,'total_assets',2024);v.parsed_number.value=190
        checks=[c for c in run_all_validations(r) if c.rule=='balance_sheet_equation']
        self.assertEqual([c.status for c in checks],['passed','failed'])

    def test_decimal_rounding_tolerance(self):
        r=report()
        for name in ['total_assets','total_liabilities','total_equity']:
            v=source(r,ST.BALANCE_SHEET,name);v.raw_value_str=f'{v.parsed_number.value:.2f}'
        v=source(r,ST.BALANCE_SHEET,'total_assets');v.parsed_number.value=200.02
        checks=[c for c in run_all_validations(r) if c.rule=='balance_sheet_equation']
        self.assertEqual(checks[0].status,'failed');self.assertAlmostEqual(checks[0].tolerance_used,.015)

    def test_million_rounding(self):
        r=report()
        for name in ['total_assets','total_liabilities','total_equity']:
            source(r,ST.BALANCE_SHEET,name).multiplier=1e6
        checks=[c for c in run_all_validations(r) if c.rule=='balance_sheet_equation']
        self.assertEqual(checks[0].tolerance_used,1.5e6)

    def test_currency_mismatch_skipped(self):
        r=report();source(r,ST.BALANCE_SHEET,'total_assets').unit='USD'
        self.assertEqual(run_all_validations(r)[0].status,'skipped')

    def test_unknown_unit_skipped(self):
        r=report();source(r,ST.BALANCE_SHEET,'total_assets').multiplier=None
        self.assertEqual(run_all_validations(r)[0].status,'skipped')

    def test_empty_report_not_passed(self):
        checks=run_all_validations(FinancialReport())
        self.assertTrue(checks);self.assertTrue(all(c.status=='skipped' for c in checks))

    def test_parent_checked_separately(self):
        r=report();parent=deepcopy(r.balance_sheet);parent.scope=Scope.PARENT
        parent.metrics[0].values[0].parsed_number.value=210;r.alternative_statements.append(parent)
        checks=run_all_validations(r)
        self.assertTrue(any(c.status=='failed' and c.scope=='parent' for c in checks))
        self.assertTrue(all(c.status=='passed' for c in checks if c.scope=='consolidated'))


    def test_restated_balance_does_not_mix(self):
        r=report();source(r,ST.BALANCE_SHEET,'total_assets').period.is_restated=True
        checks=[c for c in run_all_validations(r) if c.rule=='balance_sheet_equation' and '2025' in c.period_label]
        self.assertTrue(checks);self.assertTrue(all(c.status=='skipped' for c in checks))

    def test_nonfinite_input_rejected(self):
        r=report();source(r,ST.INCOME_STATEMENT,'revenue').parsed_number.value=float('inf')
        self.assertIsNone(metric(r,'net_margin').value)
        self.assertTrue(any(c.status=='failed' for c in run_all_validations(r)))

if __name__=='__main__':unittest.main()
