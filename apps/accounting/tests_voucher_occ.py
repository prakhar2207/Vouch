import uuid
import threading
import time
from decimal import Decimal
from datetime import date
from django.test import TestCase, TransactionTestCase
from django.db import connection, transaction, connections
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry

User = get_user_model()

class BaseOCCFixtureMixin:
    """Base fixture mixin guaranteeing strict tenant isolation against Apex Belting sandbox."""
    def setup_occ_fixtures(self):
        # 1. MANDATORY TEST ISOLATION POLICY: Strictly dedicated sandbox company
        self.sandbox_company_id = uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33')
        self.company, _ = Company.objects.get_or_create(
            id=self.sandbox_company_id,
            defaults={
                'name': 'Apex Belting & Industrial Store (Demo)',
                'gstin': '07AAAAA0000A1Z5',
                'state_code': '07'
            }
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', (
            "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
        )

        # 2. Primary Sandbox User
        self.user, _ = User.objects.get_or_create(
            email='occ_tester@apexbelting.demo',
            defaults={'first_name': 'OCC', 'last_name': 'Tester'}
        )
        self.user.set_password('ApexTestPass123!')
        self.user.save()
        UserCompany.objects.get_or_create(
            user=self.user, company=self.company,
            defaults={'role': 'OWNER'}
        )

        # 3. Secondary Tenant for Isolation Verification
        self.other_company, _ = Company.objects.get_or_create(
            id=uuid.UUID('99999999-9999-9999-9999-999999999999'),
            defaults={
                'name': 'Isolated Competitor Belts Pvt Ltd',
                'gstin': '27BBBBB1111B1Z2',
                'state_code': '27'
            }
        )
        self.other_user, _ = User.objects.get_or_create(
            email='competitor@isolated.demo',
            defaults={'first_name': 'Isolated', 'last_name': 'User'}
        )
        self.other_user.set_password('CompetitorPass123!')
        self.other_user.save()
        UserCompany.objects.get_or_create(
            user=self.other_user, company=self.other_company,
            defaults={'role': 'OWNER'}
        )

        # 4. Standard Ledger Setup
        grp_assets, _ = LedgerGroup.objects.get_or_create(company=self.company, name='Current Assets', defaults={'nature': 'ASSET'})
        grp_income, _ = LedgerGroup.objects.get_or_create(company=self.company, name='Direct Income', defaults={'nature': 'INCOME'})

        self.party_a, _ = Ledger.objects.get_or_create(
            company=self.company, name='Customer Alpha',
            defaults={'group': grp_assets, 'ledger_type': 'CUSTOMER'}
        )
        self.party_b, _ = Ledger.objects.get_or_create(
            company=self.company, name='Customer Beta',
            defaults={'group': grp_assets, 'ledger_type': 'CUSTOMER'}
        )
        self.sales_ledger, _ = Ledger.objects.get_or_create(
            company=self.company, name='Domestic Sales',
            defaults={'group': grp_income, 'ledger_type': 'SALES'}
        )

        # 5. Default API Client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_COMPANY_ID=str(self.company.id))

    def create_test_voucher(self, voucher_number="TEST-INV-101", company=None, total_amount=Decimal('1000.00')):
        target_company = company or self.company
        target_user = self.user if target_company == self.company else self.other_user
        v = Voucher.objects.create(
            company=target_company,
            created_by=target_user,
            voucher_type='SALES_INVOICE',
            voucher_number=f"{voucher_number}-{uuid.uuid4().hex[:4]}",
            voucher_date=date.today(),
            party_ledger=self.party_a if target_company == self.company else None,
            total_amount=total_amount,
            status='POSTED',
            version=1
        )
        return v


