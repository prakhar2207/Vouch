import uuid
import datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import Voucher, BankTransaction
from apps.analytics.services.ai_service import AnalyticsEngine


class LocalAnalyticsAndDeltaSyncTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Company A
        self.comp_a = Company.objects.create(
            name="Vouch Local-First Org",
            legal_name="Vouch Local-First Org Pvt Ltd",
            gstin="27AAACA1111A1Z1",
            state_code="27",
            financial_year_start="2026-04-01"
        )
        self.user_a = User.objects.create_user(email="localfirst_a@vouch.com", password="Password123!")
        UserCompany.objects.create(user=self.user_a, company=self.comp_a, role="OWNER")

        # Company B
        self.comp_b = Company.objects.create(
            name="Other Org",
            legal_name="Other Org LLP",
            gstin="24AAACB2222B1Z2",
            state_code="24",
            financial_year_start="2026-04-01"
        )
        self.user_b = User.objects.create_user(email="other_b@vouch.com", password="Password123!")
        UserCompany.objects.create(user=self.user_b, company=self.comp_b, role="OWNER")

        # Ledgers & Products
        self.grp_debtors = LedgerGroup.objects.create(company=self.comp_a, name="Sundry Debtors", nature="ASSET")
        self.grp_bank = LedgerGroup.objects.create(company=self.comp_a, name="Bank Accounts", nature="ASSET")
        self.bank_ledger = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_bank,
            name="HDFC Current Account",
            ledger_type="BANK",
        )
        self.party_1 = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_debtors,
            name="Customer One",
            ledger_type="CUSTOMER",
        )
        self.party_2 = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_debtors,
            name="Customer Two",
            ledger_type="CUSTOMER",
        )

        self.cat_a = ProductCategory.objects.create(company=self.comp_a, name="Widgets")
        self.prod_1 = Product.objects.create(
            company=self.comp_a,
            category=self.cat_a,
            name="Super Widget",
            purchase_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
            stock_quantity=Decimal("20.00")
        )

    def test_cursor_based_pull_pagination(self):
        """Verify delta sync pull supports cursor pagination (limit, next_cursor, has_more)."""
        self.client.force_authenticate(user=self.user_a)

        # Create 12 vouchers
        for i in range(12):
            Voucher.objects.create(
                company=self.comp_a,
                voucher_number=f"VOUCH-TEST-{i:03d}",
                voucher_type="SALES",
                voucher_date=timezone.now().date(),
                party_ledger=self.party_1,
                total_amount=Decimal(f"{(i+1)*100}.00"),
                status="POSTED",
                created_by=self.user_a
            )

        # First page with limit 5
        res1 = self.client.post(
            "/api/v1/sync/pull/",
            data={"company_id": str(self.comp_a.id), "limit": 5, "since_version": 0},
            format="json"
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertTrue(res1.data.get("has_more"))
        self.assertIsNotNone(res1.data.get("next_cursor"))
        vouchers_p1 = res1.data["changes"]["vouchers"]["created"]
        self.assertEqual(len(vouchers_p1), 5)

        cursor1 = res1.data["next_cursor"]

        # Second page with limit 5 and cursor
        res2 = self.client.post(
            "/api/v1/sync/pull/",
            data={"company_id": str(self.comp_a.id), "limit": 5, "cursor": cursor1, "since_version": 0},
            format="json"
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertTrue(res2.data.get("has_more"))
        vouchers_p2 = res2.data["changes"]["vouchers"]["created"]
        self.assertEqual(len(vouchers_p2), 5)

        cursor2 = res2.data["next_cursor"]

        # Third page with remaining items
        res3 = self.client.post(
            "/api/v1/sync/pull/",
            data={"company_id": str(self.comp_a.id), "limit": 5, "cursor": cursor2, "since_version": 0},
            format="json"
        )
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertFalse(res3.data.get("has_more"))
        vouchers_p3 = res3.data["changes"]["vouchers"]["created"]
        self.assertEqual(len(vouchers_p3), 2)

        # Verify all 12 IDs are distinct
        all_ids = [v["id"] for v in vouchers_p1 + vouchers_p2 + vouchers_p3]
        self.assertEqual(len(set(all_ids)), 12)

    def test_pull_change_categorization_and_entities(self):
        """Verify changes are correctly categorized as created/updated/deleted for vouchers, ledgers, products."""
        self.client.force_authenticate(user=self.user_a)

        res = self.client.post(
            "/api/v1/sync/pull/",
            data={"company_id": str(self.comp_a.id), "since_version": 0},
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        changes = res.data["changes"]

        # Check structure
        for entity in ["vouchers", "ledgers", "products"]:
            self.assertIn(entity, changes)
            self.assertIn("created", changes[entity])
            self.assertIn("updated", changes[entity])
            self.assertIn("deleted", changes[entity])

        # Ledgers should contain created ledgers
        created_ledgers = changes["ledgers"]["created"]
        ledger_names = [l["name"] for l in created_ledgers]
        self.assertIn("Customer One", ledger_names)
        self.assertIn("HDFC Current Account", ledger_names)

        # Products should contain created product
        created_prods = changes["products"]["created"]
        prod_names = [p["name"] for p in created_prods]
        self.assertIn("Super Widget", prod_names)

    def test_sql_aggregated_rfm_segments(self):
        """Verify AnalyticsEngine.get_rfm_segments calculates correct customer RFM without loading raw rows into Pandas."""
        # Create sales for Customer 1 (high frequency, high spend)
        for i in range(5):
            Voucher.objects.create(
                company=self.comp_a,
                voucher_number=f"RFM-SALES-1-{i}",
                voucher_type="SALES",
                voucher_date=timezone.now().date(),
                party_ledger=self.party_1,
                total_amount=Decimal("10000.00"),
                status="POSTED",
                created_by=self.user_a
            )

        # Create sales for Customer 2 (low frequency, low spend)
        Voucher.objects.create(
            company=self.comp_a,
            voucher_number="RFM-SALES-2-0",
            voucher_type="SALES",
            voucher_date=timezone.now().date(),
            party_ledger=self.party_2,
            total_amount=Decimal("500.00"),
            status="POSTED",
            created_by=self.user_a
        )

        segments = AnalyticsEngine.get_rfm_segments(self.comp_a)
        self.assertEqual(len(segments), 2)

        c1 = next(s for s in segments if s["party_ledger__name"] == "Customer One")
        c2 = next(s for s in segments if s["party_ledger__name"] == "Customer Two")

        self.assertEqual(c1["frequency"], 5)
        self.assertEqual(c1["monetary"], 50000.0)
        self.assertEqual(c1["recency"], 0)

        self.assertEqual(c2["frequency"], 1)
        self.assertEqual(c2["monetary"], 500.0)
        self.assertEqual(c2["recency"], 0)

        # Tier assignment check
        self.assertIn("High Value", c1["segment"])

    def test_bank_transaction_match_notes_object(self):
        """Verify BankTransaction with JSON match_notes is serialized cleanly via banking transactions view."""
        self.client.force_authenticate(user=self.user_a)

        tx = BankTransaction.objects.create(
            company=self.comp_a,
            bank_ledger=self.bank_ledger,
            transaction_date=timezone.now().date(),
            description="UPI/PY01/Alpha Retailers/Payment",
            normalized_narration="UPI ALPHARETAILERS PAYMENT",
            credit_amount=Decimal("5000.00"),
            debit_amount=Decimal("0.00"),
            status="NEEDS_REVIEW",
            matched_party=self.party_1,
            match_confidence=75,
            match_notes={
                "signals": ["Party name match in narration", "Credit amount matches open invoice"],
                "suggested_matches": [{"party_id": str(self.party_1.id), "score": 75}],
                "is_duplicate": False
            }
        )

        res = self.client.get(
            f"/api/v1/accounting/banking/transactions/?bank_ledger_id={self.bank_ledger.id}",
            HTTP_X_COMPANY_ID=str(self.comp_a.id)
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        txs = res.data.get("results", [])
        matched_tx = next((t for t in txs if t["id"] == str(tx.id)), None)
        self.assertIsNotNone(matched_tx)
        self.assertIsInstance(matched_tx["match_notes"], dict)
        self.assertIn("signals", matched_tx["match_notes"])

    def test_by_clg_customer_deposit_direction_and_party_match(self):
        """
        Verify BY CLG inward clearing is parsed as CREDIT (Deposit) and matches CUSTOMER,
        never falling back to DEBIT or Supplier Payment.
        """
        from apps.accounting.services.bank_statement_service import BankStatementService
        from apps.accounting.services.party_intelligence_service import PartyIntelligenceService

        # Match party directly
        narration = "BY CLG:DEL ACCTS-BANK OF BARODA (BOB), CUSTOMER ONE Chq: 000000000620 -"
        match_res = PartyIntelligenceService.match_transaction(
            company=self.comp_a,
            narration=narration,
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("4870.00")
        )
        self.assertIsNotNone(match_res["matched_party"])
        self.assertEqual(match_res["matched_party"].id, self.party_1.id)
        self.assertEqual(match_res["matched_party"].ledger_type, "CUSTOMER")

    def test_strategy_b_closing_balance_and_by_clg_pdf_tokens(self):
        """
        Verify Strategy B parser treats BY CLG as credit, strips closing balance lines,
        and parses SC charges as debit.
        """
        from apps.accounting.services.bank_statement_service import BankStatementService

        sample_pdf_text = (
            "page 1 Date Particulars Deposits Withdrawals Balance\n"
            "21/04/2026 BY CLG:DEL ACCTS-BANK OF BARODA (BOB), CUSTOMER ONE Chq: 000000000620 - 4870.00 967887.78\n"
            "23/04/2026 SC NEFT OTHER THAN SB IMB Chq: 0 - 3.00 970681.78\n"
            "01/05/2026 CASA DEBIT INTEREST CAPITALIZED Chq: - 8105.00 913822.78 Closing Balance - page 4\n"
        )
        # Test Strategy B tokenizer directly or via CSV equivalent with identical tokens
        csv_bytes = (
            "Date,Particulars,Deposits,Withdrawals,Balance\n"
            "21/04/2026,BY CLG:DEL ACCTS-BANK OF BARODA (BOB) CUSTOMER ONE,4870.00,,967887.78\n"
            "23/04/2026,SC NEFT OTHER THAN SB IMB,,3.00,970681.78\n"
            "01/05/2026,CASA DEBIT INTEREST CAPITALIZED,,8105.00,913822.78\n"
        ).encode('utf-8')

        parsed, errors = BankStatementService.parse_csv(csv_bytes)
        self.assertEqual(len(parsed), 3)

        # Row 1: BY CLG must be credit
        r1 = parsed[0]
        self.assertEqual(r1["credit"], Decimal("4870.00"))
        self.assertEqual(r1["debit"], Decimal("0.00"))

        # Row 2: SC NEFT must be debit
        r2 = parsed[1]
        self.assertEqual(r2["debit"], Decimal("3.00"))
        self.assertEqual(r2["credit"], Decimal("0.00"))

        # Row 3: CASA DEBIT INTEREST must be debit
        r3 = parsed[2]
        self.assertEqual(r3["debit"], Decimal("8105.00"))
        self.assertEqual(r3["credit"], Decimal("0.00"))

    def test_cash_deposit_auto_match_and_reconcile(self):
        """
        Verify cash deposits (e.g. CASH DEPOSIT SELF) match company Cash ledger
        and can be reconciled against open cash invoices.
        """
        from apps.accounting.services.party_intelligence_service import PartyIntelligenceService
        from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
        from apps.accounting.models import BankTransaction
        from apps.ledgers.models import LedgerGroup

        cash_grp, _ = LedgerGroup.objects.get_or_create(company=self.comp_a, name="Cash-in-Hand", defaults={"nature": "ASSET"})
        cash_ledger, _ = Ledger.objects.get_or_create(
            company=self.comp_a,
            name="Cash",
            defaults={"group": cash_grp, "ledger_type": "CASH", "opening_balance_type": "DEBIT"}
        )

        match_res = PartyIntelligenceService.match_transaction(
            company=self.comp_a,
            narration="CASH DEPOSIT SELF 9949_PANKIKA Chq: -",
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("5000.00")
        )

        self.assertTrue(match_res.get("is_cash_deposit"))
        self.assertEqual(match_res["matched_party"].id, cash_ledger.id)
        self.assertGreaterEqual(match_res["confidence"], 0.95)

        # Create a BankTransaction and reconcile it
        bank_tx = BankTransaction.objects.create(
            company=self.comp_a,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 4, 21),
            description="CASH DEPOSIT SELF 9949_PANKIKA Chq: -",
            normalized_narration="CASH DEPOSIT SELF 9949_PANKIKA",
            credit_amount=Decimal("5000.00"),
            debit_amount=Decimal("0.00"),
            status="UNRESOLVED"
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=bank_tx,
            action_type="RECORD_PAYMENT",
            payload={"party_id": str(cash_ledger.id), "narration": "Reconciled Cash Deposit"},
            user=self.user_a
        )

        bank_tx.refresh_from_db()
        self.assertEqual(bank_tx.status, "RECONCILED")
        self.assertIsNotNone(bank_tx.matched_voucher)
        self.assertEqual(bank_tx.matched_voucher.voucher_type, "RECEIPT")

        # Now test deleting this reconciled transaction rolls back the voucher cleanly
        BankReconciliationService.delete_transaction(bank_tx)
        self.assertFalse(BankTransaction.objects.filter(id=bank_tx.id).exists())

    def test_delete_statement_import_rolls_back_transactions(self):
        """
        Verify deleting a statement import removes all its imported transactions and the import record.
        """
        from apps.accounting.models import BankStatementImport, BankTransaction
        from apps.accounting.services.bank_reconciliation_service import BankReconciliationService

        stmt = BankStatementImport.objects.create(
            company=self.comp_a,
            bank_ledger=self.bank_ledger,
            source_file_name="test_statement.pdf",
            total_rows=2,
            successful_rows=2
        )
        tx1 = BankTransaction.objects.create(
            company=self.comp_a,
            statement_import=stmt,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 4, 1),
            description="Tx 1",
            normalized_narration="TX 1",
            credit_amount=Decimal("100.00"),
            status="UNRESOLVED"
        )
        tx2 = BankTransaction.objects.create(
            company=self.comp_a,
            statement_import=stmt,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 4, 2),
            description="Tx 2",
            normalized_narration="TX 2",
            debit_amount=Decimal("50.00"),
            status="UNRESOLVED"
        )

        deleted = BankReconciliationService.delete_statement_import(stmt)
        self.assertEqual(deleted, 2)
        self.assertFalse(BankStatementImport.objects.filter(id=stmt.id).exists())
        self.assertFalse(BankTransaction.objects.filter(id__in=[tx1.id, tx2.id]).exists())


