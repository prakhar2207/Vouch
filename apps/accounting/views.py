from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from .services.sales_service import SalesInvoiceService
from .services.voucher_service import VoucherService
from .services.purchase_service import PurchaseInvoiceService
from .services.report_service import ReportService

class CreateSalesInvoiceAPIView(APIView):
    permission_classes = [IsAuthenticated]

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
            if not cgst_ledger:
                cgst_ledger = Ledger.objects.filter(company=company, name__iexact='Output CGST').first() or \
                              Ledger.objects.filter(company=company, name__iexact='CGST').first() or \
                              Ledger.objects.filter(company=company, name__icontains='CGST').first()
                if not cgst_ledger:
                    cgst_ledger, _ = Ledger.objects.get_or_create(company=company, name='Output CGST', defaults={'group': get_or_create_duties_grp(), 'ledger_type': 'TAX'})

            sgst_ledger = None
            sgst_id = data.get('sgst_ledger_id')
            if sgst_id and str(sgst_id).strip():
                try:
                    sgst_ledger = Ledger.objects.filter(id=sgst_id, company=company).first()
                except Exception:
                    sgst_ledger = None
            if not sgst_ledger:
                sgst_ledger = Ledger.objects.filter(company=company, name__iexact='Output SGST').first() or \
                              Ledger.objects.filter(company=company, name__iexact='SGST').first() or \
                              Ledger.objects.filter(company=company, name__icontains='SGST').first()
                if not sgst_ledger:
                    sgst_ledger, _ = Ledger.objects.get_or_create(company=company, name='Output SGST', defaults={'group': get_or_create_duties_grp(), 'ledger_type': 'TAX'})

            igst_ledger = None
            igst_id = data.get('igst_ledger_id')
            if igst_id and str(igst_id).strip():
                try:
                    igst_ledger = Ledger.objects.filter(id=igst_id, company=company).first()
                except Exception:
                    igst_ledger = None
            if not igst_ledger:
                igst_ledger = Ledger.objects.filter(company=company, name__iexact='Output IGST').first() or \
                              Ledger.objects.filter(company=company, name__iexact='IGST').first() or \
                              Ledger.objects.filter(company=company, name__icontains='IGST').first()
                if not igst_ledger:
                    igst_ledger, _ = Ledger.objects.get_or_create(company=company, name='Output IGST', defaults={'group': get_or_create_duties_grp(), 'ledger_type': 'TAX'})
            
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
                    manual_voucher_date=data.get('voucher_date')
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
    permission_classes = [IsAuthenticated]

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
            if not input_cgst:
                input_cgst = Ledger.objects.filter(company=company, name__iexact='Input CGST').first() or \
                             Ledger.objects.filter(company=company, name__iexact='CGST').first() or \
                             Ledger.objects.filter(company=company, name__icontains='CGST').first()
                if not input_cgst:
                    input_cgst, _ = Ledger.objects.get_or_create(company=company, name='Input CGST', defaults={'group': get_or_create_purchase_duties_grp(), 'ledger_type': 'TAX'})

            input_sgst = None
            input_sgst_id = data.get('input_sgst_ledger_id') or data.get('sgst_ledger_id')
            if input_sgst_id and str(input_sgst_id).strip():
                try:
                    input_sgst = Ledger.objects.filter(id=input_sgst_id, company=company).first()
                except Exception:
                    input_sgst = None
            if not input_sgst:
                input_sgst = Ledger.objects.filter(company=company, name__iexact='Input SGST').first() or \
                             Ledger.objects.filter(company=company, name__iexact='SGST').first() or \
                             Ledger.objects.filter(company=company, name__icontains='SGST').first()
                if not input_sgst:
                    input_sgst, _ = Ledger.objects.get_or_create(company=company, name='Input SGST', defaults={'group': get_or_create_purchase_duties_grp(), 'ledger_type': 'TAX'})

            input_igst = None
            input_igst_id = data.get('input_igst_ledger_id') or data.get('igst_ledger_id')
            if input_igst_id and str(input_igst_id).strip():
                try:
                    input_igst = Ledger.objects.filter(id=input_igst_id, company=company).first()
                except Exception:
                    input_igst = None
            if not input_igst:
                input_igst = Ledger.objects.filter(company=company, name__iexact='Input IGST').first() or \
                             Ledger.objects.filter(company=company, name__iexact='IGST').first() or \
                             Ledger.objects.filter(company=company, name__icontains='IGST').first()
                if not input_igst:
                    input_igst, _ = Ledger.objects.get_or_create(company=company, name='Input IGST', defaults={'group': get_or_create_purchase_duties_grp(), 'ledger_type': 'TAX'})
            
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
                    voucher_date=data.get('voucher_date')
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
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            tb = ReportService.generate_trial_balance(company)
            return Response({"success": True, "data": tb})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ListVouchersAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, company_id):
        try:
            from apps.accounting.models import Voucher
            company = Company.objects.get(id=company_id, users__user=request.user)
            vouchers = Voucher.objects.filter(company=company)
            v_type = request.query_params.get('type')
            if v_type:
                vouchers = vouchers.filter(voucher_type=v_type)
            vouchers = vouchers.order_by('-voucher_date')[:50]
            data = [
                {
                    "id": str(v.id),
                    "voucher_number": v.reference_number if (v.voucher_type == 'PURCHASE' and v.reference_number and not v.voucher_number.startswith('G/')) else v.voucher_number,
                    "reference_number": v.reference_number,
                    "type": v.voucher_type,
                    "date": v.voucher_date.strftime('%Y-%m-%d'),
                    "status": v.status,
                    "total_amount": v.total_amount,
                    "has_attachment": bool(v.attachment_data),
                    "party_name": v.party_ledger.name if v.party_ledger else "N/A"
                } for v in vouchers
            ]
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class VoucherDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
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
            
            sig_data = getattr(voucher.company, 'signature_data', None)
            if not sig_data and voucher.company.proprietor_signature:
                try:
                    import os, base64
                    sig_path = voucher.company.proprietor_signature.path
                    if os.path.exists(sig_path):
                        with open(sig_path, 'rb') as f:
                            raw = f.read()
                            b64 = base64.b64encode(raw).decode('utf-8')
                            sig_data = f"data:image/png;base64,{b64}"
                            voucher.company.signature_data = sig_data
                            voucher.company.save(update_fields=['signature_data'])
                except Exception:
                    pass
                if not sig_data:
                    sig_data = voucher.company.proprietor_signature.url

            data = {
                "id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "type": voucher.voucher_type,
                "date": voucher.voucher_date.strftime('%Y-%m-%d'),
                "status": voucher.status,
                "total_amount": voucher.total_amount,
                "narration": voucher.narration,
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
                "party": {
                    "name": voucher.party_ledger.name if voucher.party_ledger else "N/A",
                    "address": voucher.party_ledger.address if voucher.party_ledger else "",
                    "gstin": voucher.party_ledger.gstin if voucher.party_ledger else "",
                    "state_code": voucher.party_ledger.state_code if voucher.party_ledger else "",
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
            from apps.accounting.services.sequence_service import InvoiceSequenceService
            from apps.ledgers.models import Ledger
            
            voucher = Voucher.objects.filter(id=voucher_id, company__users__user=request.user).first()
            if not voucher:
                return Response({
                    "success": False, 
                    "error": "Voucher not found or you do not have permission to delete it."
                }, status=status.HTTP_404_NOT_FOUND)

            with transaction.atomic():
                company = voucher.company
                financial_year = voucher.financial_year
                voucher_type = voucher.voucher_type
                product_ids = list(voucher.items.values_list('product_id', flat=True))
                voucher_num = voucher.voucher_number
                
                # Track all affected ledgers (party ledger + any ledger referenced in ledger entries)
                affected_ledger_ids = set(voucher.ledger_entries.values_list('ledger_id', flat=True))
                if voucher.party_ledger_id:
                    affected_ledger_ids.add(voucher.party_ledger_id)

                # If voucher is posted or validating, safely cancel & reverse accounting/stock first
                if voucher.status in ['POSTED', 'VALIDATING']:
                    VoucherService.cancel_voucher(voucher, user=request.user)
                
                # Delete voucher (cascades items, ledger_entries, and EDI requests)
                voucher.delete()
                
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

                # Resync sequence counter so deleted vouchers roll back sequence
                if financial_year:
                    InvoiceSequenceService.resync_sequence(company, financial_year, voucher_type)

            return Response({
                "success": True, 
                "message": f"Invoice #{voucher_num} deleted and reversed successfully."
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, voucher_id):
        try:
            from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
            from apps.accounting.services.voucher_service import VoucherService
            from apps.inventory.models import Product, ProductCategory
            from apps.gst.services.gst_calculator import GSTCalculator
            from decimal import Decimal

            voucher = Voucher.objects.select_related('company', 'party_ledger').get(
                id=voucher_id, 
                company__users__user=request.user
            )
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
                                selling_price=rate if voucher.voucher_type == 'SALES' else rate * Decimal('1.25')
                            )
                        else:
                            if item_brand and not product.brand:
                                product.brand = item_brand
                            if not product.category and category:
                                product.category = category
                            if voucher.voucher_type == 'PURCHASE' and net_rate > Decimal('0.00'):
                                product.purchase_price = net_rate
                                product.purchase_price_from_invoice = True
                            elif voucher.voucher_type == 'SALES' and rate > Decimal('0.00'):
                                product.selling_price = rate
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

                    # Apply Round Off calculation
                    unrounded_total = total_invoice_value
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
                            ledger=sales_ledger,
                            debit_amount=Decimal('0.00'),
                            credit_amount=total_taxable_value
                        )

                        tax_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Duties & Taxes', defaults={'nature': 'LIABILITY'})
                        if total_cgst > 0:
                            output_cgst, _ = Ledger.objects.get_or_create(company=company, name='Output CGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, ledger=output_cgst, debit_amount=Decimal('0.00'), credit_amount=total_cgst)
                        if total_sgst > 0:
                            output_sgst, _ = Ledger.objects.get_or_create(company=company, name='Output SGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, ledger=output_sgst, debit_amount=Decimal('0.00'), credit_amount=total_sgst)
                        if total_igst > 0:
                            output_igst, _ = Ledger.objects.get_or_create(company=company, name='Output IGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, ledger=output_igst, debit_amount=Decimal('0.00'), credit_amount=total_igst)

                        if round_off != Decimal('0.00'):
                            from apps.accounting.services.sales_service import SalesInvoiceService
                            round_off_ledger = SalesInvoiceService._get_or_create_round_off_ledger(company)
                            if round_off < Decimal('0.00'):
                                LedgerEntry.objects.create(voucher=voucher, ledger=round_off_ledger, debit_amount=abs(round_off), credit_amount=Decimal('0.00'))
                            else:
                                LedgerEntry.objects.create(voucher=voucher, ledger=round_off_ledger, debit_amount=Decimal('0.00'), credit_amount=round_off)

                    else:
                        # PURCHASE Voucher
                        if party_ledger:
                            LedgerEntry.objects.create(
                                voucher=voucher,
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
                            ledger=purchase_ledger,
                            debit_amount=total_taxable_value,
                            credit_amount=Decimal('0.00')
                        )

                        tax_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Duties & Taxes', defaults={'nature': 'LIABILITY'})
                        if total_cgst > 0:
                            input_cgst, _ = Ledger.objects.get_or_create(company=company, name='Input CGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, ledger=input_cgst, debit_amount=total_cgst, credit_amount=Decimal('0.00'))
                        if total_sgst > 0:
                            input_sgst, _ = Ledger.objects.get_or_create(company=company, name='Input SGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, ledger=input_sgst, debit_amount=total_sgst, credit_amount=Decimal('0.00'))
                        if total_igst > 0:
                            input_igst, _ = Ledger.objects.get_or_create(company=company, name='Input IGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                            LedgerEntry.objects.create(voucher=voucher, ledger=input_igst, debit_amount=total_igst, credit_amount=Decimal('0.00'))

                        if round_off != Decimal('0.00'):
                            from apps.accounting.services.purchase_service import PurchaseInvoiceService
                            round_off_ledger = PurchaseInvoiceService._get_or_create_round_off_ledger(company)
                            if round_off > Decimal('0.00'):
                                LedgerEntry.objects.create(voucher=voucher, ledger=round_off_ledger, debit_amount=round_off, credit_amount=Decimal('0.00'))
                            else:
                                LedgerEntry.objects.create(voucher=voucher, ledger=round_off_ledger, debit_amount=Decimal('0.00'), credit_amount=abs(round_off))

                    # 5. Re-post voucher to update stock & balances
                    VoucherService.post_voucher(voucher)
                else:
                    voucher.save()

            return Response({"success": True, "message": f"{voucher.voucher_type.title()} invoice updated successfully."})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class LedgerStatementAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, company_id, ledger_id):
        try:
            from apps.accounting.models import LedgerEntry
            company = Company.objects.get(id=company_id, users__user=request.user)
            ledger = Ledger.objects.get(id=ledger_id, company=company)
            
            entries = LedgerEntry.objects.filter(ledger=ledger).select_related('voucher').order_by('voucher__voucher_date', 'created_at')
            
            data = [
                {
                    "id": str(e.id),
                    "date": e.voucher.voucher_date.strftime('%Y-%m-%d') if e.voucher else None,
                    "voucher_number": e.voucher.voucher_number if e.voucher else "Opening Balance",
                    "voucher_type": e.voucher.voucher_type if e.voucher else "-",
                    "narration": e.narration,
                    "debit": e.debit_amount,
                    "credit": e.credit_amount,
                } for e in entries
            ]
            
            return Response({
                "success": True, 
                "data": {
                    "ledger_name": ledger.name,
                    "current_balance": ledger.current_balance,
                    "opening_balance": ledger.opening_balance,
                    "opening_balance_type": ledger.opening_balance_type,
                    "entries": data
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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.accounting.models import Voucher, LedgerEntry
        from datetime import date
        import uuid as uuid_lib

        data = request.data
        try:
            company = Company.objects.get(id=data['company_id'], users__user=request.user)
            party_ledger = Ledger.objects.get(id=data['party_ledger_id'], company=company)
            payment_ledger = Ledger.objects.get(id=data['payment_ledger_id'], company=company)
            
            voucher_type = data.get('voucher_type', 'RECEIPT')
            if voucher_type not in ('PAYMENT', 'RECEIPT'):
                return Response({"success": False, "error": "voucher_type must be PAYMENT or RECEIPT"}, status=400)
            
            amount = abs(float(data.get('amount', 0)))
            if amount <= 0:
                return Response({"success": False, "error": "Amount must be greater than 0"}, status=400)
            
            voucher_date_str = data.get('voucher_date')
            voucher_date = date.fromisoformat(voucher_date_str) if voucher_date_str else date.today()

            # Generate voucher number
            prefix = 'PAY' if voucher_type == 'PAYMENT' else 'REC'
            count = Voucher.objects.filter(company=company, voucher_type=voucher_type).count() + 1
            voucher_number = f"{prefix}-{count:04d}"

            with transaction.atomic():
                voucher = Voucher.objects.create(
                    company=company,
                    voucher_type=voucher_type,
                    voucher_number=voucher_number,
                    voucher_date=voucher_date,
                    party_ledger=party_ledger,
                    narration=data.get('narration', ''),
                    status='DRAFT',
                    total_amount=amount,
                    created_by=request.user,
                )

                if voucher_type == 'RECEIPT':
                    # Receipt: Debit Cash/Bank, Credit Customer
                    LedgerEntry.objects.create(voucher=voucher, ledger=payment_ledger, debit_amount=amount, credit_amount=0, narration=f"Receipt from {party_ledger.name}")
                    LedgerEntry.objects.create(voucher=voucher, ledger=party_ledger, debit_amount=0, credit_amount=amount, narration=f"Receipt via {payment_ledger.name}")
                else:
                    # Payment: Debit Supplier, Credit Cash/Bank
                    LedgerEntry.objects.create(voucher=voucher, ledger=party_ledger, debit_amount=amount, credit_amount=0, narration=f"Payment via {payment_ledger.name}")
                    LedgerEntry.objects.create(voucher=voucher, ledger=payment_ledger, debit_amount=0, credit_amount=amount, narration=f"Payment to {party_ledger.name}")

                # Auto-post
                VoucherService.post_voucher(voucher)

            return Response({
                "success": True,
                "message": f"{voucher_type.title()} Voucher posted successfully.",
                "voucher_number": voucher.voucher_number,
                "amount": amount,
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ListPaymentReceiptAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        try:
            from apps.accounting.models import Voucher
            company = Company.objects.get(id=company_id, users__user=request.user)
            
            voucher_type = request.query_params.get('type')  # PAYMENT or RECEIPT or None for both
            
            qs = Voucher.objects.filter(company=company, voucher_type__in=['PAYMENT', 'RECEIPT']).select_related('party_ledger').order_by('-voucher_date', '-created_at')
            
            if voucher_type in ('PAYMENT', 'RECEIPT'):
                qs = qs.filter(voucher_type=voucher_type)
            
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
                } for v in qs
            ]
            return Response({"success": True, "data": data})
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
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id=None):
        try:
            from apps.accounting.models import Voucher
            if not company_id:
                company = Company.objects.filter(users__user=request.user).first()
            else:
                company = Company.objects.get(id=company_id, users__user=request.user)

            if not company:
                return Response({"success": False, "error": "Company not found"}, status=404)

            v_type = request.query_params.get('type')
            qs = Voucher.objects.filter(company=company).select_related('party_ledger').order_by('-voucher_date', '-created_at')
            if v_type:
                qs = qs.filter(voucher_type=v_type.upper())

            data = [
                {
                    "id": str(v.id),
                    "voucher_number": v.voucher_number,
                    "type": v.voucher_type,
                    "date": v.voucher_date.strftime('%Y-%m-%d'),
                    "status": v.status,
                    "total_amount": str(v.total_amount),
                    "party_name": v.party_ledger.name if v.party_ledger else "General Entry",
                    "narration": v.narration or "",
                    "has_attachment": bool(v.attachment_data),
                    "attachment_mime": v.attachment_mime,
                } for v in qs
            ]
            return Response({"success": True, "data": data})
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

                        tax_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Duties & Taxes', defaults={'nature': 'LIABILITY'})
                        cgst_ledger, _ = Ledger.objects.get_or_create(company=company, name='Output CGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                        sgst_ledger, _ = Ledger.objects.get_or_create(company=company, name='Output SGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                        igst_ledger, _ = Ledger.objects.get_or_create(company=company, name='Output IGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})

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

                        tax_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Duties & Taxes', defaults={'nature': 'LIABILITY'})
                        input_cgst, _ = Ledger.objects.get_or_create(company=company, name='Input CGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                        input_sgst, _ = Ledger.objects.get_or_create(company=company, name='Input SGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})
                        input_igst, _ = Ledger.objects.get_or_create(company=company, name='Input IGST', defaults={'group': tax_grp, 'ledger_type': 'TAX'})

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

