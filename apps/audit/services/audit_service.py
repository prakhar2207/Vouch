from apps.audit.models import AuditLog

class AuditService:
    @staticmethod
    def log_action(company, user, action, model_name, record_id, changes=None, ip_address=None):
        """
        Records an immutable audit trail entry.
        """
        AuditLog.objects.create(
            company=company,
            user=user,
            action=action,
            model_name=model_name,
            record_id=str(record_id),
            changes=changes,
            ip_address=ip_address
        )
