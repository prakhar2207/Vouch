from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from apps.accounting.models import Voucher, LedgerEntry

class VoucherService:
    @staticmethod
    @transaction.atomic
    def post_voucher(voucher: Voucher):
        if voucher.status == 'POSTED':
            raise ValidationError("Voucher is already posted.")
        if voucher.status == 'CANCELLED':
            raise ValidationError("Cannot post a cancelled voucher.")
            
        voucher.status = 'VALIDATING'
        voucher.save(update_fields=['status'])
        
        # 1. Process Stock first (if applicable)
        from apps.inventory.services.stock_service import StockService
        from apps.inventory.models import Warehouse
        
        if voucher.voucher_type in ['SALES', 'PURCHASE']:
            # For simplicity, pick the first active warehouse or auto-create Main Warehouse
            warehouse = Warehouse.objects.filter(company=voucher.company, is_active=True).first()
            if not warehouse:
                warehouse = Warehouse.objects.create(
                    company=voucher.company,
                    name="Main Warehouse",
                    is_active=True
                )
            StockService.process_voucher_stock(voucher, warehouse)
        
        # 2. Process Accounting Ledger Entries
        entries = voucher.ledger_entries.all()
        
        total_debit = sum(entry.debit_amount for entry in entries)
        total_credit = sum(entry.credit_amount for entry in entries)
        
        if total_debit != total_credit:
            voucher.status = 'DRAFT'
            voucher.save(update_fields=['status'])
            raise ValidationError(f"Voucher does not balance. Dr: {total_debit}, Cr: {total_credit}")
            
        # Update ledger balances
        for entry in entries:
            if entry.debit_amount > 0 and entry.credit_amount > 0:
                raise ValidationError("Ledger entry cannot contain both debit and credit.")
                
            ledger = entry.ledger
            
            # Simplified strict balance logic:
            # We treat positive current_balance as Debit if opening_balance_type was Debit (standard Asset/Expense)
            # Or we can just calculate raw math. Let's do raw math:
            if ledger.opening_balance_type == 'DEBIT':
                ledger.current_balance = ledger.current_balance + entry.debit_amount - entry.credit_amount
            else:
                ledger.current_balance = ledger.current_balance + entry.credit_amount - entry.debit_amount
                
            ledger.save(update_fields=['current_balance'])
            
        voucher.status = 'POSTED'
        voucher.total_amount = total_debit # Store the total volume of the voucher
        voucher.save(update_fields=['status', 'total_amount'])
        
        # 3. Log Audit Trail
        from apps.audit.services.audit_service import AuditService
        AuditService.log_action(
            company=voucher.company,
            user=voucher.created_by,
            action='POST',
            model_name='Voucher',
            record_id=voucher.id,
            changes={"total_amount": str(total_debit), "status": "POSTED"}
        )
        
        return voucher

    @staticmethod
    @transaction.atomic
    def cancel_voucher(voucher: Voucher):
        if voucher.status != 'POSTED':
            raise ValidationError("Only posted vouchers can be cancelled.")
            
        # Revert Stock
        if voucher.voucher_type in ['SALES', 'PURCHASE']:
            from apps.inventory.services.stock_service import StockService
            StockService.revert_voucher_stock(voucher)
            
        # Revert Accounting Ledgers
        entries = voucher.ledger_entries.all()
        for entry in entries:
            ledger = entry.ledger
            if ledger.opening_balance_type == 'DEBIT':
                ledger.current_balance = ledger.current_balance - entry.debit_amount + entry.credit_amount
            else:
                ledger.current_balance = ledger.current_balance - entry.credit_amount + entry.debit_amount
            ledger.save(update_fields=['current_balance'])
            
        voucher.status = 'CANCELLED'
        voucher.save(update_fields=['status'])
        
        # Log Audit Trail
        from apps.audit.services.audit_service import AuditService
        AuditService.log_action(
            company=voucher.company,
            user=voucher.created_by,
            action='CANCEL',
            model_name='Voucher',
            record_id=voucher.id,
            changes={"status": "CANCELLED"}
        )
        
        return voucher
