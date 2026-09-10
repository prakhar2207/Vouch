from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher, LedgerEntry, LedgerBalance
from apps.audit.services.audit_service import AuditService
from apps.accounting.services.voucher_service import VoucherService

class PartyMergeService:
    @staticmethod
    def preview_merge(company: Company, source_id: str, target_id: str) -> dict:
        """
        Analyzes the impact of merging source_ledger into target_ledger.
        Returns party details, voucher counts, entry counts, and balance impact.
        """
        if str(source_id) == str(target_id):
            raise ValidationError("Source and target party cannot be the same.")

        source = Ledger.objects.get(id=source_id, company=company)
        target = Ledger.objects.get(id=target_id, company=company)

        vouchers_count = Voucher.objects.filter(company=company, party_ledger=source).count()
        entries_count = LedgerEntry.objects.filter(ledger=source).count()

        return {
            "source": {
                "id": str(source.id),
                "name": source.name,
                "gstin": source.gstin or "",
                "phone": source.phone or "",
                "current_balance": str(source.current_balance),
                "balance_type": source.opening_balance_type,
                "role": source.canonical_role,
            },
            "target": {
                "id": str(target.id),
                "name": target.name,
                "gstin": target.gstin or "",
                "phone": target.phone or "",
                "current_balance": str(target.current_balance),
                "balance_type": target.opening_balance_type,
                "role": target.canonical_role,
            },
            "affected_vouchers_count": vouchers_count,
            "affected_entries_count": entries_count,
        }

    @classmethod
    @transaction.atomic
    def execute_merge(cls, company: Company, source_id: str, target_id: str, user=None) -> dict:
        """
        Generic, deterministic duplicate merge:
        1. Copies missing contact/tax info from source to target.
        2. Reassigns all Vouchers and LedgerEntries from source to target.
        3. Recalculates target current_balance.
        4. Archives source ledger (is_archived=True, is_active=False).
        5. Writes immutable audit record.
        """
        if str(source_id) == str(target_id):
            raise ValidationError("Source and target party cannot be the same.")

        source = Ledger.objects.select_for_update().get(id=source_id, company=company)
        target = Ledger.objects.select_for_update().get(id=target_id, company=company)

        # 1. Fill missing target details
        updated_target = False
        if not target.gstin and source.gstin:
            target.gstin = source.gstin
            updated_target = True
        if not target.phone and source.phone:
            target.phone = source.phone
            updated_target = True
        if not target.email and source.email:
            target.email = source.email
            updated_target = True
        if not target.address and source.address:
            target.address = source.address
            updated_target = True
        if not target.state_code and source.state_code:
            target.state_code = source.state_code
            updated_target = True
        if updated_target:
            target.save()

        # 2. Reassign Vouchers & LedgerEntries
        vouchers_count = Voucher.objects.filter(company=company, party_ledger=source).count()
        entries_count = LedgerEntry.objects.filter(ledger=source).count()

        Voucher.objects.filter(company=company, party_ledger=source).update(party_ledger=target)
        LedgerEntry.objects.filter(ledger=source).update(ledger=target)
        LedgerBalance.objects.filter(ledger=source).delete()

        # 3. Recalculate target balance
        new_target_balance = VoucherService.recalculate_ledger_balance(target)

        # 4. Mark source as archived
        source.is_archived = True
        source.is_active = False
        source.current_balance = Decimal('0.00')
        source.save(update_fields=['is_archived', 'is_active', 'current_balance'])

        # 5. Log audit trail
        AuditService.log_action(
            company=company,
            user=user,
            action='UPDATE',
            model_name='PartyMerge',
            record_id=target.id,
            changes={
                'source_party_id': str(source.id),
                'source_party_name': source.name,
                'target_party_id': str(target.id),
                'target_party_name': target.name,
                'reassigned_vouchers': vouchers_count,
                'reassigned_entries': entries_count,
                'new_target_balance': str(new_target_balance)
            }
        )

        return {
            "success": True,
            "message": f"Successfully merged '{source.name}' into '{target.name}'.",
            "merged_vouchers_count": vouchers_count,
            "merged_entries_count": entries_count,
            "target_party_id": str(target.id),
            "target_current_balance": str(new_target_balance)
        }
