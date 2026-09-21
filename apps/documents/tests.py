import datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.inventory.models import Product, ProductCategory
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, VoucherItem, FinancialYear
from apps.documents.capabilities import get_document_capabilities, can_edi
from apps.documents.models import DocumentSnapshot, DocumentShare, EDIDocument, EDIExchange
from apps.documents.services import (
    DocumentSnapshotService,
    DocumentPDFService,
    DocumentShareService,
    InvoiceEDIService,
)


class DocumentArchitectureTests(TestCase):
    def setUp(self):
        # 1. Setup Seller Company
        self.seller_user = User.objects.create_user(
            email='seller@test.com',
            password='testpassword123',
            first_name='Seller'
        )
        self.seller_company = Company.objects.create(
            name='Annapurna Belting Store',
            legal_name='Maa Annapurna Belting Store',
            gstin='09CIPPS1329P2ZL',
            state_code='09',
            state_name='Uttar Pradesh',
            address='123/456 Fazalganj, Kanpur',
            city='Kanpur',
            phone='9876543210',
            email='annapurna@test.com',
        )
        UserCompany.objects.create(
            user=self.seller_user,
            company=self.seller_company,
            role='OWNER'
        )

        # 2. Setup Buyer Company
        self.buyer_user = User.objects.create_user(
            email='buyer@test.com',
            password='testpassword123',
            first_name='Buyer'
        )
        self.buyer_company = Company.objects.create(
            name='Talwar Industries',
            legal_name='Talwar Industries Pvt Ltd',
            gstin='09AAGPT8254P2ZO',
            state_code='09',
            state_name='Uttar Pradesh',
            address='D-12 Site 1 Panki, Kanpur',
            city='Kanpur',
            phone='9123456780',
            email='talwar@test.com',
        )
        UserCompany.objects.create(
            user=self.buyer_user,
            company=self.buyer_company,
            role='OWNER'
        )

        # 3. Seller Financial Year & Ledgers
        self.seller_fy = FinancialYear.objects.create(
            company=self.seller_company,
            name='FY 2026-27',
            code='26-27',
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31),
        )
        self.debtors_group = LedgerGroup.objects.create(
            company=self.seller_company,
            name='Sundry Debtors',
            nature='ASSET',
        )
        self.customer_ledger = Ledger.objects.create(
            company=self.seller_company,
            group=self.debtors_group,
            name='Talwar Industries',
            gstin='09AAGPT8254P2ZO',
            state_code='09',
            address='D-12 Site 1 Panki, Kanpur',
            phone='9123456780',
            ledger_type='CUSTOMER',
        )

        # 4. Product
        self.seller_category = ProductCategory.objects.create(
            company=self.seller_company,
            name='Industrial Belts'
        )
        self.product = Product.objects.create(
            company=self.seller_company,
            category=self.seller_category,
            name='Timing Belt 550H',
            hsn_code='40103990',
            unit='PCS',
            gst_rate=Decimal('18.00'),
            purchase_price=Decimal('500.00'),
            selling_price=Decimal('700.00'),
            stock_quantity=Decimal('100.00'),
        )

        # 5. Sales Voucher
        self.voucher = Voucher.objects.create(
            company=self.seller_company,
            financial_year=self.seller_fy,
            voucher_type='SALES',
            voucher_number='INV/26-27/0108',
            voucher_date=datetime.date(2026, 9, 21),
            party_ledger=self.customer_ledger,
            buyer_name='Talwar Industries',
            buyer_gstin='09AAGPT8254P2ZO',
            buyer_address='D-12 Site 1 Panki, Kanpur',
            buyer_state_code='09',
            status='POSTED',
            total_amount=Decimal('826.00'),
            created_by=self.seller_user,
        )
        self.item = VoucherItem.objects.create(
            voucher=self.voucher,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('700.00'),
            discount_percent=Decimal('0.00'),
            taxable_amount=Decimal('700.00'),
            gst_rate=Decimal('18.00'),
            total_amount=Decimal('826.00'),
        )

    def test_capabilities_enforcement(self):
        """Verify strict capability rules: statements and reports strictly reject EDI."""
        self.assertTrue(can_edi('SALES_INVOICE'))
        self.assertFalse(can_edi('CUSTOMER_STATEMENT'))
        self.assertFalse(can_edi('SUPPLIER_STATEMENT'))
        self.assertFalse(can_edi('LEDGER'))
        self.assertFalse(can_edi('TRIAL_BALANCE'))
        self.assertFalse(can_edi('PROFIT_AND_LOSS'))
        self.assertFalse(can_edi('BALANCE_SHEET'))

    def test_snapshot_creation_and_immutability(self):
        """Verify that document snapshot captures historical state and is immune to live mutations."""
        snapshot = DocumentSnapshotService.get_or_create_voucher_snapshot(self.voucher)
        self.assertEqual(snapshot.document_type, 'SALES_INVOICE')
        self.assertEqual(snapshot.document_number, 'INV/26-27/0108')
        self.assertEqual(snapshot.snapshot_json['seller']['name'], 'Annapurna Belting Store')
        self.assertEqual(snapshot.snapshot_json['buyer']['name'], 'Talwar Industries')

        # Mutate seller company and party in database
        self.seller_company.name = "New Mutated Name"
        self.seller_company.save()
        self.customer_ledger.name = "New Mutated Party"
        self.customer_ledger.save()

        # Retrieve existing snapshot - should preserve original historical facts
        retrieved_snapshot = DocumentSnapshotService.get_or_create_voucher_snapshot(self.voucher)
        self.assertEqual(retrieved_snapshot.snapshot_json['seller']['name'], 'Annapurna Belting Store')
        self.assertEqual(retrieved_snapshot.snapshot_json['buyer']['name'], 'Talwar Industries')

    def test_deterministic_pdf_generation(self):
        """Verify PDF bytes generation from snapshot and voucher without ORM recalculation."""
        pdf_bytes = DocumentPDFService.generate_pdf_for_voucher(self.voucher)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_statement_generation_and_pdf(self):
        """Verify Statement DTO and Statement PDF renderer."""
        pdf_bytes = DocumentPDFService.generate_pdf_for_statement(
            self.seller_company, self.customer_ledger
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_financial_reports_pdf(self):
        """Verify Trial Balance, P&L, and Balance Sheet PDF renderers."""
        tb_pdf = DocumentPDFService.generate_pdf_for_report('TRIAL_BALANCE', self.seller_company)
        self.assertTrue(tb_pdf.startswith(b'%PDF-'))

        pl_pdf = DocumentPDFService.generate_pdf_for_report('PROFIT_AND_LOSS', self.seller_company)
        self.assertTrue(pl_pdf.startswith(b'%PDF-'))

        bs_pdf = DocumentPDFService.generate_pdf_for_report('BALANCE_SHEET', self.seller_company)
        self.assertTrue(bs_pdf.startswith(b'%PDF-'))

    def test_secure_token_sharing_and_resolution(self):
        """Verify 32-char token generation, SHA-256 storage, and resolution."""
        snapshot = DocumentSnapshotService.get_or_create_voucher_snapshot(self.voucher)
        raw_token, share = DocumentShareService.create_share(snapshot, user=self.seller_user, expires_in_days=7)

        self.assertNotEqual(raw_token, share.token_hash)
        self.assertEqual(len(share.token_hash), 64)  # SHA-256 hex length
        self.assertTrue(share.is_active)

        # Resolve share using raw token
        resolved_share = DocumentShareService.resolve_share(raw_token, record_event='VIEWED')
        self.assertEqual(resolved_share.id, share.id)
        self.assertEqual(resolved_share.events.count(), 2)  # CREATED + VIEWED

        # Test revocation
        DocumentShareService.revoke_share(share, user=self.seller_user)
        self.assertFalse(share.is_active)
        with self.assertRaises(PermissionDenied):
            DocumentShareService.resolve_share(raw_token)

    def test_edi_handshake_and_duplicate_prevention(self):
        """Verify 'Add to my Vouch' imports invoice as DRAFT Purchase Bill and prevents duplicate imports."""
        snapshot = DocumentSnapshotService.get_or_create_voucher_snapshot(self.voucher)
        edi_doc = InvoiceEDIService.get_or_create_edi_document(snapshot)
        self.assertEqual(edi_doc.receiver_gstin, '09AAGPT8254P2ZO')

        # First import attempt by buyer
        result = InvoiceEDIService.import_invoice_to_buyer(edi_doc, self.buyer_company, self.buyer_user)
        self.assertTrue(result['success'])
        self.assertFalse(result['already_imported'])
        self.assertEqual(result['status'], 'DRAFT')

        draft_vch = Voucher.objects.get(id=result['voucher_id'])
        self.assertEqual(draft_vch.voucher_type, 'PURCHASE')
        self.assertEqual(draft_vch.status, 'DRAFT')  # STRICTLY DRAFT, not posted
        self.assertEqual(draft_vch.total_amount, Decimal('826.00'))
        self.assertEqual(draft_vch.party_ledger.name, 'Annapurna Belting Store')
        self.assertEqual(draft_vch.items.count(), 1)
        self.assertEqual(draft_vch.items.first().product.name, 'Timing Belt 550H')

        # Second import attempt (Duplicate Prevention)
        second_result = InvoiceEDIService.import_invoice_to_buyer(edi_doc, self.buyer_company, self.buyer_user)
        self.assertTrue(second_result['success'])
        self.assertTrue(second_result['already_imported'])
        self.assertEqual(second_result['voucher_id'], str(draft_vch.id))

    def test_statement_edi_rejection(self):
        """Verify that any attempt to perform EDI on a statement snapshot is rejected."""
        stmt_snapshot = DocumentSnapshotService.create_statement_snapshot(
            self.seller_company, self.customer_ledger
        )
        self.assertFalse(can_edi(stmt_snapshot.document_type))

        with self.assertRaises(PermissionDenied):
            InvoiceEDIService.get_or_create_edi_document(stmt_snapshot)

    def test_api_endpoints_end_to_end(self):
        """Test API endpoints: snapshot, PDF stream, share create/resolve, and EDI import."""
        from rest_framework.test import APIClient
        client = APIClient()

        # 1. Snapshot API (Authenticated)
        client.force_authenticate(user=self.seller_user)
        snap_resp = client.get(
            f"/api/v1/documents/vouchers/{self.voucher.id}/snapshot/",
            HTTP_X_COMPANY_ID=str(self.seller_company.id)
        )
        self.assertEqual(snap_resp.status_code, 200)
        self.assertEqual(snap_resp.data['document_number'], 'INV/26-27/0108')
        self.assertTrue(snap_resp.data['capabilities']['edi'])

        # 2. PDF Stream API
        pdf_resp = client.get(
            f"/api/v1/documents/vouchers/{self.voucher.id}/pdf/",
            HTTP_X_COMPANY_ID=str(self.seller_company.id)
        )
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp['Content-Type'], 'application/pdf')
        self.assertTrue(pdf_resp.content.startswith(b'%PDF-'))

        # 3. Share Create API
        share_resp = client.post(
            f"/api/v1/documents/vouchers/{self.voucher.id}/share/",
            {'expires_in_days': 15},
            HTTP_X_COMPANY_ID=str(self.seller_company.id)
        )
        self.assertEqual(share_resp.status_code, 200)
        raw_token = share_resp.data['raw_token']
        self.assertTrue(raw_token)

        # 4. Public Share Resolve API (Unauthenticated)
        client.force_authenticate(user=None)
        resolve_resp = client.get(f"/api/v1/documents/share/resolve/{raw_token}/")
        self.assertEqual(resolve_resp.status_code, 200)
        self.assertEqual(resolve_resp.data['document_number'], 'INV/26-27/0108')
        self.assertTrue(resolve_resp.data['capabilities']['edi'])

        # 5. Public Share Download PDF
        dl_resp = client.get(f"/api/v1/documents/share/download/{raw_token}/")
        self.assertEqual(dl_resp.status_code, 200)
        self.assertEqual(dl_resp['Content-Type'], 'application/pdf')

        # 6. EDI Import by Buyer
        client.force_authenticate(user=self.buyer_user)
        import_resp = client.post(
            f"/api/v1/documents/share/import/{raw_token}/",
            HTTP_X_COMPANY_ID=str(self.buyer_company.id)
        )
        self.assertEqual(import_resp.status_code, 201)
        self.assertTrue(import_resp.data['success'])
        self.assertEqual(import_resp.data['status'], 'DRAFT')

        # 7. Statement Share & EDI Hard Block Check
        client.force_authenticate(user=self.seller_user)
        stmt_share_resp = client.post(
            f"/api/v1/documents/statements/{self.customer_ledger.id}/share/",
            HTTP_X_COMPANY_ID=str(self.seller_company.id)
        )
        self.assertEqual(stmt_share_resp.status_code, 200)
        stmt_token = stmt_share_resp.data['raw_token']

        # Public resolve on statement must show can_edi = False
        client.force_authenticate(user=None)
        stmt_resolve_resp = client.get(f"/api/v1/documents/share/resolve/{stmt_token}/")
        self.assertEqual(stmt_resolve_resp.status_code, 200)
        self.assertFalse(stmt_resolve_resp.data['capabilities']['edi'])

        # Attempting EDI import on statement token must return HTTP 400
        client.force_authenticate(user=self.buyer_user)
        blocked_resp = client.post(
            f"/api/v1/documents/share/import/{stmt_token}/",
            HTTP_X_COMPANY_ID=str(self.buyer_company.id)
        )
        self.assertEqual(blocked_resp.status_code, 400)
        self.assertIn('EDI import is not permitted', blocked_resp.data['error'])
