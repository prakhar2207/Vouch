import re
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from apps.companies.models import Company
from apps.gst.models import GSTRegistration
from apps.accounting.models import Voucher, VoucherItem
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService

logger = logging.getLogger('apps.gst.validation_service')

GSTIN_REGEX = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$')


class GSTValidationService:
    """
    Centralized GST Validation & Exception Engine (Phase F).
    Evaluates accounting vouchers against statutory GST compliance rules.
    
    INVARIANT: STRICTLY READ-ONLY. Never mutates accounting vouchers or ledger entries.
    All detected issues include actionable recommendations and direct voucher linkages.
    """

    @classmethod
    def validate_gstin_format(cls, gstin: Optional[str]) -> bool:
        if not gstin or len(gstin.strip()) != 15:
            return False
        return bool(GSTIN_REGEX.match(gstin.strip().upper()))

    @classmethod
    def validate_period_vouchers(
        cls,
        company: Company,
        registration: Optional[GSTRegistration],
        start_date,
        end_date,
        return_type: str = 'GSTR1'
    ) -> Dict[str, Any]:
        """
        Scans all relevant vouchers for the return period and categorizes them into:
        - Clean vouchers ready for inclusion
        - Issues categorized by severity: ERROR (blocking), WARNING (advisory), INFO
        """
        supplier_gstin = (
            registration.gstin if registration
            else (company.gstin or '')
        ).strip().upper()

        supplier_state = (
            registration.state_code if registration
            else (company.state_code or (supplier_gstin[:2] if len(supplier_gstin) >= 2 and supplier_gstin[:2].isdigit() else '09'))
        ).zfill(2)

        voucher_types = ['SALES', 'CREDIT_NOTE', 'DEBIT_NOTE'] if return_type == 'GSTR1' else ['SALES', 'PURCHASE', 'CREDIT_NOTE', 'DEBIT_NOTE']

        vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=voucher_types,
            voucher_date__gte=start_date,
            voucher_date__lte=end_date,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items__product').order_by('voucher_date', 'voucher_number')

        errors: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        info_items: List[Dict[str, Any]] = []

        seen_invoice_numbers = set()
        clean_vouchers_count = 0
        unclassified_count = 0

        for v in vouchers:
            v_has_error = False
            v_has_warning = False

            # Check 1: Duplicate invoice number detection within the same return period
            inv_key = (v.voucher_type, v.voucher_number.strip().upper())
            if inv_key in seen_invoice_numbers:
                errors.append({
                    "error_code": "GST_ERR_DUPLICATE_INVOICE",
                    "severity": "ERROR",
                    "description": f"Duplicate {v.get_voucher_type_display()} number '{v.voucher_number}' detected in current period.",
                    "voucher_id": str(v.id),
                    "voucher_number": v.voucher_number,
                    "return_section": "Table 13 / General",
                    "recommended_correction": "Review invoice numbering series to eliminate duplicate invoice identifiers.",
                    "requires_manual_review": True
                })
                v_has_error = True
            else:
                seen_invoice_numbers.add(inv_key)

            # Check 2: Missing line items
            items = list(v.items.all())
            if not items:
                errors.append({
                    "error_code": "GST_ERR_EMPTY_VOUCHER",
                    "severity": "ERROR",
                    "description": f"Voucher '{v.voucher_number}' contains zero line items.",
                    "voucher_id": str(v.id),
                    "voucher_number": v.voucher_number,
                    "return_section": "General",
                    "recommended_correction": "Add taxable or exempt product items to the voucher.",
                    "requires_manual_review": True
                })
                v_has_error = True
                continue

            # Party GSTIN and PoS analysis
            party_gstin = (
                v.party_ledger.gstin if v.party_ledger and v.party_ledger.gstin
                else (v.buyer_gstin or '')
            ).strip().upper()

            pos = (
                v.buyer_state_code
                or (v.party_ledger.state_code if v.party_ledger else '')
                or (party_gstin[:2] if len(party_gstin) >= 2 and party_gstin[:2].isdigit() else supplier_state)
            ).zfill(2)

            is_registered = bool(party_gstin and party_gstin != 'URP')
            is_interstate = (pos != supplier_state)

            # Check 3: Registered party GSTIN format and structure
            if is_registered:
                if not cls.validate_gstin_format(party_gstin):
                    errors.append({
                        "error_code": "GST_ERR_INVALID_GSTIN_FORMAT",
                        "severity": "ERROR",
                        "description": f"Recipient GSTIN '{party_gstin}' does not match standard 15-character GSTIN format.",
                        "voucher_id": str(v.id),
                        "voucher_number": v.voucher_number,
                        "return_section": "B2B (Table 4)",
                        "recommended_correction": "Verify and update party GSTIN format in Party Ledger.",
                        "requires_manual_review": True
                    })
                    v_has_error = True

                # Check 4: GSTIN State Code vs Place of Supply alignment
                gstin_state = party_gstin[:2]
                if gstin_state.isdigit() and gstin_state != pos:
                    warnings.append({
                        "error_code": "GST_WARN_POS_GSTIN_MISMATCH",
                        "severity": "WARNING",
                        "description": f"Recipient GSTIN state '{gstin_state}' differs from invoice Place of Supply '{pos}'.",
                        "voucher_id": str(v.id),
                        "voucher_number": v.voucher_number,
                        "return_section": "B2B (Table 4)",
                        "recommended_correction": "Confirm whether bill-to/ship-to arrangement applies or update Place of Supply.",
                        "requires_manual_review": True
                    })
                    v_has_warning = True

            # Check 5: Credit/Debit Note original invoice linkage
            if v.voucher_type in ['CREDIT_NOTE', 'DEBIT_NOTE']:
                if not v.original_invoice and not v.reference_number:
                    warnings.append({
                        "error_code": "GST_WARN_UNLINKED_NOTE",
                        "severity": "WARNING",
                        "description": f"{v.get_voucher_type_display()} '{v.voucher_number}' does not reference an original tax invoice.",
                        "voucher_id": str(v.id),
                        "voucher_number": v.voucher_number,
                        "return_section": "CDNR / CDNUR (Table 9B)",
                        "recommended_correction": "Link note to the original sales invoice or specify reference number.",
                        "requires_manual_review": False
                    })
                    v_has_warning = True

            # Check 6: Item-level tax and HSN validations
            voucher_has_tax = False
            for itm in items:
                hsn = (itm.hsn_code or (itm.product.hsn_code if itm.product else '') or '').strip()
                taxable = Decimal(str(itm.taxable_amount or 0))
                rate = Decimal(str(itm.gst_rate or 0))
                igst = Decimal(str(itm.igst_amount or 0))
                cgst = Decimal(str(itm.cgst_amount or 0))
                sgst = Decimal(str(itm.sgst_amount or 0))

                if rate > 0:
                    voucher_has_tax = True

                # HSN check for B2B supplies
                if is_registered and taxable > 0:
                    if not hsn:
                        errors.append({
                            "error_code": "GST_ERR_MISSING_HSN",
                            "severity": "ERROR",
                            "description": f"Item '{itm.product.name if itm.product else 'Line Item'}' is missing mandatory HSN/SAC code.",
                            "voucher_id": str(v.id),
                            "voucher_number": v.voucher_number,
                            "return_section": "HSN Summary (Table 12)",
                            "recommended_correction": "Assign valid 4 or 6 digit HSN/SAC code to the product.",
                            "requires_manual_review": True
                        })
                        v_has_error = True
                    elif len(hsn) < 4:
                        warnings.append({
                            "error_code": "GST_WARN_SHORT_HSN",
                            "severity": "WARNING",
                            "description": f"HSN code '{hsn}' has fewer than 4 digits (CBIC requires minimum 4 digits for B2B).",
                            "voucher_id": str(v.id),
                            "voucher_number": v.voucher_number,
                            "return_section": "HSN Summary (Table 12)",
                            "recommended_correction": "Ensure HSN/SAC code has at least 4 digits.",
                            "requires_manual_review": False
                        })
                        v_has_warning = True

                # Tax component distribution check (Intrastate vs Interstate)
                if rate > 0:
                    if not is_interstate:
                        # Intrastate supply must have CGST + SGST, not IGST
                        if igst > 0 and (cgst == 0 and sgst == 0):
                            errors.append({
                                "error_code": "GST_ERR_INTRA_HAS_IGST",
                                "severity": "ERROR",
                                "description": f"Intrastate supply (PoS '{pos}') incorrectly charged IGST (₹{igst}) instead of CGST + SGST.",
                                "voucher_id": str(v.id),
                                "voucher_number": v.voucher_number,
                                "return_section": "Tax Computation",
                                "recommended_correction": "Correct tax distribution on voucher: split equally between CGST and SGST.",
                                "requires_manual_review": True
                            })
                            v_has_error = True
                    else:
                        # Interstate supply must have IGST, not CGST / SGST
                        if (cgst > 0 or sgst > 0) and igst == 0:
                            errors.append({
                                "error_code": "GST_ERR_INTER_HAS_CGST_SGST",
                                "severity": "ERROR",
                                "description": f"Interstate supply (PoS '{pos}' vs Supplier '{supplier_state}') incorrectly charged CGST/SGST instead of IGST.",
                                "voucher_id": str(v.id),
                                "voucher_number": v.voucher_number,
                                "return_section": "Tax Computation",
                                "recommended_correction": "Correct tax distribution on voucher: apply integrated tax (IGST).",
                                "requires_manual_review": True
                            })
                            v_has_error = True

            # Track classification readiness
            if not is_registered and not voucher_has_tax and v.total_amount > 0:
                unclassified_count += 1
                info_items.append({
                    "error_code": "GST_INFO_NIL_OR_EXEMPT",
                    "severity": "INFO",
                    "description": f"Voucher '{v.voucher_number}' has 0% tax rate. Classified under Nil-Rated / Exempt outward supplies.",
                    "voucher_id": str(v.id),
                    "voucher_number": v.voucher_number,
                    "return_section": "Table 8",
                    "recommended_correction": "Verify if supply qualifies for GST exemption.",
                    "requires_manual_review": False
                })

            if not v_has_error and not v_has_warning:
                clean_vouchers_count += 1

        total_issues = len(errors) + len(warnings)

        return {
            "period": f"{start_date} to {end_date}",
            "total_vouchers": len(vouchers),
            "clean_count": clean_vouchers_count,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "info_count": len(info_items),
            "unclassified_count": unclassified_count,
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "info": info_items
        }
