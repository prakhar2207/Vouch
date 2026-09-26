from decimal import Decimal
from django.db.models import Sum, Count, Avg, F, Max
from apps.inventory.models import Product, InventoryEntry, ProductCategory
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
    def get_top_moving_items(company, category_id=None, limit=10, reorder_limit=100, default_min_stock=10.0):
        # 0. Categories list
        categories = list(ProductCategory.objects.filter(company=company).values('id', 'name').order_by('name'))
        categories_data = [{"id": str(c["id"]), "name": c["name"]} for c in categories]

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

        # 3. High-Velocity Low-Stock Reorder Intelligence
        # Strictly flags items that are actively purchased/sold (sales demand >= 1 invoice and sold_qty > 0)
        # but are short or below minimum required stock (current_stock <= min_required_qty).
        # Items with no or negligible sales are treated as low priority / deadstock and omitted.
        reorder_raw = sales_qs.values(
            'product_id',
            'product__name',
            'product__brand',
            'product__sku',
            'product__unit',
            'product__category__name',
            'product__category_id',
            'product__stock_quantity',
            'product__purchase_price',
            'product__reorder_level'
        ).annotate(
            total_sold_qty=Sum('quantity'),
            invoices_count=Count('voucher_id', distinct=True)
        ).filter(total_sold_qty__gt=0, invoices_count__gte=1)

        reorder_candidates = []
        for r in reorder_raw:
            stock = float(r['product__stock_quantity'] or 0)
            custom_reorder = float(r['product__reorder_level']) if r['product__reorder_level'] is not None else 0.0

            # If the item has a custom min required quantity (> 0), use that.
            # Otherwise use default_min_stock (e.g. 10.0 or user-configured mass threshold).
            if custom_reorder > 0:
                thresh = custom_reorder
                has_custom_reorder = True
            else:
                thresh = float(default_min_stock)
                has_custom_reorder = False

            if stock <= thresh:
                sold_qty = float(r['total_sold_qty'] or 0)
                inv_cnt = r['invoices_count']
                if stock <= 0:
                    urgency = 'OUT_OF_STOCK'
                    urgency_score = 100 + inv_cnt * 10
                    urgency_label = 'Out of Stock'
                elif stock <= max(1.0, thresh * 0.3):
                    urgency = 'CRITICAL'
                    urgency_score = 60 + inv_cnt * 5 - stock * 2
                    urgency_label = 'Critical Stock'
                else:
                    urgency = 'LOW_STOCK'
                    urgency_score = 30 + inv_cnt * 2 - stock
                    urgency_label = 'Low Stock'

                avg_per_sale = sold_qty / max(1, inv_cnt)
                suggested_deficit = max(0.0, thresh - stock)
                suggested_qty = max(5, int(round(max(suggested_deficit, avg_per_sale * 2) / 5.0) * 5))
                if suggested_qty == 0:
                    suggested_qty = 5

                reorder_candidates.append({
                    'product_id': str(r['product_id']),
                    'name': r['product__name'],
                    'brand': r['product__brand'] or '',
                    'sku': r['product__sku'],
                    'unit': r['product__unit'] or 'PCS',
                    'category_name': r['product__category__name'] or 'General',
                    'category_id': str(r['product__category_id']) if r['product__category_id'] else None,
                    'current_stock': stock,
                    'reorder_level': custom_reorder,
                    'min_required_qty': thresh,
                    'has_custom_reorder': has_custom_reorder,
                    'total_sold_qty': sold_qty,
                    'invoices_count': inv_cnt,
                    'purchase_price': float(r['product__purchase_price'] or 0),
                    'suggested_qty': suggested_qty,
                    'urgency': urgency,
                    'urgency_score': urgency_score,
                    'urgency_label': urgency_label
                })

        reorder_candidates.sort(key=lambda x: -x['urgency_score'])
        top_reorder = reorder_candidates[:reorder_limit]

        # Fast batch lookup of latest purchase rates & vendors
        if top_reorder:
            cand_pids = [item['product_id'] for item in top_reorder]
            p_items = VoucherItem.objects.filter(
                product_id__in=cand_pids,
                voucher__company=company,
                voucher__voucher_type='PURCHASE',
                voucher__status='POSTED'
            ).values('product_id', 'rate', 'voucher__party_ledger__name', 'voucher__voucher_date').order_by('-voucher__voucher_date')

            last_purchases = {}
            for pi in p_items:
                pid = str(pi['product_id'])
                if pid not in last_purchases:
                    last_purchases[pid] = {
                        'rate': float(pi['rate']),
                        'supplier': pi['voucher__party_ledger__name'] or 'Direct'
                    }

            for item in top_reorder:
                pid = item['product_id']
                if pid in last_purchases:
                    item['purchase_price'] = last_purchases[pid]['rate']
                    item['last_supplier'] = last_purchases[pid]['supplier']
                else:
                    item['last_supplier'] = 'Catalog Master'

        # 4. Slow-Moving & Deadstock Intelligence (Sitting on Benches for Days)
        # Identifies products with positive stock on hand (stock_quantity > 0)
        # that have either never been sold, or haven't been sold for 30+ days.
        from django.utils import timezone
        today = timezone.now().date()

        stock_qs = Product.objects.filter(
            company=company,
            is_active=True,
            stock_quantity__gt=0
        )
        if category_id:
            stock_qs = stock_qs.filter(category_id=category_id)

        prods_with_stock = list(stock_qs.select_related('category').values(
            'id', 'name', 'brand', 'sku', 'unit',
            'category__name', 'category_id',
            'stock_quantity', 'purchase_price', 'selling_price', 'created_at'
        ))

        stock_pids = [p['id'] for p in prods_with_stock]

        # Fetch sales aggregated for these stocked products
        stock_sales_agg = VoucherItem.objects.filter(
            product_id__in=stock_pids,
            voucher__company=company,
            voucher__voucher_type='SALES',
            voucher__status='POSTED'
        ).values('product_id').annotate(
            total_sold_qty=Sum('quantity'),
            invoices_count=Count('voucher_id', distinct=True),
            last_sale_date=Max('voucher__voucher_date')
        )
        sales_by_pid = {str(s['product_id']): s for s in stock_sales_agg}

        # Fetch purchases aggregated for these stocked products
        stock_purch_agg = VoucherItem.objects.filter(
            product_id__in=stock_pids,
            voucher__company=company,
            voucher__voucher_type='PURCHASE',
            voucher__status='POSTED'
        ).values('product_id').annotate(
            last_purchase_date=Max('voucher__voucher_date')
        )
        purch_by_pid = {str(p['product_id']): p for p in stock_purch_agg}

        deadstock_candidates = []
        total_deadstock_units = 0.0
        total_deadstock_capital = 0.0
        total_deadstock_mrp = 0.0
        brand_capital_map = {}

        dormant_count = 0
        critical_90_count = 0
        stagnant_60_count = 0
        slow_30_count = 0

        for p in prods_with_stock:
            pid_str = str(p['id'])
            sq = float(p['stock_quantity'] or 0)
            pp = float(p['purchase_price'] or 0)
            sp = float(p['selling_price'] or 0)
            locked_capital = round(sq * pp, 2)
            potential_revenue = round(sq * sp, 2)
            brand_name = (p['brand'] or '').strip() or 'Unbranded'

            sale_info = sales_by_pid.get(pid_str)
            purch_info = purch_by_pid.get(pid_str)

            last_sale_date = sale_info['last_sale_date'] if sale_info else None
            invoices_count = sale_info['invoices_count'] if sale_info else 0
            total_sold_qty = float(sale_info['total_sold_qty'] or 0) if sale_info else 0.0
            last_purch_date = purch_info['last_purchase_date'] if purch_info else None

            # Calculate idle days
            if last_sale_date:
                days_idle = (today - last_sale_date).days
            elif last_purch_date:
                days_idle = (today - last_purch_date).days
            elif p.get('created_at'):
                days_idle = (today - p['created_at'].date()).days
            else:
                days_idle = 90

            # Consider slow moving / sitting on benches if invoices_count == 0 or days_idle >= 30
            if invoices_count == 0 or days_idle >= 30:
                if invoices_count == 0:
                    status = 'DORMANT'
                    status_label = 'Never Sold'
                    dormant_count += 1
                elif days_idle >= 90:
                    status = 'CRITICAL_DEADSTOCK'
                    status_label = '90+ Days Idle'
                    critical_90_count += 1
                elif days_idle >= 60:
                    status = 'STAGNANT'
                    status_label = '60-90 Days Idle'
                    stagnant_60_count += 1
                else:
                    status = 'SLOW_MOVING'
                    status_label = '30-60 Days Idle'
                    slow_30_count += 1

                total_deadstock_units += sq
                total_deadstock_capital += locked_capital
                total_deadstock_mrp += potential_revenue

                brand_capital_map[brand_name] = brand_capital_map.get(brand_name, 0.0) + locked_capital

                deadstock_candidates.append({
                    'product_id': pid_str,
                    'name': p['name'],
                    'brand': p['brand'] or '',
                    'sku': p['sku'],
                    'unit': p['unit'] or 'PCS',
                    'category_name': p['category__name'] or 'General',
                    'category_id': str(p['category_id']) if p['category_id'] else None,
                    'current_stock': sq,
                    'purchase_price': pp,
                    'selling_price': sp,
                    'locked_capital': locked_capital,
                    'potential_revenue': potential_revenue,
                    'days_idle': days_idle,
                    'last_sale_date': last_sale_date.strftime('%Y-%m-%d') if last_sale_date else None,
                    'last_purchase_date': last_purch_date.strftime('%Y-%m-%d') if last_purch_date else None,
                    'invoices_count': invoices_count,
                    'total_sold_qty': total_sold_qty,
                    'status': status,
                    'status_label': status_label
                })

        # Sort deadstock items by locked capital descending (highest trapped cash first)
        deadstock_candidates.sort(key=lambda x: -x['locked_capital'])

        # Top brands with locked capital
        top_deadstock_brands = sorted(
            [{'brand': k, 'locked_capital': round(v, 2)} for k, v in brand_capital_map.items()],
            key=lambda x: -x['locked_capital']
        )[:8]

        deadstock_summary = {
            'total_items': len(deadstock_candidates),
            'total_units': round(total_deadstock_units, 2),
            'locked_capital': round(total_deadstock_capital, 2),
            'potential_mrp': round(total_deadstock_mrp, 2),
            'dormant_count': dormant_count,
            'critical_90_count': critical_90_count,
            'stagnant_60_count': stagnant_60_count,
            'slow_30_count': slow_30_count,
            'by_brand': top_deadstock_brands
        }

        return {
            "top_purchased": top_purchased,
            "top_sold": top_sold,
            "reorder_items": top_reorder,
            "deadstock_items": deadstock_candidates,
            "deadstock_summary": deadstock_summary,
            "categories": categories_data,
            "default_min_stock": float(default_min_stock)
        }
