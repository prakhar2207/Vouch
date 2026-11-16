import json
import logging
import os
from django.conf import settings
from django.http import HttpResponse, FileResponse, Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from apps.accounts.permissions import get_authorized_company, user_has_company_roles
from apps.billing.models import (
    SubscriptionPlan,
    Subscription,
    PaymentTransaction,
    BillingInvoice,
)
from apps.billing.serializers import (
    SubscriptionPlanSerializer,
    SubscriptionSerializer,
    PaymentTransactionSerializer,
    BillingInvoiceSerializer,
    CheckoutOrderRequestSerializer,
    CheckoutVerifyRequestSerializer,
    CancelSubscriptionRequestSerializer,
)
from apps.billing.services.entitlement_service import EntitlementService
from apps.billing.services.subscription_service import SubscriptionService
from apps.billing.services.invoice_service import InvoiceService

logger = logging.getLogger(__name__)


class SubscriptionPlanListView(APIView):
    """
    Public API: List available commercial plans.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # Auto-sync plans if not yet populated
        if not SubscriptionPlan.objects.exists():
            EntitlementService.sync_default_plans()

        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('tier_order')
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response({
            "success": True,
            "plans": serializer.data
        })


class SubscriptionPlanDetailView(APIView):
    """
    Public API: Retrieve a single subscription plan by ID.
    """
    permission_classes = [AllowAny]

    def get(self, request, plan_id):
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            raise NotFound(f"Plan '{plan_id}' does not exist.")

        serializer = SubscriptionPlanSerializer(plan)
        return Response({
            "success": True,
            "plan": serializer.data
        })


class CompanySubscriptionView(APIView):
    """
    Authenticated API: Get current active subscription and entitlements for company workspace.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = get_authorized_company(request)
        entitlements = EntitlementService.get_company_entitlements(company.id)
        sub = EntitlementService.get_company_subscription(company.id)

        # Also provide current daily usage counts
        fast_usage = EntitlementService.get_daily_usage(company.id, "ocr_fast_scans")
        deep_usage = EntitlementService.get_daily_usage(company.id, "ocr_deep_scans")

        return Response({
            "success": True,
            "company_id": str(company.id),
            "company_name": company.name,
            "subscription": SubscriptionSerializer(sub).data if sub else None,
            "entitlements": entitlements,
            "daily_usage": {
                "ocr_fast_scans": fast_usage,
                "ocr_deep_scans": deep_usage,
            }
        })


class CheckoutCreateOrderAPIView(APIView):
    """
    Authenticated API: Create a Razorpay Order for purchasing a plan subscription.
    Restricted to company Owner or Admin.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutOrderRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company_id = serializer.validated_data.get('company_id')
        company = get_authorized_company(request, company_id=company_id)

        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN']):
            raise PermissionDenied("Only company Owners or Admins can purchase subscriptions.")

        plan_id = serializer.validated_data['plan_id']
        checkout_data = SubscriptionService.create_checkout_order(
            company=company,
            user=request.user,
            plan_id=plan_id
        )

        return Response({
            "success": True,
            "checkout": checkout_data
        }, status=status.HTTP_201_CREATED)


class CheckoutVerifyAPIView(APIView):
    """
    Authenticated API: Verifies Razorpay payment signature and activates the subscription.
    Restricted to company Owner or Admin.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutVerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company_id = serializer.validated_data.get('company_id')
        company = get_authorized_company(request, company_id=company_id)

        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN']):
            raise PermissionDenied("Only company Owners or Admins can activate subscriptions.")

        result = SubscriptionService.verify_and_activate_checkout(
            company=company,
            user=request.user,
            razorpay_order_id=serializer.validated_data['razorpay_order_id'],
            razorpay_payment_id=serializer.validated_data['razorpay_payment_id'],
            razorpay_signature=serializer.validated_data['razorpay_signature'],
        )

        return Response(result, status=status.HTTP_200_OK)


class CompanyPaymentsAPIView(APIView):
    """
    Authenticated API: List payment transactions for the authorized company.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = get_authorized_company(request)
        txns = PaymentTransaction.objects.filter(company=company).order_by('-created_at')
        serializer = PaymentTransactionSerializer(txns, many=True)
        return Response({
            "success": True,
            "transactions": serializer.data
        })


class CompanyInvoicesAPIView(APIView):
    """
    Authenticated API: List billing tax invoices for the authorized company.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = get_authorized_company(request)
        invoices = BillingInvoice.objects.filter(company=company).order_by('-invoice_date', '-created_at')
        serializer = BillingInvoiceSerializer(invoices, many=True)
        return Response({
            "success": True,
            "invoices": serializer.data
        })


class InvoiceDownloadAPIView(APIView):
    """
    Authenticated API: Download official PDF for a subscription billing invoice.
    Enforces strict tenant authorization.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, invoice_id):
        company = get_authorized_company(request)
        try:
            invoice = BillingInvoice.objects.get(id=invoice_id, company=company)
        except BillingInvoice.DoesNotExist:
            raise NotFound("Invoice not found or not accessible for this company.")

        # If PDF exists on disk, stream it; otherwise render on the fly
        file_path = os.path.join(settings.MEDIA_ROOT, invoice.pdf_path) if invoice.pdf_path else None
        if file_path and os.path.exists(file_path):
            response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'
            return response

        # Re-render on the fly
        pdf_bytes = InvoiceService.render_invoice_pdf(invoice)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'
        return response


class CancelSubscriptionAPIView(APIView):
    """
    Authenticated API: Cancel company subscription.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CancelSubscriptionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company_id = serializer.validated_data.get('company_id')
        company = get_authorized_company(request, company_id=company_id)

        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN']):
            raise PermissionDenied("Only company Owners or Admins can cancel subscriptions.")

        reason = serializer.validated_data.get('reason', '')
        result = SubscriptionService.cancel_subscription(
            company=company,
            user=request.user,
            reason=reason
        )

        return Response(result, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class RazorpayWebhookAPIView(APIView):
    """
    Public Webhook: Receives and securely verifies Razorpay webhook events.
    Verifies raw body signature and prevents replay attacks.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get('X-Razorpay-Signature', '')
        raw_body = request.body

        if not signature:
            logger.warning("Webhook received without X-Razorpay-Signature header.")
            return Response(
                {"error": "Missing X-Razorpay-Signature header"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except Exception:
            return Response(
                {"error": "Invalid JSON body"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = SubscriptionService.process_webhook_event(
                event_payload=payload,
                signature=signature,
                raw_body=raw_body
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(
                {"error": str(e.detail if hasattr(e, 'detail') else e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected webhook processing error: {e}", exc_info=True)
            return Response(
                {"error": "Internal processing error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
