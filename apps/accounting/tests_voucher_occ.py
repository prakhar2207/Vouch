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
    - CORS preflight allow-headers verification
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

    def test_cors_preflight_allows_version_headers(self):
        """
        Verifies that CORS preflight permits If-Match and X-Voucher-Version headers.
        """
        voucher = self.create_test_voucher("OCC-CORS-PREFLIGHT")
        url = f"/api/vouchers/{voucher.id}/"

        res = self.client.options(
            url,
            HTTP_ORIGIN='https://vouch-pi-one.vercel.app',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='PATCH',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization, content-type, if-match, x-voucher-version'
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        allow_headers = res.get('Access-Control-Allow-Headers', '').lower()
        self.assertIn('if-match', allow_headers)
        self.assertIn('x-voucher-version', allow_headers)


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
        Under PostgreSQL with select_for_update(), requests serialize:
        - Exactly ONE request succeeds (HTTP 200).
        - Exactly ONE request receives a conflict (HTTP 409).
        - The voucher ends at version 2.
        """
        voucher = self.create_test_voucher("OCC-CONCURRENT-RACE")
        voucher_id = voucher.id
        results = []

        def worker(thread_id):
            from django.db import connection as conn
            conn.close()
            try:
                client = APIClient()
                client.force_authenticate(user=self.user)
                client.credentials(HTTP_X_COMPANY_ID=str(self.company.id))

                url = f"/api/vouchers/{voucher_id}/"
                payload = {
                    "narration": f"Concurrent update from thread {thread_id}",
                    "version": 1
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

        self.assertEqual(len(results), 2, "Both threads must complete")

        status_codes = [r[1] for r in results]
        self.assertIn(status.HTTP_200_OK, status_codes, f"One thread must succeed: {results}")
        self.assertIn(status.HTTP_409_CONFLICT, status_codes, f"One thread must get 409 Conflict: {results}")

        # Final voucher state check
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

        def worker(v_id, name):
            from django.db import connection as conn
            conn.close()
            try:
                client = APIClient()
                client.force_authenticate(user=self.user)
                client.credentials(HTTP_X_COMPANY_ID=str(self.company.id))

                url = f"/api/vouchers/{v_id}/"
                payload = {
                    "narration": f"Updated {name}",
                    "version": 1
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