class VoucherOCCUnitAndWorkflowTests(BaseOCCFixtureMixin, TestCase):
    """
    Fast-executing transactional tests for OCC contract enforcement:
    - 428 on missing version
    - 428 on wildcard If-Match: *
    - 400 on malformed version
    - 200 on current version (increment to version + 1, with ETag and X-Voucher-Version)
    - 200 on If-Match header version
    - 409 on stale version with current_version in payload
    - Cross-tenant modification rejection (403)
    - Complete frontend edit and conflict refresh retry workflow
    - Zero side-effects rollback verification for 428 and 409
    - Real browser-style OPTIONS preflight test followed by PATCH using version headers
    """

    def setUp(self):
        super().setUp()
        self.setup_occ_fixtures()

    def test_database_engine_is_postgresql(self):
        """Verifies tests run on real PostgreSQL with row-locking support."""
        self.assertEqual(
            connection.vendor, 'postgresql',
            f"Mandatory requirement violated: OCC tests must execute on PostgreSQL, got '{connection.vendor}'."
        )

    def test_patch_no_version_returns_428_precondition_required(self):
        """
        Regression: PATCH request with no version in body and no If-Match header
        MUST be rejected with HTTP 428 Precondition Required.
        """
        voucher = self.create_test_voucher("OCC-TEST-428")
        url = f"/api/vouchers/{voucher.id}/"
        payload = {"narration": "Unversioned update attempt"}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_428_PRECONDITION_REQUIRED)
        self.assertIn("Precondition Required", res.data.get("error", ""))

        # Verify voucher was NOT modified
        voucher.refresh_from_db()
        self.assertEqual(voucher.version, 1)
        self.assertNotEqual(voucher.narration, "Unversioned update attempt")

    def test_patch_wildcard_if_match_rejected_with_428(self):
        """
        Regression: If-Match: * must NOT allow bypassing OCC.
        Must return HTTP 428 Precondition Required.
        """
        voucher = self.create_test_voucher("OCC-TEST-WILDCARD")
        url = f"/api/vouchers/{voucher.id}/"
        payload = {"narration": "Wildcard bypass attempt"}

        res = self.client.patch(url, payload, format="json", HTTP_IF_MATCH='*')
        self.assertEqual(res.status_code, status.HTTP_428_PRECONDITION_REQUIRED)
        self.assertIn("Wildcard '*' If-Match is not permitted", res.data.get("error", ""))

        voucher.refresh_from_db()
        self.assertEqual(voucher.version, 1)

    def test_patch_invalid_version_type_returns_400_bad_request(self):
        """
        Regression: Non-integer version in body or non-numeric If-Match returns HTTP 400.
        """
        voucher = self.create_test_voucher("OCC-TEST-400")
        url = f"/api/vouchers/{voucher.id}/"

        # Invalid body version
        res = self.client.patch(url, {"narration": "Bad version", "version": "not-an-int"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("must be an integer", res.data.get("error", ""))

        # Invalid header If-Match
        res = self.client.patch(url, {"narration": "Bad etag"}, format="json", HTTP_IF_MATCH='"invalid-etag"')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Expected numeric version", res.data.get("error", ""))

    def test_patch_current_version_succeeds_and_increments(self):
        """
        Regression: Supplying current version (1) succeeds and increments version to 2.
        Response headers must include ETag and X-Voucher-Version.
        """
        voucher = self.create_test_voucher("OCC-TEST-SUCCESS")
        url = f"/api/vouchers/{voucher.id}/"
        payload = {
            "narration": "Valid versioned update",
            "version": 1
        }

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get("success"))
        self.assertEqual(res.data.get("voucher", {}).get("version"), 2)

        # Verify headers
        self.assertIn("ETag", res)
        self.assertEqual(res["ETag"], f'"v-{voucher.id}-v2"')
        self.assertIn("X-Voucher-Version", res)
        self.assertEqual(res["X-Voucher-Version"], "2")

        # Verify DB state
        voucher.refresh_from_db()
        self.assertEqual(voucher.version, 2)
        self.assertEqual(voucher.narration, "Valid versioned update")

    def test_patch_current_version_via_if_match_succeeds(self):
        """
        Regression: Supplying current version via HTTP_IF_MATCH header succeeds.
        """
        voucher = self.create_test_voucher("OCC-TEST-IFMATCH")
        url = f"/api/vouchers/{voucher.id}/"
        payload = {"narration": "Updated via If-Match header"}

        res = self.client.patch(url, payload, format="json", HTTP_IF_MATCH=f'"{voucher.version}"')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data.get("voucher", {}).get("version"), 2)

        voucher.refresh_from_db()
        self.assertEqual(voucher.version, 2)
        self.assertEqual(voucher.narration, "Updated via If-Match header")

    def test_patch_stale_version_returns_409_conflict(self):
        """
        Regression: Stale version returns HTTP 409 Conflict with current_version in response.
        """
        voucher = self.create_test_voucher("OCC-TEST-STALE")
        # Bump voucher version to 2
        voucher.version = 2
        voucher.save(update_fields=['version'])

        url = f"/api/vouchers/{voucher.id}/"
        # Client sends stale version 1
        payload = {
            "narration": "Stale update attempt",
            "version": 1
        }

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("Conflict", res.data.get("error", ""))
        self.assertEqual(res.data.get("current_version"), 2)

        # Verify DB remained untouched
        voucher.refresh_from_db()
        self.assertEqual(voucher.version, 2)
        self.assertNotEqual(voucher.narration, "Stale update attempt")

    def test_cross_tenant_isolation_denied(self):
        """
        Security / Isolation: User from Company B cannot update Voucher in Company A,
        even if supplying valid version.
        """
        voucher_a = self.create_test_voucher("OCC-TENANT-A", company=self.company)

        # Authenticate as Other Tenant User
        competitor_client = APIClient()
        competitor_client.force_authenticate(user=self.other_user)
        competitor_client.credentials(HTTP_X_COMPANY_ID=str(self.other_company.id))

        url = f"/api/vouchers/{voucher_a.id}/"
        payload = {
            "narration": "Cross tenant tamper attempt",
            "version": 1
        }
        res = competitor_client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Permission denied", res.data.get("error", ""))

        voucher_a.refresh_from_db()
        self.assertEqual(voucher_a.version, 1)
        self.assertNotEqual(voucher_a.narration, "Cross tenant tamper attempt")

    def test_frontend_edit_workflow_and_conflict_refresh(self):
        """
        Simulates complete end-to-end frontend edit lifecycle:
        1. Client A loads voucher details (receives version 1).
        2. Client B loads voucher details (receives version 1).
        3. Client A submits edit with version 1 -> succeeds, version becomes 2.
        4. Client B submits edit with version 1 -> receives 409 Conflict.
        5. Client B refreshes voucher details (GET) -> receives latest version 2.
        6. Client B resubmits edit with version 2 -> succeeds, version becomes 3.
        """
        voucher = self.create_test_voucher("OCC-FRONTEND-FLOW")
        v_url = f"/api/vouchers/{voucher.id}/"

        # 1 & 2. Both clients load initial voucher
        get_res_a = self.client.get(v_url)
        self.assertEqual(get_res_a.status_code, status.HTTP_200_OK)
        loaded_version_a = get_res_a.data.get("data", {}).get("version")
        self.assertEqual(loaded_version_a, 1)

        get_res_b = self.client.get(v_url)
        loaded_version_b = get_res_b.data.get("data", {}).get("version")
        self.assertEqual(loaded_version_b, 1)

        # 3. Client A saves with version 1
        res_a = self.client.patch(v_url, {
            "narration": "Update by Client A",
            "version": loaded_version_a
        }, format="json")
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)
        self.assertEqual(res_a.data.get("voucher", {}).get("version"), 2)

        # 4. Client B saves with stale version 1 -> 409
        res_b = self.client.patch(v_url, {
            "narration": "Update by Client B",
            "version": loaded_version_b
        }, format="json")
        self.assertEqual(res_b.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res_b.data.get("current_version"), 2)

        # 5. Client B refreshes latest voucher state
        refresh_res = self.client.get(v_url)
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        refreshed_version = refresh_res.data.get("data", {}).get("version")
        self.assertEqual(refreshed_version, 2)

        # 6. Client B resubmits with refreshed version 2 -> succeeds
        res_retry = self.client.patch(v_url, {
            "narration": "Update by Client B after refresh",
            "version": refreshed_version
        }, format="json")
        self.assertEqual(res_retry.status_code, status.HTTP_200_OK)
        self.assertEqual(res_retry.data.get("voucher", {}).get("version"), 3)

        voucher.refresh_from_db()
        self.assertEqual(voucher.version, 3)
        self.assertEqual(voucher.narration, "Update by Client B after refresh")

    def test_real_browser_preflight_and_patch_flow(self):
        """
        Real Browser Simulation:
        1. OPTIONS Preflight with Origin, Access-Control-Request-Method, Access-Control-Request-Headers.
        2. Assert 200 OK, Access-Control-Allow-Origin, Access-Control-Allow-Headers (containing if-match and x-voucher-version),
           and Access-Control-Expose-Headers (containing ETag and X-Voucher-Version).
        3. Real PATCH request using If-Match header and X-Voucher-Version.
        4. Assert 200 OK, response ETag matches new version, X-Voucher-Version header incremented.
        """
        voucher = self.create_test_voucher("OCC-BROWSER-FLOW")
        url = f"/api/vouchers/{voucher.id}/"
        origin = 'https://vouch-pi-one.vercel.app'

        # 1. Real browser preflight OPTIONS request
        preflight_res = self.client.options(
            url,
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='PATCH',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization, content-type, if-match, x-voucher-version'
        )
        self.assertEqual(preflight_res.status_code, status.HTTP_200_OK)
        self.assertEqual(preflight_res.get('Access-Control-Allow-Origin'), origin)
        allow_headers = preflight_res.get('Access-Control-Allow-Headers', '').lower()
        self.assertIn('if-match', allow_headers)
        self.assertIn('x-voucher-version', allow_headers)

        expose_headers = preflight_res.get('Access-Control-Expose-Headers', '')
        self.assertIn('ETag', expose_headers)
        self.assertIn('X-Voucher-Version', expose_headers)

        # 2. Browser sends actual PATCH request with If-Match header
        patch_res = self.client.patch(
            url,
            {"narration": "Browser-style update with conditional headers"},
            format="json",
            HTTP_ORIGIN=origin,
            HTTP_IF_MATCH=f'"{voucher.version}"',
            HTTP_X_VOUCHER_VERSION=str(voucher.version)
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.get('Access-Control-Allow-Origin'), origin)
        self.assertEqual(patch_res.get('X-Voucher-Version'), '2')
        self.assertEqual(patch_res.get('ETag'), f'"v-{voucher.id}-v2"')

        voucher.refresh_from_db()
        self.assertEqual(voucher.version, 2)
        self.assertEqual(voucher.narration, "Browser-style update with conditional headers")

    def test_precondition_required_and_conflict_zero_side_effects(self):
        """
        P0 Invariant: Neither 428 Precondition Required nor 409 Conflict
        may produce any financial side effects or partial mutations:
        - Voucher fields (narration, amounts) remain unchanged
        - Voucher items count and quantities remain unchanged
        - Ledger entries count and amounts remain unchanged
        - Product stock quantities remain unchanged
        - Audit logs for update are NOT emitted
        """
        from apps.inventory.models import Product
        from apps.audit.models import AuditLog

        prod = Product.objects.create(
            company=self.company,
            name="OCC Belt Shield",
            sku=f"OCC-SHIELD-{uuid.uuid4().hex[:4]}",
            stock_quantity=Decimal('100.00'),
            purchase_price=Decimal('50.00'),
            selling_price=Decimal('100.00')
        )
        voucher = self.create_test_voucher("OCC-ZERO-MUTATE")
        item = VoucherItem.objects.create(
            voucher=voucher,
            product=prod,
            quantity=Decimal('10.00'),
            rate=Decimal('100.00'),
            taxable_amount=Decimal('1000.00'),
            gst_rate=Decimal('18.00'),
            total_amount=Decimal('1180.00')
        )
        entry_dr = LedgerEntry.objects.create(
            voucher=voucher,
            ledger=self.party_a,
            debit_amount=Decimal('1180.00'),
            credit_amount=Decimal('0.00')
        )
        entry_cr = LedgerEntry.objects.create(
            voucher=voucher,
            ledger=self.sales_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('1180.00')
        )

        initial_narration = voucher.narration
        initial_version = voucher.version
        initial_items_count = VoucherItem.objects.filter(voucher=voucher).count()
        initial_entries_count = LedgerEntry.objects.filter(voucher=voucher).count()
        initial_stock = prod.stock_quantity
        initial_audit_count = AuditLog.objects.filter(record_id=str(voucher.id), action='UPDATE').count()

        url = f"/api/vouchers/{voucher.id}/"

        # 1. Attempt unversioned PATCH -> 428 Precondition Required
        res_428 = self.client.patch(url, {
            "narration": "Tampered via 428 attempt",
            "items": [{"product_id": str(prod.id), "quantity": 999, "rate": 999}]
        }, format="json")
        self.assertEqual(res_428.status_code, status.HTTP_428_PRECONDITION_REQUIRED)

        # Verify ZERO side effects after 428
        voucher.refresh_from_db()
        prod.refresh_from_db()
        self.assertEqual(voucher.narration, initial_narration)
        self.assertEqual(voucher.version, initial_version)
        self.assertEqual(VoucherItem.objects.filter(voucher=voucher).count(), initial_items_count)
        self.assertEqual(LedgerEntry.objects.filter(voucher=voucher).count(), initial_entries_count)
        self.assertEqual(prod.stock_quantity, initial_stock)
        self.assertEqual(AuditLog.objects.filter(record_id=str(voucher.id), action='UPDATE').count(), initial_audit_count)

        # 2. Attempt stale version PATCH -> 409 Conflict
        res_409 = self.client.patch(url, {
            "narration": "Tampered via 409 attempt",
            "version": 999,  # Stale/incorrect version
            "items": [{"product_id": str(prod.id), "quantity": 999, "rate": 999}]
        }, format="json")
        self.assertEqual(res_409.status_code, status.HTTP_409_CONFLICT)

        # Verify ZERO side effects after 409
        voucher.refresh_from_db()
        prod.refresh_from_db()
        self.assertEqual(voucher.narration, initial_narration)
        self.assertEqual(voucher.version, initial_version)
        self.assertEqual(VoucherItem.objects.filter(voucher=voucher).count(), initial_items_count)
        self.assertEqual(LedgerEntry.objects.filter(voucher=voucher).count(), initial_entries_count)
        self.assertEqual(prod.stock_quantity, initial_stock)
        self.assertEqual(AuditLog.objects.filter(record_id=str(voucher.id), action='UPDATE').count(), initial_audit_count)


