import datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import Voucher
from apps.accounting.models_proforma import ProformaInvoice
from apps.analytics.services.ai_service import AnalyticsEngine


class SalesForecastEngineTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="forecaster@vouch.com", password="Password123!")
        self.company = Company.objects.create(
            name="Apex Dynamics Corp",
            legal_name="Apex Dynamics Pvt Ltd",
            gstin="27AAPCA9999A1Z5",
            state_code="27",
            financial_year_start="2025-04-01"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role="OWNER")

        self.grp_debtors = LedgerGroup.objects.create(company=self.company, name="Sundry Debtors", nature="ASSET")
        self.party_a = Ledger.objects.create(
            company=self.company,
            group=self.grp_debtors,
            name="Mega Corp Alpha",
            ledger_type="CUSTOMER"
        )
        self.party_b = Ledger.objects.create(
            company=self.company,
            group=self.grp_debtors,
            name="Beta Traders",
            ledger_type="CUSTOMER"
        )

        self.cat = ProductCategory.objects.create(company=self.company, name="Industrial Hardware")
        self.prod_1 = Product.objects.create(
            company=self.company,
            category=self.cat,
            name="Valve Unit X1",
            purchase_price=Decimal("500.00"),
            selling_price=Decimal("1000.00"),
            stock_quantity=Decimal("100.00"),
            is_active=True
        )

    def test_forecast_zero_sales(self):
        """When company has zero sales vouchers, forecast returns clean fallback with no errors."""
        res = AnalyticsEngine.forecast_sales(self.company, days=30)
        self.assertEqual(res["projected_total"], 0.0)
        self.assertEqual(res["trend_status"], "Insufficient Data")
        self.assertEqual(res["confidence"], "LOW")
        self.assertFalse(res["factors_analyzed"]["yoy_seasonality_applied"])

    def test_forecast_short_history_excludes_yoy_seasonality(self):
        """
        STRICT RULE: If past-year history (< 330 days) is not available,
        annual seasonality/festival feature MUST NOT be considered.
        """
        today = datetime.date.today()
        # Seed 30 days of sales
        for i in range(30):
            v_date = today - datetime.timedelta(days=30 - i)
            Voucher.objects.create(
                company=self.company,
                voucher_number=f"INV-SHORT-{i:03d}",
                voucher_type="SALES",
                voucher_date=v_date,
                party_ledger=self.party_a,
                total_amount=Decimal("10000.00"),
                status="POSTED",
                created_by=self.user
            )

        res = AnalyticsEngine.forecast_sales(self.company, days=30)
        self.assertGreater(res["projected_total"], 0.0)
        self.assertEqual(len(res["daily_forecast"]), 30)
        self.assertIn("p10_total", res)
        self.assertIn("p50_total", res)
        self.assertIn("p90_total", res)
        self.assertLessEqual(res["p10_total"], res["p50_total"])
        self.assertLessEqual(res["p50_total"], res["p90_total"])

        # Crucial assertion: YoY seasonality MUST be False because history is only 30 days
        self.assertFalse(res["factors_analyzed"]["yoy_seasonality_applied"])
        self.assertIn("Past-year records not available", res["factors_analyzed"]["yoy_summary"])
        self.assertIn("YoY Seasonality: Excluded", res["trend_summary"])

    def test_forecast_prior_year_history_applies_yoy_seasonality(self):
        """
        When >= 330 days of sales history exists AND prior year sales occurred in the seasonal window,
        the model activates YoY Seasonality.
        """
        today = datetime.date.today()

        # Seed sales 365 days ago (prior year)
        for i in range(1, 35):
            py_date = today - datetime.timedelta(days=365) + datetime.timedelta(days=i)
            Voucher.objects.create(
                company=self.company,
                voucher_number=f"INV-PY-{i:03d}",
                voucher_type="SALES",
                voucher_date=py_date,
                party_ledger=self.party_a,
                total_amount=Decimal("25000.00"),
                status="POSTED",
                created_by=self.user
            )

        # Seed current period sales (last 30 days)
        for i in range(30):
            cur_date = today - datetime.timedelta(days=30 - i)
            Voucher.objects.create(
                company=self.company,
                voucher_number=f"INV-CUR-{i:03d}",
                voucher_type="SALES",
                voucher_date=cur_date,
                party_ledger=self.party_a,
                total_amount=Decimal("20000.00"),
                status="POSTED",
                created_by=self.user
            )

        res = AnalyticsEngine.forecast_sales(self.company, days=30)
        self.assertGreater(res["projected_total"], 0.0)
        # History span is >= 330 days and prior year window has sales -> seasonality active
        self.assertTrue(res["factors_analyzed"]["yoy_seasonality_applied"])
        self.assertIn("Incorporated historical year-over-year seasonal pattern", res["factors_analyzed"]["yoy_summary"])
        self.assertIn("YoY Annual Seasonality: Enabled", res["trend_summary"])

    def test_forecast_stock_constraint_applied(self):
        """When catalog stock is depleted (<50% in stock across >=5 products), sales forecast is throttled."""
        today = datetime.date.today()
        # Seed 10 sales
        for i in range(10):
            Voucher.objects.create(
                company=self.company,
                voucher_number=f"INV-STK-{i}",
                voucher_type="SALES",
                voucher_date=today - datetime.timedelta(days=10 - i),
                party_ledger=self.party_a,
                total_amount=Decimal("5000.00"),
                status="POSTED",
                created_by=self.user
            )

        # Create 6 products, 5 of which are out of stock (stock_quantity=0)
        for j in range(6):
            Product.objects.create(
                company=self.company,
                category=self.cat,
                name=f"Out of Stock Product {j}",
                sku=f"SKU-OUT-{j}",
                purchase_price=Decimal("10.00"),
                selling_price=Decimal("20.00"),
                stock_quantity=Decimal("0.00") if j > 0 else Decimal("50.00"),
                is_active=True
            )

        res = AnalyticsEngine.forecast_sales(self.company, days=15)
        self.assertTrue(res["factors_analyzed"]["stock_constraint_applied"])
        self.assertLess(res["factors_analyzed"]["stock_health_ratio"], 0.50)
        self.assertIn("Stock Availability Ceiling", res["trend_summary"])

    def test_sales_forecast_api_view(self):
        """API endpoint /api/v1/analytics/forecast/<company_id>/ returns expected schema."""
        self.client.force_authenticate(user=self.user)

        today = datetime.date.today()
        Voucher.objects.create(
            company=self.company,
            voucher_number="INV-API-01",
            voucher_type="SALES",
            voucher_date=today,
            party_ledger=self.party_a,
            total_amount=Decimal("15000.00"),
            status="POSTED",
            created_by=self.user
        )

        url = f"/api/v1/analytics/forecast/{self.company.id}/?days=14"
        res = self.client.get(url, HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["forecast_days"], 14)
        self.assertIn("daily_forecast", data["data"])
        self.assertIn("factors_analyzed", data["data"])
        self.assertEqual(len(data["data"]["daily_forecast"]), 14)

    def test_forecast_proforma_pipeline_factor(self):
        """Open or accepted proforma invoices add pipeline velocity to the 14-day projection."""
        today = datetime.date.today()
        # Seed 1 sales voucher so base isn't 0
        Voucher.objects.create(
            company=self.company,
            voucher_number="INV-PF-01",
            voucher_type="SALES",
            voucher_date=today,
            party_ledger=self.party_a,
            total_amount=Decimal("10000.00"),
            status="POSTED",
            created_by=self.user
        )

        # Create an accepted proforma invoice of 140,000
        ProformaInvoice.objects.create(
            company=self.company,
            proforma_number="PI-2026-001",
            date=today,
            party_ledger=self.party_b,
            total_amount=Decimal("140000.00"),
            status="ACCEPTED",
            created_by=self.user
        )

        res = AnalyticsEngine.forecast_sales(self.company, days=14)
        self.assertGreater(res["factors_analyzed"]["open_proforma_pipeline"], 0.0)
        self.assertIn("Proforma Pipeline: ₹", res["trend_summary"])

    def test_forecast_customer_reorder_cycle(self):
        """When customers exhibit recurring order intervals, future reorders are scheduled into daily projection."""
        today = datetime.date.today()
        # Customer buys every 10 days
        for offset in [30, 20, 10]:
            Voucher.objects.create(
                company=self.company,
                voucher_number=f"INV-CYCLE-{offset}",
                voucher_type="SALES",
                voucher_date=today - datetime.timedelta(days=offset),
                party_ledger=self.party_a,
                total_amount=Decimal("50000.00"),
                status="POSTED",
                created_by=self.user
            )

        res = AnalyticsEngine.forecast_sales(self.company, days=15)
        self.assertGreater(res["factors_analyzed"]["repeat_buyers_modeled"], 0)
        self.assertIn("Customer Repurchase Cycles", res["trend_summary"])

    def test_monthly_comparison_structure_and_mom(self):
        """Verify present month MTD + predicted remainder is compared against last month."""
        today = datetime.date.today()
        cur_month_start = today.replace(day=1)
        prev_month_end = cur_month_start - datetime.timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)

        # 1. Seed last month sales
        Voucher.objects.create(
            company=self.company,
            voucher_number="INV-PREV-01",
            voucher_type="SALES",
            voucher_date=prev_month_start + datetime.timedelta(days=5),
            party_ledger=self.party_a,
            total_amount=Decimal("100000.00"),
            status="POSTED",
            created_by=self.user
        )

        # 2. Seed present month sales (MTD)
        Voucher.objects.create(
            company=self.company,
            voucher_number="INV-CURR-01",
            voucher_type="SALES",
            voucher_date=cur_month_start,
            party_ledger=self.party_a,
            total_amount=Decimal("60000.00"),
            status="POSTED",
            created_by=self.user
        )

        forecast = AnalyticsEngine.forecast_sales(self.company, days=30)
        self.assertIn("monthly_comparison", forecast)
        mc = forecast["monthly_comparison"]

        self.assertIn("current_month", mc)
        self.assertIn("previous_month", mc)
        self.assertIn("mom_comparison", mc)
        self.assertIn("historical_months_series", mc)

        self.assertEqual(mc["previous_month"]["total_sales"], 100000.0)
        self.assertEqual(mc["current_month"]["mtd_actual_sales"], 60000.0)
        self.assertGreaterEqual(mc["current_month"]["projected_month_total"], 60000.0)
        self.assertIn(mc["mom_comparison"]["pace_status"], ["BEATING_LAST_MONTH", "PACING_BEHIND", "ON_PAR"])

    def test_monthly_comparison_endpoint(self):
        """API endpoint /api/v1/analytics/monthly-comparison/<cid>/ returns full benchmark structure."""
        self.client.force_authenticate(user=self.user)
        today = datetime.date.today()
        Voucher.objects.create(
            company=self.company,
            voucher_number="INV-MC-API-01",
            voucher_type="SALES",
            voucher_date=today,
            party_ledger=self.party_a,
            total_amount=Decimal("25000.00"),
            status="POSTED",
            created_by=self.user
        )

        url = f"/api/v1/analytics/monthly-comparison/{self.company.id}/"
        res = self.client.get(url, HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertIn("current_month", data["data"])
        self.assertIn("mom_comparison", data["data"])
        self.assertIn("historical_months_series", data["data"])

    def test_forecast_excludes_cash_from_customer_pareto_and_tracks_churn(self):
        """Cash sales are excluded from Customer Pareto & churn radar, tracked in cash_sales_summary."""
        today = datetime.date.today()
        grp_cash = LedgerGroup.objects.create(company=self.company, name="Cash-in-Hand", nature="ASSET")
        cash_ledger = Ledger.objects.create(
            company=self.company,
            group=grp_cash,
            name="Cash",
            ledger_type="CASH"
        )

        # 1. Walk-in cash bill: 50,000
        Voucher.objects.create(
            company=self.company,
            voucher_number="INV-CASH-01",
            voucher_type="SALES",
            voucher_date=today,
            party_ledger=cash_ledger,
            total_amount=Decimal("50000.00"),
            status="POSTED",
            created_by=self.user
        )

        # 2. Party A sale: 40,000 (recent, 10 days ago)
        Voucher.objects.create(
            company=self.company,
            voucher_number="INV-PARTY-A-01",
            voucher_type="SALES",
            voucher_date=today - datetime.timedelta(days=10),
            party_ledger=self.party_a,
            total_amount=Decimal("40000.00"),
            status="POSTED",
            created_by=self.user
        )

        # 3. Party B sale: 20,000 (dormant, 95 days ago)
        Voucher.objects.create(
            company=self.company,
            voucher_number="INV-PARTY-B-01",
            voucher_type="SALES",
            voucher_date=today - datetime.timedelta(days=95),
            party_ledger=self.party_b,
            total_amount=Decimal("20000.00"),
            status="POSTED",
            created_by=self.user
        )

        forecast = AnalyticsEngine.forecast_sales(self.company, days=30)

        # Check cash summary
        self.assertIn("cash_sales_summary", forecast)
        self.assertEqual(forecast["cash_sales_summary"]["total_billed"], 50000.0)
        self.assertEqual(forecast["cash_sales_summary"]["invoice_count"], 1)

        # Check Pareto: Cash must NOT be in customer_pareto
        pareto_names = [p["party_name"] for p in forecast["customer_pareto"]]
        self.assertNotIn("Cash", pareto_names)
        self.assertEqual(pareto_names[0], "Mega Corp Alpha")
        self.assertEqual(forecast["customer_pareto"][0]["risk_status"], "HEALTHY")

        # Check churn accounts: Party B is idle >= 90 days and marked DORMANT
        churn = forecast["churn_accounts"]
        party_b_churn = next((c for c in churn if c["party_name"] == "Beta Traders"), None)
        self.assertIsNotNone(party_b_churn)
        self.assertGreaterEqual(party_b_churn["days_since_last_sale"], 90)
        self.assertEqual(party_b_churn["risk_status"], "DORMANT")



