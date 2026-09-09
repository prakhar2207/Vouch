from rest_framework.exceptions import ValidationError
from django.core.exceptions import ObjectDoesNotExist

def get_company_object(model_class, company, object_id, entity_name=None):
    """
    Safely retrieves a company-scoped object.
    Raises a validation error if the object does not belong to the given company.
    Never allows cross-company reference.
    """
    if not object_id:
        return None
    name = entity_name or model_class.__name__
    try:
        return model_class.objects.get(id=object_id, company=company)
    except model_class.DoesNotExist:
        raise ValidationError(f"{name} with ID '{object_id}' does not exist or does not belong to this company.")

def get_company_product(company, product_id):
    from apps.inventory.models import Product
    return get_company_object(Product, company, product_id, "Product")

def get_company_ledger(company, ledger_id, entity_name="Ledger"):
    from apps.ledgers.models import Ledger
    return get_company_object(Ledger, company, ledger_id, entity_name)

def get_company_warehouse(company, warehouse_id):
    from apps.inventory.models import Warehouse
    return get_company_object(Warehouse, company, warehouse_id, "Warehouse")

def get_company_party(company, party_id):
    return get_company_ledger(company, party_id, "Party Ledger")

def get_company_voucher(company, voucher_id):
    from apps.accounting.models import Voucher
    return get_company_object(Voucher, company, voucher_id, "Voucher")
