from rest_framework.permissions import BasePermission
from django.conf import settings

class IsSuperAdminOrStaff(BasePermission):
    """
    Grants access strictly to verified platform superadmins or designated staff in settings.SUPERADMIN_EMAILS.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        superadmin_emails = getattr(settings, 'SUPERADMIN_EMAILS', [])
        user_email = (request.user.email or '').strip().lower()
        if superadmin_emails and user_email in [e.strip().lower() for e in superadmin_emails]:
            return True
        return bool(request.user.is_staff and getattr(request.user, 'role', '') == 'ADMIN')

