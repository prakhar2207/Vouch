from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from apps.inventory.models import Product, Warehouse, InventoryEntry
from apps.accounting.models import Voucher, VoucherItem

class StockService:
    @staticmethod
    @transaction.atomic
    def process_voucher_stock(voucher: Voucher, warehouse: Warehouse):
        """
        Process the stock impact of a posted voucher.
        Sales -> Stock OUT
        Purchase -> Stock IN
        """
        if voucher.status != 'VALIDATING':
            raise ValidationError("Stock can only be processed during voucher validation phase.")
            
        if voucher.voucher_type not in ['SALES', 'PURCHASE']:
            return # No stock impact for other vouchers
            
        items = voucher.items.all()
        movement_type = 'OUT' if voucher.voucher_type == 'SALES' else 'IN'
        
        for item in items:
            product = item.product
            qty = item.quantity
            
            # Precise stock validation for SALES
            if movement_type == 'OUT':
                if product.stock_quantity < qty:
                    raise ValidationError(f"Insufficient stock for {product.name}. Available: {product.stock_quantity}, Required: {qty}")
                product.stock_quantity -= qty
            else:
                product.stock_quantity += qty
                
            product.save(update_fields=['stock_quantity'])
            
            # Record explicit inventory ledger entry
            InventoryEntry.objects.create(
                company=voucher.company,
                product=product,
                warehouse=warehouse,
                voucher_id=voucher.id,
                movement_type=movement_type,
                quantity=qty,
                rate=item.rate,
                total_value=item.total_amount
            )
            
    @staticmethod
    @transaction.atomic
    def revert_voucher_stock(voucher: Voucher):
        """
        Reverse stock impact if a voucher is cancelled.
        """
        entries = InventoryEntry.objects.filter(voucher_id=voucher.id)
        for entry in entries:
            product = entry.product
            # Reverse the movement
            if entry.movement_type == 'OUT':
                product.stock_quantity += entry.quantity
            else:
                product.stock_quantity -= entry.quantity
                
            # Prevent reversing purchase if stock has already been sold
            if product.stock_quantity < 0:
                raise ValidationError(f"Cannot cancel voucher. {product.name} stock would fall below zero.")
                
            product.save(update_fields=['stock_quantity'])
            
        # Delete the inventory ledger entries
        entries.delete()
