import uuid
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup
from apps.accounting.models import (
    AccountingFinding, Ledger, Voucher, VoucherItem, LedgerEntry
)
from apps.accounting.services.finding_fix_service import FindingFixService

User = get_user_model()

class AccountantTrustWorkflowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Trust Workflow Corp",
            gstin="29ABCDE1234F1Z5",
            state_code="29"
        )
        self.user = User.objects.create_user(
            email="ramesh@trustcorp.com",
            password="StrongPassword123!"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='ADMIN')

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_COMPANY_ID=str(self.company.id))

        # Ledger Groups
        self.assets_grp = LedgerGroup.objects.create(
            company=self.company,
            name="Current Assets",
            nature="ASSET"
        )
        self.income_grp = LedgerGroup.objects.create(
            company=self.company,
            name="Direct Income",
            nature="INCOME"
        )

        # Ledgers
        self.sales_ledger = Ledger.objects.create(
            company=self.company,
            name="Sales Revenue",
            group=self.income_grp,
            ledger_type="INCOME"
        )
        self.party_a = Ledger.objects.create(
            company=self.company,
            name="Party A",
            group=self.assets_grp,
            ledger_type="PARTY"
        )
        self.party_b = Ledger.objects.create(
            company=self.company,
            name="Party B",
            group=self.assets_grp,
            ledger_type="PARTY"
        )

    def _create_sample_voucher(self, party):
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='SALES',
            voucher_number=f"INV-{uuid.uuid4().hex[:6].upper()}",
            voucher_date=timezone.now().date(),
            party_ledger=party,
            total_amount=Decimal('5000.00'),
            status='POSTED'
        )

        # Entry 1: Party Debit
        LedgerEntry.objects.create(
            voucher=v,
            ledger=party,
            debit_amount=Decimal('5000.00'),
            credit_amount=Decimal('0.00')
        )
        # Entry 2: Sales Credit
        LedgerEntry.objects.create(
            voucher=v,
            ledger=self.sales_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('5000.00')
        )
        return v

    def test_preview_and_execute_fix(self):
        vch = self._create_sample_voucher(self.party_a)

        finding = AccountingFinding.objects.create(
            company=self.company,
            severity="MEDIUM",
            category="PARTY_MISMATCH",
            title="Invoice mistakenly assigned to Party A",
            description="Transaction belongs to Party B according to PO details",
            fix_action="MOVE_PARTY",
            evidence={
                "voucher_id": str(vch.id),
                "current_party_id": str(self.party_a.id),
                "suggested_party_id": str(self.party_b.id),
                "amount": "5000.00"
            }
        )

        # 1. Preview
        preview_resp = self.client.get(f'/api/v1/accounting/health/findings/{finding.id}/preview/')
        self.assertEqual(preview_resp.status_code, status.HTTP_200_OK)
        preview_data = preview_resp.json()
        self.assertTrue(preview_data.get('supported', False))
        self.assertEqual(preview_data.get('action'), 'MOVE_PARTY')
        self.assertIn('Party A', preview_data.get('summary', ''))

        # 2. Execute / Accept
        exec_resp = self.client.post(f'/api/v1/accounting/health/findings/{finding.id}/fix/')
        self.assertEqual(exec_resp.status_code, status.HTTP_200_OK)
        exec_data = exec_resp.json()
        self.assertEqual(exec_data.get('status'), 'SUCCESS')

        finding.refresh_from_db()
        self.assertTrue(finding.is_resolved)
        self.assertIsNotNone(finding.resolved_at)

        # Check that original voucher was marked CORRECTED
        vch.refresh_from_db()
        self.assertEqual(vch.status, 'CORRECTED')

        # Check new voucher was created for Party B
        new_vch_id = finding.evidence.get('created_voucher_id')
        self.assertIsNotNone(new_vch_id)
        new_vch = Voucher.objects.get(id=new_vch_id)
        self.assertEqual(new_vch.party_ledger, self.party_b)
        self.assertEqual(new_vch.total_amount, Decimal('5000.00'))
        self.assertEqual(new_vch.status, 'POSTED')

    def test_edit_and_execute_fix(self):
        # Ledger balance recalculation finding
        finding = AccountingFinding.objects.create(
            company=self.company,
            severity="HIGH",
            category="LEDGER_BALANCE",
            title="Cached ledger balance out of sync",
            description="Party balance does not match entries",
            fix_action="RECALCULATE_BALANCE",
            evidence={
                "ledger_id": str(self.party_a.id),
                "expected_balance": "1000.00"
            }
        )

        # Accountant overrides parameters during approval
        edit_resp = self.client.post(
            f'/api/v1/accounting/health/findings/{finding.id}/edit/',
            {"override_params": {"expected_balance": "2500.00"}},
            format='json'
        )
        self.assertEqual(edit_resp.status_code, status.HTTP_200_OK)

        finding.refresh_from_db()
        self.assertTrue(finding.is_resolved)
        self.assertTrue(finding.evidence.get("accountant_edited"))
        self.assertEqual(finding.evidence.get("expected_balance"), "2500.00")

    def test_reject_finding(self):
        finding = AccountingFinding.objects.create(
            company=self.company,
            severity="LOW",
            category="SUSPICIOUS_LEDGER",
            title="AI recommends renaming ledger",
            description="Suggested standard name",
            fix_action="RENAME_LEDGER",
            evidence={}
        )

        # Accountant rejects suggestion with reasons
        reject_resp = self.client.post(
            f'/api/v1/accounting/health/findings/{finding.id}/reject/',
            {"reason": "Custom ledger name required by client statutory reporting format."},
            format='json'
        )
        self.assertEqual(reject_resp.status_code, status.HTTP_200_OK)
        res_data = reject_resp.json()
        self.assertEqual(res_data["status"], "REJECTED")

        finding.refresh_from_db()
        self.assertTrue(finding.is_resolved)
        self.assertEqual(finding.evidence.get("rejection_status"), "REJECTED")
        self.assertIn("Custom ledger name", finding.evidence.get("rejection_reason", ""))



    def test_reverse_applied_fix(self):
        vch = self._create_sample_voucher(self.party_a)

        finding = AccountingFinding.objects.create(
            company=self.company,
            severity="MEDIUM",
            category="PARTY_MISMATCH",
            title="Misallocated voucher",
            description="Reassign",
            fix_action="MOVE_PARTY",
            evidence={
                "voucher_id": str(vch.id),
                "current_party_id": str(self.party_a.id),
                "suggested_party_id": str(self.party_b.id),
                "amount": "5000.00"
            }
        )

        # 1. Execute fix
        self.client.post(f'/api/v1/accounting/health/findings/{finding.id}/fix/')
        finding.refresh_from_db()
        self.assertTrue(finding.is_resolved)

        new_vch_id = finding.evidence.get('created_voucher_id')
        new_vch = Voucher.objects.get(id=new_vch_id)
        self.assertEqual(new_vch.status, 'POSTED')

        # 2. Accountant reverses fix
        reverse_resp = self.client.post(f'/api/v1/accounting/health/findings/{finding.id}/reverse/')
        self.assertEqual(reverse_resp.status_code, status.HTTP_200_OK)
        rev_data = reverse_resp.json()
        self.assertEqual(rev_data["status"], "REVERSED")

        finding.refresh_from_db()
        self.assertFalse(finding.is_resolved)
        self.assertIsNone(finding.resolved_at)

        # 3. Created voucher was cancelled
        new_vch.refresh_from_db()
        self.assertEqual(new_vch.status, 'CANCELLED')

    def test_party_change_decouples_payment_allocations(self):
        from apps.accounting.models import PaymentAllocation, PaymentAllocationTask
        # Create Sales Invoice for Party A
        inv = self._create_sample_voucher(self.party_a)

        # Create Receipt from Party A
        rcp = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='RECEIPT',
            voucher_number='RCP-TEST-001',
            voucher_date=timezone.now().date(),
            party_ledger=self.party_a,
            total_amount=Decimal('5000.00'),
            status='POSTED'
        )
        # Allocate Receipt to Invoice
        PaymentAllocation.objects.create(
            company=self.company,
            payment_voucher=rcp,
            invoice_voucher=inv,
            allocated_amount=Decimal('5000.00')
        )
        task = PaymentAllocationTask.objects.create(
            company=self.company,
            payment_voucher=rcp,
            target_amount=Decimal('5000.00'),
            allocated_amount=Decimal('5000.00'),
            remaining_amount=Decimal('0.00'),
            status='COMPLETED'
        )

        # User edits invoice to change party from Party A to Party B
        resp = self.client.patch(
            f'/api/v1/accounting/vouchers/detail/{inv.id}/',
            {"party_ledger_id": str(self.party_b.id)},
            format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        inv.refresh_from_db()
        self.assertEqual(inv.party_ledger_id, self.party_b.id)

        # Allocations must be cleanly decoupled
        self.assertEqual(PaymentAllocation.objects.filter(invoice_voucher=inv).count(), 0)

        # Party A receipt must have unallocated funds restored
        task.refresh_from_db()
        self.assertEqual(task.allocated_amount, Decimal('0.00'))
        self.assertEqual(task.remaining_amount, Decimal('5000.00'))
        self.assertEqual(task.status, 'PENDING')


