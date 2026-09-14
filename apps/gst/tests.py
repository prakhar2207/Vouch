from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product
from apps.accounting.models import Voucher, VoucherItem, FinancialYear
from apps.accounting.services.voucher_service import VoucherService
from apps.gst.models import CompanyGSTConfig, EWayBillRecord, GSTTaxpayerCache
from apps.gst.services.gstin_validator import GSTINValidator
from apps.gst.services.gstin_lookup_service import GSTINLookupService
from apps.gst.services.eway_bill_service import EWayBillService
from apps.gst.services.gstr_report_service import GSTRReportService

User = get_user_model()

class GSTIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='gst_test@example.com',
            password='testpassword123'
        )
        self.company = Company.objects.create(
            name="Maa Annapurna Belting Store",
            gstin="09AAACB1234C1Z1",
            state_code="09",
            state_name="Uttar Pradesh",
            address="Plot 10, Industrial Estate",
            city="Kanpur",
            pincode="208001"
        )
        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 2026-27",
            code="26-27",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31)
        )
        # Groups
        self.debtors_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Debtors", nature="ASSET")
        self.sales_grp = LedgerGroup.objects.create(company=self.company, name="Sales Accounts", nature="INCOME")
        self.tax_grp = LedgerGroup.objects.create(company=self.company, name="Duties & Taxes", nature="LIABILITY")

        # Ledgers
        self.customer = Ledger.objects.create(
            company=self.company,
            name="Classic Pipe Enterprises",
            group=self.debtors_grp,
            ledger_type="CUSTOMER",
            gstin="24AABCC1234D1Z8",
            state_code="24"
        )
        self.sales_ledger = Ledger.objects.create(
            company=self.company,
            name="Sales Account",
            group=self.sales_grp,
            ledger_type="SALES"
        )
        self.cgst = Ledger.objects.create(company=self.company, name="Output CGST", group=self.tax_grp, ledger_type="TAX")
        self.sgst = Ledger.objects.create(company=self.company, name="Output SGST", group=self.tax_grp, ledger_type="TAX")
        self.igst = Ledger.objects.create(company=self.company, name="Output IGST", group=self.tax_grp, ledger_type="TAX")

        # Product
        self.product = Product.objects.create(
            company=self.company,
            name="V-Belt B-65",
            sku="VB-B65",
            hsn_code="8483",
            unit="PCS",
            selling_price=Decimal("500.00"),
            purchase_price=Decimal("400.00"),
            gst_rate=Decimal("18.00")
        )

    def test_01_gstin_validator(self):
        """Test checksum verification and state code extraction"""
        valid = GSTINValidator.validate("09AAACB1234C1Z1")
        self.assertTrue(valid['is_valid'])
        self.assertEqual(valid['state_code'], "09")
        self.assertEqual(valid['state_name'], "Uttar Pradesh")
        self.assertEqual(valid['pan'], "AAACB1234C")

        invalid = GSTINValidator.validate("INVALID_GSTIN")
        self.assertFalse(invalid['is_valid'])

    def test_02_gstin_lookup_service(self):
        """Test party detail auto-fetch with mock provider and persistent caching"""
        res = GSTINLookupService.lookup_gstin("24AABCC1234D1Z8", company=self.company)
        self.assertTrue(res['success'])
        self.assertEqual(res['trade_name'], "Classic Pipe Enterprises")
        self.assertEqual(res['state_code'], "24")
        self.assertEqual(res['status'], "Active")

        # Verify cached in database
        cached = GSTTaxpayerCache.objects.filter(gstin="24AABCC1234D1Z8").first()
        self.assertIsNotNone(cached)
        self.assertEqual(cached.trade_name, "Classic Pipe Enterprises")

        # Repeated call should hit cache
        res2 = GSTINLookupService.lookup_gstin("24AABCC1234D1Z8", company=self.company)
        self.assertTrue(res2.get('is_cached'))

    def test_03_eway_bill_generation_and_lifecycle(self):
        """Test E-Way bill generation, vehicle update, and cancellation"""
        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV/26-27/0050",
            voucher_date=date(2026, 8, 15),
            party_ledger=self.customer,
            total_amount=Decimal("59000.00"),
            status="POSTED",
            created_by=self.user
        )
        VoucherItem.objects.create(
            voucher=voucher,
            product=self.product,
            quantity=Decimal("100.00"),
            rate=Decimal("500.00"),
            total_amount=Decimal("59000.00"),
            taxable_amount=Decimal("50000.00"),
            gst_rate=Decimal("18.00"),
            igst_amount=Decimal("9000.00"),
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00")
        )

        transport_details = {
            "transport_mode": "1",
            "distance_km": 350,
            "vehicle_number": "UP78BT4521",
            "transporter_id": "09AAACB1234C1Z1",
            "transporter_name": "FastTrack Logistics"
        }

        gen_res = EWayBillService.generate_for_voucher(voucher, transport_details, self.user)
        self.assertTrue(gen_res['success'])
        self.assertIn('ewb_number', gen_res)
        self.assertEqual(gen_res['status'], 'ACTIVE')

        ewb = EWayBillRecord.objects.get(ewb_number=gen_res['ewb_number'])
        self.assertEqual(ewb.vehicle_number, "UP78BT4521")
        self.assertEqual(ewb.distance_km, 350)

        # Update vehicle
        upd_res = EWayBillService.update_vehicle(ewb, "UP78BT9999", reason="Breakdown")
        self.assertTrue(upd_res['success'])
        ewb.refresh_from_db()
        self.assertEqual(ewb.vehicle_number, "UP78BT9999")

        # Cancel E-Way Bill
        can_res = EWayBillService.cancel_eway_bill(ewb, reason="1", remarks="Order cancelled by customer")
        self.assertTrue(can_res['success'])
        ewb.refresh_from_db()
        self.assertEqual(ewb.status, "CANCELLED")

    def test_04_gstr1_json_generation(self):
        """Test GSTR-1 JSON structure matches GSTN Offline format"""
        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV/26-27/0051",
            voucher_date=date(2026, 8, 20),
            party_ledger=self.customer,
            total_amount=Decimal("11800.00"),
            status="POSTED",
            created_by=self.user
        )
        VoucherItem.objects.create(
            voucher=voucher,
            product=self.product,
            quantity=Decimal("20.00"),
            rate=Decimal("500.00"),
            total_amount=Decimal("11800.00"),
            taxable_amount=Decimal("10000.00"),
            gst_rate=Decimal("18.00"),
            igst_amount=Decimal("1800.00"),
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00")
        )

        gstr1 = GSTRReportService.generate_gstr1(self.company, "2026-08-01", "2026-08-31")
        self.assertIn("b2b", gstr1)
        self.assertIn("hsn", gstr1)
        self.assertIn("doc_issue", gstr1)
        self.assertEqual(len(gstr1["b2b"]), 1)
        self.assertEqual(gstr1["b2b"][0]["ctin"], "24AABCC1234D1Z8")
        self.assertEqual(gstr1["b2b"][0]["inv"][0]["inum"], "INV/26-27/0051")
