from rest_framework.permissions import BasePermission

class IsSuperAdminOrStaff(BasePermission):
    """
    Grants access only to authenticated users who have staff or superuser privileges.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_superuser or request.user.is_staff)
        )
