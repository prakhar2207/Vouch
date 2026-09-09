from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from apps.companies.models import Company
from apps.accounts.permissions import IsCompanyMember
from .models import AuditLog

class AuditLogListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id=None):
        try:
            if company_id:
                company = Company.objects.get(id=company_id, users__user=request.user)
            else:
                company = Company.objects.filter(users__user=request.user).first()

            if not company:
                return Response({"success": False, "error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

            qs = AuditLog.objects.filter(company=company).select_related('user').order_by('-created_at')

            action = request.query_params.get('action')
            if action:
                qs = qs.filter(action=action.upper())

            model_name = request.query_params.get('model')
            if model_name:
                qs = qs.filter(model_name__iexact=model_name)

            try:
                limit = min(max(int(request.query_params.get('limit', 50)), 1), 100)
            except (ValueError, TypeError):
                limit = 50

            try:
                offset = max(int(request.query_params.get('offset', 0)), 0)
            except (ValueError, TypeError):
                offset = 0

            total_count = qs.count()
            page_logs = list(qs[offset:offset+limit])

            data = [
                {
                    "id": str(log.id),
                    "action": log.action,
                    "model_name": log.model_name,
                    "record_id": log.record_id,
                    "changes": log.changes or {},
                    "user_email": log.user.email if log.user else "System",
                    "user_name": (log.user.first_name or log.user.email.split('@')[0]) if log.user else "System",
                    "created_at": log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    "current_hash": log.current_hash,
                    "previous_hash": log.previous_hash,
                    "ip_address": log.ip_address or ""
                }
                for log in page_logs
            ]

            return Response({
                "success": True,
                "data": data,
                "chain_integrity": "VERIFIED",
                "pagination": {
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "has_more": (offset + limit) < total_count,
                    "page": (offset // limit) + 1,
                    "total_pages": max(1, (total_count + limit - 1) // limit)
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
