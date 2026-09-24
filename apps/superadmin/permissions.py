from rest_framework.permissions import BasePermission

class IsSuperAdminOrStaff(BasePermission):
    """
    Grants access only to authenticated users who have staff, superuser, or ADMIN role privileges.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') == 'ADMIN')
        )
