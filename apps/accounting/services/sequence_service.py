import datetime
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.companies.models import Company
from apps.accounting.models import FinancialYear, VoucherSequence

DEFAULT_PREFIXES = {
    'SALES': 'INV',
    'PURCHASE': 'PUR',
    'PAYMENT': 'PAY',
    'RECEIPT': 'RCP',
    'CONTRA': 'CNT',
    'JOURNAL': 'JRN',
    'CREDIT_NOTE': 'CN',
    'DEBIT_NOTE': 'DN',
}

class InvoiceSequenceService:
    @staticmethod
    def get_or_create_active_fy(company: Company, target_date=None) -> FinancialYear:
        """
        Determines Indian Financial Year (April 1 - March 31) for target_date.
        Auto-provisions the FY record for the company if it doesn't already exist.
        """
        if not target_date:
            target_date = datetime.date.today()
        elif isinstance(target_date, str):
            target_date = datetime.date.fromisoformat(target_date)

        if target_date.month >= 4:
            start_year = target_date.year
            end_year = target_date.year + 1
        else:
            start_year = target_date.year - 1
            end_year = target_date.year

        start_yy = str(start_year)[-2:]
        end_yy = str(end_year)[-2:]
        code = f"{start_yy}-{end_yy}"
        name = f"FY {start_year}-{end_yy}"
        start_date = datetime.date(start_year, 4, 1)
        end_date = datetime.date(end_year, 3, 31)

        fy, _ = FinancialYear.objects.get_or_create(
            company=company,
            code=code,
            defaults={
                'name': name,
                'start_date': start_date,
                'end_date': end_date,
                'is_closed': False,
            }
        )
        return fy

    @staticmethod
    def get_next_number(company: Company, voucher_type: str, voucher_date=None, custom_prefix=None):
        """
        Thread-safe, atomic sequence generator enforcing Indian GST Rule 46(b) (<= 16 characters).
        Acquires row-level database lock using select_for_update().
        Returns: tuple of (formatted_sequence_str, financial_year_instance)
        """
        voucher_type = voucher_type.upper()
        if not voucher_date:
            voucher_date = datetime.date.today()
        elif isinstance(voucher_date, str):
            voucher_date = datetime.date.fromisoformat(voucher_date)

        # 1. Resolve matching Financial Year
        fy = FinancialYear.objects.filter(
            company=company,
            start_date__lte=voucher_date,
            end_date__gte=voucher_date
        ).first()

        if not fy:
            fy = InvoiceSequenceService.get_or_create_active_fy(company, voucher_date)

        if fy.is_closed:
            raise ValidationError(
                f"Financial Year '{fy.name}' is closed. No new transactions can be created in a closed period."
            )

        prefix = (custom_prefix or DEFAULT_PREFIXES.get(voucher_type, 'VCH')).strip().upper()

        # 2. Acquire atomic lock on sequence counter
        with transaction.atomic():
            seq, _ = VoucherSequence.objects.select_for_update().get_or_create(
                company=company,
                financial_year=fy,
                voucher_type=voucher_type,
                defaults={
                    'prefix': prefix,
                    'last_number': 0
                }
            )

            seq.last_number += 1
            formatted = f"{seq.prefix}/{fy.code}/{seq.last_number:04d}"

            # Validate Indian GST Rule 46(b) <= 16 characters
            if len(formatted) > 16:
                raise ValidationError(
                    f"Generated invoice number '{formatted}' ({len(formatted)} chars) violates GST Rule 46(b) 16-character limit."
                )

            seq.save(update_fields=['last_number', 'updated_at'])
            return formatted, fy

    @staticmethod
    def preview_next_number(company: Company, voucher_type: str, voucher_date=None, custom_prefix=None):
        """
        Non-locking read-only preview of the upcoming serial number for frontend display.
        """
        voucher_type = voucher_type.upper()
        if not voucher_date:
            voucher_date = datetime.date.today()
        elif isinstance(voucher_date, str):
            voucher_date = datetime.date.fromisoformat(voucher_date)

        fy = FinancialYear.objects.filter(
            company=company,
            start_date__lte=voucher_date,
            end_date__gte=voucher_date
        ).first()

        if not fy:
            fy = InvoiceSequenceService.get_or_create_active_fy(company, voucher_date)

        prefix = (custom_prefix or DEFAULT_PREFIXES.get(voucher_type, 'VCH')).strip().upper()

        seq = VoucherSequence.objects.filter(
            company=company,
            financial_year=fy,
            voucher_type=voucher_type
        ).first()

        next_num = (seq.last_number + 1) if seq else 1
        preview_str = f"{prefix}/{fy.code}/{next_num:04d}"
        return {
            "preview_number": preview_str,
            "financial_year_id": str(fy.id),
            "financial_year_name": fy.name,
            "financial_year_code": fy.code,
            "is_closed": fy.is_closed,
            "is_valid_length": len(preview_str) <= 16,
            "length": len(preview_str),
        }
