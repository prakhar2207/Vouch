import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from apps.companies.models import Company
from apps.accounts.permissions import CanCreateSales
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product
from .models_proforma import ProformaInvoice, ProformaItem
from .models import Voucher
from .services.sequence_service import InvoiceSequenceService
from .services.sales_service import SalesInvoiceService
from .services.voucher_service import VoucherService


def get_user_display_name(usr):
    if not usr:
        return "System"
    first = getattr(usr, 'first_name', '') or ''
    last = getattr(usr, 'last_name', '') or ''
    full = f"{first} {last}".strip()
    return full or getattr(usr, 'email', str(usr))


def serialize_proforma(p: ProformaInvoice, include_items: bool = True) -> dict:
    data = {
        "id": str(p.id),
        "company_id": str(p.company_id),
        "financial_year_id": str(p.financial_year_id) if p.financial_year_id else None,
        "proforma_type": p.proforma_type,
        "proforma_number": p.proforma_number,
        "date": p.date.isoformat() if p.date else None,
        "valid_until": p.valid_until.isoformat() if p.valid_until else None,
        "party_ledger_id": str(p.party_ledger_id) if p.party_ledger_id else None,
        "party_name": p.party_ledger.name if p.party_ledger else (p.buyer_name or "Walk-in Customer"),
        "buyer_name": p.buyer_name or "",
        "buyer_address": p.buyer_address or "",
        "buyer_gstin": p.buyer_gstin or "",
        "buyer_state_code": p.buyer_state_code or "",
        "buyer_phone": p.buyer_phone or "",
        "buyer_email": p.buyer_email or "",
        "subtotal": float(p.subtotal or 0),
        "taxable_amount": float(p.taxable_amount or 0),
        "cgst_amount": float(p.cgst_amount or 0),
        "sgst_amount": float(p.sgst_amount or 0),
        "igst_amount": float(p.igst_amount or 0),
        "total_tax": float(p.total_tax or 0),
        "cartage_amount": float(p.cartage_amount or 0),
        "round_off": float(p.round_off or 0),
        "total_amount": float(p.total_amount or 0),
        "customer_notes": p.customer_notes or "",
        "terms_and_conditions": p.terms_and_conditions or "",
        "status": p.status,
        "converted_voucher_id": str(p.converted_voucher_id) if p.converted_voucher_id else None,
        "converted_voucher_number": p.converted_voucher.voucher_number if p.converted_voucher else None,
        "converted_at": p.converted_at.isoformat() if p.converted_at else None,
        "created_by": get_user_display_name(p.created_by),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "items_count": p.items.count() if hasattr(p, 'items') else 0,
    }

    if include_items:
        data["items"] = [
            {
                "id": str(it.id),
                "product_id": str(it.product_id) if it.product_id else None,
                "item_name": it.item_name,
                "hsn_code": it.hsn_code,
                "quantity": float(it.quantity),
                "unit": it.unit,
                "rate": float(it.rate),
                "discount_percent": float(it.discount_percent),
                "taxable_amount": float(it.taxable_amount),
                "gst_rate": float(it.gst_rate),
                "cgst_rate": float(it.cgst_rate),
                "cgst_amount": float(it.cgst_amount),
                "sgst_rate": float(it.sgst_rate),
                "sgst_amount": float(it.sgst_amount),
                "igst_rate": float(it.igst_rate),
                "igst_amount": float(it.igst_amount),
                "total_amount": float(it.total_amount),
            }
            for it in p.items.all()
        ]
    return data


