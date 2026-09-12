import uuid
import datetime
from decimal import Decimal
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import transaction

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.inventory.models import Product
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry, FinancialYear, OfflineCommand
from apps.common.tenant import get_company_product, get_company_ledger
from apps.common.money import to_decimal, quantize_money
from apps.accounts.permissions import get_authorized_company

class SyncPullAPIView(APIView):
    """
    POST /api/v1/sync/pull/
    Returns changed ledgers, products, vouchers, voucher_items, and ledger_entries
    using a reliable cursor-based incremental protocol.
    Supports multi-batch pagination (has_more, next_cursor) and categorizes changes
    into created, updated, and deleted.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.db.models import Q
        company = get_authorized_company(request, request.data.get('company_id'))
        cursor = request.data.get('cursor')
        last_pulled_at = request.data.get('last_pulled_at')
        
        try:
            limit = min(max(int(request.data.get('limit', 200)), 1), 500)
        except (ValueError, TypeError):
            limit = 200

        since_dt = None
        cursor_dt = None
        cursor_uuid = None

        if cursor and isinstance(cursor, str) and '_' in cursor:
            try:
                parts = cursor.split('_', 1)
                raw_cursor_time = parts[0]
                cursor_uuid_str = parts[1] if parts[1] != 'latest' else None
                if 'T' in raw_cursor_time:
                    cursor_dt = datetime.datetime.fromisoformat(raw_cursor_time)
                else:
                    raw_ts = float(raw_cursor_time)
                    cursor_ts = raw_ts / 1000.0 if raw_ts > 1e11 else raw_ts
                    cursor_dt = datetime.datetime.fromtimestamp(cursor_ts, tz=datetime.timezone.utc)
                if cursor_uuid_str:
                    try:
                        cursor_uuid = uuid.UUID(cursor_uuid_str)
                    except Exception:
                        cursor_uuid = cursor_uuid_str
            except Exception:
                cursor_dt = None
                cursor_uuid = None
        elif last_pulled_at:
            try:
                raw_dt = datetime.datetime.fromtimestamp(float(last_pulled_at) / 1000.0, tz=datetime.timezone.utc)
                # 2-second buffer against client-server clock skew
                since_dt = raw_dt - datetime.timedelta(seconds=2)
            except Exception:
                since_dt = None

        now_ts = int(timezone.now().timestamp() * 1000)

        # Master data (ledgers, products) is only returned on initial batch (cursor is empty/None),
        # preventing redundant queries and transfer during multi-batch voucher pagination.
        is_initial_batch = not bool(cursor)

        ledgers_created, ledgers_updated, ledgers_deleted = [], [], []
        if is_initial_batch:
            # 1. Ledgers (Incremental changes)
            ledger_qs = Ledger.objects.filter(company=company)
            if since_dt:
                ledger_qs = ledger_qs.filter(updated_at__gte=since_dt)

            for l in ledger_qs:
                item = {
                    'id': str(l.id),
                    'company_id': str(company.id),
                    'name': l.name,
                    'ledger_type': l.ledger_type or 'GENERAL',
                    'gstin': l.gstin or '',
                    'state_code': l.state_code or '',
                    'current_balance': str(l.current_balance or '0.00'),
                    'opening_balance': str(l.opening_balance or '0.00'),
                    'opening_balance_type': l.opening_balance_type or 'DEBIT',
                    'phone': l.phone or '',
                    'server_updated_at': int(l.updated_at.timestamp() * 1000) if l.updated_at else now_ts,
                }
                if l.is_archived or not l.is_active:
                    ledgers_deleted.append(item)
                elif since_dt and l.created_at and l.created_at < since_dt:
                    ledgers_updated.append(item)
                else:
                    ledgers_created.append(item)

        products_created, products_updated, products_deleted = [], [], []
        if is_initial_batch:
            # 2. Products (Incremental changes)
            product_qs = Product.objects.filter(company=company)
            if since_dt:
                product_qs = product_qs.filter(updated_at__gte=since_dt)

            for p in product_qs:
                item = {
                    'id': str(p.id),
                    'company_id': str(company.id),
                    'name': p.name,
                    'sku': p.sku or '',
                    'hsn_code': getattr(p, 'hsn_code', '') or '',
                    'unit': getattr(p, 'unit', 'PCS') or 'PCS',
                    'purchase_price': str(getattr(p, 'purchase_price', '0.00') or '0.00'),
                    'sales_price': str(getattr(p, 'selling_price', '0.00') or '0.00'),
                    'gst_rate': str(getattr(p, 'gst_rate', '0.00') or '0.00'),
                    'current_stock': str(getattr(p, 'stock_quantity', '0.00') or '0.00'),
                    'server_updated_at': int(p.updated_at.timestamp() * 1000) if p.updated_at else now_ts,
                }
                if getattr(p, 'is_active', True) is False:
                    products_deleted.append(item)
                elif since_dt and p.created_at and p.created_at < since_dt:
                    products_updated.append(item)
                else:
                    products_created.append(item)

        # 3. Vouchers (Cursor-based pagination across large historical datasets)
        # Strictly defer attachment_data to stop massive binary/base64 network egress from Neon
        voucher_qs = Voucher.objects.filter(company=company).select_related('party_ledger').defer('attachment_data', 'attachment_mime')
        if since_dt:
            voucher_qs = voucher_qs.filter(updated_at__gte=since_dt)

        if cursor_uuid and cursor_dt:
            voucher_qs = voucher_qs.filter(
                Q(updated_at__gt=cursor_dt) | Q(updated_at=cursor_dt, id__gt=cursor_uuid)
            )

        # Order deterministically by updated_at and id
        batch_raw = list(voucher_qs.order_by('updated_at', 'id')[:limit + 1])
        has_more = len(batch_raw) > limit
        vouchers = batch_raw[:limit]

        if vouchers:
            last_v = vouchers[-1]
            last_v_time = last_v.updated_at.isoformat() if last_v.updated_at else datetime.datetime.now(datetime.timezone.utc).isoformat()
            next_cursor = f"{last_v_time}_{str(last_v.id)}"
        else:
            next_cursor = f"{timezone.now().isoformat()}_latest"

        vouchers_created, vouchers_updated, vouchers_deleted = [], [], []
        voucher_ids = [v.id for v in vouchers]

        for v in vouchers:
            item = {
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
                'total_amount': str(v.total_amount or '0.00'),
                'narration': v.narration or '',
                'server_updated_at': int(v.updated_at.timestamp() * 1000) if v.updated_at else now_ts,
            }
            if v.status in ['CANCELLED', 'REVERSED']:
                vouchers_deleted.append(item)
            elif since_dt and v.created_at and v.created_at < since_dt:
                vouchers_updated.append(item)
            else:
                vouchers_created.append(item)

        # 4. Voucher Items & Ledger Entries (Only if explicitly requested to stop discarded transfer)
        include_details = str(request.data.get('include_details', request.query_params.get('include_details', 'false'))).lower() in ['true', '1']
        items_data = []
        entries_data = []
        if include_details and voucher_ids:
            for item_obj in VoucherItem.objects.filter(voucher_id__in=voucher_ids).select_related('product'):
                items_data.append({
                    'id': str(item_obj.id),
                    'voucher_id': str(item_obj.voucher_id),
                    'product_id': str(item_obj.product_id),
                    'product_name': item_obj.product.name if item_obj.product else '',
                    'quantity': str(item_obj.quantity or '0.00'),
                    'rate': str(item_obj.rate or '0.00'),
                    'discount_percent': str(item_obj.discount_percent or '0.00'),
                    'discount_amount': str(item_obj.discount_amount or '0.00'),
                    'taxable_amount': str(item_obj.taxable_amount or '0.00'),
                    'gst_rate': str(item_obj.gst_rate or '0.00'),
                    'total_amount': str(item_obj.total_amount or '0.00'),
                })

            for entry in LedgerEntry.objects.filter(voucher_id__in=voucher_ids):
                entries_data.append({
                    'id': str(entry.id),
                    'voucher_id': str(entry.voucher_id),
                    'ledger_id': str(entry.ledger_id),
                    'debit_amount': str(entry.debit_amount or '0.00'),
                    'credit_amount': str(entry.credit_amount or '0.00'),
                    'narration': entry.narration or '',
                })

        return Response({
            'changes': {
                'ledgers': {'created': ledgers_created, 'updated': ledgers_updated, 'deleted': ledgers_deleted},
                'products': {'created': products_created, 'updated': products_updated, 'deleted': products_deleted},
                'vouchers': {'created': vouchers_created, 'updated': vouchers_updated, 'deleted': vouchers_deleted},
                'voucher_items': {'created': items_data, 'updated': [], 'deleted': []},
                'ledger_entries': {'created': entries_data, 'updated': [], 'deleted': []},
            },
            'has_more': has_more,
            'next_cursor': next_cursor,
            'timestamp': now_ts,
        })


class SyncPushAPIView(APIView):
    """
    POST /api/v1/sync/push/
    Authoritative Business Command processor for offline syncing.
    Rejects raw client ledger entries or client-dictated POSTED states.
    All accounting, GST, inventory, and ledger movements are computed server-side.
    Enforces idempotency via command_id.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company_id = request.data.get('company_id')
        commands = request.data.get('commands')
        changes = request.data.get('changes', {})

        if not company_id:
            return Response({'error': 'company_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        company = get_authorized_company(request, company_id)

        # Normalize incoming payload: support explicit commands array or legacy changes payload
        raw_items = []
        if commands and isinstance(commands, list):
            raw_items = commands
        elif changes.get('vouchers'):
            for v in changes.get('vouchers', []):
                raw_items.append({
                    'command_id': str(v.get('id') or v.get('command_id')),
                    'command_type': f"CREATE_{v.get('voucher_type', 'SALES').upper()}",
                    'payload': v,
                    'device_id': request.data.get('device_id', 'offline-client')
                })

        processed_commands = []
        errors = []

        from apps.accounting.services.sales_service import SalesInvoiceService
        from apps.accounting.services.purchase_service import PurchaseInvoiceService
        from apps.accounting.services.voucher_service import VoucherService

        for cmd_item in raw_items:
            cmd_id = cmd_item.get('command_id')
            cmd_type = cmd_item.get('command_type', 'CREATE_SALE').upper()
            payload = cmd_item.get('payload', {})
            device_id = cmd_item.get('device_id', '')

            if not cmd_id:
                continue

            # P0-2 & P0-3: Persist OfflineCommand outside the business transaction so failures are not rolled back
            existing_cmd = OfflineCommand.objects.filter(command_id=cmd_id).first()
            if existing_cmd:
                if existing_cmd.company_id != company.id:
                    errors.append({
                        'command_id': cmd_id,
                        'error': 'Command ID already registered to another company/tenant',
                        'error_code': 'TENANT_MISMATCH'
                    })
                    continue
                cmd_obj = existing_cmd
                created = False
            else:
                cmd_obj = OfflineCommand.objects.create(
                    command_id=cmd_id,
                    company=company,
                    device_id=device_id,
                    user=request.user,
                    command_type=cmd_type,
                    payload=payload,
                    status='PROCESSING'
                )
                created = True

            # Idempotency Check: if command already processed, skip duplicate posting and return cached voucher result
            if not created:
                if cmd_obj.status == 'PROCESSED' and cmd_obj.result_voucher:
                    processed_commands.append({
                        'command_id': cmd_id,
                        'status': 'PROCESSED',
                        'voucher_id': str(cmd_obj.result_voucher_id),
                        'voucher_number': cmd_obj.result_voucher.voucher_number,
                        'idempotent_cached': True
                    })
                    continue
                cmd_obj.status = 'PROCESSING'
                cmd_obj.retry_count += 1
                cmd_obj.save(update_fields=['status', 'retry_count'])

            try:
                with transaction.atomic():
                    voucher = None

                    if 'SALE' in cmd_type:
                        party_ledger_id = payload.get('party_ledger_id')
                        party_ledger = get_company_ledger(company, party_ledger_id, "Party Ledger") if party_ledger_id else None
                        if not party_ledger:
                            cash_grp, _ = Ledger.objects.get_or_create(company=company, name="Cash", defaults={"ledger_type": "CASH"})
                            party_ledger = cash_grp

                        sales_ledger = Ledger.objects.filter(company=company, ledger_type='SALES').first()
                        if not sales_ledger:
                            sales_ledger, _ = Ledger.objects.get_or_create(company=company, name="Sales Account", defaults={"ledger_type": "SALES"})

                        voucher = SalesInvoiceService.generate_sales_invoice(
                            company=company,
                            user=request.user,
                            party_ledger=party_ledger,
                            items_data=payload.get('items', []),
                            sales_ledger=sales_ledger,
                            cgst_ledger=None,
                            sgst_ledger=None,
                            igst_ledger=None,
                            manual_voucher_number=payload.get('voucher_number'),
                            manual_voucher_date=payload.get('voucher_date'),
                            buyer_name=payload.get('buyer_name'),
                            buyer_address=payload.get('buyer_address'),
                            buyer_gstin=payload.get('buyer_gstin'),
                            buyer_state_code=payload.get('buyer_state_code'),
                            buyer_phone=payload.get('buyer_phone'),
                            cartage_amount=to_decimal(payload.get('cartage_amount', 0))
                        )

                    elif 'PURCHASE' in cmd_type:
                        party_ledger_id = payload.get('party_ledger_id')
                        party_ledger = get_company_ledger(company, party_ledger_id, "Party Ledger")
                        purchase_ledger = Ledger.objects.filter(company=company, ledger_type='PURCHASE').first()
                        if not purchase_ledger:
                            purchase_ledger, _ = Ledger.objects.get_or_create(company=company, name="Purchase Account", defaults={"ledger_type": "PURCHASE"})

                        voucher = PurchaseInvoiceService.generate_purchase_invoice(
                            company=company,
                            user=request.user,
                            party_ledger=party_ledger,
                            items_data=payload.get('items', []),
                            purchase_ledger=purchase_ledger,
                            input_cgst_ledger=None,
                            input_sgst_ledger=None,
                            input_igst_ledger=None,
                            supplier_invoice_number=payload.get('voucher_number') or payload.get('reference_number'),
                            voucher_date=payload.get('voucher_date'),
                            cartage_amount=to_decimal(payload.get('cartage_amount', 0))
                        )

                    elif 'PAYMENT' in cmd_type or 'RECEIPT' in cmd_type:
                        from apps.accounting.services.allocation_service import PaymentAllocationService
                        from apps.accounting.services.sequence_service import InvoiceSequenceService

                        vtype = 'PAYMENT' if 'PAYMENT' in cmd_type else 'RECEIPT'
                        party_ledger_id = payload.get('party_ledger_id')
                        party_ledger = get_company_ledger(company, party_ledger_id, "Party Ledger")
                        amount = to_decimal(payload.get('amount') or payload.get('total_amount', 0))
                        
                        payment_ledger_id = payload.get('payment_ledger_id')
                        payment_ledger = get_company_ledger(company, payment_ledger_id, "Payment Account") if payment_ledger_id else None
                        if not payment_ledger:
                            payment_ledger, _ = Ledger.objects.get_or_create(company=company, name="Cash", defaults={"ledger_type": "CASH"})

                        v_date = payload.get('voucher_date') or timezone.now().date()
                        v_num, fy = InvoiceSequenceService.get_next_number(company, vtype, v_date)

                        voucher = Voucher.objects.create(
                            company=company,
                            financial_year=fy,
                            voucher_type=vtype,
                            voucher_number=v_num,
                            voucher_date=v_date,
                            party_ledger=party_ledger,
                            status='DRAFT',
                            total_amount=amount,
                            created_by=request.user,
                            narration=payload.get('narration') or f"{vtype.capitalize()} for {party_ledger.name}"
                        )

                        if vtype == 'PAYMENT':
                            LedgerEntry.objects.create(voucher=voucher, ledger=party_ledger, debit_amount=amount, credit_amount=Decimal('0.00'))
                            LedgerEntry.objects.create(voucher=voucher, ledger=payment_ledger, debit_amount=Decimal('0.00'), credit_amount=amount)
                        else:
                            LedgerEntry.objects.create(voucher=voucher, ledger=payment_ledger, debit_amount=amount, credit_amount=Decimal('0.00'))
                            LedgerEntry.objects.create(voucher=voucher, ledger=party_ledger, debit_amount=Decimal('0.00'), credit_amount=amount)

                        VoucherService.post_voucher(voucher)
                        PaymentAllocationService.auto_allocate_voucher(voucher)

                    if voucher:
                        # Authoritative server-side posting
                        if voucher.status != 'POSTED':
                            VoucherService.post_voucher(voucher)

                        cmd_obj.status = 'PROCESSED'
                        cmd_obj.result_voucher = voucher
                        cmd_obj.processed_at = timezone.now()
                        cmd_obj.error_code = None
                        cmd_obj.error_message = None
                        cmd_obj.save(update_fields=['status', 'result_voucher', 'processed_at', 'error_code', 'error_message'])

                        processed_commands.append({
                            'command_id': cmd_id,
                            'status': 'PROCESSED',
                            'voucher_id': str(voucher.id),
                            'voucher_number': voucher.voucher_number
                        })

            except Exception as e:
                from rest_framework.exceptions import ValidationError as DRFValidationError
                from django.core.exceptions import ValidationError as DjangoValidationError

                is_val_err = isinstance(e, (DRFValidationError, DjangoValidationError))
                cmd_obj.status = 'FAILED'
                cmd_obj.error_code = 'VALIDATION_ERROR' if is_val_err else 'EXECUTION_ERROR'
                cmd_obj.error_message = str(e)
                cmd_obj.failed_at = timezone.now()
                try:
                    cmd_obj.save(update_fields=['status', 'error_code', 'error_message', 'failed_at'])
                except Exception:
                    pass

                errors.append({'command_id': cmd_id, 'error': str(e), 'error_code': cmd_obj.error_code})

        return Response({
            'success': len(errors) == 0,
            'processed_count': len(processed_commands),
            'results': processed_commands,
            'errors': errors
        }, status=status.HTTP_200_OK if len(errors) == 0 else status.HTTP_207_MULTI_STATUS)
