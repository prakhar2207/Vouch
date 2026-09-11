import io
import datetime
import hashlib
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import BankStatementImport, BankTransaction, FinancialYear, Voucher
from apps.accounting.services.bank_statement_service import BankStatementService
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
from apps.accounting.services.ocr_service import InvoiceOCRService


class OCRForensicsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="forensics@vouch.test",
            password="testpassword123",
            first_name="Forensics",
            last_name="Auditor"
        )
        self.client.force_authenticate(user=self.user)

        self.company_a = Company.objects.create(
            name="Audited Enterprise A",
            email="company_a@vouch.test",
            gstin="07AAAAA0000A1Z5",
            state_code="07"
        )
        self.company_b = Company.objects.create(
            name="Audited Enterprise B",
            email="company_b@vouch.test",
            gstin="27BBBBB1111B1Z2",
            state_code="27"
        )

        bank_group_a, _ = LedgerGroup.objects.get_or_create(
            company=self.company_a,
            name="Bank Accounts",
            defaults={"nature": "ASSET"}
        )
        self.bank_ledger_a = Ledger.objects.create(
            company=self.company_a,
            group=bank_group_a,
            name="HDFC Current Account",
            ledger_type="BANK",
            current_balance=Decimal("100000.00")
        )

        bank_group_b, _ = LedgerGroup.objects.get_or_create(
            company=self.company_b,
            name="Bank Accounts",
            defaults={"nature": "ASSET"}
        )
        self.bank_ledger_b = Ledger.objects.create(
            company=self.company_b,
            group=bank_group_b,
            name="SBI Current Account",
            ledger_type="BANK",
            current_balance=Decimal("50000.00")
        )

        self.fy_a, _ = FinancialYear.objects.get_or_create(
            company=self.company_a,
            code="26-27",
            defaults={
                "name": "FY 2026-27",
                "start_date": datetime.date(2026, 4, 1),
                "end_date": datetime.date(2027, 3, 31)
            }
        )

        debtor_group_a, _ = LedgerGroup.objects.get_or_create(
            company=self.company_a,
            name="Sundry Debtors",
            defaults={"nature": "ASSET"}
        )
        self.customer_a = Ledger.objects.create(
            company=self.company_a,
            group=debtor_group_a,
            name="Saksham Enterprises",
            ledger_type="CUSTOMER",
            current_balance=Decimal("50000.00")
        )

        creditor_group_a, _ = LedgerGroup.objects.get_or_create(
            company=self.company_a,
            name="Sundry Creditors",
            defaults={"nature": "LIABILITY"}
        )
        self.supplier_a = Ledger.objects.create(
            company=self.company_a,
            group=creditor_group_a,
            name="Apex Industrial Suppliers",
            ledger_type="SUPPLIER",
            current_balance=Decimal("25000.00")
        )

    # =========================================================================
    # 1. Bank Statement Layout Adapters (SBI, HDFC, ICICI, Axis, Kotak)
    # =========================================================================
    def test_sbi_statement_parsing(self):
        """SBI: Txn Date | Value Date | Description | Ref No./Cheque No. | Debit | Credit | Balance"""
        csv_content = (
            "Txn Date,Value Date,Description,Ref No./Cheque No.,Debit,Credit,Balance\n"
            "01/04/2026,01/04/2026,TRANSFER TO 12345678901 - UPI/rajesh@okhdfcbank/123456,TRANSFER,5000.00,,95000.00\n"
            "02/04/2026,02/04/2026,BY TRANSFER-NEFT*BARB0123456-M/S SHREE TRADERS,BARB0123456,,25000.00,120000.00\n"
        ).encode('utf-8')

        summary = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=csv_content,
            filename="sbi_statement.csv",
            user=self.user
        )

        self.assertEqual(summary["status"], "COMPLETED")
        self.assertEqual(summary["imported_count"], 2)
        self.assertTrue(summary["balance_chain_valid"])

        tx1 = BankTransaction.objects.get(statement_import_id=summary["import_id"], debit_amount=Decimal("5000.00"))
        self.assertEqual(tx1.credit_amount, Decimal("0.00"))
        self.assertEqual(tx1.balance, Decimal("95000.00"))

        tx2 = BankTransaction.objects.get(statement_import_id=summary["import_id"], credit_amount=Decimal("25000.00"))
        self.assertEqual(tx2.debit_amount, Decimal("0.00"))
        self.assertEqual(tx2.balance, Decimal("120000.00"))

    def test_hdfc_statement_parsing(self):
        """HDFC: Date | Narration | Chq./Ref.No. | Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance"""
        csv_content = (
            "Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
            "02/04/2026,UPI-KIRAN-KIRAN@OKHDFC-4091238123,000000000000,02/04/2026,1200.00,,48800.00\n"
            "03/04/2026,RTGS CR-HDFCR52026040312345678-ACME CORP,HDFCR5202604,03/04/2026,,50000.00,98800.00\n"
        ).encode('utf-8')

        summary = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=csv_content,
            filename="hdfc_statement.csv",
            user=self.user
        )

        self.assertEqual(summary["status"], "COMPLETED")
        self.assertEqual(summary["imported_count"], 2)
        self.assertTrue(summary["balance_chain_valid"])

        txs = BankTransaction.objects.filter(statement_import_id=summary["import_id"]).order_by("transaction_date")
        self.assertEqual(txs[0].debit_amount, Decimal("1200.00"))
        self.assertEqual(txs[1].credit_amount, Decimal("50000.00"))

    def test_icici_statement_parsing(self):
        """ICICI: Transaction Date | Value Date | Cheque Number | Transaction Remarks | Withdrawal Amount (INR ) | Deposit Amount (INR ) | Balance (INR )"""
        csv_content = (
            "Transaction Date,Value Date,Cheque Number,Transaction Remarks,Withdrawal Amount (INR ),Deposit Amount (INR ),Balance (INR )\n"
            "03/04/2026,03/04/2026,-,INF/NEFT/00123984/ABC TRADERS,15000.00,,85000.00\n"
            "04/04/2026,04/04/2026,-,BY CLEARING-CHQ NO 123456-DELHI,,30000.00,115000.00\n"
        ).encode('utf-8')

        summary = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=csv_content,
            filename="icici_statement.csv",
            user=self.user
        )

        self.assertEqual(summary["status"], "COMPLETED")
        self.assertEqual(summary["imported_count"], 2)
        self.assertTrue(summary["balance_chain_valid"])

    def test_axis_statement_parsing(self):
        """Axis: Tran Date | CHQNO | PARTICULARS | DR | CR | BAL | INIT BR"""
        csv_content = (
            "Tran Date,CHQNO,PARTICULARS,DR,CR,BAL,INIT BR\n"
            "04/04/2026,-,NEFT UTIB0000123 ABC CORP,10000.00,,75000.00,MUMBAI\n"
            "05/04/2026,-,BY CASH DEPOSIT,,20000.00,95000.00,MUMBAI\n"
        ).encode('utf-8')

        summary = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=csv_content,
            filename="axis_statement.csv",
            user=self.user
        )

        self.assertEqual(summary["status"], "COMPLETED")
        self.assertEqual(summary["imported_count"], 2)
        self.assertTrue(summary["balance_chain_valid"])

    def test_kotak_statement_parsing(self):
        """Kotak: Date | Narration | Chq/Ref No | Dr/Cr | Amount | Balance"""
        csv_content = (
            "Date,Narration,Chq/Ref No,Dr/Cr,Amount,Balance\n"
            "05/04/2026,MB:IMPS/P2A/1234567/VENDOR,1234567,DR,3500.00,71500.00\n"
            "06/04/2026,IMPS/P2A/7654321/CLIENT,7654321,CR,12000.00,83500.00\n"
        ).encode('utf-8')

        summary = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=csv_content,
            filename="kotak_statement.csv",
            user=self.user
        )

        self.assertEqual(summary["status"], "COMPLETED")
        self.assertEqual(summary["imported_count"], 2)
        self.assertTrue(summary["balance_chain_valid"])

        tx1 = BankTransaction.objects.get(statement_import_id=summary["import_id"], debit_amount=Decimal("3500.00"))
        self.assertEqual(tx1.credit_amount, Decimal("0.00"))

        tx2 = BankTransaction.objects.get(statement_import_id=summary["import_id"], credit_amount=Decimal("12000.00"))
        self.assertEqual(tx2.debit_amount, Decimal("0.00"))

    # =========================================================================
    # 2. Phase 4: Mandatory Balance Chain Validation
    # =========================================================================
    def test_balance_chain_validation_success(self):
        """Opening 100,000 + Credit 25,000 - Debit 12,000 == Closing 113,000."""
        rows = [
            {"date": datetime.date(2026, 4, 1), "debit": Decimal("12000.00"), "credit": Decimal("0.00"), "balance": Decimal("88000.00")},
            {"date": datetime.date(2026, 4, 2), "debit": Decimal("0.00"), "credit": Decimal("25000.00"), "balance": Decimal("113000.00")}
        ]
        report = BankStatementService.validate_balance_chain(rows, explicit_opening=Decimal("100000.00"), explicit_closing=Decimal("113000.00"))
        self.assertTrue(report["valid"])
        self.assertEqual(report["discrepancy_amount"], Decimal("0.00"))
        self.assertEqual(len(report["discrepancy_rows"]), 0)

    def test_balance_chain_validation_failure_flags_discrepancy(self):
        """If OCR misreads debit as 13,000 instead of 12,000, detects difference of ₹1,000."""
        rows = [
            {"date": datetime.date(2026, 4, 1), "debit": Decimal("13000.00"), "credit": Decimal("0.00"), "balance": Decimal("88000.00"), "description": "Vendor Payment"},
            {"date": datetime.date(2026, 4, 2), "debit": Decimal("0.00"), "credit": Decimal("25000.00"), "balance": Decimal("113000.00"), "description": "Customer Receipt"}
        ]
        report = BankStatementService.validate_balance_chain(rows, explicit_opening=Decimal("100000.00"), explicit_closing=Decimal("113000.00"))
        self.assertFalse(report["valid"])
        self.assertEqual(report["discrepancy_amount"], Decimal("1000.00"))
        self.assertGreater(len(report["discrepancy_rows"]), 0)

    # =========================================================================
    # 3. Phase 8 & 9: Statement and Transaction Deduplication
    # =========================================================================
    def test_duplicate_statement_file_hash_detection(self):
        """Uploading identical file content twice returns duplicate notice without duplicating rows."""
        csv_bytes = (
            "Date,Description,Debit,Credit,Balance\n"
            "01/04/2026,Transfer Out,1000.00,,99000.00\n"
            "02/04/2026,Transfer In,,5000.00,104000.00\n"
        ).encode('utf-8')

        # First upload
        res1 = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=csv_bytes,
            filename="statement_apr.csv",
            user=self.user
        )
        self.assertEqual(res1["imported_count"], 2)
        self.assertFalse(res1.get("is_duplicate_file", False))

        # Second upload with same exact bytes
        res2 = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=csv_bytes,
            filename="statement_apr_copy.csv",
            user=self.user
        )
        self.assertTrue(res2.get("is_duplicate_file", True))
        self.assertEqual(res2["imported_count"], 0)
        self.assertEqual(BankTransaction.objects.filter(bank_ledger=self.bank_ledger_a).count(), 2)

    def test_overlapping_statement_deduplication(self):
        """Overlapping statements (e.g. 1-15 Apr and 10-25 Apr) do not duplicate overlapping rows."""
        stmt1_bytes = (
            "Date,Description,Debit,Credit,Balance\n"
            "01/04/2026,Salary Payment,20000.00,,80000.00\n"
            "10/04/2026,Client Advance,,15000.00,95000.00\n"
        ).encode('utf-8')

        stmt2_bytes = (
            "Date,Description,Debit,Credit,Balance\n"
            "10/04/2026,Client Advance,,15000.00,95000.00\n"
            "20/04/2026,Rent Payment,10000.00,,85000.00\n"
        ).encode('utf-8')

        res1 = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=stmt1_bytes,
            filename="apr_part1.csv",
            user=self.user
        )
        self.assertEqual(res1["imported_count"], 2)

        res2 = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=stmt2_bytes,
            filename="apr_part2.csv",
            user=self.user
        )
        self.assertEqual(res2["imported_count"], 1)  # Only the new 20/04 transaction
        self.assertEqual(res2["duplicates_detected"], 1)  # The 10/04 transaction was skipped
        self.assertEqual(BankTransaction.objects.filter(bank_ledger=self.bank_ledger_a).count(), 3)

    # =========================================================================
    # 4. Phase 5 & 6: OCR Amount Safety & Date Safety
    # =========================================================================
    def test_amount_ocr_error_correction(self):
        """Cleans OCR digit confusions (O/o->0, l/I->1, B->8, S->5)."""
        self.assertEqual(BankStatementService.clean_amount_str("1O,500.00"), Decimal("10500.00"))
        self.assertEqual(BankStatementService.clean_amount_str("l,250.00"), Decimal("1250.00"))
        self.assertEqual(BankStatementService.clean_amount_str("B,000.00"), Decimal("8000.00"))
        self.assertEqual(BankStatementService.clean_amount_str("S,500.00"), Decimal("5500.00"))
        self.assertEqual(BankStatementService.clean_amount_str("₹ 1,25,000.50"), Decimal("125000.50"))
        self.assertEqual(BankStatementService.clean_amount_str("(500.00)"), Decimal("500.00"))

    def test_date_safety_impossible_dates_and_batch_disambiguation(self):
        """Rejects impossible dates and disambiguates DD/MM/YYYY."""
        self.assertIsNone(BankStatementService.parse_date_str("2026-02-30"))
        self.assertIsNone(BankStatementService.parse_date_str("32/01/2026"))
        self.assertIsNone(BankStatementService.parse_date_str("15/13/2026"))

        # Batch with day > 12 should detect DD/MM/YYYY
        batch = ["01/04/2026", "25/04/2026", "30/04/2026"]
        detected = BankStatementService.detect_batch_date_format(batch)
        self.assertEqual(detected, "%d/%m/%Y")

    # =========================================================================
    # 5. Phase 10 & 11: Invoice OCR Math & GST Validation
    # =========================================================================
    def test_invoice_ocr_math_reconciliation_valid(self):
        """Clean invoice with items matching subtotal and GST total reconciles with HIGH_CONFIDENCE."""
        invoice_data = {
            "supplier_name": "Acme Bearings Ltd",
            "supplier_gstin": "07AAACB1234A1Z5",
            "invoice_number": "INV-2026-001",
            "invoice_date": "2026-04-01",
            "subtotal": 10000.00,
            "cgst_amount": 900.00,
            "sgst_amount": 900.00,
            "igst_amount": 0.00,
            "total_amount": 11800.00,
            "line_items": [
                {"description": "Bearing 6204", "quantity": 10, "rate": 500.0, "amount": 5000.0},
                {"description": "Bearing 6205", "quantity": 10, "rate": 500.0, "amount": 5000.0}
            ]
        }
        val = InvoiceOCRService.validate_invoice_math(invoice_data)
        self.assertTrue(val["math_valid"])
        self.assertEqual(val["difference"], 0.0)
        self.assertEqual(val["risk_level"], "HIGH_CONFIDENCE")
        self.assertTrue(val["gstin_valid"])
        self.assertIsNone(val["discrepancy_message"])

    def test_invoice_ocr_math_discrepancy_flagged(self):
        """If line items + tax do not match grand total, flags discrepancy and marks HIGH_RISK."""
        invoice_data = {
            "supplier_name": "Acme Bearings Ltd",
            "supplier_gstin": "07AAACB1234A1Z5",
            "invoice_number": "INV-2026-002",
            "invoice_date": "2026-04-01",
            "subtotal": 10000.00,
            "cgst_amount": 900.00,
            "sgst_amount": 900.00,
            "igst_amount": 0.00,
            "total_amount": 12500.00,  # 700 discrepancy
            "line_items": [
                {"description": "Bearing 6204", "quantity": 10, "rate": 500.0, "amount": 5000.0},
                {"description": "Bearing 6205", "quantity": 10, "rate": 500.0, "amount": 5000.0}
            ]
        }
        val = InvoiceOCRService.validate_invoice_math(invoice_data)
        self.assertFalse(val["math_valid"])
        self.assertEqual(val["difference"], 700.00)
        self.assertEqual(val["risk_level"], "HIGH_RISK")
        self.assertIn("difference in the extracted totals", val["discrepancy_message"])

    def test_gstin_format_validation(self):
        """Validates 15-character GSTIN regex and state code prefix."""
        self.assertTrue(InvoiceOCRService.validate_gstin("07AAACB1234A1Z5"))
        self.assertTrue(InvoiceOCRService.validate_gstin("27AAAAA0000A1Z5"))
        # Invalid length
        self.assertFalse(InvoiceOCRService.validate_gstin("07AAACB1234A1Z"))
        # State code checks (99 is valid territory, 00 and 45 are invalid)
        self.assertTrue(InvoiceOCRService.validate_gstin("99AAACB1234A1Z5"))
        self.assertFalse(InvoiceOCRService.validate_gstin("00AAACB1234A1Z5"))
        self.assertFalse(InvoiceOCRService.validate_gstin("45AAACB1234A1Z5"))

    # =========================================================================
    # 6. Phase 25: Multi-Tenant Boundary Isolation
    # =========================================================================
    def test_multi_tenant_statement_isolation(self):
        """Statements uploaded for Company A must never be accessible from Company B."""
        csv_bytes = (
            "Date,Description,Debit,Credit,Balance\n"
            "01/04/2026,Confidential Transfer,5000.00,,95000.00\n"
        ).encode('utf-8')

        BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=csv_bytes,
            filename="company_a_secret.csv",
            user=self.user
        )

        # Company B query must not see Company A's transactions or imports
        tx_b = BankTransaction.objects.filter(company=self.company_b)
        self.assertEqual(tx_b.count(), 0)

        imports_b = BankStatementImport.objects.filter(company=self.company_b)
        self.assertEqual(imports_b.count(), 0)

    # =========================================================================
    # 7. Indian Banking OCR Payment vs Receipt Direction & Closing Balance Guardrails
    # =========================================================================
    def test_ocr_direction_reclassification_credit_cues(self):
        """
        When OCR extracts an Indian bank statement (e.g. Canara Bank where Deposits column precedes Withdrawals),
        any transaction with 'BY' / credit cues must be reclassified from Debit (Payment) to Credit (Receipt).
        """
        csv_bytes = (
            "Date,Description,Debit,Credit,Balance\n"
            "2026-04-21,BY CLG:DEL ACCTS-BANK OF BARODA (BOB) UNIQUE TRADERS,4870.00,0.00,104870.00\n"
            "2026-04-21,CASH DEPOSIT SELF 9949_PANKIKA,5000.00,0.00,109870.00\n"
            "2026-04-28,BY CLG:DEL ACCTS-STATE BANK OF INDIA SAKSHAM ENTERPRISES,15000.00,0.00,124870.00\n"
            "2026-04-28,BY CLG:DEL ACCTS-STATE BANK OF INDIA BHAGWANTI FOOTWEAR,1481.00,0.00,126351.00\n"
        ).encode('utf-8')

        res = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=csv_bytes,
            filename="canara_ocr_extracted.csv",
            user=self.user
        )

        self.assertEqual(res["imported_count"], 4)
        txs = BankTransaction.objects.filter(statement_import_id=res["import_id"]).order_by("transaction_date", "id")

        for tx in txs:
            self.assertEqual(tx.debit_amount, Decimal("0.00"), f"Failed for {tx.description}: debit should be 0.00")
            self.assertGreater(tx.credit_amount, Decimal("0.00"), f"Failed for {tx.description}: credit should be > 0")

    def test_ocr_direction_reclassification_debit_cues(self):
        """
        Transactions with 'TO' / debit cues (e.g. TO TRANSFER, SC NEFT, CASA DEBIT)
        must strictly be classified as Debit (Withdrawal / Payment), not Credit.
        """
        csv_bytes = (
            "Date,Description,Debit,Credit,Balance\n"
            "2026-04-17,SC NEFT OTHER THAN SB IMB,0.00,6.00,99994.00\n"
            "2026-04-23,MB NEFT DR CNRBH00127105797 PANCH MUKHI,0.00,2791.00,97203.00\n"
            "2026-05-01,CASA DEBIT INTEREST CAPITALIZED,0.00,8105.00,89098.00\n"
        ).encode('utf-8')

        res = BankStatementService.parse_statement(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            file_bytes=csv_bytes,
            filename="canara_debits.csv",
            user=self.user
        )

        self.assertEqual(res["imported_count"], 3)
        txs = BankTransaction.objects.filter(statement_import_id=res["import_id"])

        for tx in txs:
            self.assertEqual(tx.credit_amount, Decimal("0.00"), f"Failed for {tx.description}: credit should be 0.00")
            self.assertGreater(tx.debit_amount, Decimal("0.00"), f"Failed for {tx.description}: debit should be > 0")

    def test_ocr_rejection_of_closing_balance_summary_rows(self):
        """
        Closing balance summary lines (e.g. 'Closing Balance as on...', 'Current Account Balance')
        must NEVER be extracted or imported as financial transactions.
        """
        self.assertTrue(bool(BankStatementService.BOILERPLATE_REGEX.search("Current Account Balance as on 30-Apr-2026")))
        self.assertTrue(bool(BankStatementService.BOILERPLATE_REGEX.search("CLOSING BALANCE: Rs. 1,42,100.00")))
        self.assertTrue(bool(BankStatementService.BOILERPLATE_REGEX.search("TOTAL WITHDRAWALS: 50,000.00")))
        self.assertTrue(bool(BankStatementService.BOILERPLATE_REGEX.search("TOTAL DEPOSITS: 80,000.00")))
        self.assertTrue(bool(BankStatementService.BOILERPLATE_REGEX.search("STATEMENT SUMMARY")))

    def test_reconciliation_customer_payment_to_receipt_guardrail(self):
        """
        Reconciling a transaction against a Customer must strictly create a RECEIPT voucher,
        even if the transaction originally had debit_amount > 0 due to an OCR column flip.
        """
        # Create bank transaction with inverted debit amount
        tx = BankTransaction.objects.create(
            company=self.company_a,
            bank_ledger=self.bank_ledger_a,
            transaction_date=datetime.date(2026, 4, 28),
            description="BY CLG:DEL ACCTS SAKSHAM ENTERPRISES",
            normalized_narration="BY CLG DEL ACCTS SAKSHAM ENTERPRISES",
            debit_amount=Decimal("15000.00"),
            credit_amount=Decimal("0.00"),
            status="UNRESOLVED"
        )

        # Resolve to customer
        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type="RECORD_PAYMENT",
            payload={"party_id": str(self.customer_a.id)},
            user=self.user
        )

        tx.refresh_from_db()
        # Transaction amounts must be corrected
        self.assertEqual(tx.credit_amount, Decimal("15000.00"))
        self.assertEqual(tx.debit_amount, Decimal("0.00"))
        self.assertEqual(tx.status, "RECONCILED")

        # Voucher must be RECEIPT, not PAYMENT
        voucher = tx.matched_voucher
        self.assertIsNotNone(voucher)
        self.assertEqual(voucher.voucher_type, "RECEIPT")
        self.assertEqual(voucher.total_amount, Decimal("15000.00"))
        self.assertEqual(voucher.party_ledger, self.customer_a)

