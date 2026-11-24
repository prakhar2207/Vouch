# apps/payments/views.py
import json
import logging
from decimal import Decimal
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.permissions import get_authorized_company
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher, LedgerEntry
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.accounting.services.allocation_service import PaymentAllocationService

from apps.payments.models import (
    MerchantPaymentAccount,
    PaymentRequest,
    PaymentWebhookEvent,
    UnmatchedPaymentRecord,
    Beneficiary
)
from apps.payments.constants import (
    PaymentStatus,
    PaymentProviderType,
    AccountingPostingStatus,
    BeneficiaryType
)
from apps.payments.serializers import (
    MerchantPaymentAccountSerializer,
    PaymentRequestCreateSerializer,
    PaymentRequestDetailSerializer,
    PaymentConfirmManualSerializer,
    UnmatchedPaymentRecordSerializer,
    ResolveUnmatchedPaymentSerializer,
    BeneficiarySerializer,
    BeneficiaryDiscoverySerializer
)
from apps.payments.services import (
    PaymentOrchestrator,
    PaymentWebhookService,
    AccountingPostingService,
    BeneficiaryResolutionService,
    BeneficiaryVerificationService
)
from apps.payments.providers import get_payment_provider

logger = logging.getLogger(__name__)


class MerchantAccountAPIView(APIView):
    """
    Manages merchant payment account configuration, UPI VPA, and settlement ledgers.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)
        account, _ = MerchantPaymentAccount.objects.get_or_create(company=company)
        serializer = MerchantPaymentAccountSerializer(account)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, *args, **kwargs):
        company = get_authorized_company(request)
        account, _ = MerchantPaymentAccount.objects.get_or_create(company=company)
        serializer = MerchantPaymentAccountSerializer(account, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PaymentRequestListCreateAPIView(APIView):
    """
    Lists payments and initiates new SriLekh Pay transactions.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)
        direction = request.query_params.get('direction', 'all')  # outgoing, incoming, all
        status_filter = request.query_params.get('status')
        search = request.query_params.get('search', '').strip()

        qs = PaymentRequest.objects.all()

        if direction == 'outgoing':
            qs = qs.filter(company=company)
        elif direction == 'incoming':
            qs = qs.filter(recipient_company=company)
        else:
            qs = qs.filter(Q(company=company) | Q(recipient_company=company))

        if status_filter:
            qs = qs.filter(status=status_filter.upper())

        if search:
            qs = qs.filter(
                Q(srilekh_pay_id__icontains=search) |
                Q(recipient_name__icontains=search) |
                Q(utr__icontains=search) |
                Q(provider_reference__icontains=search)
            )

        qs = qs.select_related('company', 'recipient_company', 'payer_party', 'recipient_party', 'payer_voucher', 'recipient_voucher', 'invoice')[:100]
        serializer = PaymentRequestDetailSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        company = get_authorized_company(request)
        serializer = PaymentRequestCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Resolve party if provided
        payer_party = None
        if data.get('payer_party_id'):
            payer_party = Ledger.objects.filter(company=company, id=data['payer_party_id']).first()

        # Resolve invoice if provided
        invoice = None
        if data.get('invoice_id'):
            invoice = Voucher.objects.filter(company=company, id=data['invoice_id']).first()

        # Resolve recipient company if specified
        recipient_company = None
        if data.get('recipient_company_id'):
            recipient_company = Company.objects.filter(id=data['recipient_company_id'], is_active=True).first()

        # Resolve beneficiary if specified
        beneficiary = None
        if data.get('beneficiary_id'):
            beneficiary = Beneficiary.objects.filter(company=company, id=data['beneficiary_id'], is_active=True).first()

        try:
            pr = PaymentOrchestrator.initiate_payment(
                company=company,
                amount=data['amount'],
                payment_method=data.get('payment_method'),
                beneficiary=beneficiary,
                payer_party=payer_party,
                recipient_name=data.get('recipient_name', ''),
                recipient_vpa=data.get('recipient_vpa'),
                recipient_account_number=data.get('recipient_account_number'),
                recipient_ifsc=data.get('recipient_ifsc'),
                recipient_company=recipient_company,
                invoice=invoice,
                idempotency_key=data.get('idempotency_key'),
                notes=data.get('notes', ''),
                user=request.user
            )
            res_serializer = PaymentRequestDetailSerializer(pr)
            return Response(res_serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception("Payment initiation failed: %s", e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PaymentRequestDetailAPIView(APIView):
    """
    Fetches details of a single SriLekh Pay transaction.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        pr = get_object_or_404(PaymentRequest, id=pk)

        # Enforce multi-tenant access: user company must be either payer or recipient
        if pr.company_id != company.id and (not pr.recipient_company_id or pr.recipient_company_id != company.id):
            raise PermissionDenied("You are not authorized to view this payment request.")

        serializer = PaymentRequestDetailSerializer(pr)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PaymentVerifyStatusAPIView(APIView):
    """
    Triggers an active status inquiry to provider (Setu or Bank) and updates records.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        pr = get_object_or_404(PaymentRequest, id=pk)

        if pr.company_id != company.id and pr.recipient_company_id != company.id:
            raise PermissionDenied("Access denied.")

        if pr.status == PaymentStatus.SUCCESS:
            return Response({"status": pr.status, "message": "Payment already confirmed as successful."}, status=status.HTTP_200_OK)

        provider = get_payment_provider(pr.provider)
        try:
            ver_res = provider.verify_payment(pr.provider_reference or pr.srilekh_pay_id, payment_request=pr)
            if ver_res.get('status') == PaymentStatus.SUCCESS:
                updated_pr = PaymentOrchestrator.confirm_payment_success(
                    payment_request=pr,
                    utr=ver_res.get('utr'),
                    payer_vpa=ver_res.get('payer_vpa'),
                    raw_response=ver_res.get('raw_response'),
                    user=request.user
                )
                serializer = PaymentRequestDetailSerializer(updated_pr)
                return Response(serializer.data, status=status.HTTP_200_OK)
            elif ver_res.get('status') == PaymentStatus.FAILED:
                updated_pr = PaymentOrchestrator.mark_payment_failed(pr, "Provider verified payment as failed.")
                serializer = PaymentRequestDetailSerializer(updated_pr)
                return Response(serializer.data, status=status.HTTP_200_OK)

            return Response({"status": pr.status, "message": "Payment is still pending confirmation with bank."}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Error verifying payment %s: %s", pr.srilekh_pay_id, e)
            return Response({"error": f"Verification failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class PaymentManualConfirmAPIView(APIView):
    """
    Allows an authorized accountant or payer to manually confirm a payment by providing the verified bank UTR.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        pr = get_object_or_404(PaymentRequest, id=pk)

        if pr.company_id != company.id and pr.recipient_company_id != company.id:
            raise PermissionDenied("Access denied.")

        serializer = PaymentConfirmManualSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        utr = serializer.validated_data['utr']
        payer_vpa = serializer.validated_data.get('payer_vpa')
        notes = serializer.validated_data.get('notes')

        if notes:
            pr.notes = f"{pr.notes}\n[Manual Confirmation]: {notes}".strip()
            pr.save(update_fields=['notes'])

        updated_pr = PaymentOrchestrator.confirm_payment_success(
            payment_request=pr,
            utr=utr,
            payer_vpa=payer_vpa,
            raw_response={"manual_confirmation": True, "confirmed_by": str(request.user.id)},
            user=request.user
        )
        res_serializer = PaymentRequestDetailSerializer(updated_pr)
        return Response(res_serializer.data, status=status.HTTP_200_OK)


class UnmatchedPaymentListAPIView(APIView):
    """
    Lists suspense records for payments received that could not be automatically matched to a customer ledger.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)
        qs = UnmatchedPaymentRecord.objects.filter(company=company, is_resolved=False).select_related('payment_request')
        serializer = UnmatchedPaymentRecordSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UnmatchedPaymentResolveAPIView(APIView):
    """
    Resolves an unmatched payment suspense record by linking it to a customer ledger and posting the RECEIPT voucher.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        record = get_object_or_404(UnmatchedPaymentRecord, id=pk, company=company)

        if record.is_resolved:
            return Response({"error": "This unmatched payment is already resolved."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ResolveUnmatchedPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        customer_ledger = get_object_or_404(Ledger, id=serializer.validated_data['customer_ledger_id'], company=company)
        invoice = None
        if serializer.validated_data.get('invoice_id'):
            invoice = get_object_or_404(Voucher, id=serializer.validated_data['invoice_id'], company=company)

        # Post Receipt Voucher in Recipient Books
        payment_date = record.created_at.date()
        v_num, fy = InvoiceSequenceService.get_next_number(company, 'RECEIPT', payment_date)
        bank_ledger = AccountingPostingService._resolve_bank_or_clearing_ledger(company)

        receipt_voucher = Voucher.objects.create(
            company=company,
            financial_year=fy,
            voucher_type='RECEIPT',
            voucher_number=v_num,
            voucher_date=payment_date,
            party_ledger=customer_ledger,
            total_amount=record.amount,
            status='DRAFT',
            narration=f"Resolved Unmatched SriLekh Pay Receipt. UTR: {record.utr or 'N/A'}",
            reference_number=record.utr or str(record.id),
            created_by=request.user
        )

        LedgerEntry.objects.create(
            voucher=receipt_voucher,
            company=company,
            ledger=bank_ledger,
            debit_amount=record.amount,
            credit_amount=Decimal('0.00'),
            narration="Funds received"
        )
        LedgerEntry.objects.create(
            voucher=receipt_voucher,
            company=company,
            ledger=customer_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=record.amount,
            narration="Customer receipt"
        )

        VoucherService.post_voucher(receipt_voucher)

        # FIFO allocation
        try:
            PaymentAllocationService.allocate_payment_fifo(receipt_voucher, preferred_invoice_id=invoice.id if invoice else None)
        except Exception as e:
            logger.warning("Allocation warning during suspense resolution: %s", e)

        record.is_resolved = True
        record.resolved_voucher = receipt_voucher
        record.resolved_by = request.user
        record.resolved_at = timezone.now()
        record.save(update_fields=['is_resolved', 'resolved_voucher', 'resolved_by', 'resolved_at'])

        if record.payment_request:
            record.payment_request.recipient_party = customer_ledger
            record.payment_request.recipient_voucher = receipt_voucher
            record.payment_request.accounting_status = AccountingPostingStatus.POSTED
            record.payment_request.save(update_fields=['recipient_party', 'recipient_voucher', 'accounting_status'])

        return Response({
            "success": True,
            "message": f"Suspense resolved and Receipt Voucher {receipt_voucher.voucher_number} posted.",
            "voucher_number": receipt_voucher.voucher_number
        }, status=status.HTTP_200_OK)


class SetuWebhookAPIView(APIView):
    """
    Public webhook receiver for Setu UPI DeepLinks and Dynamic QR events.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        raw_body = request.body
        headers = dict(request.headers)
        try:
            parsed_json = json.loads(raw_body.decode('utf-8'))
        except Exception:
            parsed_json = request.data if isinstance(request.data, dict) else {}

        success, msg, data = PaymentWebhookService.process_incoming_webhook(
            provider_type=PaymentProviderType.SETU,
            raw_body=raw_body,
            headers=headers,
            parsed_json=parsed_json
        )
        return Response({"status": "SUCCESS" if success else "FAILED", "message": msg, "data": data}, status=status.HTTP_200_OK)


class BankWebhookAPIView(APIView):
    """
    Public webhook receiver for Virtual Account NEFT / RTGS / IMPS inbound credit events.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        raw_body = request.body
        headers = dict(request.headers)
        try:
            parsed_json = json.loads(raw_body.decode('utf-8'))
        except Exception:
            parsed_json = request.data if isinstance(request.data, dict) else {}

        success, msg, data = PaymentWebhookService.process_incoming_webhook(
            provider_type=PaymentProviderType.BANK_TRANSFER,
            raw_body=raw_body,
            headers=headers,
            parsed_json=parsed_json
        )
        return Response({"status": "SUCCESS" if success else "FAILED", "message": msg, "data": data}, status=status.HTTP_200_OK)


class BeneficiaryListCreateAPIView(APIView):
    """
    List and create company beneficiaries.
    Enforces strict tenant isolation: users only see beneficiaries belonging to their company.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)
        qs = Beneficiary.objects.filter(company=company, is_active=True)

        search = request.query_params.get('search')
        if search:
            search = search.strip()
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(nickname__icontains=search) |
                Q(vpa__icontains=search) |
                Q(mobile_number__icontains=search) |
                Q(account_number__icontains=search)
            )

        b_type = request.query_params.get('type')
        if b_type:
            qs = qs.filter(beneficiary_type=b_type)

        if request.query_params.get('favorite') == 'true':
            qs = qs.filter(is_favorite=True)

        serializer = BeneficiarySerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        company = get_authorized_company(request)
        serializer = BeneficiarySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        beneficiary = serializer.save(company=company)

        # Attempt immediate background verification if requested
        if request.data.get('auto_verify', True):
            try:
                beneficiary = BeneficiaryVerificationService.verify_beneficiary(beneficiary)
            except Exception as e:
                logger.warning("Auto-verification non-critical warning for %s: %s", beneficiary.id, e)

        return Response(BeneficiarySerializer(beneficiary).data, status=status.HTTP_201_CREATED)


class BeneficiaryDetailAPIView(APIView):
    """
    Retrieve, update or soft-delete an existing beneficiary.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        beneficiary = get_object_or_404(Beneficiary, id=pk, company=company, is_active=True)
        return Response(BeneficiarySerializer(beneficiary).data, status=status.HTTP_200_OK)

    def patch(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        beneficiary = get_object_or_404(Beneficiary, id=pk, company=company, is_active=True)
        serializer = BeneficiarySerializer(beneficiary, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(BeneficiarySerializer(updated).data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        beneficiary = get_object_or_404(Beneficiary, id=pk, company=company, is_active=True)
        beneficiary.is_active = False
        beneficiary.save(update_fields=['is_active'])
        return Response({"success": True, "message": "Beneficiary removed."}, status=status.HTTP_200_OK)


class BeneficiaryToggleFavoriteAPIView(APIView):
    """
    Toggles favorite status for a beneficiary for instant access in Send Money.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        beneficiary = get_object_or_404(Beneficiary, id=pk, company=company, is_active=True)
        beneficiary.is_favorite = not beneficiary.is_favorite
        beneficiary.save(update_fields=['is_favorite'])
        return Response({
            "success": True,
            "is_favorite": beneficiary.is_favorite,
            "message": f"Beneficiary {'marked as favorite' if beneficiary.is_favorite else 'removed from favorites'}."
        }, status=status.HTTP_200_OK)


class BeneficiaryDiscoveryAPIView(APIView):
    """
    Unified discovery endpoint:
    Resolves Mobile Numbers (UPI Numbers), UPI IDs (VPAs), QR codes, and IFSC bank codes
    prior to creating or executing a payment.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = BeneficiaryDiscoverySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mode = serializer.validated_data['discovery_mode']
        query = serializer.validated_data['query'].strip()

        try:
            if mode == 'MOBILE':
                data = BeneficiaryResolutionService.resolve_mobile_number(query)
            elif mode == 'VPA':
                data = BeneficiaryResolutionService.resolve_vpa(query)
            elif mode == 'QR':
                data = BeneficiaryResolutionService.parse_upi_qr(query)
            elif mode == 'IFSC':
                data = BeneficiaryResolutionService.validate_ifsc(query)
            else:
                return Response({"error": "Unsupported discovery mode"}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"success": True, "data": data}, status=status.HTTP_200_OK)
        except ValidationError as ve:
            return Response({"success": False, "error": str(ve.message if hasattr(ve, 'message') else ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BeneficiaryVerifyAPIView(APIView):
    """
    Executes live network verification for a stored beneficiary.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        beneficiary = get_object_or_404(Beneficiary, id=pk, company=company, is_active=True)

        try:
            verified = BeneficiaryVerificationService.verify_beneficiary(beneficiary)
            return Response({
                "success": True,
                "data": BeneficiarySerializer(verified).data,
                "message": f"Beneficiary verified as '{verified.verified_name or verified.name}'."
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Beneficiary verification failed: %s", e)
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
