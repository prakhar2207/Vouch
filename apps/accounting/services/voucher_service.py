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
    def post_voucher(voucher: Voucher):
        if voucher.status == 'POSTED':
            raise ValidationError("Voucher is already posted.")
        if voucher.status == 'CANCELLED':
            raise ValidationError("Cannot post a cancelled voucher.")
            
        voucher.status = 'VALIDATING'
        voucher.save(update_fields=['status'])
        
        # 1. Process Stock & calculate COGS
        from apps.inventory.services.stock_service import StockService
        
        if voucher.voucher_type == 'SALES':
            total_cogs = StockService.process_voucher_stock(voucher)
            # 2. Record perpetual inventory journal (Dr COGS / Cr Inventory)
            if total_cogs > Decimal('0.00'):
                cogs_ledger, inv_ledger = VoucherService._get_or_create_cogs_and_inventory_ledgers(voucher.company)
                # Check if COGS lines already exist
                if not voucher.ledger_entries.filter(ledger=cogs_ledger).exists():
                    LedgerEntry.objects.create(
                        voucher=voucher,
                        company=voucher.company,
                        ledger=cogs_ledger,
                        debit_amount=total_cogs,
                        credit_amount=Decimal('0.00'),
                        narration=f"COGS for {voucher.voucher_number}"
                    )
                    LedgerEntry.objects.create(
                        voucher=voucher,
                        company=voucher.company,
                        ledger=inv_ledger,
                        debit_amount=Decimal('0.00'),
                        credit_amount=total_cogs,
                        narration=f"Inventory reduction for {voucher.voucher_number}"
                    )
        elif voucher.voucher_type == 'PURCHASE':
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
            
            if ledger.opening_balance_type == 'DEBIT':
                ledger.current_balance = ledger.current_balance + entry.debit_amount - entry.credit_amount
            else:
                ledger.current_balance = ledger.current_balance + entry.credit_amount - entry.debit_amount
                
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
            if ledger.opening_balance_type == 'DEBIT':
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
    def create_reversal_voucher(voucher: Voucher, user=None, reason="Correction Reversal") -> Voucher:
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

        # 1. Revert Stock atomically
        if voucher.voucher_type in ['SALES', 'PURCHASE']:
            StockService.revert_voucher_stock(voucher)

        # 2. Revert Payment Allocations
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
        
        # Check if double-entry opening vouchers exist for this ledger
        has_opening_entries = LedgerEntry.objects.filter(
            ledger=locked_ledger,
            voucher__status='POSTED',
            voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
        ).exists()

        op_balance = Decimal('0.00') if has_opening_entries else Decimal(str(locked_ledger.opening_balance or '0.00'))
        
        # Only POSTED vouchers affect accounting balances
        totals = LedgerEntry.objects.filter(
            ledger=locked_ledger,
            voucher__status='POSTED'
        ).aggregate(
            total_dr=Sum('debit_amount'),
            total_cr=Sum('credit_amount')
        )

        total_dr = Decimal(str(totals['total_dr'] or '0.00'))
        total_cr = Decimal(str(totals['total_cr'] or '0.00'))

        if locked_ledger.opening_balance_type == 'DEBIT':
            locked_ledger.current_balance = op_balance + total_dr - total_cr
        else:
            locked_ledger.current_balance = op_balance + total_cr - total_dr

        locked_ledger.save(update_fields=['current_balance'])
        ledger.current_balance = locked_ledger.current_balance
        return locked_ledger.current_balance
