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

        elif fix_action == 'RECONCILE_FIFO':
            v_id = evidence.get('voucher_id')
            p_id = evidence.get('party_id')
            voucher = Voucher.objects.filter(id=v_id).first() if v_id else None
            party = Ledger.objects.filter(id=p_id).first() if p_id else (voucher.party_ledger if voucher else None)
            party_name = party.name if party else "this party"
            v_num = voucher.voucher_number if voucher else evidence.get('voucher_number', 'invoice')
            return {
                "supported": True,
                "action": "RECONCILE_FIFO",
                "summary": f"Re-run automated FIFO allocation for {party_name}",
                "accounting_mechanism": f"Clears over-allocated payments and recalculates FIFO allocations chronologically for {party_name}.",
                "before": {
                    "voucher": v_num,
                    "allocated_amount": evidence.get('allocated_amount', '0.00'),
                    "invoice_total": evidence.get('total_amount', '0.00')
                },
                "after": {
                    "voucher": v_num,
                    "allocated_amount": evidence.get('total_amount', '0.00'),
                    "excess": "0.00"
                }
            }

        elif fix_action == 'VOID_DUPLICATE_VOUCHER':
            dup_id = evidence.get('duplicate_voucher_id')
            prim_id = evidence.get('primary_voucher_id')
            if not (dup_id and prim_id):
                return {"supported": False, "reason": "Missing duplicate or primary voucher ID in evidence."}
            dup_v = Voucher.objects.filter(id=dup_id, company=finding.company).first()
            prim_v = Voucher.objects.filter(id=prim_id, company=finding.company).first()
            if not dup_v or not prim_v:
                return {"supported": False, "reason": "Referenced vouchers no longer exist."}

            party = dup_v.party_ledger
            amt = dup_v.total_amount
            current_party_bal = party.current_balance if party else Decimal('0.00')
            if party:
                if dup_v.voucher_type == 'RECEIPT':
                    after_party_bal = current_party_bal + amt if party.normal_balance == 'DEBIT' else current_party_bal - amt
                    impact_party = f"+₹{amt}" if party.normal_balance == 'DEBIT' else f"-₹{amt}"
                else:
                    after_party_bal = current_party_bal - amt if party.normal_balance == 'DEBIT' else current_party_bal + amt
                    impact_party = f"-₹{amt}" if party.normal_balance == 'DEBIT' else f"+₹{amt}"
            else:
                after_party_bal = Decimal('0.00')
                impact_party = "0.00"

            bank_entry = dup_v.ledger_entries.filter(ledger__ledger_type__in=['BANK', 'CASH']).first()
            bank_ledger = bank_entry.ledger if bank_entry else None
            current_bank_bal = bank_ledger.current_balance if bank_ledger else Decimal('0.00')
            if bank_ledger:
                if dup_v.voucher_type == 'RECEIPT':
                    after_bank_bal = current_bank_bal - amt
                    impact_bank = f"-₹{amt}"
                else:
                    after_bank_bal = current_bank_bal + amt
                    impact_bank = f"+₹{amt}"
            else:
                after_bank_bal = Decimal('0.00')
                impact_bank = "0.00"

            preview_comparison = []
            if party:
                preview_comparison.append({
                    "account": f"Party: {party.name}",
                    "before_balance": f"₹{current_party_bal}",
                    "after_balance": f"₹{after_party_bal}",
                    "impact": impact_party
                })
            if bank_ledger:
                preview_comparison.append({
                    "account": f"Account: {bank_ledger.name}",
                    "before_balance": f"₹{current_bank_bal}",
                    "after_balance": f"₹{after_bank_bal}",
                    "impact": impact_bank
                })

            history_note = (
                f"Duplicate voucher #{dup_v.voucher_number} will be cancelled. "
                f"Primary voucher #{prim_v.voucher_number} remains permanently active. "
                f"If any bank reconciliation was matched to #{dup_v.voucher_number}, it will be safely transferred to #{prim_v.voucher_number}."
            )

            return {
                "supported": True,
                "action": "VOID_DUPLICATE_VOUCHER",
                "summary": f"Cancel duplicate {dup_v.voucher_type} #{dup_v.voucher_number} (₹{amt}) and keep #{prim_v.voucher_number}",
                "history_preservation_note": history_note,
                "preview_comparison": preview_comparison,
                "before": {
                    "duplicate_voucher": dup_v.voucher_number,
                    "primary_voucher": prim_v.voucher_number,
                    "party_balance": str(current_party_bal)
                },
                "after": {
                    "duplicate_voucher": "CANCELLED",
                    "primary_voucher": f"ACTIVE ({prim_v.voucher_number})",
                    "party_balance": str(after_party_bal)
                }
            }

        elif fix_action == 'MERGE_INVENTORY_ITEMS':
            from apps.inventory.models import Product
            prim_id = evidence.get('primary_product_id')
            dup_id = evidence.get('duplicate_product_id')
            prim_p = Product.objects.filter(id=prim_id, company=finding.company).first()
            dup_p = Product.objects.filter(id=dup_id, company=finding.company).first()
            if not prim_p or not dup_p:
                return {"supported": False, "reason": "Referenced inventory products no longer exist."}

            combined_stock = prim_p.stock_quantity + dup_p.stock_quantity
            preview_comparison = [
                {
                    "account": f"Primary: {prim_p.name} ({prim_p.sku})",
                    "before_balance": f"{prim_p.stock_quantity} units",
                    "after_balance": f"{combined_stock} units",
                    "impact": f"+{dup_p.stock_quantity} units"
                },
                {
                    "account": f"Duplicate: {dup_p.name} ({dup_p.sku})",
                    "before_balance": f"{dup_p.stock_quantity} units",
                    "after_balance": "0 units (Merged)",
                    "impact": f"-{dup_p.stock_quantity} units"
                }
            ]
            return {
                "supported": True,
                "action": "MERGE_INVENTORY_ITEMS",
                "summary": f"Consolidate duplicate product {dup_p.sku} into {prim_p.sku} (Combined Stock: {combined_stock})",
                "history_preservation_note": "All historical invoices, bills, and stock movements referencing the duplicate product will be reassigned to the primary product. The duplicate product will be archived.",
                "preview_comparison": preview_comparison,
                "before": {
                    "primary_sku": prim_p.sku,
                    "duplicate_sku": dup_p.sku,
                    "primary_stock": str(prim_p.stock_quantity),
                    "duplicate_stock": str(dup_p.stock_quantity)
                },
                "after": {
                    "primary_sku": prim_p.sku,
                    "primary_stock": str(combined_stock),
                    "duplicate_status": "ARCHIVED"
                }
            }

        elif fix_action == 'LINK_BANK_TRANSACTION':
            from apps.accounting.models import BankTransaction
            b_id = evidence.get('bank_tx_id')
            v_id = evidence.get('voucher_id')
            bank_tx = BankTransaction.objects.filter(id=b_id, company=finding.company).first()
            vch = Voucher.objects.filter(id=v_id, company=finding.company).first()
            if not bank_tx or not vch:
                return {"supported": False, "reason": "Bank transaction or voucher no longer exists."}
            amt = evidence.get('amount', str(vch.total_amount))
            return {
                "supported": True,
                "action": "LINK_BANK_TRANSACTION",
                "summary": f"Link unlinked Bank Feed (₹{amt} on {bank_tx.transaction_date}) to Voucher #{vch.voucher_number}",
                "history_preservation_note": f"Associates bank statement line with existing voucher #{vch.voucher_number}, marking the bank transaction as RECONCILED without creating any redundant voucher.",
                "preview_comparison": [
                    {
                        "account": f"Bank Feed: {bank_tx.bank_ledger.name}",
                        "before_balance": "UNRESOLVED",
                        "after_balance": f"RECONCILED (#{vch.voucher_number})",
                        "impact": "Matched"
                    }
                ],
                "before": {"status": bank_tx.status, "voucher": "None"},
                "after": {"status": "RECONCILED", "voucher": vch.voucher_number}
            }

        elif fix_action == 'EXCLUDE_DUPLICATE_BANK':
            from apps.accounting.models import BankTransaction
            dup_id = evidence.get('duplicate_bank_tx_id')
            tx = BankTransaction.objects.filter(id=dup_id, company=finding.company).first()
            if not tx:
                return {"supported": False, "reason": "Bank transaction no longer exists."}
            amt = evidence.get('amount', '0.00')
            return {
                "supported": True,
                "action": "EXCLUDE_DUPLICATE_BANK",
                "summary": f"Exclude duplicate imported statement line of ₹{amt} on {tx.transaction_date}",
                "history_preservation_note": "Marks duplicate statement transaction as EXCLUDED with reason, leaving genuine statement transactions intact.",
                "preview_comparison": [
                    {
                        "account": f"Statement Feed: {tx.bank_ledger.name}",
                        "before_balance": tx.status,
                        "after_balance": "EXCLUDED",
                        "impact": "Removed"
                    }
                ],
                "before": {"status": tx.status},
                "after": {"status": "EXCLUDED"}
            }

        elif fix_action == 'MERGE_DUPLICATE_LEDGERS':
            prim_id = evidence.get('primary_ledger_id')
            dup_id = evidence.get('duplicate_ledger_id')
            prim_l = Ledger.objects.filter(id=prim_id, company=finding.company).first()
            dup_l = Ledger.objects.filter(id=dup_id, company=finding.company).first()
            if not prim_l or not dup_l:
                return {"supported": False, "reason": "Referenced ledgers no longer exist."}
            consolidated_bal = prim_l.current_balance + dup_l.current_balance
            return {
                "supported": True,
                "action": "MERGE_DUPLICATE_LEDGERS",
                "summary": f"Merge duplicate ledger '{dup_l.name}' into '{prim_l.name}'",
                "history_preservation_note": "All vouchers and ledger entries will be transferred to the primary ledger account, and the duplicate ledger will be archived.",
                "preview_comparison": [
                    {
                        "account": f"Primary: {prim_l.name}",
                        "before_balance": f"₹{prim_l.current_balance}",
                        "after_balance": f"₹{consolidated_bal}",
                        "impact": f"+₹{dup_l.current_balance}"
                    },
                    {
                        "account": f"Duplicate: {dup_l.name}",
                        "before_balance": f"₹{dup_l.current_balance}",
                        "after_balance": "₹0.00 (Archived)",
                        "impact": f"-₹{dup_l.current_balance}"
                    }
                ],
                "before": {"primary_balance": str(prim_l.current_balance), "duplicate_balance": str(dup_l.current_balance)},
                "after": {"primary_balance": str(consolidated_bal), "duplicate_status": "ARCHIVED"}
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

        elif fix_action == 'RECONCILE_FIFO':
            from apps.accounting.services.allocation_service import PaymentAllocationService
            v_id = evidence.get('voucher_id')
            p_id = evidence.get('party_id')
            voucher = Voucher.objects.filter(id=v_id, company=finding.company).first() if v_id else None
            party = Ledger.objects.filter(id=p_id, company=finding.company).first() if p_id else (voucher.party_ledger if voucher else None)

            res = PaymentAllocationService.auto_reconcile_all_unallocated(finding.company, party)

            finding.is_resolved = True
            finding.resolved_at = timezone.now()
            finding.resolved_by = user
            finding.save(update_fields=['is_resolved', 'resolved_at', 'resolved_by'])

            AuditService.log_action(
                company=finding.company,
                user=user,
                action='UPDATE',
                model_name='PaymentAllocation',
                record_id=finding.id,
                changes={"action": "RECONCILE_FIFO", "party": party.name if party else "ALL", "result": res}
            )

            return {
                "status": "SUCCESS",
                "message": f"Successfully re-allocated payments via FIFO: {res.get('message', '')}",
                "allocations_count": res.get("allocations_count", 0)
            }

        elif fix_action == 'VOID_DUPLICATE_VOUCHER':
            dup_id = evidence.get('duplicate_voucher_id')
            prim_id = evidence.get('primary_voucher_id')
            if not (dup_id and prim_id):
                raise ValidationError("Missing duplicate or primary voucher ID in finding evidence.")

            dup_v = Voucher.objects.get(id=dup_id, company=finding.company)
            prim_v = Voucher.objects.get(id=prim_id, company=finding.company)

            # 1. If duplicate voucher was matched to any bank transaction, transfer link to primary voucher
            from apps.accounting.models import BankTransaction
            linked_bank_txs = BankTransaction.objects.filter(company=finding.company, matched_voucher=dup_v)
            for btx in linked_bank_txs:
                btx.matched_voucher = prim_v
                btx.matched_party = prim_v.party_ledger
                btx.status = 'RECONCILED'
                btx.save(update_fields=['matched_voucher', 'matched_party', 'status', 'updated_at'])

            # 2. Cancel the duplicate voucher cleanly
            VoucherService.cancel_voucher(dup_v, user=user)

            # 3. Recalculate balances for party and all involved ledgers
            if dup_v.party_ledger:
                VoucherService.recalculate_ledger_balance(dup_v.party_ledger)
            if prim_v.party_ledger and prim_v.party_ledger_id != dup_v.party_ledger_id:
                VoucherService.recalculate_ledger_balance(prim_v.party_ledger)
            for ent in dup_v.ledger_entries.all():
                if ent.ledger and ent.ledger_id != dup_v.party_ledger_id:
                    VoucherService.recalculate_ledger_balance(ent.ledger)

            finding.is_resolved = True
            finding.resolved_at = timezone.now()
            finding.resolved_by = user
            finding.save(update_fields=['is_resolved', 'resolved_at', 'resolved_by'])

            AuditService.log_action(
                company=finding.company,
                user=user,
                action='CANCEL',
                model_name='Voucher',
                record_id=dup_v.id,
                changes={
                    "finding_id": str(finding.id),
                    "action": "VOID_DUPLICATE_VOUCHER",
                    "cancelled_voucher": dup_v.voucher_number,
                    "retained_primary_voucher": prim_v.voucher_number
                }
            )

            return {
                "status": "SUCCESS",
                "message": f"Successfully cancelled duplicate voucher #{dup_v.voucher_number}. Retained primary voucher #{prim_v.voucher_number}.",
                "cancelled_voucher": dup_v.voucher_number,
                "primary_voucher": prim_v.voucher_number
            }

        elif fix_action == 'MERGE_INVENTORY_ITEMS':
            from apps.inventory.models import Product, InventoryEntry
            from apps.accounting.models import VoucherItem
            prim_id = evidence.get('primary_product_id')
            dup_id = evidence.get('duplicate_product_id')
            if not (prim_id and dup_id):
                raise ValidationError("Missing product IDs for inventory merge.")

            prim_p = Product.objects.get(id=prim_id, company=finding.company)
            dup_p = Product.objects.get(id=dup_id, company=finding.company)

            # Re-link VoucherItem records
            VoucherItem.objects.filter(product=dup_p).update(product=prim_p)
            # Re-link InventoryEntry records
            InventoryEntry.objects.filter(product=dup_p).update(product=prim_p)

            # Consolidate stock
            prim_p.stock_quantity = prim_p.stock_quantity + dup_p.stock_quantity
            prim_p.save(update_fields=['stock_quantity'])

            dup_p.stock_quantity = Decimal('0.00')
            dup_p.is_active = False
            dup_p.name = f"{dup_p.name} [MERGED-{dup_p.sku}]"
            dup_p.save(update_fields=['stock_quantity', 'is_active', 'name'])

            finding.is_resolved = True
            finding.resolved_at = timezone.now()
            finding.resolved_by = user
            finding.save(update_fields=['is_resolved', 'resolved_at', 'resolved_by'])

            AuditService.log_action(
                company=finding.company,
                user=user,
                action='UPDATE',
                model_name='Product',
                record_id=prim_p.id,
                changes={
                    "finding_id": str(finding.id),
                    "action": "MERGE_INVENTORY_ITEMS",
                    "primary_product": prim_p.sku,
                    "merged_product": dup_p.sku,
                    "new_stock": str(prim_p.stock_quantity)
                }
            )

            return {
                "status": "SUCCESS",
                "message": f"Successfully merged product {dup_p.sku} into {prim_p.sku}. Consolidated stock: {prim_p.stock_quantity}.",
                "primary_sku": prim_p.sku,
                "consolidated_stock": str(prim_p.stock_quantity)
            }

        elif fix_action == 'LINK_BANK_TRANSACTION':
            from apps.accounting.models import BankTransaction
            b_id = evidence.get('bank_tx_id')
            v_id = evidence.get('voucher_id')
            if not (b_id and v_id):
                raise ValidationError("Missing bank transaction or voucher ID.")

            bank_tx = BankTransaction.objects.get(id=b_id, company=finding.company)
            vch = Voucher.objects.get(id=v_id, company=finding.company)

            bank_tx.matched_voucher = vch
            if vch.party_ledger:
                bank_tx.matched_party = vch.party_ledger
            bank_tx.status = 'RECONCILED'
            bank_tx.match_confidence = 1.0
            bank_tx.save(update_fields=['matched_voucher', 'matched_party', 'status', 'match_confidence', 'updated_at'])

            finding.is_resolved = True
            finding.resolved_at = timezone.now()
            finding.resolved_by = user
            finding.save(update_fields=['is_resolved', 'resolved_at', 'resolved_by'])

            AuditService.log_action(
                company=finding.company,
                user=user,
                action='UPDATE',
                model_name='BankTransaction',
                record_id=bank_tx.id,
                changes={
                    "finding_id": str(finding.id),
                    "action": "LINK_BANK_TRANSACTION",
                    "matched_voucher": vch.voucher_number
                }
            )

            return {
                "status": "SUCCESS",
                "message": f"Successfully linked bank transaction to voucher #{vch.voucher_number}.",
                "voucher_number": vch.voucher_number
            }

        elif fix_action == 'EXCLUDE_DUPLICATE_BANK':
            from apps.accounting.models import BankTransaction
            dup_id = evidence.get('duplicate_bank_tx_id')
            if not dup_id:
                raise ValidationError("Missing bank transaction ID.")
            bank_tx = BankTransaction.objects.get(id=dup_id, company=finding.company)
            bank_tx.status = 'EXCLUDED'
            bank_tx.save(update_fields=['status', 'updated_at'])

            finding.is_resolved = True
            finding.resolved_at = timezone.now()
            finding.resolved_by = user
            finding.save(update_fields=['is_resolved', 'resolved_at', 'resolved_by'])

            AuditService.log_action(
                company=finding.company,
                user=user,
                action='UPDATE',
                model_name='BankTransaction',
                record_id=bank_tx.id,
                changes={
                    "finding_id": str(finding.id),
                    "action": "EXCLUDE_DUPLICATE_BANK",
                    "status": "EXCLUDED"
                }
            )

            return {
                "status": "SUCCESS",
                "message": f"Successfully excluded duplicate bank statement line.",
                "bank_tx_id": str(bank_tx.id)
            }

        elif fix_action == 'MERGE_DUPLICATE_LEDGERS':
            prim_id = evidence.get('primary_ledger_id')
            dup_id = evidence.get('duplicate_ledger_id')
            if not (prim_id and dup_id):
                raise ValidationError("Missing ledger IDs for duplicate merge.")
            prim_l = Ledger.objects.get(id=prim_id, company=finding.company)
            dup_l = Ledger.objects.get(id=dup_id, company=finding.company)

            Voucher.objects.filter(party_ledger=dup_l).update(party_ledger=prim_l)
            LedgerEntry.objects.filter(ledger=dup_l).update(ledger=prim_l)

            VoucherService.recalculate_ledger_balance(prim_l)
            dup_l.is_archived = True
            dup_l.current_balance = Decimal('0.00')
            dup_l.name = f"{dup_l.name} [MERGED]"
            dup_l.save(update_fields=['is_archived', 'current_balance', 'name'])

            finding.is_resolved = True
            finding.resolved_at = timezone.now()
            finding.resolved_by = user
            finding.save(update_fields=['is_resolved', 'resolved_at', 'resolved_by'])

            AuditService.log_action(
                company=finding.company,
                user=user,
                action='UPDATE',
                model_name='Ledger',
                record_id=prim_l.id,
                changes={
                    "finding_id": str(finding.id),
                    "action": "MERGE_DUPLICATE_LEDGERS",
                    "primary_ledger": prim_l.name,
                    "merged_ledger": dup_l.name
                }
            )

            return {
                "status": "SUCCESS",
                "message": f"Successfully merged ledger '{dup_l.name}' into '{prim_l.name}'. New balance: ₹{prim_l.current_balance}.",
                "primary_ledger": prim_l.name,
                "new_balance": str(prim_l.current_balance)
            }

        else:
            raise ValidationError(f"Unsupported fix action '{fix_action}'.")
