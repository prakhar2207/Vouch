from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from apps.accounting.services.financial_statements_service import FinancialStatementsService
from apps.accounting.services.report_service import ReportService
from apps.companies.models import Company


def _serialize_decimals(obj: Any) -> Any:
    """Recursively converts Decimal instances to floats for clean JSON snapshot serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_decimals(item) for item in obj]
    return obj


def build_report_dto(
    report_type: str,
    company: Company,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    as_of_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Constructs canonical Document DTOs for:
    - TRIAL_BALANCE
    - PROFIT_AND_LOSS
    - BALANCE_SHEET
    """
    report_type = report_type.upper()

    company_info = {
        'id': str(company.id),
        'name': company.name,
        'gstin': company.gstin or '',
        'address': company.address or '',
        'city': company.city or '',
        'state_code': company.state_code or '',
        'phone': company.phone or '',
        'email': company.email or '',
    }

    if report_type == 'TRIAL_BALANCE':
        tb_data = ReportService.generate_trial_balance(company)
        payload = _serialize_decimals(tb_data)
        return {
            'schema_version': '1.0',
            'document': {
                'document_type': 'TRIAL_BALANCE',
                'title': f"{company.name} - Trial Balance",
                'as_of_date': str(as_of_date or date.today()),
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            },
            'company': company_info,
            'report_data': payload,
        }

    elif report_type == 'PROFIT_AND_LOSS':
        pl_data = FinancialStatementsService.generate_profit_and_loss(company, from_date=from_date, to_date=to_date)
        payload = _serialize_decimals(pl_data)
        return {
            'schema_version': '1.0',
            'document': {
                'document_type': 'PROFIT_AND_LOSS',
                'title': f"{company.name} - Profit & Loss Account",
                'from_date': str(from_date) if from_date else None,
                'to_date': str(to_date) if to_date else str(date.today()),
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            },
            'company': company_info,
            'report_data': payload,
        }

    elif report_type == 'BALANCE_SHEET':
        d_as_of = as_of_date or date.today()
        bs_data = FinancialStatementsService.generate_balance_sheet(company, as_of_date=d_as_of)
        payload = _serialize_decimals(bs_data)
        return {
            'schema_version': '1.0',
            'document': {
                'document_type': 'BALANCE_SHEET',
                'title': f"{company.name} - Balance Sheet",
                'as_of_date': str(d_as_of),
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            },
            'company': company_info,
            'report_data': payload,
        }

    else:
        raise ValueError(f"Unsupported report type: {report_type}")
