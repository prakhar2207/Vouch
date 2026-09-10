import io
import datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
import openpyxl

from apps.companies.models import Company, CompanySettings
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import (
    FinancialYear, Voucher, VoucherItem, LedgerEntry, PaymentAllocation,
    BankStatementImport, BankTransaction, PartyMapping, AccountingFinding
)
from apps.accounting.services.bank_statement_service import BankStatementService
from apps.accounting.services.party_intelligence_service import PartyIntelligenceService
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
from apps.accounting.services.integrity_engine import AccountingIntegrityEngine
from apps.accounting.services.finding_fix_service import FindingFixService
from apps.accounting.services.voucher_service import VoucherService
from apps.inventory.models import Product, Warehouse

class BankIntelligenceAndAccountingHealthTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Vouch Test Retailers Pvt Ltd",
            gstin="27AABCV1234F1Z5",
            state_code="27"
        )
        self.company_b = Company.objects.create(
            name="Competitor Enterprises",
            gstin="27XYZAB9999K1Z2",
            state_code="27"
        )
        self.user = User.objects.create_user(
            email="owner@vouchtest.com",
            password="testpassword123"
        )
        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 2026-27",
            code="26-27",
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31)
        )

        self.asset_grp = LedgerGroup.objects.create(company=self.company, name="Bank Accounts", nature="ASSET")
        self.debtor_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Debtors", nature="ASSET")
        self.creditor_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Creditors", nature="LIABILITY")
        self.exp_grp = LedgerGroup.objects.create(company=self.company, name="Indirect Expenses", nature="EXPENSE")
        self.income_grp = LedgerGroup.objects.create(company=self.company, name="Sales Accounts", nature="INCOME")

        self.bank_ledger = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="HDFC Current A/c",
            ledger_type="BANK",
            bank_account_number="50200012345678",
            bank_ifsc="HDFC0000123"
        )

        self.customer = Ledger.objects.create(
            company=self.company,
            group=self.debtor_grp,
            name="Rajesh Kumar Traders",
            ledger_type="CUSTOMER",
            phone="9876543210",
            gstin="27ABCDE1234F1Z5",
            state_code="27"
        )

        self.supplier = Ledger.objects.create(
            company=self.company,
            group=self.creditor_grp,
            name="Apex Industrial Suppliers Pvt Ltd",
            ledger_type="SUPPLIER",
            phone="9123456780",
            gstin="27AABCA5678M1Z8",
            state_code="27"
        )

        self.sales_ledger = Ledger.objects.create(
            company=self.company,
            group=self.income_grp,
            name="GST Sales 18%",
            ledger_type="INCOME"
        )

    # -------------------------------------------------------------
    # 1. Bank Statement Ingestion Tests
    # -------------------------------------------------------------
    def test_01_csv_parsing_standard_indian_format(self):
        """Scenario 1: Parse standard CSV with Date, Narration, Ref, Debit, Credit, Balance."""
        csv_data = (
            "Txn Date,Particulars,Chq/Ref No,Debit,Credit,Balance\n"
            "10/09/2026,UPI/rajesh@okhdfcbank/INV12,UPI123456,0.00,18500.00,118500.00\n"
            "11/09/2026,NEFT-APEX SUPPLIERS-AXIS001,NEFT789012,25000.00,0.00,93500.00\n"
        ).encode('utf-8')

        summary = BankStatementService.parse_statement(
            company=self.company,
            bank_ledger=self.bank_ledger,
            file_bytes=csv_data,
            filename="hdfc_statement.csv",
            user=self.user
        )

        self.assertEqual(summary['status'], 'COMPLETED')
        self.assertEqual(summary['successful_rows'], 2)
        self.assertEqual(summary['failed_rows'], 0)
        self.assertEqual(BankTransaction.objects.filter(company=self.company).count(), 2)

        tx1 = BankTransaction.objects.get(reference_number="UPI123456")
        self.assertEqual(tx1.credit_amount, Decimal('18500.00'))
        self.assertEqual(tx1.debit_amount, Decimal('0.00'))
        self.assertEqual(tx1.transaction_date, datetime.date(2026, 9, 10))

    def test_02_csv_parsing_single_amount_with_indicator(self):
        """Scenario 2: Parse CSV with single Amount column and Dr/Cr indicator."""
        csv_data = (
            "Date,Description,Amount,Type,Ref No\n"
            "12-09-2026,Customer Payment,15000.00,CR,REF101\n"
            "13-09-2026,Office Supplies,3200.00,DR,REF102\n"
        ).encode('utf-8')

        summary = BankStatementService.parse_statement(
            company=self.company,
            bank_ledger=self.bank_ledger,
            file_bytes=csv_data,
            filename="single_amt.csv",
            user=self.user
        )

        self.assertEqual(summary['successful_rows'], 2)
        tx_cr = BankTransaction.objects.get(reference_number="REF101")
        self.assertEqual(tx_cr.credit_amount, Decimal('15000.00'))
        tx_dr = BankTransaction.objects.get(reference_number="REF102")
        self.assertEqual(tx_dr.debit_amount, Decimal('3200.00'))

    def test_03_excel_xlsx_parsing(self):
        """Scenario 3: Parse Excel XLSX statement via openpyxl."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Transaction Date", "Narration", "Cheque No", "Withdrawal (Dr)", "Deposit (Cr)", "Balance"])
        ws.append(["15/09/2026", "UPI/rajesh@okhdfcbank/INV15", "UTR99999", None, 12000.00, 105500.00])
        ws.append(["16/09/2026", "Bank Service Charges", "CHQ001", 354.00, None, 105146.00])

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)

        summary = BankStatementService.parse_statement(
            company=self.company,
            bank_ledger=self.bank_ledger,
            file_bytes=stream.getvalue(),
            filename="statement.xlsx",
            user=self.user
        )

        self.assertEqual(summary['successful_rows'], 2)
        self.assertEqual(summary['file_format'], 'XLSX')

    def test_04_partial_failure_resilience(self):
        """Scenario 4: File with 1 invalid date row and 2 valid rows produces PARTIAL status and imports 2 valid."""
        csv_data = (
            "Date,Particulars,Ref,Debit,Credit\n"
            "10/09/2026,Valid Row 1,REF001,0.00,5000.00\n"
            "INVALID_DATE_TEXT,Bad Row,REF002,0.00,3000.00\n"
            "12/09/2026,Valid Row 2,REF003,1200.00,0.00\n"
        ).encode('utf-8')

        summary = BankStatementService.parse_statement(
            company=self.company,
            bank_ledger=self.bank_ledger,
            file_bytes=csv_data,
            filename="partial.csv",
            user=self.user
        )

        self.assertEqual(summary['status'], 'PARTIAL')
        self.assertEqual(summary['successful_rows'], 2)
        self.assertEqual(summary['failed_rows'], 1)
        self.assertEqual(len(summary['errors']), 1)
        self.assertEqual(BankTransaction.objects.filter(company=self.company).count(), 2)

    def test_05_duplicate_transaction_detection(self):
        """Scenario 5: Uploading identical statement twice detects duplicates and marks as IGNORED."""
        csv_data = (
            "Date,Particulars,Ref,Debit,Credit\n"
            "10/09/2026,Unique Deposit,DUPREF1,0.00,5000.00\n"
        ).encode('utf-8')

        # First upload
        s1 = BankStatementService.parse_statement(self.company, self.bank_ledger, csv_data, "upload1.csv", self.user)
        self.assertEqual(s1['duplicates_detected'], 0)

        # Second upload
        s2 = BankStatementService.parse_statement(self.company, self.bank_ledger, csv_data, "upload2.csv", self.user)
        self.assertEqual(s2['duplicates_detected'], 1)
        txs = BankTransaction.objects.filter(reference_number="DUPREF1")
        self.assertEqual(txs.count(), 2)
        self.assertEqual(txs.order_by('created_at').last().status, 'IGNORED')
        self.assertEqual(txs.order_by('created_at').first().status, 'UNRESOLVED')

    # -------------------------------------------------------------
    # 2. Party Intelligence & Learned Mappings Tests
    # -------------------------------------------------------------
    def test_06_upi_extraction_and_party_matching(self):
        """Scenario 6: UPI VPA extraction matches party with high confidence."""
        # Create a learned UPI mapping
        PartyIntelligenceService.learn_mapping(
            company=self.company,
            pattern="RAJESH@OKHDFCBANK",
            party=self.customer,
            mapping_type='UPI',
            confirmed_by_user=True
        )

        res = PartyIntelligenceService.match_transaction(
            company=self.company,
            narration="UPI/RAJESH@OKHDFCBANK/INV12/PAYMENT",
            credit_amount=Decimal('18500.00')
        )

        self.assertEqual(res['matched_party'], self.customer)
        self.assertEqual(res['confidence'], 1.0)
        self.assertIn("Confirmed learned UPI mapping", res['signals'][0])

    def test_07_normalized_entity_name_matching(self):
        """Scenario 7: Matches entity name even when 'Pvt Ltd' or 'Traders' is stripped."""
        res = PartyIntelligenceService.match_transaction(
            company=self.company,
            narration="NEFT-APEX INDUSTRIAL SUPPLIERS-AXIS",
            debit_amount=Decimal('25000.00')
        )

        self.assertEqual(res['matched_party'], self.supplier)
        self.assertGreaterEqual(res['confidence'], 0.90)

    def test_08_company_isolation_invariant(self):
        """Scenario 8: Company A's learned mappings never leak to Company B."""
        # Company A learns a mapping
        PartyIntelligenceService.learn_mapping(
            company=self.company,
            pattern="SECRET_PATTERN@OKBANK",
            party=self.customer,
            mapping_type='UPI',
            confirmed_by_user=True
        )

        # Company B matches with the same narration
        res_b = PartyIntelligenceService.match_transaction(
            company=self.company_b,
            narration="UPI/SECRET_PATTERN@OKBANK/PAYMENT",
            credit_amount=Decimal('10000.00')
        )

        # Company B must NOT match Company A's customer
        self.assertNotEqual(res_b['matched_party'], self.customer)
        self.assertIsNone(res_b['matched_party'])

    def test_09_learn_from_user_confirmation(self):
        """Scenario 9: Confirming a resolution stores learned mapping and increases future confidence."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 9, 15),
            description="UPI/UNKNOWN_NEW@OKAXIS/SETTLEMENT",
            normalized_narration="UPI/UNKNOWN_NEW@OKAXIS/SETTLEMENT",
            credit_amount=Decimal('5000.00'),
            status='UNRESOLVED'
        )

        # User resolves by matching party
        BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type='MATCH_PARTY',
            payload={"party_id": str(self.customer.id)},
            user=self.user
        )

        # Verify mapping was stored
        mapping = PartyMapping.objects.filter(company=self.company, pattern="UNKNOWN_NEW@OKAXIS").first()
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.party, self.customer)

        # Next time, match returns 1.0 confidence!
        next_match = PartyIntelligenceService.match_transaction(
            company=self.company,
            narration="UPI/UNKNOWN_NEW@OKAXIS/NEXT_BILL",
            credit_amount=Decimal('8000.00')
        )
        self.assertEqual(next_match['matched_party'], self.customer)
        self.assertEqual(next_match['confidence'], 1.0)

    # -------------------------------------------------------------
    # 3. Reconciliation & Auto-Allocation Tests
    # -------------------------------------------------------------
    def test_10_receipt_resolution_auto_allocates_invoice(self):
        """Scenario 10: Resolving a deposit creates RECEIPT and auto-allocates to oldest unpaid invoice."""
        # Unpaid invoice: ₹18,500
        inv = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="SAL-101",
            voucher_date=datetime.date(2026, 8, 1),
            party_ledger=self.customer,
            status="POSTED",
            total_amount=Decimal('18500.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=inv, ledger=self.customer, debit_amount=Decimal('18500.00'))
        LedgerEntry.objects.create(company=self.company, voucher=inv, ledger=self.sales_ledger, credit_amount=Decimal('18500.00'))
        VoucherService.recalculate_ledger_balance(self.customer)

        self.assertEqual(self.customer.current_balance, Decimal('18500.00'))

        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 9, 10),
            description="UPI/rajesh@okhdfcbank/INV12",
            normalized_narration="UPI/RAJESH@OKHDFCBANK/INV12",
            credit_amount=Decimal('18500.00'),
            status='UNRESOLVED'
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type='MATCH_PARTY',
            payload={"party_id": str(self.customer.id)},
            user=self.user
        )

        self.assertEqual(res['status'], 'SUCCESS')
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'RECONCILED')
        self.assertIsNotNone(tx.matched_voucher)

        # Invoice should now be fully paid!
        alloc = PaymentAllocation.objects.filter(invoice_voucher=inv).first()
        self.assertIsNotNone(alloc)
        self.assertEqual(alloc.allocated_amount, Decimal('18500.00'))

        # Customer balance should be 0.00
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal('0.00'))

    def test_11_expense_resolution(self):
        """Scenario 11: Resolving a withdrawal as expense creates payment to expense account."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 9, 15),
            description="CHQ BOOK CHARGES",
            normalized_narration="CHQ BOOK CHARGES",
            debit_amount=Decimal('250.00'),
            status='UNRESOLVED'
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type='RECORD_EXPENSE',
            payload={},
            user=self.user
        )

        self.assertEqual(res['status'], 'SUCCESS')
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'RECONCILED')
        self.bank_ledger.refresh_from_db()
        self.assertEqual(self.bank_ledger.current_balance, Decimal('-250.00'))

    # -------------------------------------------------------------
    # 4. Deterministic Accounting Integrity Engine Tests
    # -------------------------------------------------------------
    def test_12_trial_balance_check_detects_imbalance(self):
        """Scenario 12: Integrity engine detects unbalanced voucher and creates CRITICAL finding."""
        # Clean state -> balanced
        clean_findings = AccountingIntegrityEngine.check_trial_balance(self.company)
        self.assertEqual(len(clean_findings), 0)

        # Create unbalanced entry intentionally
        bad_vch = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="JOURNAL",
            voucher_number="BAD-001",
            voucher_date=datetime.date(2026, 9, 1),
            status="POSTED",
            total_amount=Decimal('1000.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=bad_vch, ledger=self.customer, debit_amount=Decimal('1000.00'))
        # No credit entry!

        findings = AccountingIntegrityEngine.check_trial_balance(self.company)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, 'CRITICAL')
        self.assertIn("difference of ₹1000.00", findings[0].title)

    def test_13_party_balance_drift_detected(self):
        """Scenario 13: Detects cached balance drift against raw ledger entries."""
        # Customer has 0 entries, but cached balance is manually corrupted to 50,000
        self.customer.current_balance = Decimal('50000.00')
        self.customer.save(update_fields=['current_balance'])

        findings = AccountingIntegrityEngine.check_party_balances(self.company)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, 'WARNING')
        self.assertEqual(findings[0].evidence['recorded_balance'], '50000.00')
        self.assertEqual(findings[0].evidence['expected_balance'], '0.00')

    def test_14_payment_over_allocation_detected(self):
        """Scenario 14: Detects payment allocations exceeding invoice total."""
        inv = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="SALES",
            voucher_number="OVER-001", voucher_date=datetime.date(2026, 9, 1),
            party_ledger=self.customer, status="POSTED", total_amount=Decimal('1000.00'), created_by=self.user
        )
        pmt = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="RECEIPT",
            voucher_number="OVER-002", voucher_date=datetime.date(2026, 9, 2),
            party_ledger=self.customer, status="POSTED", total_amount=Decimal('1500.00'), created_by=self.user
        )
        PaymentAllocation.objects.create(
            company=self.company, payment_voucher=pmt, invoice_voucher=inv, allocated_amount=Decimal('1500.00')
        )

        findings = AccountingIntegrityEngine.check_payment_allocations(self.company)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, 'CRITICAL')
        self.assertIn("over-allocated", findings[0].title)

    def test_15_wrong_party_detection(self):
        """Scenario 15: Flags invoice when bill number & amount match another party."""
        v1 = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="PURCHASE",
            voucher_number="PUR-001", external_invoice_number="BILL-8899",
            voucher_date=datetime.date(2026, 9, 1), party_ledger=self.customer, # Clerical mistake: assigned to customer!
            status="POSTED", total_amount=Decimal('5000.00'), created_by=self.user
        )
        v2 = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="PURCHASE",
            voucher_number="PUR-002", external_invoice_number="BILL-8899",
            voucher_date=datetime.date(2026, 9, 1), party_ledger=self.supplier,
            status="POSTED", total_amount=Decimal('5000.00'), created_by=self.user
        )

        findings = AccountingIntegrityEngine.check_wrong_party(self.company)
        self.assertGreaterEqual(len(findings), 1)
        self.assertEqual(findings[0].category, 'WRONG_PARTY')
        self.assertEqual(findings[0].fix_action, 'MOVE_PARTY')

    def test_16_duplicate_invoice_detection(self):
        """Scenario 16: Detects duplicate invoices with identical party, amount, and date."""
        v1 = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="SALES",
            voucher_number="DUP-01", voucher_date=datetime.date(2026, 9, 10),
            party_ledger=self.customer, status="POSTED", total_amount=Decimal('7500.00'), created_by=self.user
        )
        v2 = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="SALES",
            voucher_number="DUP-02", voucher_date=datetime.date(2026, 9, 10),
            party_ledger=self.customer, status="POSTED", total_amount=Decimal('7500.00'), created_by=self.user
        )

        findings = AccountingIntegrityEngine.check_duplicate_invoices(self.company)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, 'DUPLICATE')

    def test_17_gst_mismatch_detection(self):
        """Scenario 17: Detects intra-state sale where IGST was mistakenly applied."""
        prod = Product.objects.create(company=self.company, name="Item 1", sku="SKU1", purchase_price=100, selling_price=150)
        v = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="SALES",
            voucher_number="GST-01", voucher_date=datetime.date(2026, 9, 10),
            party_ledger=self.customer, status="POSTED", total_amount=Decimal('118.00'),
            buyer_state_code="27", created_by=self.user
        )
        VoucherItem.objects.create(
            voucher=v, product=prod, quantity=1, rate=100, taxable_amount=100,
            gst_rate=18, igst_amount=18, igst_rate=18, total_amount=118
        )

        findings = AccountingIntegrityEngine.check_gst(self.company)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, 'GST')
        self.assertIn("intra-state", findings[0].description)

    def test_18_negative_inventory_detection(self):
        """Scenario 18: Detects negative stock on a product."""
        prod = Product.objects.create(company=self.company, name="Bearing B34", sku="B34", purchase_price=200, selling_price=300, stock_quantity=-5)
        findings = AccountingIntegrityEngine.check_inventory(self.company)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, 'INVENTORY')
        self.assertIn("-5", findings[0].description)

    def test_19_unusual_transaction_warning(self):
        """Scenario 19: Warns about a payment that is 5x larger than normal average."""
        # Average payments around ₹1,000
        for i in range(3):
            Voucher.objects.create(
                company=self.company, financial_year=self.fy, voucher_type="PAYMENT",
                voucher_number=f"NORM-0{i}", voucher_date=datetime.date(2026, 9, 1),
                status="POSTED", total_amount=Decimal('1000.00'), created_by=self.user
            )

        # Huge payment: ₹50,000
        huge = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="PAYMENT",
            voucher_number="HUGE-01", voucher_date=datetime.date(2026, 9, 5),
            status="POSTED", total_amount=Decimal('50000.00'), created_by=self.user
        )

        findings = AccountingIntegrityEngine.check_unusual_transactions(self.company)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, 'INFO')
        self.assertIn("Unusually large", findings[0].title)

    def test_20_diagnose_balance_mismatch_flagship(self):
        """Scenario 20: 'Why is my balance not matching?' isolates Trial Balance discrepancy."""
        bad_vch = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="JOURNAL",
            voucher_number="MISMATCH-001", voucher_date=datetime.date(2026, 9, 1),
            status="POSTED", total_amount=Decimal('18500.00'), created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=bad_vch, ledger=self.customer, debit_amount=Decimal('18500.00'))

        diag = AccountingIntegrityEngine.diagnose_balance_mismatch(self.company)
        self.assertFalse(diag['is_balanced'])
        self.assertEqual(diag['discrepancy'], '18500.00')
        self.assertGreaterEqual(len(diag['causes']), 1)
        self.assertEqual(diag['causes'][0]['type'], 'UNBALANCED_VOUCHER')

    # -------------------------------------------------------------
    # 5. Fix Preview & Deterministic Execution Tests
    # -------------------------------------------------------------
    def test_21_wrong_party_fix_preview_and_execution(self):
        """Scenario 21: Preview and execute moving an invoice from wrong party to correct party."""
        inv = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="SALES",
            voucher_number="INV-WRONG-1", voucher_date=datetime.date(2026, 9, 1),
            party_ledger=self.customer, status="POSTED", total_amount=Decimal('10000.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=inv, ledger=self.customer, debit_amount=Decimal('10000.00'))
        LedgerEntry.objects.create(company=self.company, voucher=inv, ledger=self.sales_ledger, credit_amount=Decimal('10000.00'))
        VoucherService.recalculate_ledger_balance(self.customer)

        other_customer = Ledger.objects.create(
            company=self.company, group=self.debtor_grp, name="XYZ Traders", ledger_type="CUSTOMER"
        )

        finding = AccountingFinding.objects.create(
            company=self.company,
            severity="WARNING",
            category="WRONG_PARTY",
            title="Possible wrong party on INV-WRONG-1",
            description="Assigned to Rajesh Kumar instead of XYZ Traders",
            evidence={
                "voucher_id": str(inv.id),
                "current_party_id": str(self.customer.id),
                "suggested_party_id": str(other_customer.id),
                "amount": "10000.00"
            },
            fix_action="MOVE_PARTY"
        )

        # 1. Preview
        prev = FindingFixService.generate_fix_preview(finding)
        self.assertTrue(prev['supported'])
        self.assertEqual(prev['before']['current_party']['name'], self.customer.name)
        self.assertEqual(prev['after']['target_party']['balance'], '10000.00')

        # 2. Execute Fix
        res = FindingFixService.execute_fix(finding, user=self.user)
        self.assertEqual(res['status'], 'SUCCESS')

        # Verify old party reversed (0 balance) and target party now has 10,000 balance!
        self.customer.refresh_from_db()
        other_customer.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal('0.00'))
        self.assertEqual(other_customer.current_balance, Decimal('10000.00'))

        finding.refresh_from_db()
        self.assertTrue(finding.is_resolved)

    def test_22_recalculate_balance_fix_execution(self):
        """Scenario 22: Recalculate balance fix restores single-source-of-truth balance."""
        self.customer.current_balance = Decimal('9999.00')
        self.customer.save(update_fields=['current_balance'])

        finding = AccountingFinding.objects.create(
            company=self.company,
            severity="WARNING",
            category="WRONG_PARTY",
            title="Ledger balance drift",
            description="Cached balance drifted",
            evidence={
                "ledger_id": str(self.customer.id),
                "expected_balance": "0.00"
            },
            fix_action="RECALCULATE_BALANCE"
        )

        res = FindingFixService.execute_fix(finding, user=self.user)
        self.assertEqual(res['status'], 'SUCCESS')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal('0.00'))
        finding.refresh_from_db()
        self.assertTrue(finding.is_resolved)
