from decimal import Decimal
from django.db.models import Sum, Count, Avg, F
from apps.inventory.models import Product, InventoryEntry
from apps.accounting.models import VoucherItem, Voucher

class ItemAnalyticsService:
    @staticmethod
    def get_product_invoice_history(product_id, company):
        product = Product.objects.filter(id=product_id, company=company).select_related('category').first()
        if not product:
            return None

        # 1. Fetch Purchase Vouchers
        purchase_items = VoucherItem.objects.filter(
            product=product,
            voucher__company=company,
            voucher__voucher_type='PURCHASE',
            voucher__status='POSTED'
        ).select_related('voucher', 'voucher__party_ledger').order_by('-voucher__voucher_date', '-voucher__created_at')

        purchases_list = []
        total_purchased_qty = Decimal('0.00')
        total_purchased_val = Decimal('0.00')

        for item in purchase_items:
            v = item.voucher
            purchases_list.append({
                "voucher_id": str(v.id),
                "voucher_number": v.voucher_number or "N/A",
                "date": v.voucher_date.strftime('%Y-%m-%d') if v.voucher_date else "",
                "party_name": v.party_ledger.name if v.party_ledger else "Direct / Cash",
                "party_id": str(v.party_ledger.id) if v.party_ledger else None,
                "quantity": float(item.quantity),
                "unit": product.unit,
                "rate": float(item.rate),
                "discount_percent": float(item.discount_percent),
                "taxable_amount": float(item.taxable_amount),
                "gst_rate": float(item.gst_rate),
                "total_amount": float(item.total_amount)
            })
            total_purchased_qty += item.quantity
            total_purchased_val += item.total_amount

        # 2. Fetch Sales Invoices
        sales_items = VoucherItem.objects.filter(
            product=product,
            voucher__company=company,
            voucher__voucher_type='SALES',
            voucher__status='POSTED'
        ).select_related('voucher', 'voucher__party_ledger').order_by('-voucher__voucher_date', '-voucher__created_at')

        sales_list = []
        total_sold_qty = Decimal('0.00')
        total_sold_val = Decimal('0.00')

        for item in sales_items:
            v = item.voucher
            sales_list.append({
                "voucher_id": str(v.id),
                "voucher_number": v.voucher_number or "N/A",
                "date": v.voucher_date.strftime('%Y-%m-%d') if v.voucher_date else "",
                "party_name": v.party_ledger.name if v.party_ledger else "Direct / Cash",
                "party_id": str(v.party_ledger.id) if v.party_ledger else None,
                "quantity": float(item.quantity),
                "unit": product.unit,
                "rate": float(item.rate),
                "discount_percent": float(item.discount_percent),
                "taxable_amount": float(item.taxable_amount),
                "gst_rate": float(item.gst_rate),
                "total_amount": float(item.total_amount)
            })
            total_sold_qty += item.quantity
            total_sold_val += item.total_amount

        # 3. Aggregated Metrics
        avg_purchase_price = round(float(total_purchased_val / total_purchased_qty), 2) if total_purchased_qty > 0 else float(product.purchase_price)
        avg_selling_price = round(float(total_sold_val / total_sold_qty), 2) if total_sold_qty > 0 else float(product.selling_price)
        turnover_pct = round(float(total_sold_qty / total_purchased_qty * 100), 1) if total_purchased_qty > 0 else 0.0

        return {
            "product": {
                "id": str(product.id),
                "name": product.name,
                "brand": product.brand or "",
                "sku": product.sku,
                "category": product.category.name if product.category else "Unassigned",
                "category_id": str(product.category.id) if product.category else None,
                "unit": product.unit,
                "hsn_code": product.hsn_code or (product.category.hsn_code if product.category else ""),
                "current_stock": float(product.stock_quantity),
                "purchase_price": float(product.purchase_price),
                "purchase_price_from_invoice": getattr(product, 'purchase_price_from_invoice', False),
                "selling_price": float(product.selling_price),
            },
            "metrics": {
                "total_purchased_qty": float(total_purchased_qty),
                "total_purchased_val": float(total_purchased_val),
                "purchase_bills_count": len(purchases_list),
                "avg_purchase_price": avg_purchase_price,
                "last_purchase_date": purchases_list[0]["date"] if purchases_list else None,
                "last_supplier": purchases_list[0]["party_name"] if purchases_list else None,
                "total_sold_qty": float(total_sold_qty),
                "total_sold_val": float(total_sold_val),
                "sales_invoices_count": len(sales_list),
                "avg_selling_price": avg_selling_price,
                "last_sale_date": sales_list[0]["date"] if sales_list else None,
                "last_customer": sales_list[0]["party_name"] if sales_list else None,
                "turnover_pct": turnover_pct
            },
            "purchases": purchases_list,
            "sales": sales_list
        }

    @staticmethod
    def get_top_moving_items(company, category_id=None, limit=10):
        # 1. Top Purchased Items
        purchases_qs = VoucherItem.objects.filter(
            voucher__company=company,
            voucher__voucher_type='PURCHASE',
            voucher__status='POSTED'
        )
        if category_id:
            purchases_qs = purchases_qs.filter(product__category_id=category_id)

        top_purchased_raw = purchases_qs.values(
            'product_id',
            'product__name',
            'product__brand',
            'product__sku',
            'product__unit',
            'product__category__name',
            'product__stock_quantity'
        ).annotate(
            total_qty=Sum('quantity'),
            bills_count=Count('voucher_id', distinct=True),
            total_spend=Sum('total_amount'),
            avg_rate=Avg('rate')
        ).order_by('-bills_count', '-total_qty')[:limit]

        top_purchased = [
            {
                "product_id": str(r['product_id']),
                "name": r['product__name'],
                "brand": r['product__brand'] or "",
                "sku": r['product__sku'],
                "unit": r['product__unit'],
                "category_name": r['product__category__name'] or "General",
                "current_stock": float(r['product__stock_quantity']),
                "total_qty": float(r['total_qty']),
                "bills_count": r['bills_count'],
                "total_spend": float(r['total_spend'] or 0),
                "avg_rate": round(float(r['avg_rate'] or 0), 2)
            }
            for r in top_purchased_raw
        ]

        # 2. Top Sold Items
        sales_qs = VoucherItem.objects.filter(
            voucher__company=company,
            voucher__voucher_type='SALES',
            voucher__status='POSTED'
        )
        if category_id:
            sales_qs = sales_qs.filter(product__category_id=category_id)

        top_sold_raw = sales_qs.values(
            'product_id',
            'product__name',
            'product__brand',
            'product__sku',
            'product__unit',
            'product__category__name',
            'product__stock_quantity'
        ).annotate(
            total_qty=Sum('quantity'),
            invoices_count=Count('voucher_id', distinct=True),
            total_revenue=Sum('total_amount'),
            avg_rate=Avg('rate')
        ).order_by('-invoices_count', '-total_qty')[:limit]

        top_sold = [
            {
                "product_id": str(r['product_id']),
                "name": r['product__name'],
                "brand": r['product__brand'] or "",
                "sku": r['product__sku'],
                "unit": r['product__unit'],
                "category_name": r['product__category__name'] or "General",
                "current_stock": float(r['product__stock_quantity']),
                "total_qty": float(r['total_qty']),
                "invoices_count": r['invoices_count'],
                "total_revenue": float(r['total_revenue'] or 0),
                "avg_rate": round(float(r['avg_rate'] or 0), 2)
            }
            for r in top_sold_raw
        ]

        return {
            "top_purchased": top_purchased,
            "top_sold": top_sold
        }
