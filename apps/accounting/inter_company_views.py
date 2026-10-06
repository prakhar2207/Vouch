import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.accounting.models import InterCompanyEntry
from apps.accounting.services.inter_company_service import InterCompanyService
from apps.accounting.services.consolidated_financials_service import ConsolidatedFinancialsService
from apps.accounts.permissions import get_authorized_company, IsCompanyMember, CanManageLedgers


class InterCompanyInboxAPIView(APIView):
    """
    Returns pending inbound mirror entries for the authenticated active company.
    """
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)
        status_filter = request.query_params.get('status', 'PENDING').upper()

        qs = InterCompanyEntry.objects.filter(target_company=company)
        if status_filter != 'ALL':
            qs = qs.filter(status=status_filter)

        qs = qs.select_related(
            'source_company', 'source_voucher', 'target_voucher',
            'suggested_target_debit_ledger', 'suggested_target_credit_ledger'
        ).order_by('-created_at')

        data = [
            {
                "id": str(e.id),
                "source_company_id": str(e.source_company.id),
                "source_company_name": e.source_company.name,
                "source_voucher_id": str(e.source_voucher.id),
                "source_voucher_number": e.source_voucher.voucher_number,
                "target_voucher_id": str(e.target_voucher.id) if e.target_voucher else None,
                "target_voucher_number": e.target_voucher.voucher_number if e.target_voucher else None,
                "entry_type": e.entry_type,
                "amount": float(e.amount),
                "entry_date": str(e.entry_date),
                "narration": e.narration,
                "suggested_debit": {
                    "id": str(e.suggested_target_debit_ledger.id),
                    "name": e.suggested_target_debit_ledger.name
                } if e.suggested_target_debit_ledger else None,
                "suggested_credit": {
                    "id": str(e.suggested_target_credit_ledger.id),
                    "name": e.suggested_target_credit_ledger.name
                } if e.suggested_target_credit_ledger else None,
                "status": e.status,
                "rejection_reason": e.rejection_reason,
                "created_at": e.created_at.isoformat(),
            }
            for e in qs
        ]

        return Response({
            "success": True,
            "company_name": company.name,
            "pending_count": qs.filter(status='PENDING').count(),
            "results": data
        })


class InterCompanyAcceptAPIView(APIView):
    """
    1-Click Confirmation:
    Accepts an inbound mirror entry and atomically creates the counterpart voucher.
    """
    permission_classes = [IsAuthenticated, CanManageLedgers]

    def post(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        entry = get_object_or_404(InterCompanyEntry, id=pk, target_company=company)

        target_debit_id = request.data.get('debit_ledger_id')
        target_credit_id = request.data.get('credit_ledger_id')
        notes = request.data.get('notes', '')

        try:
            res = InterCompanyService.accept_mirror_entry(
                entry_id=entry.id,
                user=request.user,
                target_debit_ledger_id=target_debit_id,
                target_credit_ledger_id=target_credit_id,
                notes=notes
            )
            return Response(res, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Failed to accept inter-company entry: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class InterCompanyRejectAPIView(APIView):
    """
    Rejects a pending inbound mirror entry.
    """
    permission_classes = [IsAuthenticated, CanManageLedgers]

    def post(self, request, pk, *args, **kwargs):
        company = get_authorized_company(request)
        entry = get_object_or_404(InterCompanyEntry, id=pk, target_company=company)
        reason = request.data.get('reason', '')

        try:
            res = InterCompanyService.reject_mirror_entry(
                entry_id=entry.id,
                user=request.user,
                reason=reason
            )
            return Response(res, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)


class InterCompanyMatrixReconciliationAPIView(APIView):
    """
    Produces side-by-side Matrix Reconciliation between current company and a sister company.
    """
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)
        sister_id = request.query_params.get('sister_company_id')
        if not sister_id:
            # Default to first available other active sister company
            sister_comp = Company.objects.filter(
                users__user=request.user,
                is_active=True
            ).exclude(id=company.id).first()
        else:
            sister_comp = get_object_or_404(Company, id=sister_id, users__user=request.user)

        if not sister_comp:
            return Response({
                "success": False,
                "error": "No sister company found to reconcile with. Add a second company in Settings first."
            }, status=status.HTTP_404_NOT_FOUND)

        as_of = None
        as_of_str = request.query_params.get('as_of_date')
        if as_of_str:
            try:
                as_of = datetime.date.fromisoformat(as_of_str)
            except ValueError:
                pass

        matrix = InterCompanyService.get_reconciliation_matrix(company, sister_comp, as_of_date=as_of)
        return Response({"success": True, "matrix": matrix})


class ConsolidatedFinancialsAPIView(APIView):
    """
    Produces Multi-Entity Group MIS and Consolidated Financials.
    Eliminates cross-company sales/purchases and mutual receivables/payables.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company_ids_param = request.query_params.get('company_ids')
        company_ids = [c.strip() for c in company_ids_param.split(',') if c.strip()] if company_ids_param else None

        as_of = None
        as_of_str = request.query_params.get('as_of_date')
        if as_of_str:
            try:
                as_of = datetime.date.fromisoformat(as_of_str)
            except ValueError:
                pass

        report = ConsolidatedFinancialsService.get_group_consolidated_report(
            user=request.user,
            company_ids=company_ids,
            as_of_date=as_of
        )
        return Response({"success": True, "data": report})
