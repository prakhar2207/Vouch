from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from apps.accounting.models import Voucher, LedgerEntry
from apps.ledgers.models import Ledger, LedgerGroup

class VoucherService:
    @staticmethod
    def _get_or_create_cogs_and_inventory_ledgers(company):
        """
        Provisions standard perpetual inventory ledgers:
        - Cost of Goods Sold (Direct Expense)
        - Stock-in-Hand (Current Asset)
        """
        direct_exp, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name="Direct Expenses",
            defaults={"nature": "EXPENSE"}
        )
        asset_grp, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name="Current Assets",
            defaults={"nature": "ASSET"}
        )
        
        cogs_ledger = Ledger.objects.filter(company=company, name__icontains="Cost of Goods Sold").first()
        if not cogs_ledger:
            cogs_ledger = Ledger.objects.create(
                company=company,
                group=direct_exp,
                name="Cost of Goods Sold",
                ledger_type="EXPENSE"
            )
            
        inv_ledger = Ledger.objects.filter(company=company, name__icontains="Stock-in-Hand").first() or \
                     Ledger.objects.filter(company=company, name__icontains="Inventory").first()
        if not inv_ledger:
            inv_ledger = Ledger.objects.create(
                company=company,
                group=asset_grp,
                name="Stock-in-Hand",
                ledger_type="ASSET"
            )
        return cogs_ledger, inv_ledger

    @staticmethod
    @transaction.atomic
    def post_voucher(voucher: Voucher, process_stock=True):
        if voucher.status == 'POSTED':
            raise ValidationError("Voucher is already posted.")
        if voucher.status == 'CANCELLED':
            raise ValidationError("Cannot post a cancelled voucher.")
            
        voucher.status = 'VALIDATING'
        voucher.save(update_fields=['status'])
        
        # 1. Process Stock & calculate COGS
        from apps.inventory.services.stock_service import StockService
        
        if process_stock:
            if voucher.voucher_type in ('SALES', 'PURCHASE'):
                StockService.process_voucher_stock(voucher)
        
        # 3. Process Accounting Ledger Entries with Concurrency Locks
        entries = list(voucher.ledger_entries.select_related('ledger').all())
        if not entries:
            voucher.status = 'DRAFT'
            voucher.save(update_fields=['status'])
            raise ValidationError("Voucher cannot be posted without ledger entries.")
            
        total_debit = sum(entry.debit_amount for entry in entries)
        total_credit = sum(entry.credit_amount for entry in entries)
        
        # Enforce Double-Entry Invariant: Sum(Debits) == Sum(Credits)
        if total_debit != total_credit:
            voucher.status = 'DRAFT'
            voucher.save(update_fields=['status'])
            raise ValidationError(
                f"Double-entry invariant violated for {voucher.voucher_number}. "
                f"Total Debit ({total_debit}) does not equal Total Credit ({total_credit})."
            )
            
        # Ensure company is populated on all ledger entries
        for entry in entries:
            if not entry.company_id:
                entry.company_id = voucher.company_id
                entry.save(update_fields=['company'])

        # 4. Acquire row-level locks on all affected ledgers
        ledger_ids = [entry.ledger_id for entry in entries]
        locked_ledgers = {
            l.id: l for l in Ledger.objects.select_for_update().filter(id__in=ledger_ids)
        }
        
        for entry in entries:
            if entry.debit_amount > 0 and entry.credit_amount > 0:
                raise ValidationError("Ledger entry cannot contain both debit and credit.")
                
            ledger = locked_ledgers[entry.ledger_id]
            
            if ledger.normal_balance == 'CREDIT':
                ledger.current_balance = ledger.current_balance + entry.credit_amount - entry.debit_amount
            else:
                ledger.current_balance = ledger.current_balance + entry.debit_amount - entry.credit_amount
                
            ledger.save(update_fields=['current_balance'])
            
        voucher.status = 'POSTED'
        if voucher.total_amount <= Decimal('0.00'):
            voucher.total_amount = total_debit
        voucher.save(update_fields=['status', 'total_amount'])
        
        # 5. Log Audit Trail
        from apps.audit.services.audit_service import AuditService
        AuditService.log_action(
            company=voucher.company,
            user=voucher.created_by,
            action='POST',
            model_name='Voucher',
            record_id=voucher.id,
            changes={"total_amount": str(voucher.total_amount), "status": "POSTED"}
        )

        # 6. Automated Invoice PDF & Viral Claim Dispatch for Sales Invoices
        if voucher.voucher_type == 'SALES':
            from apps.accounting.services.invoice_notification_service import InvoiceNotificationService
            transaction.on_commit(lambda: InvoiceNotificationService.dispatch_invoice_on_post(voucher))
        
        return voucher


    @staticmethod
    @transaction.atomic
    def cancel_voucher(voucher: Voucher, user=None):
        if voucher.status not in ['POSTED', 'VALIDATING']:
            raise ValidationError(f"Only posted or validating vouchers can be cancelled (current status: {voucher.status}).")
            
        # 1. Revert Stock
        if voucher.voucher_type in ['SALES', 'PURCHASE']:
            from apps.inventory.services.stock_service import StockService
            StockService.revert_voucher_stock(voucher)

        # 2. Revert Payment Allocations
        from apps.accounting.models import PaymentAllocation
        from django.db.models import Q
        PaymentAllocation.objects.filter(
            Q(payment_voucher=voucher) | Q(invoice_voucher=voucher)
        ).delete()
            
        # 3. Revert Accounting Ledgers with row-level locks
        entries = list(voucher.ledger_entries.select_related('ledger').all())
        ledger_ids = [entry.ledger_id for entry in entries]
        if voucher.party_ledger_id:
            ledger_ids.append(voucher.party_ledger_id)

        locked_ledgers = {
            l.id: l for l in Ledger.objects.select_for_update().filter(id__in=set(ledger_ids))
        }

        for entry in entries:
            ledger = locked_ledgers.get(entry.ledger_id)
            if not ledger:
                continue
            current_bal = ledger.current_balance if ledger.current_balance is not None else Decimal('0.00')
            if ledger.normal_balance == 'DEBIT':
                ledger.current_balance = current_bal - entry.debit_amount + entry.credit_amount
            else:
                ledger.current_balance = current_bal - entry.credit_amount + entry.debit_amount
            ledger.save(update_fields=['current_balance'])
            
        voucher.status = 'CANCELLED'
        voucher.save(update_fields=['status'])
        
        # 3. Log Audit Trail
        from apps.audit.services.audit_service import AuditService
        AuditService.log_action(
            company=voucher.company,
            user=user or voucher.created_by,
            action='CANCEL',
            model_name='Voucher',
            record_id=voucher.id,
            changes={"status": "CANCELLED"}
        )
        
        # Ensure single-source-of-truth accuracy for all affected ledgers
        for ledger in locked_ledgers.values():
            VoucherService.recalculate_ledger_balance(ledger)

        return voucher

    @staticmethod
    @transaction.atomic
    def delete_voucher(voucher: Voucher, user=None, reason="User Deletion"):
        """
        Permanently deletes a voucher and all associated ledger entries and line items.
        Stores full snapshot in AuditLog for audit trail compliance.
        Reverts inventory stock if the voucher was posted.
        Deletes payment allocations.
        Resets voucher sequence counter if the latest voucher was deleted (Tally behavior).
        Recalculates ledger balances for all affected ledgers.
        Emits SyncEvent.
        """
        from apps.audit.services.audit_service import AuditService
        from apps.inventory.services.stock_service import StockService
        from apps.accounting.models import PaymentAllocation, SyncEvent
        from apps.accounting.services.sequence_service import InvoiceSequenceService
        from apps.inventory.models import Product
        from django.db.models import Q

        company = voucher.company
        financial_year = voucher.financial_year
        voucher_type = voucher.voucher_type
        voucher_id = voucher.id
        voucher_num = voucher.voucher_number

        # 1. Take full snapshot for AuditLog
        items_snapshot = [
            {
                "product_id": str(itm.product_id) if itm.product_id else None,
                "product_name": itm.product.name if itm.product else (itm.description or ""),
                "quantity": str(itm.quantity),
                "rate": str(itm.rate),
                "discount_percent": str(itm.discount_percent),
                "taxable_amount": str(itm.taxable_amount),
                "gst_rate": str(itm.gst_rate),
                "total_amount": str(itm.total_amount),
            }
            for itm in voucher.items.select_related('product').all()
        ]
        entries_snapshot = [
            {
                "ledger_id": str(ent.ledger_id),
                "ledger_name": ent.ledger.name if ent.ledger else None,
                "debit_amount": str(ent.debit_amount),
                "credit_amount": str(ent.credit_amount),
                "narration": ent.narration,
            }
            for ent in voucher.ledger_entries.select_related('ledger').all()
        ]
        snapshot = {
            "voucher_id": str(voucher.id),
            "voucher_number": voucher.voucher_number,
            "voucher_type": voucher.voucher_type,
            "voucher_date": str(voucher.voucher_date),
            "status": voucher.status,
            "total_amount": str(voucher.total_amount),
            "party_ledger_id": str(voucher.party_ledger_id) if voucher.party_ledger_id else None,
            "party_ledger_name": voucher.party_ledger.name if voucher.party_ledger else None,
            "narration": voucher.narration,
            "buyer_name": voucher.buyer_name,
            "buyer_gstin": voucher.buyer_gstin,
            "reason": reason,
            "items": items_snapshot,
            "ledger_entries": entries_snapshot,
        }

        # 2. Log full trail to AuditLog
        AuditService.log_action(
            company=company,
            user=user or voucher.created_by,
            action='DELETE',
            model_name='Voucher',
            record_id=voucher_id,
            changes=snapshot
        )

        # 3. Track affected ledgers and products
        affected_ledger_ids = set(voucher.ledger_entries.values_list('ledger_id', flat=True))
        if voucher.party_ledger_id:
            affected_ledger_ids.add(voucher.party_ledger_id)
        product_ids = list(voucher.items.values_list('product_id', flat=True))

        # 4. Revert stock if posted or validating
        if voucher.status in ['POSTED', 'VALIDATING']:
            if voucher.voucher_type in ['SALES', 'PURCHASE']:
                StockService.revert_voucher_stock(voucher)
            elif voucher.voucher_type == 'CREDIT_NOTE':
                for itm in voucher.items.all():
                    if itm.product:
                        itm.product.stock_quantity = max(Decimal('0.00'), itm.product.stock_quantity - itm.quantity)
                        itm.product.save(update_fields=['stock_quantity'])
            elif voucher.voucher_type == 'DEBIT_NOTE':
                for itm in voucher.items.all():
                    if itm.product:
                        itm.product.stock_quantity = itm.product.stock_quantity + itm.quantity
                        itm.product.save(update_fields=['stock_quantity'])

        # 5. Delete payment allocations
        PaymentAllocation.objects.filter(
            Q(payment_voucher=voucher) | Q(invoice_voucher=voucher)
        ).delete()

        # 6. Unlink any self-referencing reversal voucher relationships
        if voucher.reversal_voucher_id:
            rev_v = voucher.reversal_voucher
            voucher.reversal_voucher = None
            voucher.save(update_fields=['reversal_voucher'])
            if rev_v:
                rev_v.items.all().delete()
                rev_v.ledger_entries.all().delete()
                rev_v.delete()
        Voucher.objects.filter(reversal_voucher=voucher).update(reversal_voucher=None)

        # 7. Delete items and ledger entries
        voucher.items.all().delete()
        voucher.ledger_entries.all().delete()

        # 8. Delete the voucher
        voucher.delete()

        # 9. Clean up empty ad-hoc products
        for pid in set(product_ids):
            try:
                prod = Product.objects.filter(id=pid).first()
                if (prod and 
                    prod.category is None and 
                    prod.stock_quantity <= 0 and 
                    not prod.voucher_items.exists() and 
                    not prod.entries.exists()):
                    prod.delete()
            except Exception:
                pass

        # 10. Resync voucher sequence counter (resets to highest remaining voucher)
        if financial_year:
            InvoiceSequenceService.resync_sequence(
                company=company,
                financial_year=financial_year,
                voucher_type=voucher_type,
                force=True
            )

        # 11. Recalculate affected ledger balances
        for lid in affected_ledger_ids:
            l = Ledger.objects.filter(id=lid).first()
            if l:
                VoucherService.recalculate_ledger_balance(l)

        # 12. Emit SyncEvent for offline sync
        SyncEvent.objects.create(
            company=company,
            entity_type='voucher',
            entity_id=str(voucher_id),
            operation='DELETE'
        )

        return voucher_num

    @staticmethod
    @transaction.atomic
    def create_reversal_voucher(voucher: Voucher, user=None, reason="Correction Reversal", revert_stock=True, revert_allocations=True) -> Voucher:
        """
        P0-4 & P0-5: Strictly immutable posted transaction reversal.
        Creates an explicit balancing reversal Journal voucher that posts opposite debits & credits,
        reverts stock movements, and transitions original voucher to 'REVERSED'.
        Original voucher, items, and ledger entries remain permanently intact and auditable.
        """
        if voucher.status not in ['POSTED', 'VALIDATING']:
            raise ValidationError(f"Only POSTED transactions can be reversed (current status: {voucher.status}).")

        from apps.accounting.models import Voucher, LedgerEntry
        from apps.inventory.services.stock_service import StockService
        from apps.audit.services.audit_service import AuditService

        # 1. Revert Stock atomically (if requested)
        if revert_stock and voucher.voucher_type in ['SALES', 'PURCHASE']:
            StockService.revert_voucher_stock(voucher)

        # 2. Revert Payment Allocations (if requested)
        if revert_allocations:
            from apps.accounting.models import PaymentAllocation
            from django.db.models import Q
            PaymentAllocation.objects.filter(
                Q(payment_voucher=voucher) | Q(invoice_voucher=voucher)
            ).delete()

        # 3. Create explicit Reversal Voucher
        rev_num = f"REV-{voucher.voucher_number}"
        if Voucher.objects.filter(company=voucher.company, voucher_number=rev_num).exists():
            rev_num = f"REV-{voucher.voucher_number}-{int(timezone.now().timestamp())}"

        rev_voucher = Voucher.objects.create(
            company=voucher.company,
            financial_year=voucher.financial_year,
            voucher_type='JOURNAL',
            voucher_number=rev_num,
            voucher_date=timezone.now().date(),
            reference_number=voucher.voucher_number,
            party_ledger=voucher.party_ledger,
            status='POSTED',
            total_amount=voucher.total_amount,
            created_by=user or voucher.created_by,
            narration=f"Reversal of {voucher.voucher_type} #{voucher.voucher_number}. Reason: {reason}",
            reversal_voucher=voucher
        )

        # 4. Generate inverse ledger entries (Credit what was debited, Debit what was credited)
        entries = list(voucher.ledger_entries.select_related('ledger').all())
        ledger_ids = [entry.ledger_id for entry in entries]
        locked_ledgers = {
            l.id: l for l in Ledger.objects.select_for_update().filter(id__in=set(ledger_ids))
        }

        for entry in entries:
            LedgerEntry.objects.create(
                voucher=rev_voucher,
                ledger_id=entry.ledger_id,
                debit_amount=entry.credit_amount,
                credit_amount=entry.debit_amount,
                narration=f"Reversal of {voucher.voucher_number}: {entry.narration or ''}"
            )

        # 5. Mark original voucher as REVERSED and link
        voucher.status = 'REVERSED'
        voucher.reversal_voucher = rev_voucher
        voucher.save(update_fields=['status', 'reversal_voucher'])

        # 6. Recalculate single-source-of-truth balances
        for ledger in locked_ledgers.values():
            VoucherService.recalculate_ledger_balance(ledger)

        # 7. Audit log
        AuditService.log_action(
            company=voucher.company,
            user=user or voucher.created_by,
            action='REVERSE',
            model_name='Voucher',
            record_id=voucher.id,
            changes={"status": "REVERSED", "reversal_voucher_id": str(rev_voucher.id)}
        )

        return rev_voucher

    @staticmethod
    @transaction.atomic
    def recalculate_ledger_balance(ledger) -> Decimal:
        """
        Recalculates ledger.current_balance strictly from the single source of truth:
        Opening Balance + Sum of all posted LedgerEntry Debits/Credits.
        Acquires row-level database lock.
        """
        if not ledger:
            return Decimal('0.00')

        from apps.accounting.models import LedgerEntry
        from django.db.models import Sum

        locked_ledger = Ledger.objects.select_for_update().get(id=ledger.id)
        
        from apps.accounting.services.effective_voucher_service import EffectiveVoucherService

        # Check if double-entry opening vouchers exist for this ledger
        has_opening_entries = LedgerEntry.objects.filter(
            ledger=locked_ledger,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
            voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
        ).exists()

        op_balance = Decimal('0.00') if has_opening_entries else Decimal(str(locked_ledger.opening_balance or '0.00'))
        
        # Calculate opening debit and credit contribution
        if locked_ledger.opening_balance_type == 'CREDIT':
            op_dr = Decimal('0.00')
            op_cr = op_balance
        else:
            op_dr = op_balance
            op_cr = Decimal('0.00')

        # POSTED vouchers and explicit REVERSED/CORRECTED balancing history affect accounting balances
        totals = LedgerEntry.objects.filter(
            ledger=locked_ledger,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
        ).aggregate(
            total_dr=Sum('debit_amount'),
            total_cr=Sum('credit_amount')
        )

        total_dr = op_dr + Decimal(str(totals['total_dr'] or '0.00'))
        total_cr = op_cr + Decimal(str(totals['total_cr'] or '0.00'))

        if locked_ledger.normal_balance == 'CREDIT':
            locked_ledger.current_balance = total_cr - total_dr
        else:
            locked_ledger.current_balance = total_dr - total_cr

        locked_ledger.save(update_fields=['current_balance'])
        ledger.current_balance = locked_ledger.current_balance
        return locked_ledger.current_balance
