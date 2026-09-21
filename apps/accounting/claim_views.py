import logging
import urllib.parse
from decimal import Decimal
from django.http import HttpResponse
from django.db import transaction
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounting.models import Voucher, InwardVoucherRequest
from apps.companies.models import Company, UserCompany, CompanySettings
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Warehouse
from apps.accounting.services.invoice_pdf_service import InvoicePDFService
from apps.accounting.services.invoice_notification_service import (
    InvoiceNotificationService,
    CLAIM_TOKEN_SALT,
)
from apps.accounting.services.edi_service import EDIService

User = get_user_model()
logger = logging.getLogger(__name__)


class InvoiceClaimPreviewAPIView(APIView):
    """
    Public preview endpoint for counterparties who received a WhatsApp / Email invoice link.
    Decodes the claim token and returns bill details along with pre-filled onboarding fields.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        token = request.query_params.get('token', '').strip()
        if not token:
            return Response({'error': 'Claim token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = InvoiceNotificationService.verify_claim_token(token)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        voucher_id = payload.get('voucher_id')
        try:
            voucher = Voucher.objects.select_related('company', 'party_ledger').prefetch_related('items__product').get(id=voucher_id)
        except Voucher.DoesNotExist:
            return Response({'error': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)

        items_data = []
        for itm in voucher.items.all():
            items_data.append({
                'product_name': itm.product.name if itm.product else (getattr(itm, 'description', '') or 'Item'),
                'hsn_code': itm.hsn_code or (itm.product.hsn_code if itm.product else ''),
                'quantity': float(itm.quantity),
                'unit': (itm.product.unit if itm.product else getattr(itm, 'unit', '')) or 'PCS',
                'rate': float(getattr(itm, 'rate', getattr(itm, 'unit_price', Decimal('0.00')))),
                'taxable_amount': float(itm.taxable_amount),
                'gst_rate': float(itm.cgst_rate + itm.sgst_rate + itm.igst_rate),
                'total_amount': float(itm.total_amount),
            })


        return Response({
            'voucher_id': str(voucher.id),
            'voucher_number': voucher.voucher_number,
            'voucher_date': voucher.voucher_date.isoformat() if voucher.voucher_date else '',
            'total_amount': float(voucher.total_amount),
            'seller': {
                'id': str(voucher.company.id),
                'name': voucher.company.name,
                'legal_name': voucher.company.legal_name or voucher.company.name,
                'gstin': voucher.company.gstin or '',
                'state_code': voucher.company.state_code or '',
                'city': voucher.company.city or '',
            },
            'buyer_prefill': {
                'name': payload.get('buyer_name') or '',
                'gstin': payload.get('buyer_gstin') or '',
                'phone': payload.get('buyer_phone') or '',
                'email': payload.get('buyer_email') or '',
            },
            'items': items_data,
            'token': token
        })


class InvoicePDFDownloadAPIView(APIView):
    """
    Renders and streams the official GST Tax Invoice PDF.
    Accessible if:
      - Valid claim token provided in ?token=...
      - User is logged in via Bearer header or ?auth_token=... and has access to company
    """
    permission_classes = [AllowAny]

    def get(self, request, voucher_id, *args, **kwargs):
        token = request.query_params.get('token', '').strip()
        auth_token = request.query_params.get('auth_token', '').strip()

        try:
            voucher = Voucher.objects.select_related('company', 'party_ledger').prefetch_related('items__product').get(id=voucher_id)
        except Voucher.DoesNotExist:
            return Response({'error': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Authorization: either valid claim token, authenticated user session, or valid JWT auth_token in query
        authorized = False
        if token:
            try:
                payload = InvoiceNotificationService.verify_claim_token(token)
                if str(payload.get('voucher_id')) == str(voucher.id):
                    authorized = True
            except Exception:
                pass

        if not authorized and request.user.is_authenticated:
            if UserCompany.objects.filter(company=voucher.company, user=request.user).exists():
                authorized = True

        if not authorized and auth_token:
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                from django.contrib.auth import get_user_model
                User = get_user_model()
                decoded = AccessToken(auth_token)
                user_id = decoded['user_id']
                jwt_user = User.objects.get(id=user_id)
                if UserCompany.objects.filter(company=voucher.company, user=jwt_user).exists():
                    authorized = True
            except Exception as e:
                logger.warning(f"Could not validate auth_token for PDF download: {e}")

        if not authorized:
            return Response({'error': 'Unauthorized to view this invoice PDF.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            pdf_bytes = InvoicePDFService.generate_invoice_pdf(voucher)
            sanitized_num = voucher.voucher_number.replace('/', '_').replace('-', '_')
            filename = f"Tax_Invoice_{sanitized_num}.pdf"

            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            # Check if download or inline preview requested
            as_attachment = request.query_params.get('download', 'false').lower() == 'true'
            disp = 'attachment' if as_attachment else 'inline'
            response['Content-Disposition'] = f'{disp}; filename="{filename}"'
            return response
        except Exception as e:
            logger.exception("Failed to render invoice PDF")
            return Response({'error': f"PDF generation failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InvoiceClaimRegisterAPIView(APIView):
    """
    Viral Onboarding: When an unregistered counterparty receives an invoice,
    they can register their company with pre-filled GSTIN, and the invoice is
    automatically routed into their EDI Inbox (/network/inbox) ready for 1-click booking.
    """
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        token = request.data.get('token', '').strip()
        if not token:
            return Response({'error': 'Claim token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = InvoiceNotificationService.verify_claim_token(token)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        voucher_id = payload.get('voucher_id')
        try:
            voucher = Voucher.objects.select_related('company', 'party_ledger').get(id=voucher_id)
        except Voucher.DoesNotExist:
            return Response({'error': 'Target invoice does not exist.'}, status=status.HTTP_404_NOT_FOUND)

        buyer_gstin = (request.data.get('gstin') or payload.get('buyer_gstin') or '').strip().upper()
        company_name = (request.data.get('company_name') or payload.get('buyer_name') or 'My Company').strip()
        password = request.data.get('password')
        email = (request.data.get('email') or payload.get('buyer_email') or '').strip().lower()

        # 1. Resolve User
        user = request.user if request.user.is_authenticated else None
        if not user:
            if not email:
                email = f"user_{buyer_gstin.lower()}@vouchapp.in" if buyer_gstin else f"user_{voucher.id.hex[:6]}@vouchapp.in"
            if not password:
                return Response({'error': 'Password is required to create your Vouch account.'}, status=status.HTTP_400_BAD_REQUEST)

            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user:
                user = existing_user
                if not user.check_password(password):
                    return Response({'error': 'An account with this email already exists. Please enter correct password or log in.'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=company_name[:30]
                )


        # 2. Resolve or Create Target Company
        state_code = buyer_gstin[:2] if len(buyer_gstin) >= 2 and buyer_gstin[:2].isdigit() else '07'
        target_company = None

        if buyer_gstin:
            target_company = Company.objects.filter(gstin__iexact=buyer_gstin).exclude(id=voucher.company_id).first()

        if not target_company:
            # Check user's companies
            user_comp = user.companies.first()
            if user_comp and user_comp.company_id != voucher.company_id:
                target_company = user_comp.company
                if buyer_gstin and not target_company.gstin:
                    target_company.gstin = buyer_gstin
                    target_company.save(update_fields=['gstin'])
            else:
                # Create brand new company
                target_company = Company.objects.create(
                    name=company_name,
                    legal_name=company_name,
                    gstin=buyer_gstin,
                    pan=buyer_gstin[2:12] if len(buyer_gstin) >= 12 else '',
                    state_code=state_code,
                    email=email,
                )
                UserCompany.objects.get_or_create(
                    user=user,
                    company=target_company,
                    defaults={'role': 'OWNER'}
                )

                CompanySettings.objects.get_or_create(company=target_company)
                Warehouse.objects.get_or_create(company=target_company, name="Main Warehouse")


                # Bootstrap basic ledger groups
                for g_name, nature in [
                    ("Sundry Debtors", "ASSET"),
                    ("Sundry Creditors", "LIABILITY"),
                    ("Sales Accounts", "INCOME"),
                    ("Purchase Accounts", "EXPENSE"),
                    ("Bank Accounts", "ASSET"),
                    ("Duties & Taxes", "LIABILITY")
                ]:
                    LedgerGroup.objects.get_or_create(company=target_company, name=g_name, defaults={'nature': nature})

        # 3. Create EDI Inward Voucher Request
        inward_req = EDIService.create_inward_request_for_sales_voucher(voucher)
        if not inward_req:
            # If party ledger on voucher was unmapped or generic, explicitly create the InwardVoucherRequest
            items_snapshot = []
            for item in voucher.items.select_related('product').all():
                items_snapshot.append({
                    "source_product_id": str(item.product.id) if item.product else "",
                    "product_name": item.product.name if item.product else (getattr(item, 'description', '') or "Product"),
                    "hsn_code": item.hsn_code or (item.product.hsn_code if item.product else ""),
                    "unit": (item.product.unit if item.product else getattr(item, 'unit', '')) or "PCS",
                    "quantity": float(item.quantity),
                    "rate": float(getattr(item, 'rate', getattr(item, 'unit_price', Decimal('0.00')))),
                    "discount_percent": float(item.discount_percent),
                    "discount_amount": float(item.discount_amount),
                    "taxable_amount": float(item.taxable_amount),
                    "gst_rate": float(item.cgst_rate + item.sgst_rate + item.igst_rate),
                    "total_amount": float(item.total_amount),
                })


            payload_data = {
                "source_company_id": str(voucher.company.id),
                "source_company_name": voucher.company.name,
                "source_company_legal_name": voucher.company.legal_name,
                "source_company_gstin": voucher.company.gstin,
                "source_company_state_code": voucher.company.state_code,
                "voucher_id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "voucher_date": voucher.voucher_date.isoformat() if voucher.voucher_date else "",
                "total_amount": float(voucher.total_amount),
                "items": items_snapshot,
            }

            inward_req, _ = InwardVoucherRequest.objects.update_or_create(
                source_voucher=voucher,
                target_company=target_company,
                defaults={
                    "source_company": voucher.company,
                    "payload": payload_data,
                    "status": "PENDING",
                }
            )

        # 4. Generate JWT tokens for auto-login
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        return Response({
            'message': 'Welcome to Vouch! Your company has been registered and this bill is ready in your EDI Inbox.',
            'access': access_token,
            'refresh': refresh_token,
            'user': {
                'id': str(user.id),
                'email': user.email,
                'name': (user.get_full_name() if hasattr(user, 'get_full_name') else '') or user.email,
            },

            'company': {
                'id': str(target_company.id),
                'name': target_company.name,
                'gstin': target_company.gstin,
            },
            'inward_request_id': str(inward_req.id),
            'redirect_url': f"/network/inbox"
        }, status=status.HTTP_201_CREATED)


class InvoiceDispatchDetailsAPIView(APIView):
    """
    Returns WhatsApp sharing link, Claim link, and direct PDF download link
    for any sales invoice so seller can dispatch or re-send anytime.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, voucher_id, *args, **kwargs):
        try:
            company_id = (
                request.headers.get('X-Company-ID')
                or request.headers.get('company-id')
                or request.query_params.get('company_id')
            )
            voucher = Voucher.objects.select_related('company', 'party_ledger').get(id=voucher_id)
            if company_id and str(voucher.company.id) != str(company_id):
                return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        except Voucher.DoesNotExist:
            return Response({'error': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Dynamically determine frontend_url from request origin or referer
        origin = request.headers.get('Origin') or request.headers.get('Referer') or ''
        frontend_url = None
        if origin:
            try:
                parsed = urllib.parse.urlparse(origin)
                if parsed.scheme and parsed.netloc:
                    frontend_url = f"{parsed.scheme}://{parsed.netloc}"
            except Exception:
                pass

        payload = InvoiceNotificationService.generate_whatsapp_share_payload(voucher, frontend_url=frontend_url)
        claim_token = InvoiceNotificationService.generate_claim_token(voucher)
        payload['claim_token'] = claim_token
        payload['pdf_download_url'] = f"/api/v1/accounting/vouchers/{voucher.id}/pdf/?token={claim_token}"

        return Response(payload)
