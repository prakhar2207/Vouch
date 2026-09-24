from rest_framework.permissions import BasePermission

class IsSuperAdminOrStaff(BasePermission):
    """
    Grants access strictly to the designated Superadmin (prakharssa@gmail.com).
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return bool(
            request.user.email.strip().lower() == 'prakharssa@gmail.com' and
            (request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') == 'ADMIN')
        )

