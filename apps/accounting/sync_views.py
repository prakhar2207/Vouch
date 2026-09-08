import datetime
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import transaction

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.inventory.models import Product
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry, FinancialYear

class SyncPullAPIView(APIView):
    """
    POST /api/v1/sync/pull/
    Returns all changed ledgers, products, vouchers, voucher_items, and ledger_entries
    since `last_pulled_at` timestamp for the given company.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company_id = request.data.get('company_id')
        last_pulled_at = request.data.get('last_pulled_at')

        if not company_id:
            return Response({'error': 'company_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
        except Company.DoesNotExist:
            return Response({'error': 'Company not found or access denied'}, status=status.HTTP_404_NOT_FOUND)

        since_dt = None
        if last_pulled_at:
            try:
                # milliseconds to datetime
                since_dt = datetime.datetime.fromtimestamp(float(last_pulled_at) / 1000.0, tz=datetime.timezone.utc)
            except Exception:
                since_dt = None

        now_ts = int(timezone.now().timestamp() * 1000)

        # 1. Ledgers
        ledger_qs = Ledger.objects.filter(company=company)
        if since_dt:
            ledger_qs = ledger_qs.filter(updated_at__gte=since_dt)

        ledgers_data = []
        for l in ledger_qs:
            ledgers_data.append({
                'id': str(l.id),
                'company_id': str(company.id),
                'name': l.name,
                'ledger_type': l.ledger_type or 'GENERAL',
                'gstin': l.gstin or '',
                'state_code': l.state_code or '',
                'current_balance': float(l.current_balance or 0.0),
                'opening_balance': float(l.opening_balance or 0.0),
                'opening_balance_type': l.opening_balance_type or 'DEBIT',
                'phone': l.phone or '',
                'server_updated_at': int(l.updated_at.timestamp() * 1000) if l.updated_at else now_ts,
            })

        # 2. Products
        product_qs = Product.objects.filter(company=company)
        if since_dt:
            product_qs = product_qs.filter(updated_at__gte=since_dt)

        products_data = []
        for p in product_qs:
            products_data.append({
                'id': str(p.id),
                'company_id': str(company.id),
                'name': p.name,
                'sku': p.sku or '',
                'hsn_code': getattr(p, 'hsn_code', '') or '',
                'unit': getattr(p, 'unit', 'PCS') or 'PCS',
                'purchase_price': float(getattr(p, 'purchase_price', 0.0) or 0.0),
                'sales_price': float(getattr(p, 'selling_price', 0.0) or 0.0),
                'gst_rate': float(getattr(p, 'gst_rate', 0.0) or 0.0),
                'current_stock': float(getattr(p, 'stock_quantity', 0.0) or 0.0),
                'server_updated_at': int(p.updated_at.timestamp() * 1000) if p.updated_at else now_ts,
            })

        # 3. Vouchers
        voucher_qs = Voucher.objects.filter(company=company).select_related('party_ledger')
        if since_dt:
            voucher_qs = voucher_qs.filter(updated_at__gte=since_dt)

        # Cap at 500 records per pull batch to protect bandwidth
        vouchers = list(voucher_qs[:500])
        vouchers_data = []
        voucher_ids = [v.id for v in vouchers]

        for v in vouchers:
            vouchers_data.append({
                'id': str(v.id),
                'company_id': str(company.id),
                'financial_year_id': str(v.financial_year_id) if v.financial_year_id else None,
                'voucher_type': v.voucher_type,
                'voucher_number': v.voucher_number,
                'voucher_date': str(v.voucher_date),
                'reference_number': v.reference_number or '',
                'party_ledger_id': str(v.party_ledger_id) if v.party_ledger_id else None,
                'party_name': v.party_ledger.name if v.party_ledger else (v.buyer_name or ''),
                'status': v.status,
                'total_amount': float(v.total_amount or 0.0),
                'narration': v.narration or '',
                'server_updated_at': int(v.updated_at.timestamp() * 1000) if v.updated_at else now_ts,
            })

        # 4. Voucher Items & Ledger Entries for changed vouchers
        items_data = []
        for item in VoucherItem.objects.filter(voucher_id__in=voucher_ids):
            items_data.append({
                'id': str(item.id),
                'voucher_id': str(item.voucher_id),
                'product_id': str(item.product_id),
                'product_name': item.product.name if item.product else '',
                'quantity': float(item.quantity or 0.0),
                'rate': float(item.rate or 0.0),
                'discount_percent': float(item.discount_percent or 0.0),
                'discount_amount': float(item.discount_amount or 0.0),
                'taxable_amount': float(item.taxable_amount or 0.0),
                'gst_rate': float(item.gst_rate or 0.0),
                'total_amount': float(item.total_amount or 0.0),
            })

        entries_data = []
        for entry in LedgerEntry.objects.filter(voucher_id__in=voucher_ids):
            entries_data.append({
                'id': str(entry.id),
                'voucher_id': str(entry.voucher_id),
                'ledger_id': str(entry.ledger_id),
                'debit_amount': float(entry.debit_amount or 0.0),
                'credit_amount': float(entry.credit_amount or 0.0),
                'narration': entry.narration or '',
            })

        return Response({
            'changes': {
                'ledgers': {'created': ledgers_data, 'updated': [], 'deleted': []},
                'products': {'created': products_data, 'updated': [], 'deleted': []},
                'vouchers': {'created': vouchers_data, 'updated': [], 'deleted': []},
                'voucher_items': {'created': items_data, 'updated': [], 'deleted': []},
                'ledger_entries': {'created': entries_data, 'updated': [], 'deleted': []},
            },
            'timestamp': now_ts,
        })


class SyncPushAPIView(APIView):
    """
    POST /api/v1/sync/push/
    Receives batch changes from offline clients and applies them atomically.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company_id = request.data.get('company_id')
        changes = request.data.get('changes', {})

        if not company_id:
            return Response({'error': 'company_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
        except Company.DoesNotExist:
            return Response({'error': 'Company not found or access denied'}, status=status.HTTP_404_NOT_FOUND)

        vouchers_payload = changes.get('vouchers', [])
        synced_count = 0

        try:
            with transaction.atomic():
                for v_data in vouchers_payload:
                    v_id = v_data.get('id')
                    v_num = v_data.get('voucher_number')
                    v_type = v_data.get('voucher_type', 'SALES')
                    v_date = v_data.get('voucher_date') or timezone.now().date()
                    total_amount = float(v_data.get('total_amount', 0.0))

                    # Resolve Financial Year
                    fy = FinancialYear.objects.filter(
                        company=company,
                        start_date__lte=v_date,
                        end_date__gte=v_date
                    ).first()

                    # Find or create voucher
                    voucher, _ = Voucher.objects.update_or_create(
                        id=v_id,
                        defaults={
                            'company': company,
                            'financial_year': fy,
                            'voucher_type': v_type,
                            'voucher_number': v_num,
                            'voucher_date': v_date,
                            'reference_number': v_data.get('reference_number', ''),
                            'party_ledger_id': v_data.get('party_ledger_id') or None,
                            'narration': v_data.get('narration', ''),
                            'total_amount': total_amount,
                            'status': v_data.get('status', 'POSTED'),
                            'created_by': request.user,
                        }
                    )

                    # Replace / upsert items
                    items = v_data.get('items', [])
                    if items:
                        VoucherItem.objects.filter(voucher=voucher).delete()
                        for itm in items:
                            prod_id = itm.get('product_id')
                            if prod_id:
                                VoucherItem.objects.create(
                                    voucher=voucher,
                                    product_id=prod_id,
                                    quantity=itm.get('quantity', 1),
                                    rate=itm.get('rate', 0),
                                    discount_percent=itm.get('discount_percent', 0),
                                    discount_amount=itm.get('discount_amount', 0),
                                    taxable_amount=itm.get('taxable_amount', 0),
                                    gst_rate=itm.get('gst_rate', 0),
                                    total_amount=itm.get('total_amount', 0),
                                )

                    # Replace / upsert ledger entries
                    entries = v_data.get('ledger_entries', [])
                    if entries:
                        LedgerEntry.objects.filter(voucher=voucher).delete()
                        for ent in entries:
                            ledg_id = ent.get('ledger_id')
                            if ledg_id:
                                LedgerEntry.objects.create(
                                    voucher=voucher,
                                    ledger_id=ledg_id,
                                    debit_amount=ent.get('debit_amount', 0),
                                    credit_amount=ent.get('credit_amount', 0),
                                    narration=ent.get('narration', ''),
                                )

                    synced_count += 1

            return Response({
                'success': True,
                'message': f'Successfully synced {synced_count} vouchers',
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
            }, status=status.HTTP_400_BAD_REQUEST)
