import hashlib
import logging
from typing import Dict, Any, Optional, List
from django.utils import timezone
from apps.companies.models import Company
from apps.gst.models import GSTRegistration, GSTReturnWorkspace
from apps.gst.services.returns_service import GSTReturnsService
from apps.gst.services.validation_service import GSTValidationService
from apps.accounting.models import Voucher
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService

logger = logging.getLogger('apps.gst.workspace_service')


class GSTWorkspaceService:
    """
    Unified GST Return Workspace & Lifecycle Engine (Phase B).
    Manages return drafts, snapshots, change detection, validations, and sign-offs.
    
    INVARIANT: STRICTLY READ-ONLY with respect to accounting vouchers and ledger entries.
    """

    @classmethod
    def compute_source_voucher_hash(
        cls,
        company: Company,
        start_date,
        end_date,
        voucher_types: List[str]
    ) -> str:
        """
        Computes SHA-256 fingerprint over the set of active vouchers and their line items for the period.
        Comprehensive drift detection captures changes to:
        - Voucher header (voucher_number, voucher_date, total_amount, party, GSTIN, PoS, RCM, status)
        - Voucher items (product, HSN/SAC, quantity, rate, taxable_amount, gst_rate, tax components)
        - Master ledger data affecting tax classification
        """
        vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=voucher_types,
            voucher_date__gte=start_date,
            voucher_date__lte=end_date,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items__product').order_by('id')

        hasher = hashlib.sha256()
        for v in vouchers:
            party_g = (v.party_ledger.gstin if v.party_ledger else '') or (v.buyer_gstin or '')
            party_pos = (v.buyer_state_code or (v.party_ledger.state_code if v.party_ledger else '') or '')
            hdr_str = (
                f"v:{v.id}|{v.voucher_number}|{v.voucher_type}|{v.voucher_date}|"
                f"{v.status}|{v.total_amount}|{party_g}|{party_pos}|"
                f"{getattr(v, 'is_reverse_charge', False)}|{getattr(v, 'is_advance', False)}|"
                f"{v.updated_at.isoformat()};"
            )
            hasher.update(hdr_str.encode('utf-8'))

            for itm in v.items.all().order_by('id'):
                hsn = (itm.hsn_code or (itm.product.hsn_code if itm.product else '') or '').strip()
                itm_str = (
                    f"itm:{itm.id}|{itm.product_id}|{hsn}|{itm.quantity}|{itm.rate}|"
                    f"{itm.taxable_amount}|{itm.gst_rate}|{itm.cgst_amount}|{itm.sgst_amount}|"
                    f"{itm.igst_amount}|{getattr(itm, 'cess_amount', 0)}|{itm.total_amount};"
                )
                hasher.update(itm_str.encode('utf-8'))

        return hasher.hexdigest()

    @classmethod
    def get_or_create_workspace(
        cls,
        company: Company,
        registration: Optional[GSTRegistration],
        return_type: str,
        return_period: str
    ) -> GSTReturnWorkspace:
        """
        Retrieves or initializes a return workspace record for the specified parameters.
        Checks for source voucher data availability in the period.
        """
        start_date, end_date, period_code, fy = GSTReturnsService.parse_period(return_period)

        sales_exists = Voucher.objects.filter(
            company=company,
            voucher_type__in=['SALES', 'CREDIT_NOTE', 'DEBIT_NOTE'],
            voucher_date__gte=start_date,
            voucher_date__lte=end_date,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).exists()

        purchase_exists = Voucher.objects.filter(
            company=company,
            voucher_type='PURCHASE',
            voucher_date__gte=start_date,
            voucher_date__lte=end_date,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).exists()

        workspace, created = GSTReturnWorkspace.objects.get_or_create(
            company=company,
            gst_registration=registration,
            return_type=return_type,
            return_period=period_code,
            defaults={
                "financial_year": fy,
                "sales_data_available": sales_exists,
                "purchase_data_available": purchase_exists,
                "status": 'NOT_STARTED'
            }
        )

        if not created:
            workspace.sales_data_available = sales_exists
            workspace.purchase_data_available = purchase_exists
            workspace.save(update_fields=['sales_data_available', 'purchase_data_available'])

        return workspace

    @classmethod
    def check_drift(cls, workspace: GSTReturnWorkspace) -> bool:
        """
        Detects whether vouchers have been added, modified, or cancelled since draft generation.
        Sets workspace.is_stale = True if drift is detected.
        """
        if not workspace.source_voucher_hash or workspace.status == 'NOT_STARTED':
            return False

        start_date, end_date, _, _ = GSTReturnsService.parse_period(workspace.return_period)
        vtypes = ['SALES', 'CREDIT_NOTE', 'DEBIT_NOTE'] if workspace.return_type == 'GSTR1' else ['SALES', 'PURCHASE', 'CREDIT_NOTE', 'DEBIT_NOTE']

        current_hash = cls.compute_source_voucher_hash(
            company=workspace.company,
            start_date=start_date,
            end_date=end_date,
            voucher_types=vtypes
        )

        is_stale = (current_hash != workspace.source_voucher_hash)
        if workspace.is_stale != is_stale:
            workspace.is_stale = is_stale
            workspace.save(update_fields=['is_stale', 'updated_at'])

        return is_stale

    @classmethod
    def generate_draft(
        cls,
        workspace: GSTReturnWorkspace,
        user: Any = None
    ) -> GSTReturnWorkspace:
        """
        Compiles the official return draft snapshot and runs comprehensive validation.
        Retains an immutable snapshot in draft_payload.
        """
        start_date, end_date, period_code, fy = GSTReturnsService.parse_period(workspace.return_period)
        vtypes = ['SALES', 'CREDIT_NOTE', 'DEBIT_NOTE'] if workspace.return_type == 'GSTR1' else ['SALES', 'PURCHASE', 'CREDIT_NOTE', 'DEBIT_NOTE']

        # 1. Validation check
        val_res = GSTValidationService.validate_period_vouchers(
            company=workspace.company,
            registration=workspace.gst_registration,
            start_date=start_date,
            end_date=end_date,
            return_type=workspace.return_type
        )

        # 2. Compile Draft
        if workspace.return_type == 'GSTR1':
            draft_data = GSTReturnsService.prepare_gstr1(
                company=workspace.company,
                registration=workspace.gst_registration,
                return_period=workspace.return_period
            )
            tax_summary = draft_data.get("summary", {})
            itc_summary = {}
        elif workspace.return_type == 'GSTR3B':
            draft_data = GSTReturnsService.prepare_gstr3b(
                company=workspace.company,
                registration=workspace.gst_registration,
                return_period=workspace.return_period
            )
            tax_summary = draft_data.get("table_3_1", {})
            itc_summary = draft_data.get("table_4_itc", {})
        else:
            # GSTR-2B Recon draft
            draft_data = {"type": "GSTR2B_RECON", "period": period_code}
            tax_summary = {}
            itc_summary = {}

        # 3. Compute source voucher fingerprint
        voucher_hash = cls.compute_source_voucher_hash(
            company=workspace.company,
            start_date=start_date,
            end_date=end_date,
            voucher_types=vtypes
        )

        # 4. Status Transition
        if val_res["error_count"] > 0:
            new_status = 'VALIDATION_REQUIRED'
        elif workspace.status in ['NOT_STARTED', 'VALIDATION_REQUIRED']:
            new_status = 'DRAFT'
        else:
            new_status = workspace.status

        workspace.financial_year = fy
        workspace.status = new_status
        workspace.sales_data_available = bool(val_res["total_vouchers"] > 0)
        workspace.unclassified_count = val_res["unclassified_count"]
        workspace.validation_error_count = val_res["error_count"]
        workspace.validation_warning_count = val_res["warning_count"]
        workspace.validation_errors = val_res["errors"] + val_res["warnings"]
        workspace.tax_liability_summary = tax_summary
        workspace.itc_summary = itc_summary
        workspace.draft_payload = draft_data
        workspace.source_voucher_hash = voucher_hash
        workspace.is_stale = False
        workspace.last_generated_at = timezone.now()
        workspace.save()

        return workspace

    @classmethod
    def sign_off_draft(
        cls,
        workspace: GSTReturnWorkspace,
        user: Any
    ) -> Dict[str, Any]:
        """
        Marks return draft as REVIEWED following accountant/CA sign-off.
        Requires zero blocking validation errors and non-stale snapshot.
        """
        # Re-verify drift
        if cls.check_drift(workspace):
            return {
                "success": False,
                "error": "Vouchers have changed since draft generation. Please regenerate draft before review."
            }

        if workspace.validation_error_count > 0:
            return {
                "success": False,
                "error": f"Cannot review draft with {workspace.validation_error_count} unresolved critical validation errors."
            }

        workspace.status = 'REVIEWED'
        workspace.reviewed_by = user if getattr(user, 'is_authenticated', False) else None
        workspace.reviewed_at = timezone.now()
        workspace.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])

        return {
            "success": True,
            "status": workspace.status,
            "reviewed_at": workspace.reviewed_at.isoformat()
        }

    @classmethod
    def export_draft(
        cls,
        workspace: GSTReturnWorkspace,
        export_format: str = 'JSON'
    ) -> Dict[str, Any]:
        """
        Exports official return schema payload (JSON or structured dictionary for Excel).
        Updates status to EXPORTED.
        """
        if not workspace.draft_payload:
            cls.generate_draft(workspace)

        workspace.status = 'EXPORTED'
        workspace.save(update_fields=['status', 'updated_at'])

        if workspace.return_type == 'GSTR1':
            official_payload = workspace.draft_payload.get("official_gstr1_json", {})
        else:
            official_payload = workspace.draft_payload

        return {
            "success": True,
            "return_type": workspace.return_type,
            "return_period": workspace.return_period,
            "format": export_format,
            "payload": official_payload
        }
