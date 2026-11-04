import logging
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import user_has_company_roles
from apps.companies.models import Company, UserCompany
from .models import (
    PushSubscription,
    Notification,
    NotificationPreference,
    SecureInvoiceAccessToken,
    EmailDeliveryLog,
)

logger = logging.getLogger(__name__)


def _get_target_company(request):
    """Resolves company context from header, query param, or first company membership."""
    company_id = request.headers.get('X-Company-ID') or request.query_params.get('company_id')
    if company_id:
        company = Company.objects.filter(id=company_id).first()
        if company and UserCompany.objects.filter(user=request.user, company=company).exists():
            return company

    uc = UserCompany.objects.filter(user=request.user).select_related('company').first()
    return uc.company if uc else None


# =============================================================================
# Push & In-App Notifications
# =============================================================================

class PushSubscriptionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sub_info = request.data
        endpoint = sub_info.get('endpoint')
        keys = sub_info.get('keys', {})
        p256dh = keys.get('p256dh')
        auth = keys.get('auth')

        if not endpoint or not p256dh or not auth:
            return Response({'error': 'Invalid subscription info'}, status=status.HTTP_400_BAD_REQUEST)

        sub, created = PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={'p256dh': p256dh, 'auth': auth}
        )
        return Response({'success': True, 'created': created})


class NotificationListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifs = Notification.objects.filter(user=request.user)[:50]
        data = [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'link': n.link,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat()
        } for n in notifs]
        return Response(data)


class NotificationMarkReadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        if pk:
            Notification.objects.filter(user=request.user, id=pk).update(is_read=True)
        else:
            Notification.objects.filter(user=request.user).update(is_read=True)
        return Response({'success': True})


# =============================================================================
# Company Email Notification Preferences API
# =============================================================================

class NotificationPreferencesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = _get_target_company(request)
        if not company:
            return Response({"success": False, "error": "No company associated with this account."}, status=400)

        pref, _ = NotificationPreference.objects.get_or_create(company=company)
        return Response({
            "success": True,
            "data": {
                "company_id": str(company.id),
                "send_invoice_email_on_post": pref.send_invoice_email_on_post,
                "attach_invoice_pdf": pref.attach_invoice_pdf,
                "send_payment_receipt_email": pref.send_payment_receipt_email,
                "send_credit_note_email": pref.send_credit_note_email,
                "send_revised_invoice_email": pref.send_revised_invoice_email,
                "send_overdue_reminder_email": pref.send_overdue_reminder_email,
                "updated_at": pref.updated_at.isoformat() if pref.updated_at else None,
                "updated_by": pref.updated_by.email if pref.updated_by else None,
            }
        })

    def patch(self, request):
        company = _get_target_company(request)
        if not company:
            return Response({"success": False, "error": "No company associated with this account."}, status=400)

        if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER']):
            return Response({
                "success": False,
                "error": "Only Administrators and Owners can modify notification preferences."
            }, status=status.HTTP_403_FORBIDDEN)

        pref, _ = NotificationPreference.objects.get_or_create(company=company)
        data = request.data

        toggles = [
            'send_invoice_email_on_post',
            'attach_invoice_pdf',
            'send_payment_receipt_email',
            'send_credit_note_email',
            'send_revised_invoice_email',
            'send_overdue_reminder_email',
        ]

        for toggle in toggles:
            if toggle in data:
                val = data[toggle]
                if isinstance(val, str):
                    val = val.lower() in ('true', '1', 'yes')
                setattr(pref, toggle, bool(val))

        pref.updated_by = request.user
        pref.save()

        return Response({
            "success": True,
            "message": "Notification preferences updated successfully.",
            "data": {
                "company_id": str(company.id),
                "send_invoice_email_on_post": pref.send_invoice_email_on_post,
                "attach_invoice_pdf": pref.attach_invoice_pdf,
                "send_payment_receipt_email": pref.send_payment_receipt_email,
                "send_credit_note_email": pref.send_credit_note_email,
                "send_revised_invoice_email": pref.send_revised_invoice_email,
                "send_overdue_reminder_email": pref.send_overdue_reminder_email,
                "updated_at": pref.updated_at.isoformat(),
                "updated_by": request.user.email,
            }
        })