class ListCreateProformaAPIView(APIView):
    permission_classes = [IsAuthenticated, CanCreateSales]

    def get(self, request, company_id=None):
        cid = company_id or request.query_params.get('company_id')
        if not cid:
            return Response({"error": "company_id is required."}, status=400)

        company = Company.objects.filter(id=cid, users__user=request.user).first()
        if not company:
            return Response({"error": "Company not found or unauthorized."}, status=404)

        qs = ProformaInvoice.objects.filter(company=company).select_related(
            'party_ledger', 'converted_voucher', 'created_by'
        ).prefetch_related('items')

        # Filters
        status_filter = request.query_params.get('status', 'ALL').strip().upper()
        if status_filter and status_filter != 'ALL':
            qs = qs.filter(status=status_filter)

        type_filter = request.query_params.get('type', 'ALL').strip().upper()
        if type_filter and type_filter != 'ALL':
            qs = qs.filter(proforma_type=type_filter)

        search_query = request.query_params.get('search', '').strip()
        if search_query:
            qs = qs.filter(
                Q(proforma_number__icontains=search_query) |
                Q(buyer_name__icontains=search_query) |
                Q(party_ledger__name__icontains=search_query) |
                Q(buyer_gstin__icontains=search_query)
            )

        start_date = request.query_params.get('start_date')
        if start_date:
            qs = qs.filter(date__gte=start_date)

        end_date = request.query_params.get('end_date')
        if end_date:
            qs = qs.filter(date__lte=end_date)

        # Summary KPIs across the filtered or full scope
        all_qs = ProformaInvoice.objects.filter(company=company)
        total_count = all_qs.count()
        total_amount = all_qs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')

        active_qs = all_qs.exclude(status__in=['CONVERTED', 'CANCELLED'])
        active_count = active_qs.count()
        active_amount = active_qs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')

        converted_qs = all_qs.filter(status='CONVERTED')
        converted_count = converted_qs.count()
        converted_amount = converted_qs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')

        # Pagination
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))
        filtered_count = qs.count()

        results = qs[offset:offset + limit]

        return Response({
            "success": True,
            "data": [serialize_proforma(p, include_items=False) for p in results],
            "total_count": filtered_count,
            "metrics": {
                "total_count": total_count,
                "total_amount": float(total_amount),
                "active_count": active_count,
                "active_amount": float(active_amount),
                "converted_count": converted_count,
                "converted_amount": float(converted_amount),
            }
        })

    def post(self, request, company_id=None):
        data = request.data
        cid = company_id or data.get('company_id')
        if not cid:
            return Response({"error": "company_id is required."}, status=400)

        company = Company.objects.filter(id=cid, users__user=request.user).first()
        if not company:
            return Response({"error": "Company not found or unauthorized."}, status=404)

        proforma_type = data.get('proforma_type', 'PROFORMA').strip().upper()
        if proforma_type not in ['PROFORMA', 'QUOTATION']:
            proforma_type = 'PROFORMA'

        v_date = data.get('date') or timezone.now().date()
        if isinstance(v_date, str):
            v_date = datetime.date.fromisoformat(v_date.split('T')[0])

        valid_until = data.get('valid_until')
        if valid_until and isinstance(valid_until, str):
            valid_until = datetime.date.fromisoformat(valid_until.split('T')[0])

        # Party
        party_ledger = None
        party_ledger_id = data.get('party_ledger_id')
        if party_ledger_id:
            party_ledger = Ledger.objects.filter(id=party_ledger_id, company=company).first()

        # Sequential document number
        manual_number = data.get('proforma_number', '').strip()
        if manual_number:
            proforma_number = manual_number
            fy = InvoiceSequenceService.get_or_create_active_fy(company, v_date)
        else:
            proforma_number, fy = InvoiceSequenceService.get_next_number(company, proforma_type, v_date)

        # Buyer info
        buyer_name = (data.get('buyer_name') or '').strip()
        buyer_address = (data.get('buyer_address') or '').strip()
        buyer_gstin = (data.get('buyer_gstin') or '').strip().upper()
        buyer_state_code = (data.get('buyer_state_code') or '').strip()
        buyer_phone = (data.get('buyer_phone') or '').strip()
        buyer_email = (data.get('buyer_email') or '').strip()

        if not buyer_name and party_ledger:
            buyer_name = party_ledger.name
        if not buyer_address and party_ledger:
            buyer_address = getattr(party_ledger, 'address', '') or ''
        if not buyer_gstin and party_ledger:
            buyer_gstin = getattr(party_ledger, 'gstin', '') or ''
        if not buyer_state_code and party_ledger:
            buyer_state_code = getattr(party_ledger, 'state_code', '') or ''

        # State code determination for GST
        company_state = (company.gstin[:2] if company.gstin and len(company.gstin) >= 2 else "09")
        target_state = buyer_state_code or (buyer_gstin[:2] if len(buyer_gstin) >= 2 else company_state)
        is_inter_state = (target_state != company_state)

        cartage_amount = Decimal(str(data.get('cartage_amount', '0.00') or '0.00'))

        raw_items = data.get('items', [])
        if not raw_items:
            return Response({"error": "At least one item is required."}, status=400)

        with transaction.atomic():
            proforma = ProformaInvoice.objects.create(
                company=company,
                financial_year=fy,
                proforma_type=proforma_type,
                proforma_number=proforma_number,
                date=v_date,
                valid_until=valid_until,
                party_ledger=party_ledger,
                buyer_name=buyer_name,
                buyer_address=buyer_address,
                buyer_gstin=buyer_gstin,
                buyer_state_code=buyer_state_code or target_state,
                buyer_phone=buyer_phone,
                buyer_email=buyer_email,
                customer_notes=data.get('customer_notes', ''),
                terms_and_conditions=data.get('terms_and_conditions', ''),
                cartage_amount=cartage_amount,
                status='DRAFT',
                created_by=request.user
            )

            total_taxable = Decimal('0.00')
            total_cgst = Decimal('0.00')
            total_sgst = Decimal('0.00')
            total_igst = Decimal('0.00')

            for it in raw_items:
                product = None
                pid = it.get('product_id')
                if pid:
                    product = Product.objects.filter(id=pid, company=company).first()

                name = it.get('item_name') or (product.name if product else "Item")
                hsn = it.get('hsn_code') or (product.hsn_code if product else "")
                qty = Decimal(str(it.get('quantity', 1)))
                unit = it.get('unit') or (product.unit if product else 'PCS')
                rate = Decimal(str(it.get('rate', 0)))
                disc_pct = Decimal(str(it.get('discount_percent', 0)))
                gst_pct = Decimal(str(it.get('gst_rate', product.tax_rate if product else 18)))

                gross = qty * rate
                discount_val = gross * (disc_pct / Decimal('100.00'))
                taxable = gross - discount_val

                if is_inter_state:
                    cgst_r = Decimal('0.00')
                    cgst_a = Decimal('0.00')
                    sgst_r = Decimal('0.00')
                    sgst_a = Decimal('0.00')
                    igst_r = gst_pct
                    igst_a = taxable * (igst_r / Decimal('100.00'))
                else:
                    cgst_r = gst_pct / Decimal('2.00')
                    cgst_a = taxable * (cgst_r / Decimal('100.00'))
                    sgst_r = cgst_r
                    sgst_a = taxable * (sgst_r / Decimal('100.00'))
                    igst_r = Decimal('0.00')
                    igst_a = Decimal('0.00')

                line_total = taxable + cgst_a + sgst_a + igst_a

                ProformaItem.objects.create(
                    proforma=proforma,
                    product=product,
                    item_name=name,
                    hsn_code=hsn,
                    quantity=qty,
                    unit=unit,
                    rate=rate,
                    discount_percent=disc_pct,
                    taxable_amount=taxable,
                    gst_rate=gst_pct,
                    cgst_rate=cgst_r,
                    cgst_amount=cgst_a,
                    sgst_rate=sgst_r,
                    sgst_amount=sgst_a,
                    igst_rate=igst_r,
                    igst_amount=igst_a,
                    total_amount=line_total
                )

                total_taxable += taxable
                total_cgst += cgst_a
                total_sgst += sgst_a
                total_igst += igst_a

            total_tax = total_cgst + total_sgst + total_igst
            gross_invoice_val = total_taxable + total_tax + cartage_amount
            rounded_total = gross_invoice_val.quantize(Decimal('1.00'))
            round_off = rounded_total - gross_invoice_val

            proforma.subtotal = total_taxable
            proforma.taxable_amount = total_taxable
            proforma.cgst_amount = total_cgst
            proforma.sgst_amount = total_sgst
            proforma.igst_amount = total_igst
            proforma.total_tax = total_tax
            proforma.round_off = round_off
            proforma.total_amount = rounded_total
            proforma.save()

        # If user requested 1-click conversion immediately upon creation
        if data.get('convert_immediately'):
            conv_resp = ConvertProformaToInvoiceAPIView.convert_proforma(proforma, request.user)
            return Response({
                "success": True,
                "message": f"{proforma_type} created and converted to GST Tax Invoice {conv_resp['voucher_number']}!",
                "data": serialize_proforma(proforma, include_items=True),
                "conversion": conv_resp
            }, status=status.HTTP_201_CREATED)

        return Response({
            "success": True,
            "message": f"{proforma_type} {proforma.proforma_number} created successfully.",
            "data": serialize_proforma(proforma, include_items=True)
        }, status=status.HTTP_201_CREATED)


class ProformaDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, CanCreateSales]

    def get(self, request, pk):
        proforma = ProformaInvoice.objects.filter(
            id=pk, company__users__user=request.user
        ).select_related('company', 'party_ledger', 'converted_voucher', 'created_by').first()
        if not proforma:
            return Response({"error": "Proforma invoice not found."}, status=404)

        data = serialize_proforma(proforma, include_items=True)
        # Add company billing meta for print layout
        data["company_details"] = {
            "name": proforma.company.name,
            "gstin": proforma.company.gstin,
            "pan": getattr(proforma.company, 'pan', ''),
            "email": getattr(proforma.company, 'email', ''),
            "phone": getattr(proforma.company, 'phone', ''),
            "address": getattr(proforma.company, 'address', ''),
            "bank_details": {
                "bank_name": getattr(proforma.company, 'bank_name', ''),
                "account_number": getattr(proforma.company, 'bank_account_number', ''),
                "ifsc": getattr(proforma.company, 'bank_ifsc', ''),
                "branch": getattr(proforma.company, 'bank_branch', ''),
            }
        }
        return Response({"success": True, "data": data})

    def put(self, request, pk):
        proforma = ProformaInvoice.objects.filter(
            id=pk, company__users__user=request.user
        ).first()
        if not proforma:
            return Response({"error": "Proforma invoice not found."}, status=404)

        if proforma.status == 'CONVERTED':
            return Response({"error": "Cannot edit a proforma invoice that has already been converted to a GST Tax Invoice."}, status=400)

        data = request.data
        with transaction.atomic():
            if 'status' in data and data['status'] in ['DRAFT', 'SENT', 'ACCEPTED', 'CANCELLED']:
                proforma.status = data['status']
            if 'customer_notes' in data:
                proforma.customer_notes = data['customer_notes']
            if 'terms_and_conditions' in data:
                proforma.terms_and_conditions = data['terms_and_conditions']
            if 'valid_until' in data:
                proforma.valid_until = data['valid_until']
            proforma.save()

        return Response({"success": True, "message": "Updated successfully.", "data": serialize_proforma(proforma, include_items=True)})

    def delete(self, request, pk):
        proforma = ProformaInvoice.objects.filter(
            id=pk, company__users__user=request.user
        ).first()
        if not proforma:
            return Response({"error": "Proforma invoice not found."}, status=404)

        if proforma.status == 'CONVERTED':
            return Response({"error": "Cannot delete a proforma invoice that has been converted to an official GST Tax Invoice."}, status=400)

        p_num = proforma.proforma_number
        proforma.delete()
        return Response({"success": True, "message": f"Proforma {p_num} deleted."})


