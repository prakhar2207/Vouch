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

            telemetry = self.verify_company_chain_telemetry(company)

            return Response({
                "success": True,
                "data": data,
                "chain_integrity": telemetry["status"],
                "chain_telemetry": telemetry,
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

    @classmethod
    def verify_company_chain_telemetry(cls, company) -> dict:
        """
        P1-17: Cryptographic audit chain verification with full telemetry.
        Valid states: 'VERIFIED', 'BROKEN', 'NOT_VERIFIED'
        Detects any broken previous_hash, invalid current_hash, or tampering.
        """
        import hashlib, json
        from django.utils import timezone
        logs = list(AuditLog.objects.filter(company=company).order_by('sequence', 'created_at'))
        if not logs:
            return {
                "status": "NOT_VERIFIED",
                "message": "No audit records found for this company.",
                "total_records_checked": 0,
                "invalid_records_count": 0,
                "last_verified_at": timezone.now().isoformat(),
                "first_tampered_id": None,
                "details": []
            }

        expected_prev = "0" * 64
        invalid_count = 0
        first_tampered_id = None
        details = []

        for log in logs:
            if log.previous_hash != expected_prev:
                invalid_count += 1
                if not first_tampered_id:
                    first_tampered_id = str(log.id)
                details.append(f"Broken previous_hash link at log {log.id}: expected {expected_prev}, got {log.previous_hash}")
                break

            if getattr(log, 'schema_version', 'v1') == 'v2':
                computed = log.compute_hash(expected_prev)
            else:
                payload = f"{log.previous_hash}:{log.company_id}:{log.action}:{log.model_name}:{log.record_id}:{json.dumps(log.changes, sort_keys=True) if log.changes else ''}"
                computed = hashlib.sha256(payload.encode('utf-8')).hexdigest()

            if log.current_hash != computed:
                invalid_count += 1
                if not first_tampered_id:
                    first_tampered_id = str(log.id)
                details.append(f"Hash mismatch at log {log.id}: expected {log.current_hash}, computed {computed}")
                break

            expected_prev = log.current_hash

        status_str = "VERIFIED" if invalid_count == 0 else "BROKEN"
        return {
            "status": status_str,
            "message": "Audit chain intact and cryptographically verified." if status_str == "VERIFIED" else "Audit chain compromised.",
            "total_records_checked": len(logs),
            "invalid_records_count": invalid_count,
            "last_verified_at": timezone.now().isoformat(),
            "first_tampered_id": first_tampered_id,
            "details": details
        }

    @classmethod
    def verify_company_chain(cls, company) -> str:
        return cls.verify_company_chain_telemetry(company)["status"]


class AuditVerificationAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id=None):
        if company_id:
            company = Company.objects.filter(id=company_id, users__user=request.user).first()
        else:
            company = Company.objects.filter(users__user=request.user).first()

        if not company:
            return Response({"success": False, "error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        telemetry = AuditLogListView.verify_company_chain_telemetry(company)
        return Response({
            "success": True,
            "company_id": str(company.id),
            "telemetry": telemetry
        }, status=status.HTTP_200_OK)
