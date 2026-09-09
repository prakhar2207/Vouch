from rest_framework.permissions import BasePermission
from apps.companies.models import UserCompany

def get_user_company_role(user, company):
    """
    Returns the user's role in the specified company.
    Superusers automatically receive OWNER privileges.
    """
    if not user or not user.is_authenticated:
        return None
    if getattr(user, 'is_superuser', False):
        return 'OWNER'
    if not company:
        return None
    
    uc = UserCompany.objects.filter(user=user, company=company).first()
    return uc.role if uc else None

def user_has_company_roles(user, company, allowed_roles):
    role = get_user_company_role(user, company)
    return role in allowed_roles

class BaseCompanyPermission(BasePermission):
    allowed_roles = ['OWNER', 'ADMIN', 'ACCOUNTANT', 'SALES', 'PURCHASE', 'VIEWER']

    def resolve_company(self, request, view):
        # 1. From view kwargs
        company_id = view.kwargs.get('company_id') or view.kwargs.get('pk')
        if company_id:
            from apps.companies.models import Company
            try:
                return Company.objects.get(id=company_id)
            except Exception:
                pass
        # 2. From related IDs in view kwargs
        voucher_id = view.kwargs.get('voucher_id')
        if voucher_id:
            from apps.accounting.models import Voucher
            v = Voucher.objects.filter(id=voucher_id).select_related('company').first()
            if v:
                return v.company
        product_id = view.kwargs.get('product_id')
        if product_id:
            from apps.inventory.models import Product
            p = Product.objects.filter(id=product_id).select_related('company').first()
            if p:
                return p.company
        ledger_id = view.kwargs.get('ledger_id')
        if ledger_id:
            from apps.ledgers.models import Ledger
            l = Ledger.objects.filter(id=ledger_id).select_related('company').first()
            if l:
                return l.company

        # 3. From request data or query params
        if hasattr(request, 'data') and isinstance(request.data, dict):
            company_id = request.data.get('company_id')
            if company_id:
                from apps.companies.models import Company
                try:
                    return Company.objects.get(id=company_id)
                except Exception:
                    pass
        if hasattr(request, 'query_params'):
            company_id = request.query_params.get('company_id')
            if company_id:
                from apps.companies.models import Company
                try:
                    return Company.objects.get(id=company_id)
                except Exception:
                    pass
        return None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False):
            return True
        company = self.resolve_company(request, view)
        if not company:
            # If company cannot be resolved at view-level, allow check to proceed to object level or view queryset filter
            return True
        return user_has_company_roles(request.user, company, self.allowed_roles)

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False):
            return True
        company = getattr(obj, 'company', None)
        if company is None and hasattr(obj, 'company_id'):
            from apps.companies.models import Company
            company = Company.objects.filter(id=obj.company_id).first()
        if company:
            return user_has_company_roles(request.user, company, self.allowed_roles)
        return True

class IsCompanyMember(BaseCompanyPermission):
    allowed_roles = ['OWNER', 'ADMIN', 'ACCOUNTANT', 'SALES', 'PURCHASE', 'VIEWER']

class IsCompanyAdmin(BaseCompanyPermission):
    allowed_roles = ['OWNER', 'ADMIN']

class IsCompanyOwner(BaseCompanyPermission):
    allowed_roles = ['OWNER']

class CanCreateSales(BaseCompanyPermission):
    allowed_roles = ['OWNER', 'ADMIN', 'ACCOUNTANT', 'SALES']

class CanCreatePurchases(BaseCompanyPermission):
    allowed_roles = ['OWNER', 'ADMIN', 'ACCOUNTANT', 'PURCHASE']

class CanPostVoucher(BaseCompanyPermission):
    allowed_roles = ['OWNER', 'ADMIN', 'ACCOUNTANT']

class CanCancelVoucher(BaseCompanyPermission):
    allowed_roles = ['OWNER', 'ADMIN', 'ACCOUNTANT']

class CanManageLedgers(BaseCompanyPermission):
    allowed_roles = ['OWNER', 'ADMIN', 'ACCOUNTANT']

class CanManageInventory(BaseCompanyPermission):
    allowed_roles = ['OWNER', 'ADMIN', 'ACCOUNTANT', 'PURCHASE']

class CanManageCompanySettings(BaseCompanyPermission):
    allowed_roles = ['OWNER', 'ADMIN']

class CanDeleteCompany(BaseCompanyPermission):
    allowed_roles = ['OWNER']
