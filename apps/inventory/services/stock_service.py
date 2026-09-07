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
        Guarantees stock integrity by checking InventoryEntry records or falling back
        directly to VoucherItem lines.
        """
        company_settings = getattr(voucher.company, 'settings', None)
        allow_negative = company_settings.allow_negative_stock if company_settings else False

        entries = InventoryEntry.objects.filter(voucher_id=voucher.id)
        if entries.exists():
            for entry in entries:
                product = entry.product
                if not product:
                    continue
                # Reverse the movement:
                # If OUT (Sales), restore stock by adding back quantity
                # If IN (Purchase), deduct stock
                if entry.movement_type == 'OUT':
                    product.stock_quantity += entry.quantity
                else:
                    product.stock_quantity -= entry.quantity
                    
                if product.stock_quantity < 0 and not allow_negative:
                    raise ValidationError(f"Cannot cancel voucher. {product.name} stock would fall below zero ({product.stock_quantity}).")
                    
                product.save(update_fields=['stock_quantity'])
                
            # Delete the inventory ledger entries
            entries.delete()
        else:
            # Fallback directly to voucher items if InventoryEntry was not explicitly generated
            for item in voucher.items.select_related('product').all():
                product = item.product
                if not product:
                    continue
                if voucher.voucher_type == 'SALES':
                    product.stock_quantity += item.quantity
                elif voucher.voucher_type == 'PURCHASE':
                    product.stock_quantity -= item.quantity
                    if product.stock_quantity < 0 and not allow_negative:
                        raise ValidationError(f"Cannot cancel voucher. {product.name} stock would fall below zero ({product.stock_quantity}).")
                product.save(update_fields=['stock_quantity'])
