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
from apps.accounts.permissions import get_authorized_company

import logging

logger = logging.getLogger(__name__)

class AccountingHealthAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        Runs all 11 accounting integrity checks and returns a comprehensive health report.
        """
        try:
            company = get_authorized_company(request)
            report = AccountingIntegrityEngine.run_all_checks(company)
            return Response(report, status=status.HTTP_200_OK)
        except (ValidationError,) as e:
            return Response({"error": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Let DRF exceptions (e.g. PermissionDenied, NotFound) propagate or return 500
            from rest_framework.exceptions import APIException
            if isinstance(e, APIException):
                raise e
            logger.exception("Error executing accounting health audit: %s", e)
            return Response(
                {"error": f"Health audit calculation failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DiagnoseBalanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        Specialized investigative diagnostic for 'Why is my balance not matching?'
        """
        try:
            company = get_authorized_company(request)
            diagnosis = AccountingIntegrityEngine.diagnose_balance_mismatch(company)
            return Response(diagnosis, status=status.HTTP_200_OK)
        except (ValidationError,) as e:
            return Response({"error": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            from rest_framework.exceptions import APIException
            if isinstance(e, APIException):
                raise e
            logger.exception("Error executing balance diagnosis: %s", e)
            return Response(
                {"error": f"Balance diagnosis failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FindingFixPreviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        """
        Generates a non-destructive BEFORE vs AFTER financial impact preview for a finding.
        """
        company = get_authorized_company(request)
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
        company = get_authorized_company(request)
        finding = get_object_or_404(AccountingFinding, id=pk, company=company)
        try:
            res = FindingFixService.execute_fix(finding, user=request.user)
            return Response(res, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Failed to apply fix: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
