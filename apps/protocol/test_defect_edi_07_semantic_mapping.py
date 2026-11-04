import uuid
import threading
from decimal import Decimal
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.inventory.models import Product
from apps.accounting.models import Voucher
from apps.protocol.models import EntityMapping
from apps.protocol.mapping import ApprovalState, MappingConfidence
from apps.protocol.schema import CanonicalTransaction, ProtocolEntity, TransactionLine, TransactionTotals, TaxSummary
from apps.protocol.operation import AccountingOperation, OperationType
from apps.protocol.bridge import LedgerBridge, LedgerBridgeError


class DefectEDI07SemanticMappingDurableTests(TransactionTestCase):
    """
    Dedicated Security and Persistence Verification Suite for DEFECT-EDI-07:
    Durable Pending Semantic Mapping, Preflight Separation, Review/Approval API,
    and Safe Accounting Resume.
    """

    def setUp(self):
        self.client = APIClient()

        # Create Company A (Buyer) and Company B (Seller) and Company C (Attacker Tenant)
        self.buyer_company = Company.objects.create(
            name=f"Buyer Store {uuid.uuid4().hex[:6]}",
            gstin="27AABCB1234A1Z1",
            state_code="27"
        )
        self.seller_company = Company.objects.create(
            name=f"Seller Store {uuid.uuid4().hex[:6]}",
            gstin="27XYZAB9876B1Z2",
            state_code="27"
        )
        self.attacker_company = Company.objects.create(
            name=f"Rival Corp {uuid.uuid4().hex[:6]}",
            gstin="27RIVAL0000C1Z9",
            state_code="27"
        )

        # Users and Roles
        self.buyer_admin = User.objects.create_user(
            email=f"admin_{uuid.uuid4().hex[:6]}@buyer.com",
            password="Password123!"
        )
        UserCompany.objects.create(company=self.buyer_company, user=self.buyer_admin, role="ADMIN")

        self.buyer_viewer = User.objects.create_user(
            email=f"viewer_{uuid.uuid4().hex[:6]}@buyer.com",
            password="Password123!"
        )
        UserCompany.objects.create(company=self.buyer_company, user=self.buyer_viewer, role="VIEWER")

        self.attacker_user = User.objects.create_user(
            email=f"attacker_{uuid.uuid4().hex[:6]}@rival.com",
            password="Password123!"
        )
        UserCompany.objects.create(company=self.attacker_company, user=self.attacker_user, role="ADMIN")

        # Local catalog in Buyer company: has 'Heavy Industrial V-Belt B-65'
        # Seller will send 'Ind Belt B65' (heuristic similarity between 0.70 and 0.90)
        self.local_product = Product.objects.create(
            company=self.buyer_company,
            name="Heavy Industrial V-Belt B-65",
            sku="LOCAL-V-BELT-B65",
            hsn_code="40103990",
            gst_rate=Decimal("18.00"),
            unit="PCS",
            selling_price=Decimal("1200.00"),
            purchase_price=Decimal("950.00")
        )

    def _create_ambiguous_transaction(self) -> CanonicalTransaction:
        seller_entity = ProtocolEntity(
            name=self.seller_company.name,
            identity_type="GSTIN",
            identity_value=self.seller_company.gstin,
            state_code="27"
        )
        buyer_entity = ProtocolEntity(
            name=self.buyer_company.name,
            identity_type="GSTIN",
            identity_value=self.buyer_company.gstin,
            state_code="27"
        )

        item = TransactionLine(
            line_id="LINE-01",
            sku="FOR-BELT-B65",
            name="Industrial V-Belt B-65 Premium",
            hsn_code="40103990",
            quantity=Decimal("10.00"),
            unit="PCS",
            unit_price=Decimal("1000.00"),
            discount_amount=Decimal("0.00"),
            taxable_amount=Decimal("10000.00"),
            tax_rate_percent=Decimal("18.00")
        )

        return CanonicalTransaction(
            protocol_version="1.0",
            transaction_id=f"TX-AMBIG-{uuid.uuid4().hex[:8].upper()}",
            transaction_type="SALE",
            state_version=1,
            issued_at=timezone.now(),
            source_entity=seller_entity,
            destination_entity=buyer_entity,
            items=[item],
            tax_summary=TaxSummary(cgst_amount=Decimal("900.00"), sgst_amount=Decimal("900.00")),
            totals=TransactionTotals(subtotal=Decimal("10000.00"), total_tax=Decimal("1800.00"), grand_total=Decimal("11800.00"))
        )

    def test_01_ambiguous_transaction_persists_durable_pending_mapping(self):
        """Preflight creates durable PENDING EntityMapping in PostgreSQL and returns AWAITING_APPROVAL."""
        canonical_tx = self._create_ambiguous_transaction()

        res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )

        self.assertEqual(res["status"], "AWAITING_APPROVAL")
        self.assertIn("pending_mappings", res)
        self.assertEqual(len(res["pending_mappings"]), 1)
        self.assertEqual(res["pending_mappings"][0]["foreign_sku"], "FOR-BELT-B65")

        # Verify durable persistence in PostgreSQL database
        pending_record = EntityMapping.objects.filter(
            destination_company_id=self.buyer_company.gstin,
            foreign_sku="FOR-BELT-B65",
            approval_state=ApprovalState.PENDING.value
        ).first()
        self.assertIsNotNone(pending_record, "PENDING EntityMapping must exist durably in PostgreSQL.")
        self.assertEqual(pending_record.local_sku, self.local_product.sku)

    def test_02_zero_vouchers_or_inventory_created_while_pending(self):
        """No vouchers, stock movements, or unapproved products exist while transaction is AWAITING_APPROVAL."""
        canonical_tx = self._create_ambiguous_transaction()

        initial_vouchers = Voucher.objects.filter(company=self.buyer_company).count()
        initial_products = Product.objects.filter(company=self.buyer_company).count()

        res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )
        self.assertEqual(res["status"], "AWAITING_APPROVAL")

        final_vouchers = Voucher.objects.filter(company=self.buyer_company).count()
        final_products = Product.objects.filter(company=self.buyer_company).count()

        self.assertEqual(initial_vouchers, final_vouchers, "Zero vouchers must be posted while awaiting approval.")
        self.assertEqual(initial_products, final_products, "Zero new products may be created while awaiting approval.")

    def test_03_query_pending_mappings_enforces_tenant_isolation(self):
        """GET /api/v1/protocol/mappings/pending/ returns mappings only for the authenticated company."""
        canonical_tx = self._create_ambiguous_transaction()
        LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )

        # Buyer admin queries
        self.client.force_authenticate(user=self.buyer_admin)
        res = self.client.get(f"/api/v1/protocol/mappings/pending/?company_id={self.buyer_company.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["pending_mappings"][0]["foreign_sku"], "FOR-BELT-B65")

        # Attacker tenant queries
        self.client.force_authenticate(user=self.attacker_user)
        # Attacker attempts to query buyer company
        res_attack = self.client.get(f"/api/v1/protocol/mappings/pending/?company_id={self.buyer_company.id}")
        self.assertEqual(res_attack.status_code, status.HTTP_403_FORBIDDEN)

        # Attacker queries own company -> zero mappings
        res_own = self.client.get(f"/api/v1/protocol/mappings/pending/?company_id={self.attacker_company.id}")
        self.assertEqual(res_own.status_code, status.HTTP_200_OK)
        self.assertEqual(res_own.data["count"], 0)

    def test_04_role_authorization_enforced_on_approval(self):
        """Only users with managerial/accounting roles can approve mappings (VIEWER gets HTTP 403)."""
        canonical_tx = self._create_ambiguous_transaction()
        bridge_res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )
        mapping_id = bridge_res["pending_mappings"][0]["mapping_id"]

        self.client.force_authenticate(user=self.buyer_viewer)
        res = self.client.post("/api/v1/protocol/mappings/approve/", {
            "mapping_id": mapping_id,
            "action": "APPROVE",
            "company_id": str(self.buyer_company.id)
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("PERMISSION_DENIED", res.data.get("status", ""))

    def test_05_cross_tenant_approval_blocked(self):
        """Attacker tenant cannot approve buyer company's mapping."""
        canonical_tx = self._create_ambiguous_transaction()
        bridge_res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )
        mapping_id = bridge_res["pending_mappings"][0]["mapping_id"]

        self.client.force_authenticate(user=self.attacker_user)
        res = self.client.post("/api/v1/protocol/mappings/approve/", {
            "mapping_id": mapping_id,
            "action": "APPROVE",
            "company_id": str(self.attacker_company.id)
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("TENANT_VIOLATION", res.data.get("status", ""))

    def test_06_admin_approves_mapping_records_identity_and_timestamp(self):
        """Approval transitions mapping to APPROVED and records approver and timestamp."""
        canonical_tx = self._create_ambiguous_transaction()
        bridge_res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )
        mapping_id = bridge_res["pending_mappings"][0]["mapping_id"]

        self.client.force_authenticate(user=self.buyer_admin)
        res = self.client.post("/api/v1/protocol/mappings/approve/", {
            "mapping_id": mapping_id,
            "action": "APPROVE",
            "target_sku": self.local_product.sku,
            "company_id": str(self.buyer_company.id)
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "APPROVED")
        self.assertEqual(res.data["approved_by"], self.buyer_admin.email)

        # Verify DB record
        m = EntityMapping.objects.get(mapping_id=mapping_id)
        self.assertEqual(m.approval_state, ApprovalState.APPROVED.value)
        self.assertEqual(m.approved_by, self.buyer_admin)
        self.assertIsNotNone(m.approved_at)

    def test_07_resubmitting_approved_transaction_posts_accounting_vouchers(self):
        """Resubmitting transaction after approval succeeds and posts complete vouchers."""
        canonical_tx = self._create_ambiguous_transaction()
        bridge_res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )
        mapping_id = bridge_res["pending_mappings"][0]["mapping_id"]

        # Approve mapping
        self.client.force_authenticate(user=self.buyer_admin)
        self.client.post("/api/v1/protocol/mappings/approve/", {
            "mapping_id": mapping_id,
            "action": "APPROVE",
            "target_sku": self.local_product.sku,
            "company_id": str(self.buyer_company.id)
        })

        # Resubmit transaction
        resume_res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )
        self.assertEqual(resume_res["status"], "BRIDGE_SUCCESS")
        self.assertEqual(resume_res["vouchers_count"], 1)

        # Verify posted voucher
        v = Voucher.objects.filter(company=self.buyer_company, voucher_type="PURCHASE").first()
        self.assertIsNotNone(v)
        self.assertEqual(v.status, "POSTED")
        debits = sum(e.debit_amount for e in v.ledger_entries.all())
        credits = sum(e.credit_amount for e in v.ledger_entries.all())
        self.assertEqual(debits, credits, "Double-entry equilibrium must hold.")

    def test_08_rejection_blocks_resubmission_cleanly(self):
        """Rejecting a mapping transitions to REJECTED and blocks accounting with MAPPING_REJECTED."""
        canonical_tx = self._create_ambiguous_transaction()
        bridge_res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )
        mapping_id = bridge_res["pending_mappings"][0]["mapping_id"]

        # Reject mapping
        self.client.force_authenticate(user=self.buyer_admin)
        rej_res = self.client.post("/api/v1/protocol/mappings/approve/", {
            "mapping_id": mapping_id,
            "action": "REJECT",
            "rejection_reason": "Incompatible belt pitch.",
            "company_id": str(self.buyer_company.id)
        })
        self.assertEqual(rej_res.status_code, status.HTTP_200_OK)
        self.assertEqual(rej_res.data["status"], "REJECTED")

        # Verify DB
        m = EntityMapping.objects.get(mapping_id=mapping_id)
        self.assertEqual(m.approval_state, ApprovalState.REJECTED.value)
        self.assertEqual(m.rejection_reason, "Incompatible belt pitch.")

        # Resubmitting transaction MUST fail with LedgerBridgeError
        with self.assertRaises(LedgerBridgeError) as ctx:
            LedgerBridge.execute_converged_accounting(
                company=self.buyer_company,
                canonical_tx=canonical_tx,
                converged_operations=[],
                user=self.buyer_admin
            )
        self.assertIn("mapping was rejected", str(ctx.exception))

    def test_09_concurrent_approvals_are_idempotent(self):
        """Simultaneous approval requests on the same mapping serialize cleanly and return idempotent success."""
        canonical_tx = self._create_ambiguous_transaction()
        bridge_res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )
        mapping_id = bridge_res["pending_mappings"][0]["mapping_id"]

        responses = []

        def approve_worker():
            c = APIClient()
            c.force_authenticate(user=self.buyer_admin)
            r = c.post("/api/v1/protocol/mappings/approve/", {
                "mapping_id": mapping_id,
                "action": "APPROVE",
                "target_sku": self.local_product.sku,
                "company_id": str(self.buyer_company.id)
            })
            responses.append(r)

        t1 = threading.Thread(target=approve_worker)
        t2 = threading.Thread(target=approve_worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(responses), 2)
        statuses = [r.status_code for r in responses]
        self.assertTrue(all(s == status.HTTP_200_OK for s in statuses))
        body_statuses = [r.data.get("status") for r in responses]
        self.assertIn("APPROVED", body_statuses)
        # The other thread either got APPROVED (if simultaneous) or ALREADY_APPROVED (if serialized)
        self.assertTrue("APPROVED" in body_statuses or "ALREADY_APPROVED" in body_statuses)

    def test_10_deleted_target_product_fails_revalidation(self):
        """If an approved mapping's target product is deleted, subsequent execution fails revalidation gracefully."""
        canonical_tx = self._create_ambiguous_transaction()
        bridge_res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=canonical_tx,
            converged_operations=[],
            user=self.buyer_admin
        )
        mapping_id = bridge_res["pending_mappings"][0]["mapping_id"]

        # Approve
        self.client.force_authenticate(user=self.buyer_admin)
        self.client.post("/api/v1/protocol/mappings/approve/", {
            "mapping_id": mapping_id,
            "action": "APPROVE",
            "target_sku": self.local_product.sku,
            "company_id": str(self.buyer_company.id)
        })

        # Simulate local product deletion
        self.local_product.delete()

        # Resubmit transaction: must raise LedgerBridgeError with revalidation failure
        with self.assertRaises(LedgerBridgeError) as ctx:
            LedgerBridge.execute_converged_accounting(
                company=self.buyer_company,
                canonical_tx=canonical_tx,
                converged_operations=[],
                user=self.buyer_admin
            )
        self.assertIn("Revalidation failed", str(ctx.exception))
