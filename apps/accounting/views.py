from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.exceptions import ValidationError
from django.db import transaction

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
            company = Company.objects.get(id=data['company_id'], users__user=request.user)
            party_ledger = Ledger.objects.get(id=data['party_ledger_id'], company=company)
            sales_ledger = Ledger.objects.get(id=data['sales_ledger_id'], company=company)
            cgst_ledger = Ledger.objects.get(id=data['cgst_ledger_id'], company=company)
            sgst_ledger = Ledger.objects.get(id=data['sgst_ledger_id'], company=company)
            igst_ledger = Ledger.objects.get(id=data['igst_ledger_id'], company=company)
            
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
            company = Company.objects.get(id=data['company_id'], users__user=request.user)
            party_ledger = Ledger.objects.get(id=data['party_ledger_id'], company=company)
            purchase_ledger = Ledger.objects.get(id=data['purchase_ledger_id'], company=company)
            cgst_ledger = Ledger.objects.get(id=data['input_cgst_ledger_id'], company=company)
            sgst_ledger = Ledger.objects.get(id=data['input_sgst_ledger_id'], company=company)
            igst_ledger = Ledger.objects.get(id=data['input_igst_ledger_id'], company=company)
            
            with transaction.atomic():
                voucher = PurchaseInvoiceService.generate_purchase_invoice(
                    company=company,
                    user=request.user,
                    party_ledger=party_ledger,
                    items_data=data['items'],
                    purchase_ledger=purchase_ledger,
                    input_cgst_ledger=cgst_ledger,
                    input_sgst_ledger=sgst_ledger,
                    input_igst_ledger=igst_ledger,
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
                    "product_name": item.product.name,
                    "hsn_code": item.product.hsn_code,
                    "quantity": item.quantity,
                    "unit": item.product.unit,
                    "rate": item.rate,
                    "discount_percent": item.discount_percent,
                    "discount_amount": item.discount_amount,
                    "taxable_amount": item.taxable_amount,
                    "gst_rate": item.gst_rate,
                    "total_amount": item.total_amount
                })
            
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
                    "proprietor_signature": voucher.company.proprietor_signature.url if voucher.company.proprietor_signature else None,
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

