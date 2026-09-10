from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.accounting.models import AccountingFinding
from apps.accounting.services.integrity_engine import AccountingIntegrityEngine
from apps.accounting.services.finding_fix_service import FindingFixService

class AccountingHealthAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        Runs all 11 accounting integrity checks and returns a comprehensive health report.
        """
        company_id = request.headers.get('X-Company-ID') or request.query_params.get('company_id')
        if not company_id:
            return Response({"error": "X-Company-ID header is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_object_or_404(Company, id=company_id)

        report = AccountingIntegrityEngine.run_all_checks(company)
        return Response(report, status=status.HTTP_200_OK)


class DiagnoseBalanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        Specialized investigative diagnostic for 'Why is my balance not matching?'
        """
        company_id = request.headers.get('X-Company-ID') or request.query_params.get('company_id')
        if not company_id:
            return Response({"error": "X-Company-ID header is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_object_or_404(Company, id=company_id)

        diagnosis = AccountingIntegrityEngine.diagnose_balance_mismatch(company)
        return Response(diagnosis, status=status.HTTP_200_OK)


class FindingFixPreviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        """
        Generates a non-destructive BEFORE vs AFTER financial impact preview for a finding.
        """
        company_id = request.headers.get('X-Company-ID') or request.query_params.get('company_id')
        if not company_id:
            return Response({"error": "X-Company-ID header is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_object_or_404(Company, id=company_id)

        finding = get_object_or_404(AccountingFinding, id=pk, company=company)
        preview = FindingFixService.generate_fix_preview(finding)
        return Response(preview, status=status.HTTP_200_OK)


class FindingFixExecuteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        """
        Deterministically applies a user-approved fix for an AccountingFinding.
        Preserves complete accounting history and updates balances.
        """
        company_id = request.headers.get('X-Company-ID') or request.data.get('company_id')
        if not company_id:
            return Response({"error": "X-Company-ID header is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_object_or_404(Company, id=company_id)

        finding = get_object_or_404(AccountingFinding, id=pk, company=company)
        try:
            res = FindingFixService.execute_fix(finding, user=request.user)
            return Response(res, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Failed to apply fix: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
