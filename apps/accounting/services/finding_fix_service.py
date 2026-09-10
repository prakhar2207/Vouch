import datetime
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher, LedgerEntry, AccountingFinding
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.audit.services.audit_service import AuditService

class FindingFixService:
    """
    Fix preview generator and deterministic execution engine for AccountingFinding items.
    NEVER mutates records without generating a preview first.
    Preserves complete accounting history via reversal and correction vouchers.
    """

    @classmethod
    def generate_fix_preview(cls, finding: AccountingFinding) -> Dict[str, Any]:
        """
        Generates structured 'BEFORE vs AFTER' financial impact data without touching the database.
        """
        evidence = finding.evidence or {}
        fix_action = finding.fix_action

        if fix_action == 'MOVE_PARTY':
            v_id = evidence.get('voucher_id')
            curr_p_id = evidence.get('current_party_id')
            sugg_p_id = evidence.get('suggested_party_id')

            if not (v_id and curr_p_id and sugg_p_id):
                return {"supported": False, "reason": "Insufficient evidence details to preview party transfer."}

            voucher = Voucher.objects.get(id=v_id)
            current_party = Ledger.objects.get(id=curr_p_id)
            target_party = Ledger.objects.get(id=sugg_p_id)
            amt = Decimal(str(evidence.get('amount', voucher.total_amount)))

            # Project after balances
            if voucher.voucher_type == 'SALES':
                curr_after = current_party.current_balance - amt
                targ_after = target_party.current_balance + amt
            else:
                curr_after = current_party.current_balance - amt
                targ_after = target_party.current_balance + amt

            return {
                "supported": True,
                "action": "MOVE_PARTY",
                "summary": f"Move Invoice #{voucher.voucher_number} from {current_party.name} to {target_party.name}",
                "accounting_mechanism": "Creates explicit reversal voucher for old party and posts new corrected voucher under target party. Accounting history is preserved.",
                "before": {
                    "current_party": {"name": current_party.name, "balance": str(current_party.current_balance)},
                    "target_party": {"name": target_party.name, "balance": str(target_party.current_balance)}
                },
                "after": {
                    "current_party": {"name": current_party.name, "balance": str(curr_after)},
                    "target_party": {"name": target_party.name, "balance": str(targ_after)}
                }
            }

        elif fix_action == 'RECALCULATE_BALANCE':
            l_id = evidence.get('ledger_id')
            if not l_id:
                return {"supported": False, "reason": "No ledger specified in evidence."}
            party = Ledger.objects.get(id=l_id)
            expected = evidence.get('expected_balance', str(party.current_balance))

            return {
                "supported": True,
                "action": "RECALCULATE_BALANCE",
                "summary": f"Recalculate balance for {party.name}",
                "accounting_mechanism": "Re-derives balance from single source of truth: Opening vouchers + posted ledger entries.",
                "before": {
                    "party": {"name": party.name, "balance": str(party.current_balance)}
                },
                "after": {
                    "party": {"name": party.name, "balance": str(expected)}
                }
            }

        return {
            "supported": False,
            "reason": f"No automatic fix preview supported for action '{fix_action}'."
        }

    @classmethod
    @transaction.atomic
    def execute_fix(cls, finding: AccountingFinding, user=None) -> Dict[str, Any]:
        """
        Deterministically executes a user-approved fix for an AccountingFinding.
        Creates an audit log, preserves reversal records, and recalculates balances.
        """
        if finding.is_resolved:
            raise ValidationError("This finding is already resolved.")

        evidence = finding.evidence or {}
        fix_action = finding.fix_action

        if fix_action == 'MOVE_PARTY':
            v_id = evidence.get('voucher_id')
            sugg_p_id = evidence.get('suggested_party_id')
            if not (v_id and sugg_p_id):
                raise ValidationError("Missing voucher or target party in finding evidence.")

            original_voucher = Voucher.objects.get(id=v_id, company=finding.company)
            target_party = Ledger.objects.get(id=sugg_p_id, company=finding.company)
            old_party = original_voucher.party_ledger

            # 1. Reverse the original voucher (P0-4 / P0-5 compliant reversal)
            rev_vch = VoucherService.create_reversal_voucher(
                original_voucher,
                user=user,
                reason=f"Corrected party assignment to {target_party.name} (Finding: {finding.title})"
            )

            # 2. Create new corrected voucher for target party
            new_num = f"{original_voucher.voucher_number}-C"
            if Voucher.objects.filter(company=finding.company, voucher_number=new_num).exists():
                new_num = f"{original_voucher.voucher_number}-C{int(timezone.now().timestamp()) % 1000}"

            new_voucher = Voucher.objects.create(
                company=finding.company,
                financial_year=original_voucher.financial_year,
                voucher_type=original_voucher.voucher_type,
                voucher_number=new_num,
                voucher_date=original_voucher.voucher_date,
                external_invoice_number=original_voucher.external_invoice_number,
                party_ledger=target_party,
                status='POSTED',
                total_amount=original_voucher.total_amount,
                narration=f"Correction of {original_voucher.voucher_number} reassigned to {target_party.name}",
                corrects_voucher=original_voucher,
                created_by=user or original_voucher.created_by
            )

            # 3. Create replacement ledger entries
            for entry in original_voucher.ledger_entries.all():
                entry_ledger = target_party if (old_party and entry.ledger_id == old_party.id) else entry.ledger
                LedgerEntry.objects.create(
                    company=finding.company,
                    voucher=new_voucher,
                    ledger=entry_ledger,
                    debit_amount=entry.debit_amount,
                    credit_amount=entry.credit_amount,
                    narration=f"Transferred to {target_party.name}: {entry.narration or ''}"
                )

            # 4. Mark original voucher status as CORRECTED
            original_voucher.status = 'CORRECTED'
            original_voucher.save(update_fields=['status'])

            # 5. Recalculate balances
            if old_party:
                VoucherService.recalculate_ledger_balance(old_party)
            VoucherService.recalculate_ledger_balance(target_party)

            finding.is_resolved = True
            finding.resolved_at = timezone.now()
            finding.resolved_by = user
            finding.save(update_fields=['is_resolved', 'resolved_at', 'resolved_by'])

            AuditService.log_action(
                company=finding.company,
                user=user,
                action='UPDATE',
                model_name='Voucher',
                record_id=original_voucher.id,
                changes={
                    "finding_id": str(finding.id),
                    "action": "MOVE_PARTY",
                    "old_party": old_party.name if old_party else "None",
                    "new_party": target_party.name,
                    "reversal_voucher": rev_vch.voucher_number,
                    "corrected_voucher": new_voucher.voucher_number
                }
            )

            return {
                "status": "SUCCESS",
                "message": f"Successfully moved invoice #{original_voucher.voucher_number} to {target_party.name}.",
                "reversal_voucher": rev_vch.voucher_number,
                "new_voucher": new_voucher.voucher_number
            }

        elif fix_action == 'RECALCULATE_BALANCE':
            l_id = evidence.get('ledger_id')
            if not l_id:
                raise ValidationError("Missing ledger in finding evidence.")
            party = Ledger.objects.get(id=l_id, company=finding.company)
            new_bal = VoucherService.recalculate_ledger_balance(party)

            finding.is_resolved = True
            finding.resolved_at = timezone.now()
            finding.resolved_by = user
            finding.save(update_fields=['is_resolved', 'resolved_at', 'resolved_by'])

            AuditService.log_action(
                company=finding.company,
                user=user,
                action='UPDATE',
                model_name='Ledger',
                record_id=party.id,
                changes={"action": "RECALCULATE_BALANCE", "new_balance": str(new_bal)}
            )

            return {
                "status": "SUCCESS",
                "message": f"Successfully recalculated balance for {party.name} to ₹{new_bal}.",
                "new_balance": str(new_bal)
            }

        else:
            raise ValidationError(f"Unsupported fix action '{fix_action}'.")
