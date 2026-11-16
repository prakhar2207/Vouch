from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from apps.accounts.permissions import get_authorized_company
from apps.billing.services.entitlement_service import EntitlementService


class RequiresFeature:
    """
    Decorator / Validator for enforcing plan feature entitlements at the API view layer.
    """

    @classmethod
    def enforce(cls, request, company, feature_key: str, feature_title: str, required_tier: str):
        is_allowed = EntitlementService.check_feature_access(company.id, feature_key)
        if not is_allowed:
            raise PermissionDenied({
                "success": False,
                "error": f"{feature_title} is not available on your current plan. Upgrade to {required_tier} at /pricing to unlock this feature.",
                "upgrade_required": True,
                "feature": feature_key,
                "required_tier": required_tier,
                "upgrade_url": "/pricing"
            })