def _apply_invoice_security_headers(response):
    """Enforces strict caching, referrer, and framing controls to prevent token leakage."""
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Content-Type-Options'] = 'nosniff'
    response['X-Frame-Options'] = 'DENY'
    return response


# =============================================================================
# Secure Public Invoice View & Download API (IDOR Protected)
# =============================================================================

class SecureInvoicePublicView(APIView):
    """
    Public, cryptographically tokenized endpoint for viewing/downloading invoices.
    IDOR-safe: completely eliminates predictable ID traversal.
    Minimizes PII exposure by withholding personal buyer phone and email.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # Support token via header or query parameter
        token = request.headers.get('X-Invoice-Token') or request.query_params.get('token')
        if not token:
            return _apply_invoice_security_headers(
                Response({"success": False, "error": "Access token is required."}, status=status.HTTP_400_BAD_REQUEST)
            )

        access_token = (
            SecureInvoiceAccessToken.objects
            .select_related('voucher__company', 'voucher__party_ledger')
            .filter(token=token)
            .first()
        )

        if not access_token or access_token.is_revoked:
            return _apply_invoice_security_headers(
                Response(
                    {"success": False, "error": "Invoice access link is invalid or has been revoked."},
                    status=status.HTTP_404_NOT_FOUND
                )
            )

        if not access_token.is_valid():
            return _apply_invoice_security_headers(
                Response(
                    {"success": False, "error": "This invoice access link has expired."},
                    status=status.HTTP_410_GONE
                )
            )

        # Record access forensics safely
        client_ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
        user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:500]

        access_token.view_count += 1
        access_token.last_accessed_at = timezone.now()
        access_token.last_accessed_ip = client_ip if client_ip and len(client_ip) <= 45 else None
        access_token.user_agent = user_agent
        access_token.save(update_fields=['view_count', 'last_accessed_at', 'last_accessed_ip', 'user_agent'])

        voucher = access_token.voucher
        company = voucher.company
        party = voucher.party_ledger

        # Stream PDF if requested
        if request.query_params.get('format') == 'pdf':
            from apps.accounting.services.invoice_pdf_service import InvoicePDFService
            pdf_bytes = InvoicePDFService.generate_invoice_pdf(voucher)
            clean_inv_no = str(voucher.voucher_number).replace('/', '_').replace('-', '_')
            filename = f"Invoice_{clean_inv_no}.pdf"
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return _apply_invoice_security_headers(response)

        # Return structured invoice payload (minimizing buyer PII disclosure)
        items = list(voucher.items.all()) if hasattr(voucher, 'items') else []
        taxable_amt = sum(getattr(i, 'taxable_amount', 0) for i in items) if items else voucher.total_amount
        cgst_amt = sum(getattr(i, 'cgst_amount', 0) for i in items) if items else 0
        sgst_amt = sum(getattr(i, 'sgst_amount', 0) for i in items) if items else 0
        igst_amt = sum(getattr(i, 'igst_amount', 0) for i in items) if items else 0

        res_data = {
            "success": True,
            "data": {
                "invoice_number": voucher.voucher_number,
                "invoice_date": voucher.voucher_date.isoformat() if hasattr(voucher.voucher_date, 'isoformat') else str(voucher.voucher_date),
                "due_date": voucher.due_date.isoformat() if getattr(voucher, 'due_date', None) and hasattr(voucher.due_date, 'isoformat') else None,
                "total_amount": float(voucher.total_amount),
                "taxable_amount": float(taxable_amt),
                "cgst_amount": float(cgst_amt),
                "sgst_amount": float(sgst_amt),
                "igst_amount": float(igst_amt),
                "status": voucher.status,
                "seller": {
                    "name": company.name,
                    "gstin": company.gstin,
                    "address": company.address,
                    "phone": company.phone,
                    "email": company.email,
                },
                "buyer": {
                    "name": voucher.buyer_name or (party.name if party else 'Valued Customer'),
                    "gstin": voucher.buyer_gstin or (party.gstin if party else None),
                    "address": voucher.buyer_address or (party.address if party else None),
                    "state_code": voucher.buyer_state_code or (party.state_code if party else None),
                },
                "items": [
                    {
                        "item_name": item.product.name if getattr(item, 'product', None) else (getattr(item, 'description', '') or "Custom Item"),
                        "quantity": float(item.quantity),
                        "unit_price": float(getattr(item, 'rate', 0)),
                        "total_amount": float(item.total_amount),
                    }
                    for item in items
                ],
            }
        }
        response = Response(res_data)
        return _apply_invoice_security_headers(response)


# =============================================================================
# Delivery Logs Inspection & Manual Retry API (RBAC Protected: OWNER / ADMIN)
# =============================================================================

class EmailDeliveryLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = _get_target_company(request)
        if not company:
            return Response({"success": False, "error": "No company associated with this account."}, status=400)

        # Enforce strict RBAC: Only OWNER and ADMIN can inspect company email delivery logs
        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN']):
            return Response(
                {"success": False, "error": "Permission denied: Only company Owners and Administrators can inspect notification logs."},
                status=status.HTTP_403_FORBIDDEN
            )

        logs = EmailDeliveryLog.objects.filter(company=company)[:50]
        data = [
            {
                "id": str(log.id),
                "recipient_email": log.recipient_email,
                "subject": log.subject,
                "email_type": log.email_type,
                "status": log.status,
                "attempts": log.attempts,
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                "created_at": log.created_at.isoformat(),
                "error_message": (log.error_message or '')[:200],  # Sanitize to prevent credential/trace exposure
            }
            for log in logs
        ]
        return Response({"success": True, "data": data})


class EmailDeliveryLogRetryAPIView(APIView):
    """
    Manual authorized retry endpoint for failed or retry-pending email deliveries.
    Strictly restricted to company OWNER and ADMIN roles.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, log_id):
        company = _get_target_company(request)
        if not company:
            return Response({"success": False, "error": "No company associated with this account."}, status=400)

        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN']):
            return Response(
                {"success": False, "error": "Permission denied: Only company Owners and Administrators can trigger delivery retries."},
                status=status.HTTP_403_FORBIDDEN
            )

        log = EmailDeliveryLog.objects.filter(id=log_id, company=company).first()
        if not log:
            return Response({"success": False, "error": "Delivery log entry not found."}, status=status.HTTP_404_NOT_FOUND)

        if log.status == 'SENT':
            return Response({"success": False, "error": "This message has already been successfully delivered."}, status=status.HTTP_400_BAD_REQUEST)

        # Reset log status and retry
        log.status = 'PENDING'
        log.attempts = 0
        log.claim_token = None
        log.claim_expires_at = None
        log.error_message = None
        log.save()

        # If there is a corresponding outbox event, reset and re-dispatch it
        from apps.notifications.models import TransactionalOutboxEvent
        from apps.notifications.outbox_service import OutboxService

        if log.idempotency_key:
            outbox_ev = TransactionalOutboxEvent.objects.filter(idempotency_key=log.idempotency_key).first()
            if outbox_ev:
                outbox_ev.status = 'PENDING'
                outbox_ev.retry_count = 0
                outbox_ev.claim_token = None
                outbox_ev.lease_expires_at = None
                outbox_ev.next_retry_at = timezone.now()
                outbox_ev.save()
                OutboxService.dispatch_outbox_event_async(outbox_ev.id)
                return Response({
                    "success": True,
                    "message": "Outbox event and delivery retry dispatched successfully."
                }, status=status.HTTP_200_OK)

        return Response({
            "success": True,
            "message": "Delivery log status reset to PENDING for retry."
        }, status=status.HTTP_200_OK)
