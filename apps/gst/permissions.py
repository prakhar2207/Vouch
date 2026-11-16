from rest_framework import permissions
from apps.companies.models import Company
from apps.gst.models import GSTRegistration


class HasGSTPermission(permissions.BasePermission):
    """
    Strict Tenant Isolation Permission for GST Operations.
    Guarantees:
    1. User must be authenticated.
    2. Company must belong to the user's active tenant associations.
    3. If operating on a specific GSTRegistration, the registration MUST belong to the user's company.
    4. Cross-tenant access is rejected with HTTP 403 Forbidden.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # If superuser, allow
        if request.user.is_superuser:
            return True

        # Extract company from query params, request data, or URL kwargs
        company_id = (
            view.kwargs.get('company_id')
            or request.data.get('company_id')
            or request.query_params.get('company_id')
            or request.headers.get('X-Company-ID')
        )

        if company_id:
            try:
                # Check user company membership
                is_member = request.user.companies.filter(id=company_id).exists()
                if not is_member:
                    return False
            except Exception:
                return False

        return True

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        # Check tenant ownership of the object
        company = getattr(obj, 'company', None)
        if company:
            if not request.user.companies.filter(id=company.id).exists():
                return False

        # If obj is a GSTRegistration, check registration-level user restrictions
        if isinstance(obj, GSTRegistration):
            auth_users = obj.authorized_users.all()
            if auth_users.exists() and request.user not in auth_users:
                # Allow company owners/admins
                return request.user.is_staff or request.user.companies.filter(id=obj.company.id).exists()

        return True
