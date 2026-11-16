from rest_framework import permissions
from apps.companies.models import Company
from apps.gst.models import GSTRegistration
from apps.accounts.permissions import user_has_company_roles


class HasGSTPermission(permissions.BasePermission):
    """
    Strict Tenant Isolation Permission for GST Operations.
    Guarantees:
    1. User must be authenticated.
    2. Company must belong to the user's active tenant associations.
    3. If operating on a specific GSTRegistration, the registration MUST belong to the user's company.
    4. Registration-level authorized-user restrictions are enforced: non-admin members
       must be explicitly present in authorized_users.
    5. Cross-tenant access is rejected with HTTP 403 Forbidden.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        # Extract company from query params, request data, URL kwargs, or header
        company_id = (
            view.kwargs.get('company_id')
            or request.data.get('company_id')
            or request.query_params.get('company_id')
            or request.headers.get('X-Company-ID')
        )

        if company_id:
            try:
                is_member = request.user.companies.filter(company_id=company_id).exists()
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
            if not request.user.companies.filter(company_id=company.id).exists():
                return False

        # If obj is a GSTRegistration, check registration-level user restrictions
        if isinstance(obj, GSTRegistration):
            auth_users = obj.authorized_users.all()
            if auth_users.exists() and request.user not in auth_users:
                # Only staff or company owners/admins can bypass authorized_users restriction!
                is_privileged = request.user.is_staff or user_has_company_roles(
                    request.user, obj.company, ['OWNER', 'ADMIN']
                )
                if not is_privileged:
                    return False

        return True


class CanManageGSTRegistration(permissions.BasePermission):
    """
    Strict Role-Based Permission for Mutating GST Registrations.
    Only company OWNER or ADMIN (or superuser) may create, update, or deactivate registrations.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        company_id = (
            view.kwargs.get('company_id')
            or request.data.get('company_id')
            or request.query_params.get('company_id')
            or request.headers.get('X-Company-ID')
        )

        if not company_id:
            return False

        try:
            from apps.companies.models import UserCompany
            user_comp = UserCompany.objects.filter(user=request.user, company_id=company_id).first()
            if not user_comp:
                return False
            return user_has_company_roles(request.user, user_comp.company, ['OWNER', 'ADMIN'])
        except Exception:
            return False
