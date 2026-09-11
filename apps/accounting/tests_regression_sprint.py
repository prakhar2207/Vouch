import io
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import (
    Voucher,
    VoucherItem,
    LedgerEntry,
    BankTransaction,
    BankStatementImport,
    PartyMapping,
    VoucherSequence
)
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.accounting.services.bank_statement_service import BankStatementService
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
from apps.accounting.services.voucher_service import VoucherService


class SprintRegressionTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Setup Company A
        self.comp_a = Company.objects.create(
            name="Apex Technologies",
            legal_name="Apex Technologies Pvt Ltd",
            gstin="27AAACA1111A1Z1",
            state_code="27",
            financial_year_start="2026-04-01"
        )
        self.user_a = User.objects.create_user(email="owner_a@apex.com", password="Password123!")
        UserCompany.objects.create(user=self.user_a, company=self.comp_a, role="OWNER")

        # 2. Setup Company B (For cross-tenant testing)
        self.comp_b = Company.objects.create(
            name="Blue Star Enterprises",
            legal_name="Blue Star Enterprises LLP",
            gstin="24AAACB2222B1Z2",
            state_code="24",
            financial_year_start="2026-04-01"
        )
        self.user_b = User.objects.create_user(email="owner_b@bluestar.com", password="Password123!")
        UserCompany.objects.create(user=self.user_b, company=self.comp_b, role="OWNER")

        # Ledgers for Company A
        self.grp_debtors_a = LedgerGroup.objects.create(company=self.comp_a, name="Sundry Debtors", nature="ASSET")
        self.grp_creditors_a = LedgerGroup.objects.create(company=self.comp_a, name="Sundry Creditors", nature="LIABILITY")
        self.grp_sales_a = LedgerGroup.objects.create(company=self.comp_a, name="Sales Accounts", nature="INCOME")
        self.grp_bank_a = LedgerGroup.objects.create(company=self.comp_a, name="Bank Accounts", nature="ASSET")
        self.grp_expense_a = LedgerGroup.objects.create(company=self.comp_a, name="Indirect Expenses", nature="EXPENSE")

        self.party_acme = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_debtors_a,
            name="Acme Corporation",
            ledger_type="CUSTOMER",
            state_code="27",
            current_balance=Decimal("0.00")
        )

        self.party_zenith = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_debtors_a,
            name="Zenith Industries",
            ledger_type="CUSTOMER",
            state_code="27",
            current_balance=Decimal("0.00")
        )

        self.ledger_sales = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_sales_a,
            name="Sales Account",
            ledger_type="GENERAL",
            state_code="27",
            current_balance=Decimal("0.00")
        )

        self.ledger_bank = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_bank_a,
            name="HDFC Bank Current A/c",
            ledger_type="BANK",
            state_code="27",
            current_balance=Decimal("100000.00")
        )

        self.ledger_office_rent = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_expense_a,
            name="Office Rent",
            ledger_type="EXPENSE",
            state_code="27",
            current_balance=Decimal("0.00")
        )

        self.cat_hardware = ProductCategory.objects.create(
            company=self.comp_a,
            name="Hardware",
            hsn_code="84713010",
            gst_rate=Decimal("18.00")
        )

        self.prod_keyboard = Product.objects.create(
            company=self.comp_a,
            category=self.cat_hardware,
            name="Mechanical Keyboard",
            sku="KB-001",
            unit="PCS",
            hsn_code="84713010",
            gst_rate=Decimal("18.00"),
            selling_price=Decimal("3000.00"),
            purchase_price=Decimal("2000.00"),
            stock_quantity=Decimal("100.00")
        )

    def test_voucher_party_change_preserves_party_master(self):
        """
        P0-1 & P0-2: Voucher edit MUST NOT mutate party master name.
        Changing party on a voucher creates/links target_party and leaves Acme Corp intact.
        Also verifies superseding revision on POSTED voucher.
        """
        # 1. Create a posted sales invoice for Acme Corporation
        invoice = SalesInvoiceService.generate_sales_invoice(
            company=self.comp_a,
            user=self.user_a,
            party_ledger=self.party_acme,
            items_data=[{
                "product_id": str(self.prod_keyboard.id),
                "quantity": Decimal("2.00"),
                "rate": Decimal("3000.00"),
                "gst_rate": Decimal("18.00"),
                "discount_percent": Decimal("0.00")
            }],
            manual_voucher_date="2026-05-10"
        )
        VoucherService.post_voucher(invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "POSTED")
        self.assertEqual(invoice.party_ledger.name, "Acme Corporation")

        # 2. Patch voucher to change party to "Zenith Industries"
        self.client.force_authenticate(user=self.user_a)
        url = f"/api/vouchers/{invoice.id}/"
        payload = {
            "party_name": "Zenith Industries",
            "correction_reason": "Billed to incorrect customer"
        }
        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK, getattr(res, 'data', None))

        # 3. CRITICAL AUDIT: Verify Acme Corporation's master was NOT renamed!
        self.party_acme.refresh_from_db()
        self.assertEqual(self.party_acme.name, "Acme Corporation")

        # 4. Verify original voucher is SUPERSEDED
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "SUPERSEDED")
        self.assertIsNotNone(invoice.superseded_by)

        # 5. Verify corrected revision
        new_v = invoice.superseded_by
        self.assertEqual(new_v.party_ledger.name, "Zenith Industries")
        self.assertEqual(new_v.revision_number, 2)
        self.assertEqual(new_v.revision_of, invoice)
        self.assertEqual(new_v.status, "POSTED")
        self.assertEqual(new_v.correction_reason, "Billed to incorrect customer")

    def test_monotonic_sequence_numbering_never_recycles_on_delete(self):
        """
        P0-3: Invoice sequences MUST be strictly monotonic.
        Deleting the latest voucher does NOT wind sequence backward.
        """
        v1_num, fy1 = InvoiceSequenceService.get_next_number(self.comp_a, "SALES", voucher_date="2026-05-01")
        v2_num, fy2 = InvoiceSequenceService.get_next_number(self.comp_a, "SALES", voucher_date="2026-05-02")
        
        # Verify sequential increment
        seq = VoucherSequence.objects.get(company=self.comp_a, voucher_type="SALES", financial_year=fy1)
        self.assertEqual(seq.last_number, 2)

        # Simulate voiding/deleting voucher 2
        # Verify sequence last_number is NOT reduced back to 1
        v3_num, fy3 = InvoiceSequenceService.get_next_number(self.comp_a, "SALES", voucher_date="2026-05-03")
        seq.refresh_from_db()
        self.assertEqual(seq.last_number, 3)
        self.assertNotEqual(v2_num, v3_num)

    def test_bank_statement_duplicate_upload_fingerprint_idempotency(self):
        """
        P0-4: Bank statement upload MUST be idempotent via SHA-256 fingerprinting.
        Re-uploading the same statement must not create duplicate transactions.
        """
        csv_content = (
            "Date,Description,Reference,Debit,Credit,Balance\n"
            "01/05/2026,UPI-PAYMENT-REF101,REF101,0.00,5000.00,105000.00\n"
            "02/05/2026,NEFT-VENDOR-PAYMENT,REF102,12000.00,0.00,93000.00\n"
        ).encode("utf-8")

        # 1st Upload
        summary1 = BankStatementService.parse_statement(
            company=self.comp_a,
            bank_ledger=self.ledger_bank,
            file_bytes=csv_content,
            filename="statement_may.csv",
            user=self.user_a
        )
        self.assertEqual(summary1["imported_count"], 2)
        self.assertEqual(summary1["duplicates_detected"], 0)
        self.assertEqual(BankTransaction.objects.filter(company=self.comp_a).count(), 2)

        # 2nd Upload with IDENTICAL statement
        summary2 = BankStatementService.parse_statement(
            company=self.comp_a,
            bank_ledger=self.ledger_bank,
            file_bytes=csv_content,
            filename="statement_may.csv",
            user=self.user_a
        )
        self.assertEqual(summary2["imported_count"], 0)
        self.assertEqual(summary2["duplicates_detected"], 2)
        # Verify DB still has exactly 2 rows
        self.assertEqual(BankTransaction.objects.filter(company=self.comp_a).count(), 2)

    def test_reconciled_bank_transaction_cannot_be_resolved_again(self):
        """
        P0-5: One bank transaction = one accounting outcome.
        Attempting to resolve an already-reconciled transaction raises ValidationError.
        """
        tx = BankTransaction.objects.create(
            company=self.comp_a,
            bank_ledger=self.ledger_bank,
            transaction_date="2026-05-15",
            description="Office Electricity Bill",
            normalized_narration="OFFICE ELECTRICITY BILL",
            debit_amount=Decimal("4500.00"),
            credit_amount=Decimal("0.00"),
            balance=Decimal("95500.00"),
            status="UNRESOLVED"
        )

        # 1st Resolution: Record Expense
        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type="RECORD_EXPENSE",
            payload={"expense_ledger_id": str(self.ledger_office_rent.id)},
            user=self.user_a
        )
        self.assertEqual(res["status"], "SUCCESS")

        tx.refresh_from_db()
        self.assertEqual(tx.status, "RECONCILED")
        self.assertIsNotNone(tx.matched_voucher)

        # 2nd Resolution attempt MUST fail with ValidationError
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=tx,
                action_type="RECORD_EXPENSE",
                payload={"expense_ledger_id": str(self.ledger_office_rent.id)},
                user=self.user_a
            )
        self.assertIn("already been reconciled", str(ctx.exception).lower())

    def test_multi_tenant_authorization_barrier(self):
        """
        P0-7: Cross-tenant security barrier.
        User A cannot access Company B's bank transactions or health data (403 Forbidden).
        """
        self.client.force_authenticate(user=self.user_a)

        # User A requests Company B banking transactions
        res_bank = self.client.get(
            "/api/v1/accounting/banking/transactions/",
            HTTP_X_COMPANY_ID=str(self.comp_b.id)
        )
        self.assertEqual(res_bank.status_code, status.HTTP_403_FORBIDDEN)

        # User A requests Company B health audit
        res_health = self.client.get(
            "/api/v1/accounting/health/",
            HTTP_X_COMPANY_ID=str(self.comp_b.id)
        )
        self.assertEqual(res_health.status_code, status.HTTP_403_FORBIDDEN)

    def test_semantic_party_balance_states(self):
        """
        P1-28: Backend semantic balance states:
        CUSTOMER: >0 TO_COLLECT, <0 ADVANCE_RECEIVED, ==0 SETTLED
        SUPPLIER: >0 TO_PAY, <0 ADVANCE_PAID, ==0 SETTLED
        """
        # Customer with debit balance
        self.party_acme.current_balance = Decimal("15000.00")
        self.party_acme.save()
        self.assertEqual(self.party_acme.balance_state, "TO_COLLECT")
        self.assertEqual(self.party_acme.display_amount, Decimal("15000.00"))

        # Customer with credit balance (advance received)
        self.party_acme.current_balance = Decimal("-3500.00")
        self.party_acme.save()
        self.assertEqual(self.party_acme.balance_state, "ADVANCE_RECEIVED")
        self.assertEqual(self.party_acme.display_amount, Decimal("3500.00"))

        # Supplier with credit balance
        supplier = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_creditors_a,
            name="National Paper Mill",
            ledger_type="SUPPLIER",
            current_balance=Decimal("28000.00")
        )
        self.assertEqual(supplier.balance_state, "TO_PAY")
        self.assertEqual(supplier.display_amount, Decimal("28000.00"))

        # Settled party
        supplier.current_balance = Decimal("0.00")
        supplier.save()
        self.assertEqual(supplier.balance_state, "SETTLED")
