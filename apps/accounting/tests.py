import json
import xml.etree.ElementTree as ET
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, Warehouse
from apps.accounting.models import Voucher, InwardVoucherRequest
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.edi_service import EDIService
from apps.accounting.services.tally_export import TallyXMLExporter


class B2BEDIAndTallyExportTests(TestCase):
    def setUp(self):
        # 1. Create Users
        self.user_seller = User.objects.create_user(email="seller@vouch.com", password="password123")
        self.user_buyer = User.objects.create_user(email="buyer@vouch.com", password="password123")

        # 2. Create Seller Company (Company A - Maharashtra)
        self.seller_company = Company.objects.create(
            name="Apex Industrial Supplies",
            legal_name="Apex Industrial Supplies Pvt Ltd",
            gstin="27AAACA1234A1Z5",
            pan="AAACA1234A",
            state_code="27",
            state_name="Maharashtra",
            address="101 Tech Park, Andheri East",
            city="Mumbai",
            pincode="400069",
            email="sales@apex.com",
            phone="9876543210",
            financial_year_start="2026-04-01"
        )
        UserCompany.objects.create(user=self.user_seller, company=self.seller_company, role="ADMIN")
        self.seller_warehouse = Warehouse.objects.create(company=self.seller_company, name="Apex Warehouse")

        # 3. Create Buyer Company (Company B - Gujarat)
        self.buyer_company = Company.objects.create(
            name="Gujarat Machine Works",
            legal_name="Gujarat Machine Works Ltd",
            gstin="24AAACG5678B1Z2",
            pan="AAACG5678B",
            state_code="24",
            state_name="Gujarat",
            address="Plot 42, GIDC Estate",
            city="Ahmedabad",
            pincode="380001",
            email="purchase@gmw.com",
            phone="9123456780",
            financial_year_start="2026-04-01"
        )
        UserCompany.objects.create(user=self.user_buyer, company=self.buyer_company, role="ADMIN")
        self.buyer_warehouse = Warehouse.objects.create(company=self.buyer_company, name="GIDC Warehouse")

        # 4. Seller Groups & Ledgers
        self.debtors_grp = LedgerGroup.objects.create(company=self.seller_company, name="Sundry Debtors", nature="ASSET")
        self.sales_grp = LedgerGroup.objects.create(company=self.seller_company, name="Sales Accounts", nature="INCOME")
        self.duties_grp = LedgerGroup.objects.create(company=self.seller_company, name="Duties & Taxes", nature="LIABILITY")

        self.buyer_party_ledger = Ledger.objects.create(
            company=self.seller_company,
            group=self.debtors_grp,
            name="Gujarat Machine Works",
            gstin="24AAACG5678B1Z2",
            state_code="24",
            ledger_type="CUSTOMER"
        )
        self.sales_ledger = Ledger.objects.create(company=self.seller_company, group=self.sales_grp, name="Interstate Sales", ledger_type="SALES")
        self.cgst_ledger = Ledger.objects.create(company=self.seller_company, group=self.duties_grp, name="Output CGST", ledger_type="TAX")
        self.sgst_ledger = Ledger.objects.create(company=self.seller_company, group=self.duties_grp, name="Output SGST", ledger_type="TAX")
        self.igst_ledger = Ledger.objects.create(company=self.seller_company, group=self.duties_grp, name="Output IGST", ledger_type="TAX")

        # 5. Seller Products
        self.product_bearing = Product.objects.create(
            company=self.seller_company,
            name="Bearing 6205-2RS",
            sku="BRG-6205",
            hsn_code="84821011",
            gst_rate=Decimal("18.00"),
            selling_price=Decimal("250.00"),
            stock_quantity=Decimal("100.00"),
            unit="PCS"
        )

        self.client = APIClient()

    def test_sales_voucher_triggers_inward_edi_request(self):
        """When seller generates a sales invoice for buyer with matching GSTIN, InwardVoucherRequest is created."""
        items_data = [
            {
                "product_id": str(self.product_bearing.id),
                "quantity": 10,
                "rate": 250.00,
                "discount_percent": 0.0,
            }
        ]

        sales_vch = SalesInvoiceService.generate_sales_invoice(
            company=self.seller_company,
            user=self.user_seller,
            party_ledger=self.buyer_party_ledger,
            items_data=items_data,
            sales_ledger=self.sales_ledger,
            cgst_ledger=self.cgst_ledger,
            sgst_ledger=self.sgst_ledger,
            igst_ledger=self.igst_ledger
        )

        # Verify inward request is automatically staged for Buyer
        edi_req = InwardVoucherRequest.objects.filter(target_company=self.buyer_company, source_voucher=sales_vch).first()
        self.assertIsNotNone(edi_req)
        self.assertEqual(edi_req.status, 'PENDING')
        self.assertEqual(edi_req.source_company, self.seller_company)
        self.assertEqual(len(edi_req.payload['items']), 1)
        self.assertEqual(edi_req.payload['items'][0]['product_name'], "Bearing 6205-2RS")

    def test_buyer_accepts_and_digitally_signs_inward_edi_request(self):
        """Buyer accepts InwardVoucherRequest -> verified Purchase Voucher & stock entry created."""
        items_data = [
            {
                "product_id": str(self.product_bearing.id),
                "quantity": 20,
                "rate": 250.00,
                "discount_percent": 0.0,
            }
        ]
        sales_vch = SalesInvoiceService.generate_sales_invoice(
            company=self.seller_company,
            user=self.user_seller,
            party_ledger=self.buyer_party_ledger,
            items_data=items_data,
            sales_ledger=self.sales_ledger,
            cgst_ledger=self.cgst_ledger,
            sgst_ledger=self.sgst_ledger,
            igst_ledger=self.igst_ledger
        )
        VoucherService.post_voucher(sales_vch)

        edi_req = InwardVoucherRequest.objects.get(target_company=self.buyer_company, source_voucher=sales_vch)

        # Authenticate as buyer and call accept endpoint
        self.client.force_authenticate(user=self.user_buyer)
        response = self.client.post(f"/api/b2b/inbox/{edi_req.id}/accept/", data={}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertIsNotNone(response.data['digital_signature_hash'])

        # Refresh from DB
        edi_req.refresh_from_db()
        self.assertEqual(edi_req.status, 'ACCEPTED')
        self.assertIsNotNone(edi_req.digital_signature_hash)
        self.assertIsNotNone(edi_req.signed_at)
        self.assertIsNotNone(edi_req.created_purchase_voucher)

        # Verify Purchase Voucher exists and is posted
        purchase_vch = edi_req.created_purchase_voucher
        self.assertEqual(purchase_vch.company, self.buyer_company)
        self.assertEqual(purchase_vch.voucher_type, 'PURCHASE')
        self.assertEqual(purchase_vch.status, 'POSTED')

        # Verify Product auto-created in Buyer catalog with stock
        buyer_product = Product.objects.filter(company=self.buyer_company, name="Bearing 6205-2RS").first()
        self.assertIsNotNone(buyer_product)
        self.assertEqual(buyer_product.stock_quantity, Decimal("20.00"))

    def test_buyer_rejects_inward_edi_request(self):
        """Buyer rejects InwardVoucherRequest with reason."""
        items_data = [{"product_id": str(self.product_bearing.id), "quantity": 5, "rate": 250.00}]
        sales_vch = SalesInvoiceService.generate_sales_invoice(
            company=self.seller_company,
            user=self.user_seller,
            party_ledger=self.buyer_party_ledger,
            items_data=items_data,
            sales_ledger=self.sales_ledger,
            cgst_ledger=self.cgst_ledger,
            sgst_ledger=self.sgst_ledger,
            igst_ledger=self.igst_ledger
        )
        edi_req = InwardVoucherRequest.objects.get(target_company=self.buyer_company, source_voucher=sales_vch)

        self.client.force_authenticate(user=self.user_buyer)
        response = self.client.post(f"/api/b2b/inbox/{edi_req.id}/reject/", data={"reason": "Incorrect rate quoted"}, format='json')

        self.assertEqual(response.status_code, 200)
        edi_req.refresh_from_db()
        self.assertEqual(edi_req.status, 'REJECTED')
        self.assertEqual(edi_req.rejection_reason, "Incorrect rate quoted")

    def test_tally_xml_exporter_output_structure(self):
        """Tally XML engine produces valid XML adhering to standard schema."""
        xml_output = TallyXMLExporter.generate_xml(company=self.seller_company, export_type="all")
        
        # Parse XML to verify valid syntax
        root = ET.fromstring(xml_output.encode('utf-8'))
        self.assertEqual(root.tag, "ENVELOPE")
        self.assertIsNotNone(root.find("HEADER"))
        self.assertIsNotNone(root.find("BODY/IMPORTDATA/REQUESTDATA"))

        # Verify Ledgers & Stock items are inside TALLYMESSAGE
        messages = root.findall(".//TALLYMESSAGE")
        self.assertGreater(len(messages), 0)

        # Check API Endpoint
        self.client.force_authenticate(user=self.user_seller)
        response = self.client.get(f"/api/export/tally/xml/?company_id={self.seller_company.id}&type=all")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')
        self.assertIn("Tally_Export", response['Content-Disposition'])


class MultiYearInvoicingAndYearEndTests(TestCase):
    def setUp(self):
        import datetime
        self.user = User.objects.create_user(email="cfo@vouch.com", password="password123")
        self.company = Company.objects.create(
            name="Apex Dynamics Pvt Ltd",
            legal_name="Apex Dynamics Pvt Ltd",
            gstin="27AAACA9999A1Z1",
            pan="AAACA9999A",
            state_code="27",
            state_name="Maharashtra"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role="ADMIN")

        from apps.accounting.services.sequence_service import InvoiceSequenceService
        self.fy = InvoiceSequenceService.get_or_create_active_fy(self.company, datetime.date(2026, 6, 1))

        # Groups & Ledgers
        self.asset_grp = LedgerGroup.objects.create(company=self.company, name="Current Assets", nature="ASSET")
        self.income_grp = LedgerGroup.objects.create(company=self.company, name="Direct Income", nature="INCOME")
        self.expense_grp = LedgerGroup.objects.create(company=self.company, name="Direct Expenses", nature="EXPENSE")

        self.bank_ledger = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="HDFC Bank Current A/c",
            ledger_type="BANK",
            opening_balance=Decimal("50000.00"),
            opening_balance_type="DEBIT"
        )

        self.sales_ledger = Ledger.objects.create(
            company=self.company,
            group=self.income_grp,
            name="Domestic Sales",
            ledger_type="SALES",
            opening_balance=Decimal("0.00"),
            opening_balance_type="CREDIT"
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_invoice_sequence_generation_rule_46b(self):
        """Sequential numbers adhere to Indian GST Rule 46(b) <= 16 chars."""
        import datetime
        from apps.accounting.services.sequence_service import InvoiceSequenceService

        num1, fy1 = InvoiceSequenceService.get_next_number(self.company, 'SALES', datetime.date(2026, 5, 10))
        num2, fy2 = InvoiceSequenceService.get_next_number(self.company, 'SALES', datetime.date(2026, 5, 11))

        self.assertEqual(num1, "INV/26-27/0001")
        self.assertEqual(num2, "INV/26-27/0002")
        self.assertLessEqual(len(num1), 16)
        self.assertLessEqual(len(num2), 16)
        self.assertEqual(fy1.id, self.fy.id)

    def test_closed_financial_year_blocks_voucher_creation(self):
        """Closed Financial Year raises ValidationError upon sequence generation."""
        import datetime
        from django.core.exceptions import ValidationError
        from apps.accounting.services.sequence_service import InvoiceSequenceService

        self.fy.is_closed = True
        self.fy.save()

        with self.assertRaises(ValidationError):
            InvoiceSequenceService.get_next_number(self.company, 'SALES', datetime.date(2026, 7, 15))

    def test_year_end_closing_and_balance_carry_forward(self):
        """Year-end closing computes balances, rolls forward real accounts and net profit to equity."""
        import datetime
        from apps.accounting.models import Voucher, LedgerEntry
        from apps.accounting.services.year_end_service import YearEndClosingService

        # Post a transaction in current FY: Debit Bank 10,000, Credit Sales 10,000
        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCP/26-27/0001",
            voucher_date=datetime.date(2026, 8, 1),
            status="POSTED",
            created_by=self.user,
            total_amount=Decimal("10000.00")
        )
        LedgerEntry.objects.create(voucher=voucher, ledger=self.bank_ledger, debit_amount=Decimal("10000.00"), credit_amount=Decimal("0.00"))
        LedgerEntry.objects.create(voucher=voucher, ledger=self.sales_ledger, debit_amount=Decimal("0.00"), credit_amount=Decimal("10000.00"))

        # Execute Year End Closing & Roll Forward
        result = YearEndClosingService.close_and_roll_forward(self.company.id, str(self.fy.id))
        self.assertTrue(result['success'])

        self.fy.refresh_from_db()
        self.assertTrue(self.fy.is_closed)

        # Verify next FY was created (FY 2027-28)
        from apps.accounting.models import FinancialYear, LedgerBalance
        next_fy = FinancialYear.objects.get(company=self.company, code="27-28")
        self.assertIsNotNone(next_fy)
        self.assertFalse(next_fy.is_closed)

        # Verify Bank Ledger (Asset) carried forward: 50,000 Op + 10,000 Dr = 60,000 Dr
        bank_next_lb = LedgerBalance.objects.get(ledger=self.bank_ledger, financial_year=next_fy)
        self.assertEqual(bank_next_lb.opening_balance, Decimal("60000.00"))
        self.assertEqual(bank_next_lb.opening_type, "DR")

        # Verify Sales Ledger (Income) reset to 0 in next FY
        sales_next_lb = LedgerBalance.objects.get(ledger=self.sales_ledger, financial_year=next_fy)
        self.assertEqual(sales_next_lb.opening_balance, Decimal("0.00"))

        # Verify Retained Earnings was credited with 10,000 Net Profit
        re_lb = LedgerBalance.objects.filter(ledger__name="Retained Earnings", financial_year=next_fy).first()
        self.assertIsNotNone(re_lb)
        self.assertEqual(re_lb.opening_balance, Decimal("10000.00"))
        self.assertEqual(re_lb.opening_type, "CR")

