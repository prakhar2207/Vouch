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
        company = get_authorized_company(request, request.data.get('company_id'))
        cursor = request.data.get('cursor', 0)
        
        try:
            limit = min(max(int(request.data.get('limit', 200)), 1), 1000)
        except (ValueError, TypeError):
            limit = 200

        # Try to parse cursor as integer (new monotonic sequence)
        skip_master_data = str(request.data.get('skip_master_data', '')).lower() == 'true'
        include_details = str(request.data.get('include_details', '')).lower() == 'true'
        try:
            if cursor == 'latest':
                cursor_id = -1 # Special flag
            else:
                cursor_id = int(cursor) if cursor else 0
        except (ValueError, TypeError):
            cursor_id = 0

        from apps.accounting.models import SyncEvent, BankTransaction, PaymentAllocation
        now_ts = int(timezone.now().timestamp() * 1000)
        
        # Get server snapshot cursor
        latest_event = SyncEvent.objects.filter(company=company).order_by('-id').first()
        snapshot_cursor = latest_event.id if latest_event else 0

        if cursor_id == -1:
            # Client just wants the snapshot cursor to start fresh
            return Response({
                'success': True,
                'changes': {
                    'ledgers': {'created': [], 'updated': [], 'deleted': []},
                    'products': {'created': [], 'updated': [], 'deleted': []},
                    'vouchers': {'created': [], 'updated': [], 'deleted': []},
                    'voucher_items': {'created': [], 'updated': [], 'deleted': []},
                    'ledger_entries': {'created': [], 'updated': [], 'deleted': []},
                    'bank_transactions': {'created': [], 'updated': [], 'deleted': []},
                    'payment_allocations': {'created': [], 'updated': [], 'deleted': []},
                },
                'next_cursor': snapshot_cursor,
                'has_more': False,
                'snapshot_cursor': snapshot_cursor,
                'server_time': now_ts
            })

        # Query events
        events_qs = SyncEvent.objects.filter(company=company, id__gt=cursor_id).order_by('id')
        
        # Fetch bounded limit + 1
        batch_events = list(events_qs[:limit + 1])
        has_more = len(batch_events) > limit
        events = batch_events[:limit]
        
        next_cursor = events[-1].id if events else cursor_id

        # Collapse events (only care about the final state of an entity in this batch)
        entity_map = {}
        for ev in events:
            key = (ev.entity_type, ev.entity_id)
            current_op = entity_map.get(key)
            if current_op == 'CREATE' and ev.operation == 'UPDATE':
                entity_map[key] = 'CREATE'
            elif current_op == 'CREATE' and ev.operation == 'DELETE':
                entity_map[key] = 'DELETE'
            else:
                entity_map[key] = ev.operation

        # Group by type and operation
        grouped = {
            'LEDGER': {'CREATE': set(), 'UPDATE': set(), 'DELETE': set()},
            'PRODUCT': {'CREATE': set(), 'UPDATE': set(), 'DELETE': set()},
            'VOUCHER': {'CREATE': set(), 'UPDATE': set(), 'DELETE': set()},
            'BANKTRANSACTION': {'CREATE': set(), 'UPDATE': set(), 'DELETE': set()},
            'PAYMENTALLOCATION': {'CREATE': set(), 'UPDATE': set(), 'DELETE': set()},
        }
        
        for (e_type, e_id), op in entity_map.items():
            if e_type in grouped:
                grouped[e_type][op].add(e_id)

        changes_dict = {
            'ledgers': {'created': [], 'updated': [], 'deleted': []},
            'products': {'created': [], 'updated': [], 'deleted': []},
            'vouchers': {'created': [], 'updated': [], 'deleted': []},
            'voucher_items': {'created': [], 'updated': [], 'deleted': []},
            'ledger_entries': {'created': [], 'updated': [], 'deleted': []},
            'bank_transactions': {'created': [], 'updated': [], 'deleted': []},
            'payment_allocations': {'created': [], 'updated': [], 'deleted': []},
        }

        # --- Hydrate LEDGERS ---
        ledger_ids = grouped['LEDGER']['CREATE'].union(grouped['LEDGER']['UPDATE'])
        if not skip_master_data and ledger_ids:
            ledgers = Ledger.objects.filter(id__in=ledger_ids)
            for l in ledgers:
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
                    'server_updated_at': int(l.updated_at.timestamp() * 1000) if getattr(l, 'updated_at', None) else now_ts,
                }
                if l.id in grouped['LEDGER']['CREATE']:
                    changes_dict['ledgers']['created'].append(item)
                else:
                    changes_dict['ledgers']['updated'].append(item)
        for d_id in grouped['LEDGER']['DELETE']:
            changes_dict['ledgers']['deleted'].append({'id': str(d_id)})

        # --- Hydrate PRODUCTS ---
        product_ids = grouped['PRODUCT']['CREATE'].union(grouped['PRODUCT']['UPDATE'])
        if not skip_master_data and product_ids:
            products = Product.objects.filter(id__in=product_ids)
            for p in products:
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
                    'reorder_level': str(getattr(p, 'reorder_level', '0.00') or '0.00'),
                    'server_updated_at': int(p.updated_at.timestamp() * 1000) if getattr(p, 'updated_at', None) else now_ts,
                }
                if p.id in grouped['PRODUCT']['CREATE']:
                    changes_dict['products']['created'].append(item)
                else:
                    changes_dict['products']['updated'].append(item)
        for d_id in grouped['PRODUCT']['DELETE']:
            changes_dict['products']['deleted'].append({'id': str(d_id)})

        # --- Hydrate VOUCHERS ---
        voucher_ids = grouped['VOUCHER']['CREATE'].union(grouped['VOUCHER']['UPDATE'])
        if voucher_ids:
            vouchers = Voucher.objects.filter(id__in=voucher_ids).select_related('party_ledger').defer('attachment_data', 'attachment_mime')
            for v in vouchers:
                item = {
                    'id': str(v.id),
                    'company_id': str(company.id),
                    'financial_year_id': str(v.financial_year_id) if v.financial_year_id else None,
                    'voucher_type': v.voucher_type,
                    'voucher_number': v.voucher_number,
                    'voucher_date': str(v.voucher_date),
                    'due_date': str(v.due_date) if v.due_date else None,
                    'reference_number': v.reference_number or '',
                    'party_ledger_id': str(v.party_ledger_id) if v.party_ledger_id else None,
                    'party_name': v.party_ledger.name if v.party_ledger else (v.buyer_name or ''),
                    'status': v.status,
                    'total_amount': str(v.total_amount or '0.00'),
                    'narration': v.narration or '',
                    'server_updated_at': int(v.updated_at.timestamp() * 1000) if getattr(v, 'updated_at', None) else now_ts,
                }
                if v.status in ['CANCELLED', 'REVERSED', 'SUPERSEDED']:
                    changes_dict['vouchers']['deleted'].append(item)
                elif v.id in grouped['VOUCHER']['CREATE']:
                    changes_dict['vouchers']['created'].append(item)
                else:
                    changes_dict['vouchers']['updated'].append(item)
        for d_id in grouped['VOUCHER']['DELETE']:
            changes_dict['vouchers']['deleted'].append({'id': str(d_id)})

        # --- Hydrate Details if Requested ---
        if include_details and voucher_ids:
            # We don't emit SyncEvents for items/entries (optimization), 
            # so we just pull all items/entries for the affected vouchers in this batch.
            from apps.accounting.models import VoucherItem, LedgerEntry
            
            v_items = VoucherItem.objects.filter(voucher_id__in=voucher_ids).select_related('product')
            for vi in v_items:
                changes_dict['voucher_items']['created'].append({
                    'id': str(vi.id),
                    'voucher_id': str(vi.voucher_id),
                    'product_id': str(vi.product_id),
                    'product_name': vi.product.name if vi.product else '',
                    'quantity': str(vi.quantity),
                    'rate': str(vi.rate),
                    'total_amount': str(vi.total_amount),
                    'taxable_amount': str(vi.taxable_amount),
                    'gst_rate': str(vi.gst_rate),
                    'cgst_amount': str(vi.cgst_amount),
                    'sgst_amount': str(vi.sgst_amount),
                    'igst_amount': str(vi.igst_amount),
                })
                
            l_entries = LedgerEntry.objects.filter(voucher_id__in=voucher_ids).select_related('ledger')
            for le in l_entries:
                changes_dict['ledger_entries']['created'].append({
                    'id': str(le.id),
                    'company_id': str(le.company_id) if le.company_id else None,
                    'voucher_id': str(le.voucher_id),
                    'ledger_id': str(le.ledger_id),
                    'ledger_name': le.ledger.name if le.ledger else '',
                    'debit_amount': str(le.debit_amount),
                    'credit_amount': str(le.credit_amount),
                })

        # --- Hydrate BANK TRANSACTIONS ---
        bt_ids = grouped['BANKTRANSACTION']['CREATE'].union(grouped['BANKTRANSACTION']['UPDATE'])
        if bt_ids:
            bts = BankTransaction.objects.filter(id__in=bt_ids).select_related('bank_ledger', 'matched_party', 'matched_voucher')
            for bt in bts:
                item = {
                    'id': str(bt.id),
                    'company_id': str(bt.company_id),
                    'bank_ledger_id': str(bt.bank_ledger_id),
                    'bank_ledger_name': bt.bank_ledger.name if bt.bank_ledger else '',
                    'transaction_date': str(bt.transaction_date),
                    'value_date': str(bt.value_date) if bt.value_date else None,
                    'description': bt.description,
                    'normalized_narration': bt.normalized_narration,
                    'reference_number': bt.reference_number or '',
                    'debit_amount': str(bt.debit_amount),
                    'credit_amount': str(bt.credit_amount),
                    'balance': str(bt.balance) if bt.balance is not None else None,
                    'status': bt.status,
                    'matched_party_id': str(bt.matched_party_id) if bt.matched_party_id else None,
                    'matched_party_name': bt.matched_party.name if bt.matched_party else None,
                    'matched_voucher_id': str(bt.matched_voucher_id) if bt.matched_voucher_id else None,
                    'matched_voucher_number': bt.matched_voucher.voucher_number if bt.matched_voucher else None,
                    'match_confidence': bt.match_confidence,
                    'match_notes': str(bt.match_notes) if bt.match_notes else None,
                    'server_updated_at': int(bt.updated_at.timestamp() * 1000) if getattr(bt, 'updated_at', None) else now_ts,
                }
                if bt.id in grouped['BANKTRANSACTION']['CREATE']:
                    changes_dict['bank_transactions']['created'].append(item)
                else:
                    changes_dict['bank_transactions']['updated'].append(item)
        for d_id in grouped['BANKTRANSACTION']['DELETE']:
            changes_dict['bank_transactions']['deleted'].append({'id': str(d_id)})

        # --- Hydrate PAYMENT ALLOCATIONS ---
        pa_ids = grouped['PAYMENTALLOCATION']['CREATE'].union(grouped['PAYMENTALLOCATION']['UPDATE'])
        if pa_ids:
            pas = PaymentAllocation.objects.filter(id__in=pa_ids)
            for pa in pas:
                item = {
                    'id': str(pa.id),
                    'company_id': str(pa.company_id),
                    'payment_voucher_id': str(pa.payment_voucher_id),
                    'invoice_voucher_id': str(pa.invoice_voucher_id),
                    'allocated_amount': str(pa.allocated_amount),
                    'server_updated_at': int(getattr(pa, 'updated_at', timezone.now()).timestamp() * 1000) if hasattr(pa, 'updated_at') else now_ts,
                }
                if pa.id in grouped['PAYMENTALLOCATION']['CREATE']:
                    changes_dict['payment_allocations']['created'].append(item)
                else:
                    changes_dict['payment_allocations']['updated'].append(item)
        for d_id in grouped['PAYMENTALLOCATION']['DELETE']:
            changes_dict['payment_allocations']['deleted'].append({'id': str(d_id)})

        return Response({
            'success': True,
            'changes': changes_dict,
            'next_cursor': str(next_cursor),
            'has_more': has_more,
            'snapshot_cursor': str(snapshot_cursor),
            'server_time': now_ts,
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

            from django.db import IntegrityError
            
            # P0-2 & P0-3: Persist OfflineCommand outside the business transaction so failures are not rolled back
            try:
                cmd_obj, created = OfflineCommand.objects.get_or_create(
                    command_id=cmd_id,
                    defaults={
                        'company': company,
                        'device_id': device_id,
                        'user': request.user,
                        'command_type': cmd_type,
                        'payload': payload,
                        'status': 'PROCESSING'
                    }
                )
            except IntegrityError:
                cmd_obj = OfflineCommand.objects.get(command_id=cmd_id)
                created = False

            if not created and cmd_obj.company_id != company.id:
                errors.append({
                    'command_id': cmd_id,
                    'error': 'Command ID already registered to another company/tenant',
                    'error_code': 'TENANT_MISMATCH'
                })
                continue

            # Idempotency Check: if command already processed, skip duplicate posting and return cached voucher result
            if not created:
                if cmd_obj.status == 'PROCESSED' and cmd_obj.result_voucher:
                    voucher = cmd_obj.result_voucher
                    voucher_data = {
                        'id': str(voucher.id),
                        'companyId': str(voucher.company_id),
                        'voucherType': voucher.voucher_type,
                        'voucherNumber': voucher.voucher_number,
                        'voucherDate': str(voucher.voucher_date),
                        'totalAmount': str(voucher.total_amount),
                        'status': voucher.status,
                        'partyLedgerId': str(voucher.party_ledger_id) if voucher.party_ledger_id else None,
                        'partyName': voucher.party_ledger.name if voucher.party_ledger else (voucher.buyer_name or ''),
                    }
                    processed_commands.append({
                        'command_id': cmd_id,
                        'status': 'PROCESSED',
                        'voucher_id': str(cmd_obj.result_voucher_id),
                        'voucher_number': cmd_obj.result_voucher.voucher_number,
                        'idempotent_cached': True,
                        'voucher_data': voucher_data
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

                        voucher_data = {
                            'id': str(voucher.id),
                            'companyId': str(voucher.company_id),
                            'voucherType': voucher.voucher_type,
                            'voucherNumber': voucher.voucher_number,
                            'voucherDate': str(voucher.voucher_date),
                            'totalAmount': str(voucher.total_amount),
                            'status': voucher.status,
                            'partyLedgerId': str(voucher.party_ledger_id) if voucher.party_ledger_id else None,
                            'partyName': voucher.party_ledger.name if voucher.party_ledger else (voucher.buyer_name or ''),
                        }

                        processed_commands.append({
                            'command_id': cmd_id,
                            'status': 'PROCESSED',
                            'voucher_id': str(voucher.id),
                            'voucher_number': voucher.voucher_number,
                            'voucher_data': voucher_data
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
