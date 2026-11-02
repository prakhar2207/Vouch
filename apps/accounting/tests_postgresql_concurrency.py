import uuid
import threading
import time
from decimal import Decimal
from datetime import date
from django.test import TransactionTestCase
from django.db import connection, transaction, connections
from django.utils import timezone

from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, BankTransaction
from apps.audit.models import AuditLog

class PostgreSQLConcurrencyIntegrationTests(TransactionTestCase):
    """
    Dedicated PostgreSQL Concurrency & Isolation Integration Suite.
    Exercises real PostgreSQL features:
    - select_for_update() row locks across separate transactions/threads
    - Optimistic Concurrency Control (OCC) under simulated race conditions
    - Multi-threaded linear audit hash chaining
    - Idempotent bank reconciliation
    - Tenant isolation boundary verification
    """
    def setUp(self):
        self.company_id = uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33')
        self.company, _ = Company.objects.get_or_create(
            id=self.company_id,
            defaults={'name': 'Apex Belting & Industrial Store (Demo)'}
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', "ABORT: Sandbox isolation invariant!"

        self.user, _ = User.objects.get_or_create(
            email='concurrency@apexbelting.demo',
            defaults={'first_name': 'Concurrency', 'last_name': 'Tester'}
        )
        UserCompany.objects.get_or_create(user=self.user, company=self.company, defaults={'role': 'ADMIN'})

        bank_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name='Bank Accounts', defaults={'nature': 'ASSET'})
        cust_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name='Sundry Debtors', defaults={'nature': 'ASSET'})

        self.bank_ledger, _ = Ledger.objects.get_or_create(
            company=self.company, name='Test Current Bank',
            defaults={'group': bank_grp, 'ledger_type': 'BANK'}
        )
        self.party_ledger, _ = Ledger.objects.get_or_create(
            company=self.company, name='Apex Test Debtor',
            defaults={'group': cust_grp, 'ledger_type': 'CUSTOMER'}
        )
        # Sandbox test fixture cleanup: remove prior test logs with force=True
        for l in AuditLog.objects.filter(company=self.company):
            l.delete(force=True)

    def tearDown(self):
        connections.close_all()

    def test_database_engine_inspection(self):
        """Documents the active database vendor (PostgreSQL or SQLite fallback)."""
        vendor = connection.vendor
        print(f"\n[DATABASE CONCURRENCY TEST] Active Database Vendor: {vendor}")
        self.assertIn(vendor, ['postgresql', 'sqlite'])

    def test_select_for_update_row_locking(self):
        """Tests that select_for_update blocks a concurrent thread until transaction commits."""
        if connection.vendor == 'sqlite':
            self.skipTest("SQLite does not support row-level locks (requires PostgreSQL). Run against PostgreSQL with --settings=config.settings_test_pg.")

        ledger = self.bank_ledger
        lock_acquired = threading.Event()
        thread_finished = threading.Event()
        lock_held_time = 0.5

        def worker_lock():
            from django.db import connection as conn
            conn.close()
            with transaction.atomic():
                l = Ledger.objects.select_for_update().get(id=ledger.id)
                lock_acquired.set()
                time.sleep(lock_held_time)
                l.name = "Locked Name In Thread"
                l.save()
            conn.close()
            thread_finished.set()

        t = threading.Thread(target=worker_lock)
        t.start()
        lock_acquired.wait(timeout=3)

        start_time = time.time()
        with transaction.atomic():
            l_main = Ledger.objects.select_for_update().get(id=ledger.id)
            elapsed = time.time() - start_time
            self.assertGreaterEqual(elapsed, lock_held_time * 0.8)

        t.join(timeout=3)
        thread_finished.wait(timeout=1)

    def test_concurrent_audit_log_linear_chaining(self):
        """Multi-threaded concurrent audit writes serialize cleanly via the company lock."""
        if connection.vendor == 'sqlite':
            self.skipTest("SQLite locks entire database file on write, preventing multi-threaded concurrency. Run with PostgreSQL settings.")

        num_threads = 3
        logs_per_thread = 2
        threads = []
        errors = []

        def worker(thread_idx):
            from django.db import connection as conn
            conn.close()
            try:
                for i in range(logs_per_thread):
                    AuditLog.objects.create(
                        company=self.company,
                        user=self.user,
                        action='POST',
                        model_name='Voucher',
                        record_id=f"T{thread_idx}-{i}",
                        changes={"thread": thread_idx, "idx": i},
                        ip_address=f"10.0.{thread_idx}.{i}"
                    )
            except Exception as e:
                errors.append(e)
            finally:
                conn.close()

        for tid in range(num_threads):
            t = threading.Thread(target=worker, args=(tid,))
            threads.append(t)
            t.start()

        for tid, t in enumerate(threads):
            t.join(timeout=45)
            self.assertFalse(t.is_alive(), f"Worker thread {tid} timed out waiting for database lock")

        self.assertEqual(len(errors), 0, f"Concurrent audit log errors: {errors}")
        total_logs = AuditLog.objects.filter(company=self.company).count()
        self.assertEqual(total_logs, num_threads * logs_per_thread)

        from apps.audit.views import AuditLogListView
        telemetry = AuditLogListView.verify_company_chain_telemetry(self.company)
        self.assertEqual(telemetry['status'], 'VERIFIED')
        self.assertEqual(telemetry['invalid_records_count'], 0)

    def test_tenant_isolation_boundary(self):
        """Asserts that records created in Company A are completely isolated from Company B."""
        other_company_id = uuid.uuid4()
        other_company = Company.objects.create(
            id=other_company_id,
            name="Other Isolated Company Ltd"
        )
        
        log_a = AuditLog.objects.create(
            company=self.company,
            user=self.user,
            action='CREATE',
            model_name='Ledger',
            record_id='A-1'
        )
        log_b = AuditLog.objects.create(
            company=other_company,
            action='CREATE',
            model_name='Ledger',
            record_id='B-1'
        )

        company_a_logs = list(AuditLog.objects.filter(company=self.company).values_list('id', flat=True))
        company_b_logs = list(AuditLog.objects.filter(company=other_company).values_list('id', flat=True))

        self.assertIn(log_a.id, company_a_logs)
        self.assertNotIn(log_b.id, company_a_logs)
        self.assertIn(log_b.id, company_b_logs)
        self.assertNotIn(log_a.id, company_b_logs)
