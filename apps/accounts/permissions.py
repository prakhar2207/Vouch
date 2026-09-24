from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied, NotFound
from apps.companies.models import UserCompany

def get_authorized_company(request, company_id=None):
    """
    Strict multi-tenant security barrier:
    Resolves company from explicit argument, X-Company-ID header, request body, or query params.
    Validates that request.user is authenticated and is a verified member of the target company
    via UserCompany (or is a Django superuser).
    Raises PermissionDenied (403) or NotFound (404) if unauthorized or nonexistent.
    """
    from apps.companies.models import Company, UserCompany

    if not request.user or not request.user.is_authenticated:
        raise PermissionDenied("Authentication credentials were not provided.")

    target_id = company_id
    if not target_id and hasattr(request, 'headers'):
        target_id = request.headers.get('X-Company-ID')
    if not target_id and hasattr(request, 'data') and isinstance(request.data, dict):
        target_id = request.data.get('company_id')
    if not target_id and hasattr(request, 'query_params'):
        target_id = request.query_params.get('company_id')

    if not target_id or str(target_id).strip().lower() in ['undefined', 'null', 'none', '']:
        raise PermissionDenied("X-Company-ID header or company_id parameter is required.")

    import uuid
    try:
        clean_uuid = uuid.UUID(str(target_id).strip())
        target_id = str(clean_uuid)
    except (ValueError, TypeError, AttributeError):
        raise NotFound(f"Company ID '{target_id}' is not a valid UUID.")

    company = Company.objects.filter(id=target_id).defer('signature_data').first()
    if not company:
        raise NotFound(f"Company with ID '{target_id}' not found.")

    if not UserCompany.objects.filter(user=request.user, company=company).exists():
        raise PermissionDenied("Access denied: You are not authorized to view or modify this company's books.")

    return company

def get_user_company_role(user, company):
    """
    Returns the user's role in the specified company.
    Requires explicit membership via UserCompany.
    """
    if not user or not user.is_authenticated or not company:
        return None
    
    uc = UserCompany.objects.filter(user=user, company=company).first()
    return uc.role if uc else None

def user_has_company_roles(user, company, allowed_roles):
    """
    Checks if user has one of allowed_roles for the given company.
    Requires explicit membership via UserCompany.
    """
    if not user or not user.is_authenticated or not company:
        return False
    role = get_user_company_role(user, company)
    if not role:
        return False
    if role == 'ADMIN':
        return True
    if 'OWNER' in allowed_roles and role in ['ADMIN', 'OWNER']:
        return True
    return role in allowed_roles

class BaseCompanyPermission(BasePermission):
    allowed_roles = ['ADMIN', 'OWNER', 'CA', 'EMPLOYEE', 'VIEWER']

    def resolve_company(self, request, view):
        from apps.companies.models import Company

        def get_company_by_id(cid):
            if not cid:
                return None
            try:
                return Company.objects.filter(id=cid).only('id', 'name', 'is_active').first()
            except Exception:
                return None

        # 1. From X-Company-ID header
        if hasattr(request, 'headers') and request.headers.get('X-Company-ID'):
            comp = get_company_by_id(request.headers.get('X-Company-ID'))
            if comp:
                return comp

        # 2. From view kwargs
        company_id = view.kwargs.get('company_id') or view.kwargs.get('pk')
        if company_id:
            comp = get_company_by_id(company_id)
            if comp:
                return comp

        # 3. From related IDs in view kwargs
        voucher_id = view.kwargs.get('voucher_id')
        if voucher_id:
            from apps.accounting.models import Voucher
            cid = Voucher.objects.filter(id=voucher_id).values_list('company_id', flat=True).first()
            if cid:
                return get_company_by_id(cid)

        product_id = view.kwargs.get('product_id')
        if product_id:
            from apps.inventory.models import Product
            cid = Product.objects.filter(id=product_id).values_list('company_id', flat=True).first()
            if cid:
                return get_company_by_id(cid)

        ledger_id = view.kwargs.get('ledger_id')
        if ledger_id:
            from apps.ledgers.models import Ledger
            cid = Ledger.objects.filter(id=ledger_id).values_list('company_id', flat=True).first()
            if cid:
                return get_company_by_id(cid)

        # 4. From request data or query params
        if hasattr(request, 'data') and isinstance(request.data, dict):
            company_id = request.data.get('company_id')
            if company_id:
                comp = get_company_by_id(company_id)
                if comp:
                    return comp

        if hasattr(request, 'query_params'):
            company_id = request.query_params.get('company_id')
            if company_id:
                comp = get_company_by_id(company_id)
                if comp:
                    return comp

        return None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        company = self.resolve_company(request, view)
        if not company:
            # If company cannot be resolved at view-level, allow check to proceed to object level or view queryset filter
            return True
        return user_has_company_roles(request.user, company, self.allowed_roles)

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        company = getattr(obj, 'company', None)
        if company is None and hasattr(obj, 'company_id'):
            from apps.companies.models import Company
            company = Company.objects.filter(id=obj.company_id).only('id', 'name', 'is_active').first()
        if company:
            return user_has_company_roles(request.user, company, self.allowed_roles)
        return True

class IsCompanyMember(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER', 'CA', 'EMPLOYEE', 'VIEWER']

class IsCompanyAdmin(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER']

class IsCompanyOwner(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER']

class CanCreateSales(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER', 'CA', 'EMPLOYEE']

class CanCreatePurchases(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER', 'CA', 'EMPLOYEE']

class CanPostVoucher(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER', 'CA', 'EMPLOYEE']

class CanCancelVoucher(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER', 'CA']

class CanManageLedgers(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER', 'CA']

class CanManageInventory(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER', 'CA', 'EMPLOYEE']

class CanManageCompanySettings(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER']

class CanDeleteCompany(BaseCompanyPermission):
    allowed_roles = ['ADMIN', 'OWNER']