class ConvertProformaToInvoiceAPIView(APIView):
    """
    1-Click Convert Proforma / Quotation to GST Sales Invoice.
    Takes an existing ProformaInvoice, maps all lines, rates, buyer details,
    generates a real Voucher(voucher_type='SALES'), and links them together.
    """
    permission_classes = [IsAuthenticated, CanCreateSales]

    @classmethod
    def convert_proforma(cls, proforma: ProformaInvoice, user, custom_date=None) -> dict:
        if proforma.status == 'CONVERTED':
            raise ValidationError("This document has already been converted to a GST Tax Invoice.")

        company = proforma.company

        # 1. Resolve Party Ledger
        party_ledger = proforma.party_ledger
        if not party_ledger:
            # Check if there is an existing ledger matching buyer name
            if proforma.buyer_name:
                party_ledger = Ledger.objects.filter(
                    company=company,
                    name__iexact=proforma.buyer_name.strip()
                ).first()

            if not party_ledger:
                # Find Sundry Debtors ledger or Cash customer
                debtors_group = LedgerGroup.objects.filter(
                    company=company,
                    name__icontains='Sundry Debtors'
                ).first()
                if not debtors_group:
                    debtors_group, _ = LedgerGroup.objects.get_or_create(
                        company=company,
                        name='Sundry Debtors',
                        defaults={'nature': 'ASSET'}
                    )
                party_ledger = Ledger.objects.filter(
                    company=company,
                    group=debtors_group
                ).first() or Ledger.objects.filter(
                    company=company,
                    ledger_type='PARTY'
                ).first()

            if not party_ledger:
                party_ledger, _ = Ledger.objects.get_or_create(
                    company=company,
                    name=proforma.buyer_name or "Cash Sales Customer",
                    defaults={
                        'group': debtors_group,
                        'gstin': proforma.buyer_gstin or '',
                        'state_code': proforma.buyer_state_code or '',
                        'address': proforma.buyer_address or '',
                    }
                )

        # 2. Build items payload for SalesInvoiceService
        items_data = []
        for it in proforma.items.all():
            items_data.append({
                'product_id': str(it.product_id) if it.product_id else None,
                'item_name': it.item_name,
                'hsn_code': it.hsn_code,
                'quantity': float(it.quantity),
                'unit': it.unit,
                'rate': float(it.rate),
                'discount_percent': float(it.discount_percent),
                'gst_rate': float(it.gst_rate),
            })

        voucher_date = custom_date or timezone.now().date()
        if isinstance(voucher_date, str):
            voucher_date = datetime.date.fromisoformat(voucher_date.split('T')[0])

        with transaction.atomic():
            # 3. Generate Sales Invoice using core SalesInvoiceService
            voucher = SalesInvoiceService.generate_sales_invoice(
                company=company,
                user=user,
                party_ledger=party_ledger,
                items_data=items_data,
                sales_ledger=proforma.sales_ledger,
                cgst_ledger=proforma.cgst_ledger,
                sgst_ledger=proforma.sgst_ledger,
                igst_ledger=proforma.igst_ledger,
                manual_voucher_date=voucher_date,
                buyer_name=proforma.buyer_name,
                buyer_address=proforma.buyer_address,
                buyer_gstin=proforma.buyer_gstin,
                buyer_state_code=proforma.buyer_state_code,
                buyer_phone=proforma.buyer_phone,
                cartage_amount=proforma.cartage_amount
            )

            # Link reference
            voucher.reference_number = proforma.proforma_number
            voucher.narration = f"Converted from {proforma.proforma_type} {proforma.proforma_number}. {voucher.narration or ''}".strip()
            voucher.save(update_fields=['reference_number', 'narration'])

            # 4. Post the voucher to make it active, generate accounting lines & stock effects
            try:
                VoucherService.post_voucher(voucher, process_stock=True)
            except (ValidationError, DjangoValidationError) as ve:
                if "Insufficient stock" in str(ve):
                    # Gracefully post financial accounting entries without stock reduction
                    VoucherService.post_voucher(voucher, process_stock=False)
                    voucher.narration = f"{voucher.narration or ''} (Stock deduction pending: insufficient quantity at conversion)".strip()
                    voucher.save(update_fields=['narration'])
                else:
                    raise ve

            # 5. Update Proforma status & source link
            proforma.status = 'CONVERTED'
            proforma.converted_voucher = voucher
            proforma.converted_at = timezone.now()
            proforma.save(update_fields=['status', 'converted_voucher', 'converted_at'])

        return {
            "voucher_id": str(voucher.id),
            "voucher_number": voucher.voucher_number,
            "total_amount": float(voucher.total_amount),
            "proforma_id": str(proforma.id),
            "proforma_number": proforma.proforma_number,
        }

    def post(self, request, pk):
        proforma = ProformaInvoice.objects.filter(
            id=pk, company__users__user=request.user
        ).first()
        if not proforma:
            return Response({"error": "Proforma invoice not found."}, status=404)

        try:
            custom_date = request.data.get('invoice_date')
            result = self.convert_proforma(proforma, request.user, custom_date)
            return Response({
                "success": True,
                "message": f"Successfully converted {proforma.proforma_number} into GST Tax Invoice {result['voucher_number']}!",
                "data": result
            })
        except Exception as e:
            return Response({"error": str(e)}, status=400)
