from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from decimal import Decimal

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from .services.sales_service import SalesInvoiceService
from .services.voucher_service import VoucherService
from .services.purchase_service import PurchaseInvoiceService
from .services.report_service import ReportService
from apps.accounts.permissions import (
    IsCompanyMember,
    IsCompanyAdmin,
    IsCompanyOwner,
    CanCreateSales,
    CanCreatePurchases,
    CanPostVoucher,
    CanCancelVoucher,
    CanManageLedgers,
    CanManageInventory,
    CanManageCompanySettings,
    user_has_company_roles
)

class CreateSalesInvoiceAPIView(APIView):
    permission_classes = [IsAuthenticated, CanCreateSales]

    def post(self, request):
        """
        Expects JSON:
        {
            "company_id": "uuid",
            "party_ledger_id": "uuid",
            "sales_ledger_id": "uuid",
            "cgst_ledger_id": "uuid",
            "sgst_ledger_id": "uuid",
            "igst_ledger_id": "uuid",
            "items": [
                {
                    "product_id": "uuid",
                    "quantity": "10.00",
                    "rate": "150.00",
                    "discount_percent": "5.00"
                }
            ],
            "post_immediately": true
        }
        """
        data = request.data
        try:
            from apps.ledgers.models import LedgerGroup
            company = Company.objects.get(id=data['company_id'], users__user=request.user)
            party_ledger = Ledger.objects.get(id=data['party_ledger_id'], company=company)

            # Resolve sales ledger
            sales_ledger = None
            sales_ledger_id = data.get('sales_ledger_id')
            if sales_ledger_id and str(sales_ledger_id).strip():
                try:
                    sales_ledger = Ledger.objects.filter(id=sales_ledger_id, company=company).first()
                except Exception:
                    sales_ledger = None
            if not sales_ledger:
                sales_ledger = Ledger.objects.filter(company=company, ledger_type='SALES').first() or \
                               Ledger.objects.filter(company=company, name__icontains='Sales').first()
                if not sales_ledger:
                    income_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Sales Accounts', defaults={'nature': 'INCOME'})
                    sales_ledger, _ = Ledger.objects.get_or_create(company=company, name='Sales Account', defaults={'group': income_grp, 'ledger_type': 'SALES'})

            # Resolve tax ledgers
            tax_grp = None
            def get_or_create_duties_grp():
                nonlocal tax_grp
                if not tax_grp:
                    tax_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Duties & Taxes', defaults={'nature': 'LIABILITY'})
                return tax_grp

            cgst_ledger = None
            cgst_id = data.get('cgst_ledger_id')
            if cgst_id and str(cgst_id).strip():
                try:
                    cgst_ledger = Ledger.objects.filter(id=cgst_id, company=company).first()
                except Exception:
                    cgst_ledger = None
            if not cgst_ledger or 'input' in cgst_ledger.name.lower():
                cgst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'CGST')

            sgst_ledger = None
            sgst_id = data.get('sgst_ledger_id')
            if sgst_id and str(sgst_id).strip():
                try:
                    sgst_ledger = Ledger.objects.filter(id=sgst_id, company=company).first()
                except Exception:
                    sgst_ledger = None
            if not sgst_ledger or 'input' in sgst_ledger.name.lower():
                sgst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'SGST')

            igst_ledger = None
            igst_id = data.get('igst_ledger_id')
            if igst_id and str(igst_id).strip():
                try:
                    igst_ledger = Ledger.objects.filter(id=igst_id, company=company).first()
                except Exception:
                    igst_ledger = None
            if not igst_ledger or 'input' in igst_ledger.name.lower():
                igst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'IGST')
            
            with transaction.atomic():
                # 1. Orchestrate Invoice Creation
                voucher = SalesInvoiceService.generate_sales_invoice(
                    company=company,
                    user=request.user,
                    party_ledger=party_ledger,
                    items_data=data['items'],
                    sales_ledger=sales_ledger,
                    cgst_ledger=cgst_ledger,
                    sgst_ledger=sgst_ledger,
                    igst_ledger=igst_ledger,
                    manual_voucher_number=data.get('voucher_number'),
                    manual_voucher_date=data.get('voucher_date'),
                    buyer_name=data.get('buyer_name'),
                    buyer_address=data.get('buyer_address'),
                    buyer_gstin=data.get('buyer_gstin'),
                    buyer_state_code=data.get('buyer_state_code'),
                    buyer_phone=data.get('buyer_phone'),
                    cartage_amount=Decimal(str(data.get('cartage_amount', 0) or 0)),
                    cartage_ledger=Ledger.objects.filter(id=data.get('cartage_ledger_id'), company=company).first() if data.get('cartage_ledger_id') else None
                )
                
                # 2. Automatically post it if requested
                if data.get('post_immediately', True):
                    VoucherService.post_voucher(voucher)
                    
            return Response({
                "success": True,
                "message": "Sales Invoice Generated Successfully.",
                "voucher_number": voucher.voucher_number,
                "status": voucher.status,
                "total_amount": voucher.total_amount
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class CreatePurchaseInvoiceAPIView(APIView):
    permission_classes = [IsAuthenticated, CanCreatePurchases]

    def post(self, request):
        data = request.data
        try:
            from apps.ledgers.models import LedgerGroup
            company = Company.objects.get(id=data['company_id'], users__user=request.user)
            party_ledger = Ledger.objects.get(id=data['party_ledger_id'], company=company)

            # Resolve purchase ledger
            purchase_ledger = None
            purchase_id = data.get('purchase_ledger_id')
            if purchase_id and str(purchase_id).strip():
                try:
                    purchase_ledger = Ledger.objects.filter(id=purchase_id, company=company).first()
                except Exception:
                    purchase_ledger = None
            if not purchase_ledger:
                purchase_ledger = Ledger.objects.filter(company=company, ledger_type='PURCHASE').first() or \
                                  Ledger.objects.filter(company=company, name__icontains='Purchase').first()
                if not purchase_ledger:
                    exp_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Purchase Accounts', defaults={'nature': 'EXPENSE'})
                    purchase_ledger, _ = Ledger.objects.get_or_create(company=company, name='Purchase Account', defaults={'group': exp_grp, 'ledger_type': 'PURCHASE'})

            # Resolve input tax ledgers
            tax_grp = None
            def get_or_create_purchase_duties_grp():
                nonlocal tax_grp
                if not tax_grp:
                    tax_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Duties & Taxes', defaults={'nature': 'LIABILITY'})
                return tax_grp

            input_cgst = None
            input_cgst_id = data.get('input_cgst_ledger_id') or data.get('cgst_ledger_id')
            if input_cgst_id and str(input_cgst_id).strip():
                try:
                    input_cgst = Ledger.objects.filter(id=input_cgst_id, company=company).first()
                except Exception:
                    input_cgst = None
            if not input_cgst or 'output' in input_cgst.name.lower():
                input_cgst = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'CGST')

            input_sgst = None
            input_sgst_id = data.get('input_sgst_ledger_id') or data.get('sgst_ledger_id')
            if input_sgst_id and str(input_sgst_id).strip():
                try:
                    input_sgst = Ledger.objects.filter(id=input_sgst_id, company=company).first()
                except Exception:
                    input_sgst = None
            if not input_sgst or 'output' in input_sgst.name.lower():
                input_sgst = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'SGST')

            input_igst = None
            input_igst_id = data.get('input_igst_ledger_id') or data.get('igst_ledger_id')
            if input_igst_id and str(input_igst_id).strip():
                try:
                    input_igst = Ledger.objects.filter(id=input_igst_id, company=company).first()
                except Exception:
                    input_igst = None
            if not input_igst or 'output' in input_igst.name.lower():
                input_igst = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'IGST')
            
            with transaction.atomic():
                voucher = PurchaseInvoiceService.generate_purchase_invoice(
                    company=company,
                    user=request.user,
                    party_ledger=party_ledger,
                    items_data=data['items'],
                    purchase_ledger=purchase_ledger,
                    input_cgst_ledger=input_cgst,
                    input_sgst_ledger=input_sgst,
                    input_igst_ledger=input_igst,
                    supplier_invoice_number=data.get('voucher_number') or data.get('supplier_invoice_number'),
                    voucher_date=data.get('voucher_date'),
                    cartage_amount=Decimal(str(data.get('cartage_amount', 0) or 0)),
                    cartage_ledger=Ledger.objects.filter(id=data.get('cartage_ledger_id'), company=company).first() if data.get('cartage_ledger_id') else None
                )
                
                if data.get('post_immediately', True):
                    VoucherService.post_voucher(voucher)
                    
            return Response({
                "success": True,
                "voucher_number": voucher.voucher_number,
                "status": voucher.status
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class TrialBalanceAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            tb = ReportService.generate_trial_balance(company)
            return Response({"success": True, "data": tb})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ListVouchersAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]
    
    def get(self, request, company_id):
        try:
            from apps.accounting.models import Voucher
            from django.db.models import Case, When, Value, BooleanField
            company = Company.objects.get(id=company_id, users__user=request.user)

            try:
                limit = min(max(int(request.query_params.get('limit', 50)), 1), 50)
            except (ValueError, TypeError):
                limit = 50

            try:
                offset = max(int(request.query_params.get('offset', 0)), 0)
            except (ValueError, TypeError):
                offset = 0

            vouchers = Voucher.objects.filter(company=company).select_related('party_ledger')
            v_type = request.query_params.get('type')
            if v_type:
                vouchers = vouchers.filter(voucher_type=v_type.upper())

            total_count = vouchers.count()

            vouchers = vouchers.annotate(
                has_attachment_flag=Case(
                    When(attachment_data__gt='', then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField()
                )
            ).only(
                'id', 'voucher_number', 'reference_number', 'voucher_type',
                'voucher_date', 'status', 'total_amount', 'party_ledger__name'
            ).order_by('-voucher_date', '-created_at')

            page_vouchers = list(vouchers[offset:offset+limit])

            from apps.accounting.models import PaymentAllocation
            from django.db.models import Sum
            page_v_ids = [v.id for v in page_vouchers]
            alloc_by_inv = {row['invoice_voucher_id']: row['paid'] for row in PaymentAllocation.objects.filter(invoice_voucher_id__in=page_v_ids).values('invoice_voucher_id').annotate(paid=Sum('allocated_amount'))}
            alloc_by_pmt = {row['payment_voucher_id']: row['allocated'] for row in PaymentAllocation.objects.filter(payment_voucher_id__in=page_v_ids).values('payment_voucher_id').annotate(allocated=Sum('allocated_amount'))}

            data = []
            for v in page_vouchers:
                tot = v.total_amount or Decimal('0.00')
                if v.voucher_type in ['SALES', 'PURCHASE']:
                    paid = alloc_by_inv.get(v.id, Decimal('0.00'))
                    if paid >= tot and tot > 0:
                        p_status = 'PAID'
                    elif paid > 0:
                        p_status = 'PARTIAL'
                    else:
                        p_status = 'UNPAID'
                    paid_amt = float(paid)
                elif v.voucher_type in ['PAYMENT', 'RECEIPT']:
                    allocated = alloc_by_pmt.get(v.id, Decimal('0.00'))
                    if allocated >= tot and tot > 0:
                        p_status = 'ALLOCATED'
                    elif allocated > 0:
                        p_status = 'PARTIAL'
                    else:
                        p_status = 'UNALLOCATED'
                    paid_amt = float(allocated)
                else:
                    p_status = 'N/A'
                    paid_amt = 0.0

                data.append({
                    "id": str(v.id),
                    "voucher_number": v.reference_number if (v.voucher_type == 'PURCHASE' and v.reference_number and not v.voucher_number.startswith('G/')) else v.voucher_number,
                    "reference_number": v.reference_number or "",
                    "type": v.voucher_type,
                    "date": v.voucher_date.strftime('%Y-%m-%d'),
                    "status": v.status,
                    "total_amount": v.total_amount,
                    "paid_amount": paid_amt,
                    "payment_status": p_status,
                    "has_attachment": bool(v.has_attachment_flag),
                    "party_name": v.party_ledger.name if v.party_ledger else "N/A"
                })
            return Response({
                "success": True,
                "data": data,
                "pagination": {
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "has_more": (offset + limit) < total_count,
                    "page": (offset // limit) + 1,
                    "total_pages": max(1, (total_count + limit - 1) // limit)
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class VoucherDetailAPIView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanCancelVoucher()]
    
    def get(self, request, voucher_id):
        try:
            from apps.accounting.models import Voucher, VoucherItem
            voucher = Voucher.objects.select_related('company', 'party_ledger').get(id=voucher_id, company__users__user=request.user)
            items = VoucherItem.objects.filter(voucher=voucher).select_related('product')
            
            items_data = []
            for item in items:
                items_data.append({
                    "id": str(item.id),
                    "product_id": str(item.product.id) if item.product else None,
                    "product_name": item.product.name if item.product else "Unnamed Product",
                    "brand": item.product.brand or "" if item.product else "",
                    "hsn_code": item.product.hsn_code if item.product else "",
                    "quantity": item.quantity,
                    "unit": item.product.unit if item.product else "PCS",
                    "rate": item.rate,
                    "discount_percent": item.discount_percent,
                    "discount_amount": item.discount_amount,
                    "taxable_amount": item.taxable_amount,
                    "gst_rate": item.gst_rate,
                    "total_amount": item.total_amount
                })
            
            # Signature data URL
            sig_data = None
            if voucher.company.proprietor_signature:
                import base64
                try:
                    sig_data = f"data:image/png;base64,{base64.b64encode(voucher.company.proprietor_signature).decode('utf-8')}"
                except Exception:
                    pass

            cartage_amount = Decimal('0.00')
            round_off_amount = Decimal('0.00')
            payment_ledger_obj = None
            for entry in voucher.ledger_entries.select_related('ledger').all():
                lname = entry.ledger.name.lower()
                if 'cartage' in lname or 'freight' in lname:
                    amt = entry.credit_amount if voucher.voucher_type == 'SALES' else entry.debit_amount
                    if amt > 0:
                        cartage_amount += amt
                elif 'round off' in lname or entry.ledger.ledger_type == 'ROUND_OFF':
                    if voucher.voucher_type == 'SALES':
                        round_off_amount += (entry.credit_amount - entry.debit_amount)
                    else:
                        round_off_amount += (entry.debit_amount - entry.credit_amount)
                elif voucher.voucher_type in ['PAYMENT', 'RECEIPT']:
                    if entry.ledger_id != voucher.party_ledger_id:
                        payment_ledger_obj = entry.ledger

            from apps.accounting.models import PaymentAllocation
            allocations_data = []
            paid_amount_total = Decimal('0.00')
            if voucher.voucher_type in ['SALES', 'PURCHASE']:
                for alloc in PaymentAllocation.objects.filter(invoice_voucher=voucher).select_related('payment_voucher'):
                    paid_amount_total += alloc.allocated_amount
                    allocations_data.append({
                        "id": str(alloc.id),
                        "voucher_id": str(alloc.payment_voucher_id),
                        "voucher_number": alloc.payment_voucher.voucher_number,
                        "voucher_type": alloc.payment_voucher.voucher_type,
                        "date": alloc.payment_voucher.voucher_date.strftime('%Y-%m-%d'),
                        "allocated_amount": float(alloc.allocated_amount)
                    })
            elif voucher.voucher_type in ['PAYMENT', 'RECEIPT']:
                for alloc in PaymentAllocation.objects.filter(payment_voucher=voucher).select_related('invoice_voucher'):
                    paid_amount_total += alloc.allocated_amount
                    allocations_data.append({
                        "id": str(alloc.id),
                        "voucher_id": str(alloc.invoice_voucher_id),
                        "voucher_number": alloc.invoice_voucher.voucher_number,
                        "voucher_type": alloc.invoice_voucher.voucher_type,
                        "date": alloc.invoice_voucher.voucher_date.strftime('%Y-%m-%d'),
                        "allocated_amount": float(alloc.allocated_amount)
                    })

            data = {
                "id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "type": voucher.voucher_type,
                "date": voucher.voucher_date.strftime('%Y-%m-%d'),
                "status": voucher.status,
                "total_amount": voucher.total_amount,
                "paid_amount": float(paid_amount_total),
                "unallocated_amount": float(max(Decimal('0.00'), (voucher.total_amount or Decimal('0.00')) - paid_amount_total)),
                "allocations": allocations_data,
                "cartage_amount": float(cartage_amount),
                "round_off_amount": float(round_off_amount),
                "narration": voucher.narration,
                "reference_number": voucher.reference_number or "",
                "party_ledger_id": str(voucher.party_ledger.id) if voucher.party_ledger else None,
                "payment_ledger_id": str(payment_ledger_obj.id) if payment_ledger_obj else None,
                "payment_ledger_name": payment_ledger_obj.name if payment_ledger_obj else None,
                "company": {
                    "name": voucher.company.name,
                    "address": voucher.company.address,
                    "city": voucher.company.city,
                    "gstin": voucher.company.gstin,
                    "state_code": voucher.company.state_code,
                    "state_name": voucher.company.state_name,
                    "phone": voucher.company.phone,
                    "email": voucher.company.email,
                    "tagline": voucher.company.tagline,
                    "proprietor_signature": sig_data,
                    "bank_name": voucher.company.bank_name,
                    "bank_account_number": voucher.company.bank_account_number,
                    "bank_ifsc": voucher.company.bank_ifsc,
                    "bank_branch": voucher.company.bank_branch,
                },
                "buyer_details": {
                    "buyer_name": voucher.buyer_name or "",
                    "buyer_address": voucher.buyer_address or "",
                    "buyer_gstin": voucher.buyer_gstin or "",
                    "buyer_state_code": voucher.buyer_state_code or "",
                    "buyer_phone": voucher.buyer_phone or "",
                },
                "party": {
                    "name": voucher.buyer_name if voucher.buyer_name else (voucher.party_ledger.name if voucher.party_ledger else "N/A"),
                    "settlement_ledger": voucher.party_ledger.name if voucher.party_ledger else "N/A",
                    "address": voucher.buyer_address if voucher.buyer_address else (voucher.party_ledger.address if voucher.party_ledger else ""),
                    "gstin": voucher.buyer_gstin if voucher.buyer_gstin else (voucher.party_ledger.gstin if voucher.party_ledger else ""),
                    "state_code": voucher.buyer_state_code if voucher.buyer_state_code else (voucher.party_ledger.state_code if voucher.party_ledger else ""),
                    "phone": voucher.buyer_phone if voucher.buyer_phone else (voucher.party_ledger.phone if voucher.party_ledger else ""),
                } if voucher.party_ledger else None,
                "attachment_data": voucher.attachment_data,
                "attachment_mime": voucher.attachment_mime,
                "items": items_data
            }
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, voucher_id):
        try:
            from apps.accounting.models import Voucher
            from apps.accounting.services.voucher_service import VoucherService
            from apps.ledgers.models import Ledger
            
            voucher = Voucher.objects.filter(id=voucher_id, company__users__user=request.user).first()
            if not voucher:
                return Response({
                    "success": False, 
                    "error": "Voucher not found or you do not have permission to delete it."
                }, status=status.HTTP_404_NOT_FOUND)

            if not user_has_company_roles(request.user, voucher.company, ['OWNER', 'ADMIN', 'ACCOUNTANT']):
                return Response({
                    "success": False,
                    "error": "Permission denied: Only Owner, Admin, or Accountant can delete or cancel vouchers."
                }, status=status.HTTP_403_FORBIDDEN)

            with transaction.atomic():
                company = voucher.company
                voucher_type = voucher.voucher_type
                product_ids = list(voucher.items.values_list('product_id', flat=True))
                voucher_num = voucher.voucher_number
                
                # Track all affected ledgers (party ledger + any ledger referenced in ledger entries)
                affected_ledger_ids = set(voucher.ledger_entries.values_list('ledger_id', flat=True))
                if voucher.party_ledger_id:
                    affected_ledger_ids.add(voucher.party_ledger_id)

                if voucher.status in ['POSTED', 'VALIDATING']:
                    # Safely cancel & reverse accounting/stock/allocations
                    VoucherService.cancel_voucher(voucher, user=request.user)
                    # POSTED vouchers remain recorded with status CANCELLED to preserve audit trail and sequence numbers.
                    action_msg = "cancelled and reversed"
                else:
                    # DRAFT vouchers can be deleted safely
                    voucher.delete()
                    action_msg = "deleted"
                    
                    # Safe cleanup: only delete auto-created ad-hoc products with no category, no stock, no other entries
                    from apps.inventory.models import Product
                    for pid in set(product_ids):
                        try:
                            prod = Product.objects.filter(id=pid).first()
                            if (prod and 
                                prod.category is None and 
                                prod.stock_quantity <= 0 and 
                                not prod.voucher_items.exists() and 
                                not prod.entries.exists()):
                                prod.delete()
                        except Exception:
                            pass

                # Single-source-of-truth recalculation for all affected ledgers
                for lid in affected_ledger_ids:
                    l = Ledger.objects.filter(id=lid).first()
                    if l:
                        VoucherService.recalculate_ledger_balance(l)

            type_label = "Voucher" if voucher_type in ['PAYMENT', 'RECEIPT', 'CONTRA', 'JOURNAL'] else "Invoice"
            return Response({
                "success": True, 
                "message": f"{type_label} #{voucher_num} {action_msg} successfully."
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, voucher_id):
        try:
            from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
            from apps.accounting.services.voucher_service import VoucherService
            from apps.accounting.services.allocation_service import PaymentAllocationService
            from apps.inventory.models import Product, ProductCategory
            from apps.gst.services.gst_calculator import GSTCalculator
            from decimal import Decimal

            voucher = Voucher.objects.select_related('company', 'party_ledger').get(
                id=voucher_id, 
                company__users__user=request.user
            )
            if not user_has_company_roles(request.user, voucher.company, ['OWNER', 'ADMIN', 'ACCOUNTANT']):
                return Response({
                    "success": False,
                    "error": "Permission denied: Only Owner, Admin, or Accountant can modify vouchers."
                }, status=status.HTTP_403_FORBIDDEN)

            company = voucher.company
            data = request.data

            with transaction.atomic():
                if 'voucher_number' in data and data['voucher_number']:
                    voucher.voucher_number = str(data['voucher_number']).strip()
                    voucher.reference_number = str(data['voucher_number']).strip()
                if 'voucher_date' in data and data['voucher_date']:
                    voucher.voucher_date = data['voucher_date']
                if 'narration' in data:
                    voucher.narration = data['narration']

                # If party name changed
                if 'party_name' in data and str(data['party_name']).strip() and voucher.party_ledger:
                    new_party_name = str(data['party_name']).strip()
                    if voucher.party_ledger.name != new_party_name:
                        voucher.party_ledger.name = new_party_name
                        voucher.party_ledger.save(update_fields=['name'])

                # Full line items update
                if 'items' in data and isinstance(data['items'], list):
                    # 1. Reverse previous accounting & stock if POSTED or VALIDATING
                    if voucher.status in ['POSTED', 'VALIDATING']:
                        VoucherService.cancel_voucher(voucher, user=request.user)

                    # 2. Clear old items and ledger entries (never delete product master records during edit)
                    voucher.items.all().delete()
                    voucher.ledger_entries.all().delete()

                    # 3. Process each updated line item
                    total_invoice_value = Decimal('0.00')
                    total_taxable_value = Decimal('0.00')
                    total_cgst = Decimal('0.00')
                    total_sgst = Decimal('0.00')
                    total_igst = Decimal('0.00')

                    party_ledger = voucher.party_ledger

                    for item in data['items']:
                        raw_name = str(item.get('product_name') or item.get('description') or 'Unnamed Product').strip()
                        if not raw_name:
                            continue

                        qty = Decimal(str(item.get('quantity', 1)))
                        rate = Decimal(str(item.get('rate', 0)))
                        hsn = str(item.get('hsn_code', '')).strip()
                        gst_pct = Decimal(str(item.get('gst_rate', 18)))
                        unit = str(item.get('unit', 'PCS')).strip().upper()
                        fractional_units = ['KG', 'KGS', 'KILOGRAM', 'KILOGRAMS', 'LTR', 'LTRS', 'LITRE', 'LITRES', 'LITER', 'LITERS', 'MTR', 'MTRS', 'METER', 'METERS', 'METRE', 'METRES']
                        if unit not in fractional_units:
                            qty = Decimal(str(int(round(float(qty)))))

                        # Resolve category first (especially for purchase vouchers)
                        from apps.inventory.models import ProductCategory
                        from apps.inventory.services.normalization_service import normalize_product_name, get_canonical_key, strip_category_prefix
                        category = None
                        category_id = item.get('category_id') or data.get('category_id')
                        category_name = item.get('category_name') or data.get('category_name')
                        if category_id and str(category_id).strip():
                            try:
                                category = ProductCategory.objects.filter(id=category_id, company=company).first()
                            except Exception:
                                pass
                        elif category_name and str(category_name).strip():
                            category = ProductCategory.objects.filter(name__iexact=str(category_name).strip(), company=company).first()
                            if not category:
                                category = ProductCategory.objects.create(
                                    company=company,
                                    name=str(category_name).strip(),
                                    hsn_code=hsn,
                                    gst_rate=gst_pct
                                )

                        cat_name = category.name if category else None
                        clean_item_name = normalize_product_name(raw_name, cat_name)
                        canon_key = get_canonical_key(raw_name, cat_name)
                        item_brand = str(item.get('brand', '')).strip()

                        product = None
                        prod_id = item.get('product_id')
                        if prod_id and str(prod_id).strip():
                            try:
                                product = Product.objects.filter(id=prod_id, company=company).first()
                            except Exception:
                                product = None

                        # If product was fetched by ID, verify that the brand has not been changed
                        if product:
                            existing_brand = (product.brand or '').strip()
                            if item_brand:
                                if existing_brand.lower() != item_brand.lower():
                                    product = None
                            else:
                                if existing_brand and existing_brand.lower() not in ['unbranded', 'generic']:
                                    product = None

                        if not product and item_brand:
                            # Strict brand search - only match products belonging to this specific brand
                            product = Product.objects.filter(
                                company=company,
                                name__iexact=clean_item_name,
                                brand__iexact=item_brand
                            ).first()
                            if not product:
                                for p in Product.objects.filter(company=company, brand__iexact=item_brand):
                                    if get_canonical_key(p.name, p.category.name if p.category else cat_name) == canon_key:
                                        product = p
                                        if p.name != clean_item_name:
                                            p.name = clean_item_name
                                            p.save(update_fields=['name'])
                                        break

                        if not product and not item_brand:
                            # Strict unbranded search - NEVER hijack a branded product (like PIX or Modicord)
                            unbranded_q = Q(brand__isnull=True) | Q(brand='') | Q(brand__iexact='unbranded') | Q(brand__iexact='generic')
                            product = Product.objects.filter(
                                company=company,
                                name__iexact=clean_item_name
                            ).filter(unbranded_q).first()
                            if not product:
                                for p in Product.objects.filter(company=company).filter(unbranded_q):
                                    if get_canonical_key(p.name, p.category.name if p.category else cat_name) == canon_key:
                                        product = p
                                        if p.name != clean_item_name:
                                            p.name = clean_item_name
                                            p.save(update_fields=['name'])
                                        break

                        discount_pct = Decimal(str(item.get('discount_percent', '0.00')))
                        net_rate = (rate * (Decimal('100') - discount_pct) / Decimal('100')).quantize(Decimal('0.01'))

                        if not product:
                            # Auto-create product only if no product exists with this name and brand in inventory
                            if not category:
                                existing_sibling = Product.objects.filter(company=company, name__iexact=clean_item_name).first()
                                if existing_sibling and existing_sibling.category:
                                    category = existing_sibling.category
                                else:
                                    category = ProductCategory.objects.filter(company=company).first()
                            
                            if not category:
                                category = ProductCategory.objects.create(
                                    company=company,
                                    name="General Belts" if "BELT" in clean_item_name.upper() else "General Products",
                                    hsn_code=hsn,
                                    gst_rate=gst_pct
                                )
                            import uuid
                            sku = f"{clean_item_name[:4].upper()}-{uuid.uuid4().hex[:6].upper()}"
                            product = Product.objects.create(
                                company=company,
                                category=category,
                                name=clean_item_name,
                                brand=item_brand,
                                sku=sku,
                                hsn_code=hsn or category.hsn_code,
                                gst_rate=gst_pct,
                                unit=unit,
                                purchase_price=net_rate if voucher.voucher_type == 'PURCHASE' else Decimal('0.00'),
                                purchase_price_from_invoice=(voucher.voucher_type == 'PURCHASE'),
                                selling_price=rate if voucher.voucher_type == 'SALES' else Decimal('0.00')
                            )
                        else:
                            if item_brand and not product.brand:
                                product.brand = item_brand
                            if not product.category and category:
                                product.category = category
                            if voucher.voucher_type == 'PURCHASE' and net_rate > Decimal('0.00'):
                                product.purchase_price = net_rate
                                product.purchase_price_from_invoice = True
                            # Sales vouchers must NEVER mutate product master selling_price (MRP)
                            if hsn:
                                product.hsn_code = hsn
                            if gst_pct > Decimal('0.00'):
                                product.gst_rate = gst_pct
                            product.save()

                        gross = qty * rate
                        discount_amt = (gross * discount_pct / Decimal('100')).quantize(Decimal('0.01'))
                        taxable_amount = gross - discount_amt
                        
                        taxes = GSTCalculator.calculate_taxes(
                            company_state_code=company.state_code,
                            party_state_code=party_ledger.state_code if party_ledger else company.state_code,
                            taxable_amount=taxable_amount,
                            gst_rate=gst_pct
                        )
                        total_line_amount = taxable_amount + taxes['total_tax']

                        VoucherItem.objects.create(
                            voucher=voucher,
                            product=product,
                            quantity=qty,
                            rate=rate,
                            discount_percent=discount_pct,
                            discount_amount=discount_amt,
                            taxable_amount=taxable_amount,
                            gst_rate=gst_pct,
                            total_amount=total_line_amount
                        )

                        total_taxable_value += taxable_amount
                        total_cgst += taxes['cgst']
                        total_sgst += taxes['sgst']
                        total_igst += taxes['igst']
                        total_invoice_value += total_line_amount

                    # Cartage amount
                    try:
                        cartage_amt = Decimal(str(data.get('cartage_amount') or '0.00')).quantize(Decimal('0.01'))
                    except Exception:
                        cartage_amt = Decimal('0.00')

                    # Apply Round Off calculation
                    unrounded_total = total_invoice_value + cartage_amt
                    integer_part = Decimal(int(unrounded_total))
                    decimal_part = unrounded_total - integer_part
                    if decimal_part < Decimal('0.50'):
                        rounded_total = integer_part.quantize(Decimal('0.01'))
                    else:
                        rounded_total = (integer_part + Decimal('1.00')).quantize(Decimal('0.01'))
                    round_off = (rounded_total - unrounded_total).quantize(Decimal('0.01'))

                    voucher.total_amount = rounded_total
                    voucher.status = 'DRAFT'
                    voucher.save()

                    from apps.ledgers.models import Ledger, LedgerGroup

                    # 4. Re-create double-entry ledger entries based on voucher_type
                    if voucher.voucher_type == 'SALES':
                        # Debit Party (Customer)
                        if party_ledger:
                            LedgerEntry.objects.create(
                                voucher=voucher,
                                company=company,
                                ledger=party_ledger,
                                debit_amount=rounded_total,
                                credit_amount=Decimal('0.00')
                            )

                        sales_ledger = Ledger.objects.filter(company=company, ledger_type='SALES').first() or \
                                       Ledger.objects.filter(company=company, name__icontains='Sales').first()
                        if not sales_ledger:
                            income_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Sales Accounts', defaults={'nature': 'INCOME'})
                            sales_ledger, _ = Ledger.objects.get_or_create(company=company, name='Sales Account', defaults={'group': income_grp, 'ledger_type': 'SALES'})

                        LedgerEntry.objects.create(
                            voucher=voucher,
                            company=company,
                            ledger=sales_ledger,
                            debit_amount=Decimal('0.00'),
                            credit_amount=total_taxable_value
                        )

                        tax_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Duties & Taxes', defaults={'nature': 'LIABILITY'})
                        if total_cgst > 0:
                            output_cgst, _ = Ledger.objects.get_or_create(company=company, name='Output CGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, company=company, ledger=output_cgst, debit_amount=Decimal('0.00'), credit_amount=total_cgst)
                        if total_sgst > 0:
                            output_sgst, _ = Ledger.objects.get_or_create(company=company, name='Output SGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, company=company, ledger=output_sgst, debit_amount=Decimal('0.00'), credit_amount=total_sgst)
                        if total_igst > 0:
                            output_igst, _ = Ledger.objects.get_or_create(company=company, name='Output IGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, company=company, ledger=output_igst, debit_amount=Decimal('0.00'), credit_amount=total_igst)

                        # Credit Cartage Outward
                        if cartage_amt > Decimal('0.00'):
                            from apps.accounting.services.sales_service import SalesInvoiceService
                            cartage_ledger = SalesInvoiceService._get_or_create_cartage_ledger(company, 'OUTWARD')
                            LedgerEntry.objects.create(
                                voucher=voucher,
                                company=company,
                                ledger=cartage_ledger,
                                debit_amount=Decimal('0.00'),
                                credit_amount=cartage_amt
                            )

                        if round_off != Decimal('0.00'):
                            from apps.accounting.services.sales_service import SalesInvoiceService
                            round_off_ledger = SalesInvoiceService._get_or_create_round_off_ledger(company)
                            if round_off < Decimal('0.00'):
                                LedgerEntry.objects.create(voucher=voucher, company=company, ledger=round_off_ledger, debit_amount=abs(round_off), credit_amount=Decimal('0.00'))
                            else:
                                LedgerEntry.objects.create(voucher=voucher, company=company, ledger=round_off_ledger, debit_amount=Decimal('0.00'), credit_amount=round_off)

                    else:
                        # PURCHASE Voucher
                        if party_ledger:
                            LedgerEntry.objects.create(
                                voucher=voucher,
                                company=company,
                                ledger=party_ledger,
                                debit_amount=Decimal('0.00'),
                                credit_amount=rounded_total
                            )

                        purchase_ledger = Ledger.objects.filter(company=company, ledger_type='PURCHASE').first() or \
                                          Ledger.objects.filter(company=company, name__icontains='Purchase').first()
                        if not purchase_ledger:
                            exp_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Purchase Accounts', defaults={'nature': 'EXPENSE'})
                            purchase_ledger, _ = Ledger.objects.get_or_create(company=company, name='Purchase Account', defaults={'group': exp_grp, 'ledger_type': 'PURCHASE'})

                        LedgerEntry.objects.create(
                            voucher=voucher,
                            company=company,
                            ledger=purchase_ledger,
                            debit_amount=total_taxable_value,
                            credit_amount=Decimal('0.00')
                        )

                        tax_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Duties & Taxes', defaults={'nature': 'LIABILITY'})
                        if total_cgst > 0:
                            input_cgst, _ = Ledger.objects.get_or_create(company=company, name='Input CGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, company=company, ledger=input_cgst, debit_amount=total_cgst, credit_amount=Decimal('0.00'))
                        if total_sgst > 0:
                            input_sgst, _ = Ledger.objects.get_or_create(company=company, name='Input SGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, company=company, ledger=input_sgst, debit_amount=total_sgst, credit_amount=Decimal('0.00'))
                        if total_igst > 0:
                            input_igst, _ = Ledger.objects.get_or_create(company=company, name='Input IGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, company=company, ledger=input_igst, debit_amount=total_igst, credit_amount=Decimal('0.00'))

                        # Debit Cartage Inward
                        if cartage_amt > Decimal('0.00'):
                            from apps.accounting.services.purchase_service import PurchaseInvoiceService
                            cartage_ledger = PurchaseInvoiceService._get_or_create_cartage_ledger(company, 'INWARD')
                            LedgerEntry.objects.create(
                                voucher=voucher,
                                company=company,
                                ledger=cartage_ledger,
                                debit_amount=cartage_amt,
                                credit_amount=Decimal('0.00')
                            )

                        if round_off != Decimal('0.00'):
                            from apps.accounting.services.purchase_service import PurchaseInvoiceService
                            round_off_ledger = PurchaseInvoiceService._get_or_create_round_off_ledger(company)
                            if round_off > Decimal('0.00'):
                                LedgerEntry.objects.create(voucher=voucher, company=company, ledger=round_off_ledger, debit_amount=round_off, credit_amount=Decimal('0.00'))
                            else:
                                LedgerEntry.objects.create(voucher=voucher, company=company, ledger=round_off_ledger, debit_amount=Decimal('0.00'), credit_amount=abs(round_off))

                    # 5. Re-post voucher to update stock & balances
                    VoucherService.post_voucher(voucher)
                elif voucher.voucher_type in ['PAYMENT', 'RECEIPT']:
                    # Update Payment or Receipt voucher
                    from apps.ledgers.models import Ledger
                    from datetime import date

                    # Track all affected ledgers (previous + new)
                    affected_ledger_ids = set(voucher.ledger_entries.values_list('ledger_id', flat=True))
                    if voucher.party_ledger_id:
                        affected_ledger_ids.add(voucher.party_ledger_id)

                    # 1. Reverse previous accounting if posted or validating
                    if voucher.status in ['POSTED', 'VALIDATING']:
                        VoucherService.cancel_voucher(voucher, user=request.user)

                    # 2. Clear old ledger entries
                    voucher.ledger_entries.all().delete()

                    # 3. Determine updated party and cash/bank ledgers
                    if 'party_ledger_id' in data and data['party_ledger_id']:
                        party_ledger = Ledger.objects.get(id=data['party_ledger_id'], company=company)
                        voucher.party_ledger = party_ledger
                    else:
                        party_ledger = voucher.party_ledger

                    payment_ledger_id = data.get('payment_ledger_id')
                    if payment_ledger_id:
                        payment_ledger = Ledger.objects.get(id=payment_ledger_id, company=company)
                    else:
                        # Fallback to existing non-party ledger
                        existing_entry = voucher.ledger_entries.exclude(ledger=party_ledger).first()
                        payment_ledger = existing_entry.ledger if existing_entry else None

                    if not party_ledger or not payment_ledger:
                        raise ValueError("Both party ledger and cash/bank ledger are required to update a payment/receipt voucher.")

                    affected_ledger_ids.add(party_ledger.id)
                    affected_ledger_ids.add(payment_ledger.id)

                    # Update amount
                    if 'amount' in data and data['amount']:
                        amount = abs(Decimal(str(data['amount'])))
                    else:
                        amount = voucher.total_amount

                    voucher.total_amount = amount

                    if 'reference_number' in data:
                        voucher.reference_number = str(data.get('reference_number') or '').strip()
                    if 'narration' in data:
                        voucher.narration = str(data.get('narration') or '').strip()
                    if 'voucher_date' in data and data['voucher_date']:
                        voucher.voucher_date = date.fromisoformat(str(data['voucher_date']))

                    # 4. Create new ledger entries
                    if voucher.voucher_type == 'RECEIPT':
                        # Receipt: Debit Cash/Bank, Credit Customer
                        LedgerEntry.objects.create(voucher=voucher, company=company, ledger=payment_ledger, debit_amount=amount, credit_amount=Decimal('0.00'), narration=f"Receipt from {party_ledger.name}")
                        LedgerEntry.objects.create(voucher=voucher, company=company, ledger=party_ledger, debit_amount=Decimal('0.00'), credit_amount=amount, narration=f"Receipt via {payment_ledger.name}")
                    else:
                        # Payment: Debit Supplier, Credit Cash/Bank
                        LedgerEntry.objects.create(voucher=voucher, company=company, ledger=party_ledger, debit_amount=amount, credit_amount=Decimal('0.00'), narration=f"Payment via {payment_ledger.name}")
                        LedgerEntry.objects.create(voucher=voucher, company=company, ledger=payment_ledger, debit_amount=Decimal('0.00'), credit_amount=amount, narration=f"Payment to {party_ledger.name}")

                    # 5. Re-post voucher
                    VoucherService.post_voucher(voucher)

                    # 6. Auto-allocate against unpaid invoices FIFO
                    PaymentAllocationService.auto_allocate_voucher(voucher)

                    # 7. Recalculate balances for all affected ledgers (old and new)
                    for lid in affected_ledger_ids:
                        l = Ledger.objects.filter(id=lid).first()
                        if l:
                            VoucherService.recalculate_ledger_balance(l)
                else:
                    voucher.save()

            type_label = "Voucher" if voucher.voucher_type in ['PAYMENT', 'RECEIPT', 'CONTRA', 'JOURNAL'] else "invoice"
            return Response({"success": True, "message": f"{voucher.voucher_type.title()} {type_label} updated successfully."})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class LedgerStatementAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]
    
    def get(self, request, company_id, ledger_id):
        try:
            from apps.accounting.models import LedgerEntry, Voucher
            from apps.ledgers.models import Ledger
            from decimal import Decimal
            from datetime import datetime
            import collections

            company = Company.objects.get(id=company_id, users__user=request.user)
            
            # Enforce strict GST separation & auto-heal historical misallocated entries
            SalesInvoiceService.reassign_misallocated_tax_entries(company)

            ledger = Ledger.objects.select_related('group').get(id=ledger_id, company=company)

            # Date Range Filters
            from_date_str = request.query_params.get('from_date')
            to_date_str = request.query_params.get('to_date')

            from_date = None
            to_date = None
            if from_date_str and from_date_str.strip():
                try:
                    from_date = datetime.strptime(from_date_str.strip(), '%Y-%m-%d').date()
                except ValueError:
                    pass
            if to_date_str and to_date_str.strip():
                try:
                    to_date = datetime.strptime(to_date_str.strip(), '%Y-%m-%d').date()
                except ValueError:
                    pass

            # Pagination parameters (Capped at 50 max rows per request)
            try:
                limit = min(max(int(request.query_params.get('limit', 50)), 1), 50)
            except (ValueError, TypeError):
                limit = 50

            try:
                offset = max(int(request.query_params.get('offset', 0)), 0)
            except (ValueError, TypeError):
                offset = 0

            from django.db.models import Sum

            # Determine normal balance type
            # Asset and Expense are Debit-normal; Liability, Equity, Income are Credit-normal.
            ledger_nature = ledger.group.nature if ledger.group else 'ASSET'
            is_debit_normal = ledger_nature in ['ASSET', 'EXPENSE'] or ledger.opening_balance_type == 'DEBIT'
            normal_balance_type = 'DEBIT' if is_debit_normal else 'CREDIT'

            # Calculate Period Opening Balance:
            # Starts with ledger.opening_balance (and opening_balance_type)
            # If from_date is provided, accumulate all transactions strictly BEFORE from_date into opening balance
            initial_op_amount = Decimal(str(ledger.opening_balance or '0.00'))
            initial_op_type = ledger.opening_balance_type or ('DEBIT' if is_debit_normal else 'CREDIT')

            # Convert initial opening balance to signed net based on ledger's normal type
            if is_debit_normal:
                period_running = initial_op_amount if initial_op_type == 'DEBIT' else -initial_op_amount
            else:
                period_running = initial_op_amount if initial_op_type == 'CREDIT' else -initial_op_amount

            if from_date:
                prior_entries = LedgerEntry.objects.filter(
                    ledger=ledger,
                    voucher__company=company,
                    voucher__voucher_date__lt=from_date
                ).values_list('debit_amount', 'credit_amount')
                for dr, cr in prior_entries:
                    dr_dec = Decimal(str(dr or '0.00'))
                    cr_dec = Decimal(str(cr or '0.00'))
                    if is_debit_normal:
                        period_running += (dr_dec - cr_dec)
                    else:
                        period_running += (cr_dec - dr_dec)

            if is_debit_normal:
                period_opening_amount = abs(period_running)
                period_opening_type = 'DEBIT' if period_running >= 0 else 'CREDIT'
            else:
                period_opening_amount = abs(period_running)
                period_opening_type = 'CREDIT' if period_running >= 0 else 'DEBIT'

            # Base query of entries within period
            entries_qs = LedgerEntry.objects.filter(
                ledger=ledger,
                voucher__company=company
            ).select_related('voucher', 'voucher__party_ledger')

            if from_date:
                entries_qs = entries_qs.filter(voucher__voucher_date__gte=from_date)
            if to_date:
                entries_qs = entries_qs.filter(voucher__voucher_date__lte=to_date)

            entries_qs = entries_qs.order_by('voucher__voucher_date', 'created_at', 'id')

            # Aggregate total period debit & credit in single fast SQL query
            total_count = entries_qs.count()
            period_agg = entries_qs.aggregate(
                total_dr=Sum('debit_amount'),
                total_cr=Sum('credit_amount')
            )
            total_period_debit = Decimal(str(period_agg['total_dr'] or '0.00'))
            total_period_credit = Decimal(str(period_agg['total_cr'] or '0.00'))

            if is_debit_normal:
                period_net = total_period_debit - total_period_credit
                closing_signed = period_running + period_net
                closing_amount = abs(closing_signed)
                closing_type = 'DEBIT' if closing_signed >= 0 else 'CREDIT'
            else:
                period_net = total_period_credit - total_period_debit
                closing_signed = period_running + period_net
                closing_amount = abs(closing_signed)
                closing_type = 'CREDIT' if closing_signed >= 0 else 'DEBIT'

            # Calculate running balance at the start of current page (offset > 0)
            running_signed = period_running
            if offset > 0 and total_count > 0:
                prior_ids = entries_qs.values('id')[:offset]
                prior_offset_agg = LedgerEntry.objects.filter(id__in=prior_ids).aggregate(
                    prior_dr=Sum('debit_amount'),
                    prior_cr=Sum('credit_amount')
                )
                p_dr = Decimal(str(prior_offset_agg['prior_dr'] or '0.00'))
                p_cr = Decimal(str(prior_offset_agg['prior_cr'] or '0.00'))
                if is_debit_normal:
                    running_signed += (p_dr - p_cr)
                else:
                    running_signed += (p_cr - p_dr)

            # Page Opening Balance
            if is_debit_normal:
                page_opening_amount = abs(running_signed)
                page_opening_type = 'DEBIT' if running_signed >= 0 else 'CREDIT'
            else:
                page_opening_amount = abs(running_signed)
                page_opening_type = 'CREDIT' if running_signed >= 0 else 'DEBIT'

            # Project ONLY required table columns (strictly exclude attachment_data)
            projected_qs = entries_qs.only(
                'id', 'voucher_id', 'ledger_id', 'debit_amount', 'credit_amount', 'narration', 'created_at',
                'voucher__id', 'voucher__voucher_number', 'voucher__voucher_type', 'voucher__voucher_date',
                'voucher__narration', 'voucher__buyer_name', 'voucher__party_ledger__name'
            )
            entries = list(projected_qs[offset:offset+limit])

            # Batch fetch opposing entries for ONLY the current page's vouchers
            voucher_ids = [e.voucher_id for e in entries if e.voucher_id]
            siblings = LedgerEntry.objects.filter(
                voucher_id__in=voucher_ids
            ).select_related('ledger').only(
                'id', 'voucher_id', 'ledger_id', 'debit_amount', 'credit_amount',
                'ledger__name', 'ledger__ledger_type'
            )

            voucher_entries_map = collections.defaultdict(list)
            for s in siblings:
                voucher_entries_map[s.voucher_id].append(s)

            # Build statement rows with continuous running balance
            statement_rows = []
            for e in entries:
                dr = Decimal(str(e.debit_amount or '0.00'))
                cr = Decimal(str(e.credit_amount or '0.00'))

                if is_debit_normal:
                    running_signed += (dr - cr)
                    row_bal = abs(running_signed)
                    row_bal_type = 'DR' if running_signed >= 0 else 'CR'
                else:
                    running_signed += (cr - dr)
                    row_bal = abs(running_signed)
                    row_bal_type = 'CR' if running_signed >= 0 else 'DR'

                # Opposing ledger logic:
                v_sibs = voucher_entries_map.get(e.voucher_id, [])
                if dr > 0:
                    opp = [s for s in v_sibs if s.id != e.id and s.credit_amount > 0]
                else:
                    opp = [s for s in v_sibs if s.id != e.id and s.debit_amount > 0]

                if not opp:
                    opp = [s for s in v_sibs if s.id != e.id]

                prefix = "To " if dr > 0 else "By "
                opposing_details = []
                for o in opp:
                    amt = o.credit_amount if dr > 0 else o.debit_amount
                    opposing_details.append({
                        "ledger_id": str(o.ledger_id),
                        "ledger_name": o.ledger.name,
                        "amount": float(amt)
                    })

                if len(opp) == 0:
                    particulars = e.narration or "Adjustment"
                elif len(opp) == 1:
                    opp_name = opp[0].ledger.name
                    if opp[0].ledger.ledger_type == 'CASH' and e.voucher and e.voucher.buyer_name:
                        opp_name = f"{opp_name} ({e.voucher.buyer_name})"
                    particulars = f"{prefix}{opp_name}"
                else:
                    main_opp = opp[0].ledger.name
                    particulars = f"{prefix}{main_opp} (+ {len(opp) - 1} other{'s' if len(opp) > 2 else ''})"

                statement_rows.append({
                    "id": str(e.id),
                    "voucher_id": str(e.voucher_id) if e.voucher_id else None,
                    "date": e.voucher.voucher_date.strftime('%Y-%m-%d') if (e.voucher and e.voucher.voucher_date) else None,
                    "particulars": particulars,
                    "opposing_ledger_name": opp[0].ledger.name if opp else "As per details",
                    "opposing_details": opposing_details,
                    "voucher_number": e.voucher.voucher_number if e.voucher else "Opening Balance",
                    "voucher_type": e.voucher.voucher_type if e.voucher else "-",
                    "narration": e.narration or (e.voucher.narration if e.voucher else ""),
                    "debit": float(dr),
                    "credit": float(cr),
                    "running_balance": float(row_bal),
                    "running_balance_type": row_bal_type,
                })

            return Response({
                "success": True,
                "data": {
                    "ledger_id": str(ledger.id),
                    "ledger_name": ledger.name,
                    "group_name": ledger.group.name if ledger.group else "",
                    "nature": ledger_nature,
                    "normal_balance_type": normal_balance_type,
                    "gstin": ledger.gstin or "",
                    "state_code": ledger.state_code or "",
                    "phone": ledger.phone or "",
                    "email": ledger.email or "",
                    "from_date": from_date_str or None,
                    "to_date": to_date_str or None,
                    "period_opening_balance": float(period_opening_amount),
                    "period_opening_type": period_opening_type,
                    "page_opening_balance": float(page_opening_amount),
                    "page_opening_type": page_opening_type,
                    "total_debit": float(total_period_debit),
                    "total_credit": float(total_period_credit),
                    "net_movement": float(period_net),
                    "closing_balance": float(closing_amount),
                    "closing_type": closing_type,
                    "entries": statement_rows,
                    "pagination": {
                        "total_count": total_count,
                        "limit": limit,
                        "offset": offset,
                        "has_more": (offset + limit) < total_count,
                        "page": (offset // limit) + 1,
                        "total_pages": max(1, (total_count + limit - 1) // limit)
                    }
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CreatePaymentReceiptAPIView(APIView):
    """
    Create a Payment or Receipt voucher.
    Payment = You PAY a supplier (Debit Supplier, Credit Cash/Bank)
    Receipt = You RECEIVE money from a customer (Debit Cash/Bank, Credit Customer)
    
    Expects JSON:
    {
        "company_id": "uuid",
        "voucher_type": "PAYMENT" or "RECEIPT",
        "party_ledger_id": "uuid",     # Customer or Supplier ledger
        "payment_ledger_id": "uuid",    # Cash or Bank ledger
        "amount": "5000.00",
        "narration": "Payment against invoice SAL-001",
        "voucher_date": "2026-08-27"    # optional, defaults to today
    }
    """
    permission_classes = [IsAuthenticated, CanPostVoucher]

    def post(self, request):
        from apps.accounting.models import Voucher, LedgerEntry
        from datetime import date
        import uuid as uuid_lib

        data = request.data
        try:
            from apps.common.tenant import get_company_ledger
            from apps.common.money import to_decimal, quantize_money
            from apps.accounting.services.sequence_service import InvoiceSequenceService
            from apps.accounting.services.allocation_service import PaymentAllocationService
            from apps.accounts.permissions import user_has_company_roles

            company = Company.objects.get(id=data['company_id'], users__user=request.user, is_active=True)
            
            if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN', 'ACCOUNTANT', 'SALES', 'PURCHASE']):
                return Response({"success": False, "error": "Permission denied: Your role cannot create payment/receipt vouchers."}, status=403)

            party_ledger = get_company_ledger(company, data['party_ledger_id'], "Party Ledger")
            payment_ledger = get_company_ledger(company, data['payment_ledger_id'], "Payment/Bank Ledger")
            
            voucher_type = data.get('voucher_type', 'RECEIPT').upper()
            if voucher_type not in ('PAYMENT', 'RECEIPT'):
                return Response({"success": False, "error": "voucher_type must be PAYMENT or RECEIPT"}, status=400)
            
            amount = abs(quantize_money(data.get('amount', '0.00')))
            if amount <= Decimal('0.00'):
                return Response({"success": False, "error": "Amount must be greater than 0"}, status=400)
            
            voucher_date_str = data.get('voucher_date')
            voucher_date = date.fromisoformat(voucher_date_str) if voucher_date_str else date.today()

            with transaction.atomic():
                # Sequential number generator with select_for_update
                voucher_number, fy = InvoiceSequenceService.get_next_number(company, voucher_type, voucher_date)

                voucher = Voucher.objects.create(
                    company=company,
                    financial_year=fy,
                    voucher_type=voucher_type,
                    voucher_number=voucher_number,
                    voucher_date=voucher_date,
                    party_ledger=party_ledger,
                    reference_number=str(data.get('reference_number') or '').strip(),
                    narration=data.get('narration', ''),
                    status='DRAFT',
                    total_amount=amount,
                    created_by=request.user,
                )

                if voucher_type == 'RECEIPT':
                    # Receipt: Debit Cash/Bank, Credit Customer
                    LedgerEntry.objects.create(voucher=voucher, company=company, ledger=payment_ledger, debit_amount=amount, credit_amount=Decimal('0.00'), narration=f"Receipt from {party_ledger.name}")
                    LedgerEntry.objects.create(voucher=voucher, company=company, ledger=party_ledger, debit_amount=Decimal('0.00'), credit_amount=amount, narration=f"Receipt via {payment_ledger.name}")
                else:
                    # Payment: Debit Supplier, Credit Cash/Bank
                    LedgerEntry.objects.create(voucher=voucher, company=company, ledger=party_ledger, debit_amount=amount, credit_amount=Decimal('0.00'), narration=f"Payment via {payment_ledger.name}")
                    LedgerEntry.objects.create(voucher=voucher, company=company, ledger=payment_ledger, debit_amount=Decimal('0.00'), credit_amount=amount, narration=f"Payment to {party_ledger.name}")

                # Auto-post voucher atomically
                VoucherService.post_voucher(voucher)

                # Auto-allocate against unpaid invoices FIFO
                allocations = PaymentAllocationService.auto_allocate_voucher(voucher)

            return Response({
                "success": True,
                "message": f"{voucher_type.title()} Voucher posted successfully.",
                "voucher_number": voucher.voucher_number,
                "amount": str(amount),
                "allocations": allocations
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ListPaymentReceiptAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id):
        try:
            from apps.accounting.models import Voucher
            company = Company.objects.get(id=company_id, users__user=request.user)
            
            voucher_type = request.query_params.get('type')  # PAYMENT or RECEIPT or None for both
            try:
                limit = min(max(int(request.query_params.get('limit', 50)), 1), 50)
            except (ValueError, TypeError):
                limit = 50

            try:
                offset = max(int(request.query_params.get('offset', 0)), 0)
            except (ValueError, TypeError):
                offset = 0

            qs = Voucher.objects.filter(company=company, voucher_type__in=['PAYMENT', 'RECEIPT']).select_related('party_ledger')
            
            if voucher_type in ('PAYMENT', 'RECEIPT'):
                qs = qs.filter(voucher_type=voucher_type)
            
            total_count = qs.count()

            qs = qs.only(
                'id', 'voucher_number', 'voucher_type', 'voucher_date',
                'status', 'total_amount', 'party_ledger__name', 'narration'
            ).order_by('-voucher_date', '-created_at')

            page_vouchers = list(qs[offset:offset+limit])
            
            data = [
                {
                    "id": str(v.id),
                    "voucher_number": v.voucher_number,
                    "type": v.voucher_type,
                    "date": v.voucher_date.strftime('%Y-%m-%d'),
                    "status": v.status,
                    "total_amount": str(v.total_amount),
                    "party_name": v.party_ledger.name if v.party_ledger else "N/A",
                    "narration": v.narration or "",
                } for v in page_vouchers
            ]
            return Response({
                "success": True,
                "data": data,
                "pagination": {
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "has_more": (offset + limit) < total_count,
                    "page": (offset // limit) + 1,
                    "total_pages": max(1, (total_count + limit - 1) // limit)
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

def compress_and_clean_attachment(b64_str, mime_type="application/pdf"):
    if not b64_str:
        return None, None
    try:
        import io, base64
        from PIL import Image
        from pypdf import PdfReader, PdfWriter

        header = ""
        actual_b64 = b64_str
        if "," in b64_str:
            header, actual_b64 = b64_str.split(",", 1)
            header += ","

        missing_padding = len(actual_b64) % 4
        if missing_padding:
            actual_b64 += "=" * (4 - missing_padding)

        raw = base64.b64decode(actual_b64)
        MAX_BYTES = 2 * 1024 * 1024 # 2MB

        if len(raw) <= MAX_BYTES:
            return b64_str, mime_type

        # Auto-compress PDF
        if "pdf" in mime_type or raw[:4] == b'%PDF':
            reader = PdfReader(io.BytesIO(raw))
            writer = PdfWriter()
            for page in reader.pages:
                page.compress_content_streams()
                writer.add_page(page)
            out_buf = io.BytesIO()
            writer.write(out_buf)
            compressed_bytes = out_buf.getvalue()
            new_b64 = base64.b64encode(compressed_bytes).decode("utf-8")
            return f"data:application/pdf;base64,{new_b64}", "application/pdf"
        else: # Auto-compress Image
            img = Image.open(io.BytesIO(raw))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            if max(img.size) > 1800:
                img.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            out_buf = io.BytesIO()
            img.save(out_buf, format="JPEG", quality=75, optimize=True)
            compressed_bytes = out_buf.getvalue()
            new_b64 = base64.b64encode(compressed_bytes).decode("utf-8")
            return f"data:image/jpeg;base64,{new_b64}", "image/jpeg"
    except Exception as err:
        print(f"Attachment compression error: {err}")
        return b64_str, mime_type

class UniversalVoucherAPIView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanPostVoucher()]

    def get(self, request, company_id=None):
        try:
            from apps.accounting.models import Voucher
            from django.db.models import Case, When, Value, BooleanField
            if not company_id:
                company = Company.objects.filter(users__user=request.user).first()
            else:
                company = Company.objects.get(id=company_id, users__user=request.user)

            if not company:
                return Response({"success": False, "error": "Company not found"}, status=404)

            v_type = request.query_params.get('type')
            try:
                limit = min(max(int(request.query_params.get('limit', 50)), 1), 50)
            except (ValueError, TypeError):
                limit = 50

            try:
                offset = max(int(request.query_params.get('offset', 0)), 0)
            except (ValueError, TypeError):
                offset = 0

            qs = Voucher.objects.filter(company=company).select_related('party_ledger')
            if v_type:
                qs = qs.filter(voucher_type=v_type.upper())

            total_count = qs.count()

            qs = qs.annotate(
                has_attachment_flag=Case(
                    When(attachment_data__gt='', then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField()
                )
            ).only(
                'id', 'voucher_number', 'reference_number', 'voucher_type',
                'voucher_date', 'status', 'total_amount', 'party_ledger__name',
                'narration', 'attachment_mime'
            ).order_by('-voucher_date', '-created_at')

            page_vouchers = list(qs[offset:offset+limit])

            from apps.accounting.models import PaymentAllocation
            from django.db.models import Sum
            page_v_ids = [v.id for v in page_vouchers]
            alloc_by_inv = {row['invoice_voucher_id']: row['paid'] for row in PaymentAllocation.objects.filter(invoice_voucher_id__in=page_v_ids).values('invoice_voucher_id').annotate(paid=Sum('allocated_amount'))}
            alloc_by_pmt = {row['payment_voucher_id']: row['allocated'] for row in PaymentAllocation.objects.filter(payment_voucher_id__in=page_v_ids).values('payment_voucher_id').annotate(allocated=Sum('allocated_amount'))}

            data = []
            for v in page_vouchers:
                tot = v.total_amount or Decimal('0.00')
                if v.voucher_type in ['SALES', 'PURCHASE']:
                    paid = alloc_by_inv.get(v.id, Decimal('0.00'))
                    if paid >= tot and tot > 0:
                        p_status = 'PAID'
                    elif paid > 0:
                        p_status = 'PARTIAL'
                    else:
                        p_status = 'UNPAID'
                    paid_amt = float(paid)
                elif v.voucher_type in ['PAYMENT', 'RECEIPT']:
                    allocated = alloc_by_pmt.get(v.id, Decimal('0.00'))
                    if allocated >= tot and tot > 0:
                        p_status = 'ALLOCATED'
                    elif allocated > 0:
                        p_status = 'PARTIAL'
                    else:
                        p_status = 'UNALLOCATED'
                    paid_amt = float(allocated)
                else:
                    p_status = 'N/A'
                    paid_amt = 0.0

                data.append({
                    "id": str(v.id),
                    "voucher_number": v.reference_number if (v.voucher_type == 'PURCHASE' and v.reference_number and not v.voucher_number.startswith('G/')) else v.voucher_number,
                    "reference_number": v.reference_number or "",
                    "type": v.voucher_type,
                    "date": v.voucher_date.strftime('%Y-%m-%d'),
                    "status": v.status,
                    "total_amount": str(v.total_amount),
                    "paid_amount": paid_amt,
                    "payment_status": p_status,
                    "party_name": v.party_ledger.name if v.party_ledger else "General Entry",
                    "narration": v.narration or "",
                    "has_attachment": bool(v.has_attachment_flag),
                    "attachment_mime": v.attachment_mime or "",
                })
            return Response({
                "success": True,
                "data": data,
                "pagination": {
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "has_more": (offset + limit) < total_count,
                    "page": (offset // limit) + 1,
                    "total_pages": max(1, (total_count + limit - 1) // limit)
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        """
        Supports:
        1. Sales / Purchase vouchers with item list (auto GST and inventory)
        2. Generic double-entry vouchers with entries: [{ledger_id, debit_amount, credit_amount}]
        """
        data = request.data
        try:
            from apps.accounting.models import Voucher, LedgerEntry
            from apps.ledgers.models import Ledger, LedgerGroup
            from decimal import Decimal
            from django.utils import timezone
            import uuid, time

            company_id = data.get('company_id')
            if not company_id:
                company = Company.objects.filter(users__user=request.user).first()
            else:
                company = Company.objects.get(id=company_id, users__user=request.user)

            if not company:
                return Response({"success": False, "error": "Company not found"}, status=400)

            voucher_type = data.get('voucher_type', data.get('type', 'JOURNAL')).upper()
            voucher_date = data.get('voucher_date', data.get('date', timezone.now().date()))
            narration = data.get('narration', '')
            manual_vnum = data.get('voucher_number')

            with transaction.atomic():
                # Case 1: Structured Items provided (Sales or Purchase)
                if 'items' in data and len(data['items']) > 0:
                    party_ledger_id = data.get('party_ledger_id')
                    party_ledger = Ledger.objects.get(id=party_ledger_id, company=company) if party_ledger_id else None

                    if voucher_type == 'SALES':
                        # Find or resolve default ledgers
                        sales_ledger = Ledger.objects.filter(company=company, name__icontains='Sales').first()
                        if not sales_ledger:
                            income_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Sales Accounts', defaults={'nature': 'INCOME'})
                            sales_ledger, _ = Ledger.objects.get_or_create(company=company, name='Sales Account', defaults={'group': income_grp, 'ledger_type': 'GENERAL'})

                        cgst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'CGST')
                        sgst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'SGST')
                        igst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'IGST')

                        voucher = SalesInvoiceService.generate_sales_invoice(
                            company=company,
                            user=request.user,
                            party_ledger=party_ledger,
                            items_data=data['items'],
                            sales_ledger=sales_ledger,
                            cgst_ledger=cgst_ledger,
                            sgst_ledger=sgst_ledger,
                            igst_ledger=igst_ledger,
                            manual_voucher_number=manual_vnum,
                            manual_voucher_date=voucher_date
                        )
                    else: # PURCHASE
                        purchase_ledger = Ledger.objects.filter(company=company, name__icontains='Purchase').first()
                        if not purchase_ledger:
                            exp_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Purchase Accounts', defaults={'nature': 'EXPENSE'})
                            purchase_ledger, _ = Ledger.objects.get_or_create(company=company, name='Purchase Account', defaults={'group': exp_grp, 'ledger_type': 'GENERAL'})

                        input_cgst = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'CGST')
                        input_sgst = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'SGST')
                        input_igst = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'IGST')

                        voucher = PurchaseInvoiceService.generate_purchase_invoice(
                            company=company,
                            user=request.user,
                            party_ledger=party_ledger,
                            items_data=data['items'],
                            purchase_ledger=purchase_ledger,
                            input_cgst_ledger=input_cgst,
                            input_sgst_ledger=input_sgst,
                            input_igst_ledger=input_igst,
                            supplier_invoice_number=manual_vnum,
                            voucher_date=voucher_date
                        )

                    # Save attachment if provided (auto-compressed under 2MB)
                    att_data = data.get('attachment_data') or data.get('file_base64')
                    att_mime = data.get('attachment_mime') or data.get('mime_type', 'application/pdf')
                    if att_data:
                        compressed_data, final_mime = compress_and_clean_attachment(att_data, att_mime)
                        voucher.attachment_data = compressed_data
                        voucher.attachment_mime = final_mime
                        voucher.save(update_fields=['attachment_data', 'attachment_mime'])

                    VoucherService.post_voucher(voucher)
                    return Response({
                        "success": True,
                        "message": f"{voucher_type.title()} voucher created and posted successfully.",
                        "id": str(voucher.id),
                        "voucher_number": voucher.voucher_number,
                        "total_amount": str(voucher.total_amount),
                        "has_attachment": bool(voucher.attachment_data)
                    }, status=status.HTTP_201_CREATED)

                # Case 2: Generic Double-Entry Rows (e.g. from AG Grid / Journal)
                entries_data = data.get('entries', data.get('ledger_entries', []))
                if not entries_data:
                    return Response({"success": False, "error": "Either 'items' or 'entries' must be provided."}, status=400)

                from apps.accounting.services.sequence_service import InvoiceSequenceService
                if manual_vnum:
                    v_num = manual_vnum
                    fy = InvoiceSequenceService.get_or_create_active_fy(company, voucher_date)
                else:
                    v_num, fy = InvoiceSequenceService.get_next_number(company, voucher_type, voucher_date)

                voucher = Voucher.objects.create(
                    company=company,
                    financial_year=fy,
                    voucher_type=voucher_type,
                    voucher_number=v_num,
                    voucher_date=voucher_date,
                    narration=narration,
                    status='DRAFT',
                    created_by=request.user
                )

                total_dr = Decimal('0.00')
                total_cr = Decimal('0.00')

                for entry in entries_data:
                    ledger_id = entry.get('ledger_id')
                    ledger = Ledger.objects.get(id=ledger_id, company=company)
                    dr = Decimal(str(entry.get('debit_amount', 0) or 0))
                    cr = Decimal(str(entry.get('credit_amount', 0) or 0))

                    if dr > 0 and cr > 0:
                        raise ValidationError(f"Ledger {ledger.name} cannot have both Debit and Credit amounts.")

                    total_dr += dr
                    total_cr += cr

                    LedgerEntry.objects.create(
                        voucher=voucher,
                        company=company,
                        ledger=ledger,
                        debit_amount=dr,
                        credit_amount=cr,
                        narration=entry.get('narration', '')
                    )

                if total_dr != total_cr:
                    raise ValidationError(f"Double-entry mismatch! Total Debit ({total_dr}) must equal Total Credit ({total_cr}).")
                if total_dr == 0:
                    raise ValidationError("Total voucher amount cannot be 0.00.")

                VoucherService.post_voucher(voucher)

                return Response({
                    "success": True,
                    "message": "Voucher created and posted successfully.",
                    "id": str(voucher.id),
                    "voucher_number": voucher.voucher_number,
                    "total_amount": str(voucher.total_amount)
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class SyncTaxLedgersAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageLedgers]

    def post(self, request, company_id=None):
        try:
            from apps.companies.models import Company
            from apps.accounting.services.sales_service import SalesInvoiceService
            if company_id:
                company = Company.objects.get(id=company_id, users__user=request.user)
                SalesInvoiceService.reassign_misallocated_tax_entries(company)
            else:
                user_companies = Company.objects.filter(users__user=request.user)
                for comp in user_companies:
                    SalesInvoiceService.reassign_misallocated_tax_entries(comp)
            return Response({"success": True, "message": "All Input and Output tax ledgers successfully synchronized."})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, company_id=None):
        return self.post(request, company_id)


class PartyRatesAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id=None):
        """
        Returns the most recent invoiced rates for products sold to (or bought from) a specific party ledger.
        Query params:
          - party_id: UUID of party ledger (required)
          - company_id: UUID of company (optional if in path or user has active company)
          - type: 'SALES' (default) or 'PURCHASE'
        """
        party_id = request.query_params.get('party_id')
        cid = company_id or request.query_params.get('company_id')
        v_type = request.query_params.get('type', 'SALES').upper()

        if not party_id:
            return Response({"success": False, "error": "party_id query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.accounting.models import VoucherItem, Voucher
            from apps.ledgers.models import Ledger
            from apps.companies.models import Company

            if cid:
                company = Company.objects.get(id=cid, users__user=request.user)
            else:
                company = Company.objects.filter(users__user=request.user).first()

            if not company:
                return Response({"success": False, "error": "Company not found."}, status=status.HTTP_400_BAD_REQUEST)

            party_ledger = Ledger.objects.filter(id=party_id, company=company).first()
            if not party_ledger:
                return Response({"success": False, "error": "Party ledger not found."}, status=status.HTTP_404_NOT_FOUND)

            # Query historical voucher items for this party ordered by date desc
            items = VoucherItem.objects.filter(
                voucher__company=company,
                voucher__party_ledger=party_ledger,
                voucher__voucher_type=v_type,
                voucher__status__in=['POSTED', 'VALIDATING', 'DRAFT']
            ).select_related('product', 'voucher').order_by('-voucher__voucher_date', '-voucher__created_at')

            rates_map = {}
            for vi in items:
                if not vi.product:
                    continue
                pid = str(vi.product_id)
                pname = vi.product.name.strip().lower()
                pbrand = (vi.product.brand or '').strip().lower()
                key_brand = f"{pname}|{pbrand}"

                # First seen is the latest due to descending ordering
                if pid not in rates_map:
                    entry = {
                        "product_id": pid,
                        "product_name": vi.product.name,
                        "brand": vi.product.brand or "",
                        "rate": float(vi.rate),
                        "discount_percent": float(vi.discount_percent),
                        "voucher_number": vi.voucher.voucher_number,
                        "voucher_date": vi.voucher.voucher_date.strftime('%Y-%m-%d') if vi.voucher.voucher_date else "",
                        "mrp": float(vi.product.selling_price or 0)
                    }
                    rates_map[pid] = entry
                    if key_brand not in rates_map:
                        rates_map[key_brand] = entry
                    if pname not in rates_map:
                        rates_map[pname] = entry

            return Response({"success": True, "data": rates_map})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class RebuildBalancesAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageLedgers]

    def post(self, request, company_id=None):
        try:
            from apps.companies.models import Company
            from apps.accounting.services.balance_rebuild import BalanceRebuildService
            if company_id:
                company = Company.objects.get(id=company_id, users__user=request.user)
            else:
                company = Company.objects.filter(users__user=request.user).first()
            if not company:
                return Response({"success": False, "error": "Company not found."}, status=status.HTTP_404_NOT_FOUND)

            res = BalanceRebuildService.rebuild_company_ledger_balances(company)
            return Response({
                "success": True,
                "message": f"Successfully recalculated {res['rebuilt_ledgers_count']} ledger balances.",
                "data": res
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


