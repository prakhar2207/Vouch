from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from apps.inventory.models import Product, Warehouse, InventoryEntry
from apps.accounting.models import Voucher, VoucherItem

class StockService:
    @classmethod
    @transaction.atomic
    def process_voucher_stock(cls, voucher: Voucher, default_warehouse: Warehouse = None) -> Decimal:
        """
        Processes stock changes atomically for a posted voucher with row-level locking.
        Sales -> Stock OUT
        Purchase -> Stock IN
        Returns total COGS value for the voucher (Decimal).
        """
        if voucher.status != 'VALIDATING':
            raise ValidationError("Stock can only be processed during voucher validation phase.")
            
        if voucher.voucher_type not in ['SALES', 'PURCHASE']:
            return Decimal('0.00')

        items = list(voucher.items.select_related('product', 'warehouse').all())
        movement_type = 'OUT' if voucher.voucher_type == 'SALES' else 'IN'
        total_cogs = Decimal('0.00')
        
        company_settings = getattr(voucher.company, 'settings', None)
        allow_negative = getattr(company_settings, 'allow_negative_stock', False)

        # 1. Resolve fallback warehouse if needed
        fallback_wh = default_warehouse
        if not fallback_wh:
            fallback_wh = Warehouse.objects.filter(company=voucher.company, is_active=True).first()
            if not fallback_wh:
                fallback_wh = Warehouse.objects.create(
                    company=voucher.company,
                    name="Main Godown",
                    is_active=True
                )

        # 2. Lock and update each product atomically
        for item in items:
            # Acquire row lock on product to prevent concurrent stock race conditions
            product = Product.objects.select_for_update().get(id=item.product_id, company=voucher.company)
            qty = Decimal(str(item.quantity))
            
            line_wh = item.warehouse or fallback_wh
            if line_wh.company_id != voucher.company_id:
                raise ValidationError(f"Warehouse '{line_wh.name}' does not belong to company '{voucher.company.name}'.")

            if movement_type == 'OUT':
                if product.stock_quantity < qty and not allow_negative:
                    raise ValidationError(
                        f"Insufficient stock for '{product.name}'. Available: {product.stock_quantity}, Required: {qty}. "
                        f"Negative stock is prohibited by company policy."
                    )
                product.stock_quantity -= qty

                # Compute mathematically sound COGS based on configured costing method
                line_cogs, unit_cost = cls.calculate_cogs_valuation(product, qty, exclude_voucher_id=voucher.id)
                total_cogs += line_cogs
                entry_rate = unit_cost
                entry_total = line_cogs
            else:
                product.stock_quantity += qty
                # P0-9: Separate Recoverable GST from Inventory Cost
                # Recoverable GST (Input CGST, SGST, IGST) is recorded in balance sheet tax asset ledgers.
                # Only the taxable value (net of item discounts) represents inventory acquisition cost.
                taxable_amt = Decimal(str(getattr(item, 'taxable_amount', 0) or 0))
                if taxable_amt <= Decimal('0.00'):
                    rate_val = Decimal(str(item.rate))
                    disc_pct = Decimal(str(getattr(item, 'discount_percent', 0) or 0))
                    taxable_amt = (qty * rate_val * (Decimal('100') - disc_pct) / Decimal('100')).quantize(Decimal('0.01'))
                
                entry_total = taxable_amt
                entry_rate = (entry_total / qty).quantize(Decimal('0.01')) if qty > Decimal('0.00') else Decimal('0.00')
                
            product.save(update_fields=['stock_quantity', 'updated_at'])
            
            # Record immutable inventory ledger entry
            InventoryEntry.objects.create(
                company=voucher.company,
                product=product,
                warehouse=line_wh,
                voucher_id=voucher.id,
                movement_type=movement_type,
                quantity=qty,
                rate=entry_rate,
                total_value=entry_total
            )

        return total_cogs

    @classmethod
    def calculate_cogs_valuation(cls, product: Product, qty_to_sell: Decimal, exclude_voucher_id=None, method=None) -> tuple[Decimal, Decimal]:
        """
        Calculates the total cost value and effective unit rate for a sale of qty_to_sell
        based on the product's configured costing method:
        - AVG_COST / MOVING_AVG (Default): True Moving Weighted Average computed strictly on remaining unconsumed inventory layers
        - FIFO: Consumes unexhausted historical inward lots in chronological order
        - LIFO: Consumes unexhausted historical inward lots in reverse chronological order
        - STD_COST: Fixed purchase_price
        Returns (total_cost, unit_cost_rate)
        """
        qty_needed = Decimal(str(qty_to_sell))
        if qty_needed <= Decimal('0.00'):
            return Decimal('0.00'), Decimal('0.00')

        method = (method or getattr(product, 'costing_method', 'AVG_COST') or 'AVG_COST').upper()
        fallback_rate = product.purchase_price if (product.purchase_price and product.purchase_price > Decimal('0.00')) else Decimal('0.00')

        if method == 'STD_COST':
            total = (fallback_rate * qty_needed).quantize(Decimal('0.01'))
            return total, fallback_rate

        in_qs = InventoryEntry.objects.filter(product=product, movement_type='IN').order_by('created_at')
        if not in_qs.exists():
            total = (fallback_rate * qty_needed).quantize(Decimal('0.01'))
            return total, fallback_rate

        # Determine how much quantity has already been consumed by prior sales
        out_qs = InventoryEntry.objects.filter(product=product, movement_type='OUT')
        if exclude_voucher_id:
            out_qs = out_qs.exclude(voucher_id=exclude_voucher_id)
        already_consumed = sum(e.quantity for e in out_qs)

        in_entries = list(in_qs)

        # Deduct already_consumed from chronological inward entries to find actual remaining inventory layers
        rem_consumed = already_consumed
        available_layers = []
        for entry in in_entries:
            if rem_consumed >= entry.quantity:
                rem_consumed -= entry.quantity
            else:
                avail_qty = entry.quantity - rem_consumed
                rem_consumed = Decimal('0.00')
                available_layers.append({
                    'rate': entry.rate,
                    'qty': avail_qty,
                    'total_value': (avail_qty * entry.rate).quantize(Decimal('0.01'))
                })

        # P0-8: Moving Weighted Average on remaining unexhausted inventory
        if method in ['AVG_COST', 'MOVING_AVG', 'WEIGHTED_AVG']:
            rem_stock_qty = sum(l['qty'] for l in available_layers)
            rem_stock_val = sum(l['total_value'] for l in available_layers)

            if rem_stock_qty > Decimal('0.00'):
                avg_rate = (rem_stock_val / rem_stock_qty).quantize(Decimal('0.01'))
                # If selling within available stock, value at moving average
                take_qty = min(qty_needed, rem_stock_qty)
                total = (avg_rate * take_qty).quantize(Decimal('0.01'))
                # Remainder (if negative stock) priced at fallback
                over_qty = qty_needed - take_qty
                if over_qty > Decimal('0.00'):
                    total += (over_qty * fallback_rate).quantize(Decimal('0.01'))
                effective_rate = (total / qty_needed).quantize(Decimal('0.01'))
                return total, effective_rate

            total = (fallback_rate * qty_needed).quantize(Decimal('0.01'))
            return total, fallback_rate

        # FIFO / LIFO layer-by-layer consumption
        if method == 'LIFO':
            available_layers.reverse()

        total_cost = Decimal('0.00')
        still_needed = qty_needed
        for layer in available_layers:
            if still_needed <= Decimal('0.00'):
                break
            take_qty = min(still_needed, layer['qty'])
            total_cost += take_qty * layer['rate']
            still_needed -= take_qty

        # If more quantity was sold than available inward layers (negative stock), price remainder at fallback_rate
        if still_needed > Decimal('0.00'):
            total_cost += still_needed * fallback_rate

        total_cost = total_cost.quantize(Decimal('0.01'))
        unit_rate = (total_cost / qty_needed).quantize(Decimal('0.01')) if qty_needed > Decimal('0.00') else Decimal('0.00')
        return total_cost, unit_rate

    @classmethod
    def calculate_cost_rate(cls, product: Product) -> Decimal:
        """
        Compatibility helper for unit rate estimation.
        """
        _, rate = cls.calculate_cogs_valuation(product, Decimal('1.00'))
        return rate

    @staticmethod
    @transaction.atomic
    def revert_voucher_stock(voucher: Voucher):
        """
        Reverses stock movements atomically with row-level locking when a voucher is cancelled.
        """
        company_settings = getattr(voucher.company, 'settings', None)
        allow_negative = getattr(company_settings, 'allow_negative_stock', False)

        entries = InventoryEntry.objects.filter(voucher_id=voucher.id)
        if entries.exists():
            for entry in entries:
                # Lock product for update
                product = Product.objects.select_for_update().filter(id=entry.product_id).first()
                if not product:
                    continue
                # If OUT (Sales), restore stock by adding back quantity
                # If IN (Purchase), deduct stock
                if entry.movement_type == 'OUT':
                    product.stock_quantity += entry.quantity
                else:
                    product.stock_quantity -= entry.quantity
                    
                if product.stock_quantity < 0 and not allow_negative:
                    raise ValidationError(f"Cannot cancel voucher. {product.name} stock would fall below zero ({product.stock_quantity}).")
                    
                product.save(update_fields=['stock_quantity', 'updated_at'])
                
            entries.delete()
        else:
            for item in voucher.items.all():
                product = Product.objects.select_for_update().filter(id=item.product_id).first()
                if not product:
                    continue
                if voucher.voucher_type == 'SALES':
                    product.stock_quantity += item.quantity
                elif voucher.voucher_type == 'PURCHASE':
                    product.stock_quantity -= item.quantity
                    if product.stock_quantity < 0 and not allow_negative:
                        raise ValidationError(f"Cannot cancel voucher. {product.name} stock would fall below zero ({product.stock_quantity}).")
                product.save(update_fields=['stock_quantity', 'updated_at'])
