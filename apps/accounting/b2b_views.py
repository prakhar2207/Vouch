from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

from apps.companies.models import Company, UserCompany
from apps.accounting.models import InwardVoucherRequest
from apps.accounting.services.edi_service import EDIService


class InwardVoucherInboxView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company_id = request.query_params.get('company_id')
        if not company_id:
            user_company = UserCompany.objects.filter(user=request.user).first()
            if not user_company:
                return Response({"error": "No associated company found."}, status=status.HTTP_400_BAD_REQUEST)
            company = user_company.company
        else:
            company = get_object_or_404(Company, id=company_id)
            if not UserCompany.objects.filter(user=request.user, company=company).exists():
                return Response({"error": "Unauthorized for this company."}, status=status.HTTP_403_FORBIDDEN)

        status_filter = request.query_params.get('status', 'ALL').upper()
        queryset = InwardVoucherRequest.objects.filter(target_company=company).select_related(
            'source_company', 'created_purchase_voucher'
        )

        # Counters
        counts = {
            "all": queryset.count(),
            "pending": queryset.filter(status='PENDING').count(),
            "accepted": queryset.filter(status='ACCEPTED').count(),
            "rejected": queryset.filter(status='REJECTED').count(),
        }

        if status_filter in ['PENDING', 'ACCEPTED', 'REJECTED', 'DISPUTED']:
            queryset = queryset.filter(status=status_filter)

        results = []
        for req in queryset:
            results.append({
                "id": str(req.id),
                "source_company": {
                    "id": str(req.source_company.id),
                    "name": req.source_company.name,
                    "legal_name": req.source_company.legal_name,
                    "gstin": req.source_company.gstin,
                    "state_code": req.source_company.state_code,
                    "city": req.source_company.city,
                    "email": req.source_company.email,
                    "phone": req.source_company.phone,
                },
                "status": req.status,
                "payload": req.payload,
                "digital_signature_hash": req.digital_signature_hash,
                "signed_at": req.signed_at.isoformat() if req.signed_at else None,
                "created_purchase_voucher": {
                    "id": str(req.created_purchase_voucher.id),
                    "voucher_number": req.created_purchase_voucher.voucher_number,
                    "total_amount": float(req.created_purchase_voucher.total_amount),
                    "status": req.created_purchase_voucher.status,
                } if req.created_purchase_voucher else None,
                "rejection_reason": req.rejection_reason,
                "created_at": req.created_at.isoformat(),
            })

        return Response({
            "counts": counts,
            "data": results
        })


class InwardVoucherDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        inward_req = get_object_or_404(InwardVoucherRequest.objects.select_related('source_company', 'target_company', 'created_purchase_voucher'), id=pk)
        if not UserCompany.objects.filter(user=request.user, company=inward_req.target_company).exists():
            return Response({"error": "Unauthorized access to this EDI request."}, status=status.HTTP_403_FORBIDDEN)

        return Response({
            "id": str(inward_req.id),
            "source_company": {
                "id": str(inward_req.source_company.id),
                "name": inward_req.source_company.name,
                "legal_name": inward_req.source_company.legal_name,
                "gstin": inward_req.source_company.gstin,
                "state_code": inward_req.source_company.state_code,
                "address": inward_req.source_company.address,
                "city": inward_req.source_company.city,
            },
            "status": inward_req.status,
            "payload": inward_req.payload,
            "digital_signature_hash": inward_req.digital_signature_hash,
            "signed_at": inward_req.signed_at.isoformat() if inward_req.signed_at else None,
            "rejection_reason": inward_req.rejection_reason,
            "created_purchase_voucher": {
                "id": str(inward_req.created_purchase_voucher.id),
                "voucher_number": inward_req.created_purchase_voucher.voucher_number,
                "total_amount": float(inward_req.created_purchase_voucher.total_amount),
            } if inward_req.created_purchase_voucher else None,
            "created_at": inward_req.created_at.isoformat(),
        })


class InwardVoucherAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        inward_req = get_object_or_404(InwardVoucherRequest, id=pk)
        if not UserCompany.objects.filter(user=request.user, company=inward_req.target_company).exists():
            return Response({"error": "Unauthorized to approve requests for this company."}, status=status.HTTP_403_FORBIDDEN)

        item_mappings = request.data.get('item_mappings', {})

        try:
            purchase_voucher = EDIService.accept_inward_request(
                inward_req=inward_req,
                user=request.user,
                item_mappings=item_mappings
            )
            return Response({
                "success": True,
                "message": f"Purchase Voucher #{purchase_voucher.voucher_number} successfully generated & posted.",
                "purchase_voucher_id": str(purchase_voucher.id),
                "voucher_number": purchase_voucher.voucher_number,
                "digital_signature_hash": inward_req.digital_signature_hash,
                "signed_at": inward_req.signed_at.isoformat() if inward_req.signed_at else None,
            }, status=status.HTTP_200_OK)
        except ValidationError as ve:
            return Response({"error": str(ve.message if hasattr(ve, 'message') else ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Failed to accept EDI voucher: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InwardVoucherRejectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        inward_req = get_object_or_404(InwardVoucherRequest, id=pk)
        if not UserCompany.objects.filter(user=request.user, company=inward_req.target_company).exists():
            return Response({"error": "Unauthorized for this company."}, status=status.HTTP_403_FORBIDDEN)

        reason = request.data.get('reason', '')
        try:
            EDIService.reject_inward_request(inward_req, reason=reason)
            return Response({
                "success": True,
                "message": "EDI Inward Voucher Request has been rejected.",
                "status": inward_req.status,
                "rejection_reason": inward_req.rejection_reason
            }, status=status.HTTP_200_OK)
        except ValidationError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
