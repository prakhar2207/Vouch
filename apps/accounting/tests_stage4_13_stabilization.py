import datetime
import json
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.audit.services.audit_service import AuditService
from apps.common.services.backup_service import DatabaseBackupService
from apps.companies.models import Company, UserCompany
from apps.inventory.models import Product, ProductCategory
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import (
    FinancialYear,
    LedgerEntry,
    PaymentAllocation,
    SyncEvent,
    Voucher,
)
from apps.accounting.services.allocation_service import PaymentAllocationService
from apps.accounting.services.financial_statements_service import FinancialStatementsService
from apps.accounting.services.period_service import PeriodBalanceService
from apps.accounting.services.report_service import ReportService
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.voucher_service import VoucherService
from apps.notifications.models import EmailDeliveryLog, TransactionalOutboxEvent
from apps.notifications.outbox_service import OutboxService


class Stage413DisasterRecoveryAuditLogTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.user = User.objects.create_user(
            email="dr413@example.com", password="Password123!", role="OWNER", email_verified=True
        )
        self.company = Company.objects.create(
            name="DR Stage 4.13 Co", gstin="27AAACD4130M1Z5", state_code="27"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role="OWNER")
        AuditService.log_action(
            company=self.company,
            user=self.user,
            action="CREATE",
            model_name="Company",
            record_id=self.company.id,
            changes={"name": self.company.name},
        )
        AuditService.log_action(
            company=self.company,
            user=self.user,
            action="UPDATE",
            model_name="Company",
            record_id=self.company.id,
            changes={"gstin": self.company.gstin},
        )
        SyncEvent.objects.create(
            company=self.company,
            entity_type="voucher",
            entity_id="00000000-0000-0000-0000-000000000001",
            operation="CREATE",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_backup_includes_auditlog_and_syncevent_and_preserves_hashes_on_restore(self):
        # Scope to self.company so TestCase uncommitted AuditLog & SyncEvent rows are
        # serialized inside the active transaction on hosts with pg_dump/pg_restore installed.
        res = DatabaseBackupService.perform_backup(
            upload_s3=False,
            encrypt=True,
            output_dir=self.temp_dir,
            company_id=str(self.company.id),
        )
        self.assertTrue(res["success"], res)
        backup_path = Path(res["file_path"])
        raw = DatabaseBackupService.unpack_backup(backup_path)
        if raw.strip().startswith(b"["):
            docs = json.loads(raw.decode("utf-8"))
            models_present = {d["model"] for d in docs}
            self.assertIn("audit.auditlog", models_present)
            self.assertIn("accounting.syncevent", models_present)

            snap_audit_rows = [d for d in docs if d["model"] == "audit.auditlog"]
            self.assertGreaterEqual(len(snap_audit_rows), 2)
        orig_hashes = {
            str(a.id): (a.sequence, a.previous_hash, a.current_hash)
            for a in AuditLog.objects.filter(company=self.company)
        }

        # Idempotent restore validation must preserve immutable AuditLog hashes without PermissionDenied
        rest = DatabaseBackupService.restore_backup(backup_path, target_db_alias="default", dry_run=False)
        self.assertTrue(rest["success"], rest)
        self.assertEqual(rest["error_count"], 0)
        for aid, expected_tuple in orig_hashes.items():
            refreshed = AuditLog.objects.get(id=aid)
            self.assertEqual(
                (refreshed.sequence, refreshed.previous_hash, refreshed.current_hash),
                expected_tuple,
            )


class Stage413ReversalReportConsistencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="rev413@example.com", password="Password123!", role="OWNER", email_verified=True
        )
        self.company = Company.objects.create(
            name="Reversal Parity Co", gstin="27AAACR4130M1Z1", state_code="27"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role="OWNER")
        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 26-27",
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31),
        )
        self.asset_grp = LedgerGroup.objects.create(
            company=self.company, name="Sundry Debtors", nature="ASSET"
        )
        self.inc_grp = LedgerGroup.objects.create(
            company=self.company, name="Sales Accounts", nature="INCOME"
        )
        self.liab_grp = LedgerGroup.objects.create(
            company=self.company, name="Duties & Taxes", nature="LIABILITY"
        )
        self.customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="Customer Saksham Test",
            ledger_type="CUSTOMER",
            state_code="27",
        )
        self.sales = Ledger.objects.create(
            company=self.company,
            group=self.inc_grp,
            name="Domestic Sales",
            ledger_type="SALES",
        )
        self.cgst = Ledger.objects.create(
            company=self.company,
            group=self.liab_grp,
            name="Output CGST",
            ledger_type="TAX",
        )
        self.sgst = Ledger.objects.create(
            company=self.company,
            group=self.liab_grp,
            name="Output SGST",
            ledger_type="TAX",
        )
        self.cat = ProductCategory.objects.create(company=self.company, name="Belts")
        self.prod = Product.objects.create(
            company=self.company,
            category=self.cat,
            name="V-Belt A50",
            sku="VB-A50",
            selling_price=Decimal("1000.00"),
            purchase_price=Decimal("700.00"),
            gst_rate=Decimal("18.00"),
            stock_quantity=Decimal("50.00"),
        )

    def test_reversed_invoice_agreement_across_all_reports_and_cached_balance(self):
        bs_before = FinancialStatementsService.generate_balance_sheet(
            self.company, datetime.date(2027, 3, 31)
        )
        v1 = SalesInvoiceService.generate_sales_invoice(
            company=self.company,
            user=self.user,
            party_ledger=self.customer,
            items_data=[{"product_id": self.prod.id, "quantity": 1, "rate": Decimal("1000.00"), "gst_rate": Decimal("18.00")}],
            sales_ledger=self.sales,
            cgst_ledger=self.cgst,
            sgst_ledger=self.sgst,
            manual_voucher_date=datetime.date(2026, 5, 10),
        )
        VoucherService.post_voucher(v1)
        VoucherService.create_reversal_voucher(v1, user=self.user, reason="Test reversal parity")

        self.customer.refresh_from_db()
        self.sales.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal("0.00"))
        self.assertEqual(self.sales.current_balance, Decimal("0.00"))

        # auto_reconcile=True must detect ZERO drift and keep cached balances at 0.00
        tb = ReportService.generate_trial_balance(self.company, auto_reconcile=True)
        self.assertTrue(tb["totals"]["is_balanced"])
        self.assertEqual(tb["integrity_audit"]["discrepancies_detected"], 0)
        self.assertEqual(tb["totals"]["total_debit"], Decimal("0.00"))
        self.assertEqual(tb["totals"]["total_credit"], Decimal("0.00"))

        self.customer.refresh_from_db()
        self.sales.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal("0.00"))
        self.assertEqual(self.sales.current_balance, Decimal("0.00"))

        # Period TB, Period Ledger Balance, P&L, Balance Sheet must all show net 0.00
        ptb = PeriodBalanceService.get_period_trial_balance(
            self.company, datetime.date(2026, 4, 1), datetime.date(2027, 3, 31)
        )
        self.assertTrue(ptb["totals"]["is_closing_balanced"])
        self.assertEqual(Decimal(ptb["totals"]["closing_debit"]), Decimal("0.00"))

        p_cust = PeriodBalanceService.calculate_ledger_period_balance(
            self.customer, datetime.date(2026, 4, 1), datetime.date(2027, 3, 31)
        )
        self.assertEqual(Decimal(p_cust["closing_balance"]), Decimal("0.00"))

        pl = FinancialStatementsService.generate_profit_and_loss(
            self.company, datetime.date(2026, 4, 1), datetime.date(2027, 3, 31)
        )
        self.assertEqual(Decimal(str(pl["trading_account"]["direct_income"]["total"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(pl["profit_and_loss"]["net_profit"])), Decimal("0.00"))

        bs = FinancialStatementsService.generate_balance_sheet(
            self.company, datetime.date(2027, 3, 31)
        )
        self.assertTrue(bs["is_balanced"])
        self.assertEqual(Decimal(str(bs["assets"]["total_assets"])), Decimal(str(bs_before["assets"]["total_assets"])))
        self.assertEqual(Decimal(str(bs["assets"]["total_assets"])), Decimal("35000.00"))


class Stage413OutboxAndAgingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="oa413@example.com", password="Password123!", role="OWNER", email_verified=True
        )
        self.company = Company.objects.create(
            name="Outbox Aging Co", gstin="27AAACO4130M1Z9", state_code="27"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role="OWNER")
        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 26-27",
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31),
        )
        self.debtor_grp = LedgerGroup.objects.create(
            company=self.company, name="Sundry Debtors", nature="ASSET"
        )
        self.cash_grp = LedgerGroup.objects.create(
            company=self.company, name="Cash-in-Hand", nature="ASSET"
        )
        self.customer = Ledger.objects.create(
            company=self.company,
            group=self.debtor_grp,
            name="Credit Customer",
            ledger_type="CUSTOMER",
            gstin="27CUST0001A1Z1",
        )
        self.cash_cust = Ledger.objects.create(
            company=self.company,
            group=self.cash_grp,
            name="Cash",
            ledger_type="CASH",
        )

    def test_classify_and_recover_pending_outbox_without_duplicate_send(self):
        v_no_email = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV-OA-001",
            voucher_date=datetime.date(2026, 5, 1),
            party_ledger=self.customer,
            status="POSTED",
            total_amount=Decimal("1000.00"),
            created_by=self.user,
        )
        ev_skip = TransactionalOutboxEvent.objects.create(
            event_type="INVOICE_POSTED",
            aggregate_type="Voucher",
            aggregate_id=str(v_no_email.id),
            company=self.company,
            payload={"voucher_id": str(v_no_email.id)},
            idempotency_key=f"skip_{v_no_email.id}",
            status="PENDING",
        )

        # Unacknowledged already-SENT email event
        dlv = EmailDeliveryLog.objects.create(
            company=self.company,
            recipient_email="sent@example.com",
            subject="Already sent",
            email_type="INVOICE_POSTED",
            status="SENT",
            idempotency_key="already_sent_key",
        )
        ev_unack = TransactionalOutboxEvent.objects.create(
            event_type="INVOICE_POSTED",
            aggregate_type="Voucher",
            aggregate_id=str(v_no_email.id),
            company=self.company,
            payload={"voucher_id": str(v_no_email.id), "recipient_email": "sent@example.com"},
            idempotency_key="already_sent_key",
            email_delivery_log=dlv,
            status="PENDING",
        )

        # Expired lease pointing to non-existent voucher -> DEAD_LETTER on recovery
        ev_orphan = TransactionalOutboxEvent.objects.create(
            event_type="INVOICE_POSTED",
            aggregate_type="Voucher",
            aggregate_id="11111111-1111-1111-1111-111111111111",
            company=self.company,
            payload={"voucher_id": "11111111-1111-1111-1111-111111111111"},
            idempotency_key="orphan_key",
            status="PROCESSING",
            claim_token="dead_worker",
            lease_expires_at=timezone.now() - datetime.timedelta(minutes=10),
        )

        cls_list = OutboxService.classify_pending_events(company=self.company)
        cats = {c["event_id"]: c["category"] for c in cls_list}
        self.assertEqual(cats[str(ev_skip.id)], "VALID_NO_RECIPIENT_SKIPPABLE")
        self.assertEqual(cats[str(ev_unack.id)], "ALREADY_PROCESSED_UNACK")
        self.assertEqual(cats[str(ev_orphan.id)], "EXPIRED_LEASE")

        stats = OutboxService.recover_pending_outbox_events(company=self.company, batch_limit=50)
        ev_skip.refresh_from_db()
        ev_unack.refresh_from_db()
        ev_orphan.refresh_from_db()
        self.assertEqual(ev_skip.status, "SKIPPED")
        self.assertEqual(ev_unack.status, "PROCESSED")
        self.assertEqual(ev_orphan.status, "DEAD_LETTER")
        self.assertEqual(EmailDeliveryLog.objects.filter(idempotency_key="already_sent_key").count(), 1)
        self.assertEqual(stats["recovered_unack"], 1)

    def test_single_query_aging_excludes_cash_and_applies_allocations_accurately(self):
        v_credit = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV-AG-1",
            voucher_date=datetime.date(2026, 4, 1),
            due_date=datetime.date(2026, 4, 10),
            party_ledger=self.customer,
            status="POSTED",
            total_amount=Decimal("5000.00"),
            created_by=self.user,
        )
        # Spot cash invoice must be ignored in CUSTOMER aging
        Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV-AG-CASH",
            voucher_date=datetime.date(2026, 4, 2),
            due_date=datetime.date(2026, 4, 2),
            party_ledger=self.cash_cust,
            status="POSTED",
            total_amount=Decimal("900.00"),
            created_by=self.user,
        )
        rcp = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCP-AG-1",
            voucher_date=datetime.date(2026, 4, 20),
            party_ledger=self.customer,
            status="POSTED",
            total_amount=Decimal("2000.00"),
            created_by=self.user,
        )
        PaymentAllocation.objects.create(
            company=self.company,
            payment_voucher=rcp,
            invoice_voucher=v_credit,
            allocated_amount=Decimal("2000.00"),
        )

        with self.assertNumQueries(1):
            ag = PaymentAllocationService.get_aging_analysis(
                self.company, party_type="CUSTOMER", as_of_date=datetime.date(2026, 5, 5)
            )
        self.assertEqual(ag["total_outstanding"], 3000.0)
        self.assertEqual(ag["summary"]["days_1_30"], 3000.0)
        self.assertEqual(len(ag["parties"]), 1)
        self.assertEqual(ag["parties"][0]["party_name"], "Credit Customer")