class VoucherOCCConcurrencyIntegrationTests(BaseOCCFixtureMixin, TransactionTestCase):
    """
    Multi-threaded PostgreSQL Concurrency Integration Tests:
    - Exercises real PostgreSQL select_for_update() row locking across distinct threads.
    - Two concurrent updates using the same version serialize: exactly one succeeds and one receives 409.
    - Two concurrent updates to different vouchers both succeed.
    """

    def setUp(self):
        super().setUp()
        self.setup_occ_fixtures()

    def tearDown(self):
        connections.close_all()

    def test_two_concurrent_updates_same_version_one_succeeds_one_conflicts(self):
        """
        CRITICAL CONCURRENCY INVARIANT:
        Two concurrent threads attempt to update the same voucher using the same initial version (1).
        
        Proof of Race Condition Setup:
        1. Both threads execute client.get(url) and independently read the EXACT same initial version (1).
        2. Both threads synchronize on a threading.Barrier(2).
        3. Both threads submit concurrent PATCH requests using that identical initial version.
        
        Under PostgreSQL with select_for_update(), requests serialize:
        - Exactly ONE request succeeds (HTTP 200).
        - Exactly ONE request receives a conflict (HTTP 409).
        - The voucher ends at version 2.
        """
        voucher = self.create_test_voucher("OCC-CONCURRENT-RACE")
        voucher_id = voucher.id
        results = []
        barrier = threading.Barrier(2)
        initial_versions_read = []

        def worker(thread_id):
            from django.db import connection as conn
            conn.close()
            try:
                client = APIClient()
                client.force_authenticate(user=self.user)
                client.credentials(HTTP_X_COMPANY_ID=str(self.company.id))

                url = f"/api/vouchers/{voucher_id}/"

                # Step 1: Independently fetch latest voucher details from server
                get_res = client.get(url)
                self.assertEqual(get_res.status_code, status.HTTP_200_OK)
                read_version = get_res.data.get("data", {}).get("version")
                initial_versions_read.append((thread_id, read_version))

                # Step 2: Synchronize at barrier to ensure both threads read before either writes
                barrier.wait(timeout=10)

                # Step 3: Concurrently attempt update using the loaded version
                payload = {
                    "narration": f"Concurrent update from thread {thread_id}",
                    "version": read_version
                }
                res = client.patch(url, payload, format="json")
                results.append((thread_id, res.status_code, getattr(res, 'data', {})))
            finally:
                conn.close()

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))

        t1.start()
        t2.start()

        t1.join(timeout=30)
        t2.join(timeout=30)

        # Verification 1: Prove both threads read the identical version (1)
        self.assertEqual(len(initial_versions_read), 2, "Both threads must have read initial voucher")
        self.assertEqual(initial_versions_read[0][1], 1, "Thread 1 must have read version 1")
        self.assertEqual(initial_versions_read[1][1], 1, "Thread 2 must have read version 1")

        # Verification 2: Exactly one 200 and one 409
        self.assertEqual(len(results), 2, "Both threads must complete")
        status_codes = [r[1] for r in results]
        self.assertIn(status.HTTP_200_OK, status_codes, f"One thread must succeed: {results}")
        self.assertIn(status.HTTP_409_CONFLICT, status_codes, f"One thread must get 409 Conflict: {results}")

        # Verification 3: Final voucher state check
        voucher.refresh_from_db()
        self.assertEqual(voucher.version, 2, "Voucher version must increment exactly once")

    def test_two_concurrent_updates_different_vouchers_both_succeed(self):
        """
        Concurrency Non-Blocking: Two concurrent updates to DIFFERENT vouchers
        should both succeed without blocking or conflicting.
        """
        v1 = self.create_test_voucher("OCC-DIFF-V1")
        v2 = self.create_test_voucher("OCC-DIFF-V2")
        results = []
        barrier = threading.Barrier(2)

        def worker(v_id, name):
            from django.db import connection as conn
            conn.close()
            try:
                client = APIClient()
                client.force_authenticate(user=self.user)
                client.credentials(HTTP_X_COMPANY_ID=str(self.company.id))

                url = f"/api/vouchers/{v_id}/"

                # Both read initial state
                get_res = client.get(url)
                self.assertEqual(get_res.status_code, status.HTTP_200_OK)
                read_version = get_res.data.get("data", {}).get("version")

                barrier.wait(timeout=10)

                payload = {
                    "narration": f"Updated {name}",
                    "version": read_version
                }
                res = client.patch(url, payload, format="json")
                results.append((name, res.status_code))
            finally:
                conn.close()

        t1 = threading.Thread(target=worker, args=(v1.id, "V1"))
        t2 = threading.Thread(target=worker, args=(v2.id, "V2"))

        t1.start()
        t2.start()

        t1.join(timeout=30)
        t2.join(timeout=30)

        self.assertEqual(len(results), 2)
        for name, code in results:
            self.assertEqual(code, status.HTTP_200_OK, f"{name} update should have succeeded with 200")

        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.version, 2)
        self.assertEqual(v2.version, 2)
