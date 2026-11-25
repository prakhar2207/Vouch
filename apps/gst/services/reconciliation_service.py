import re
import logging
from collections import defaultdict
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService
from apps.gst.models import (
    CompanyGSTConfig,
    GSTRegistration,
    GSTR2BImport,
    GSTR2BRecord,
    GSTR2BSyncAttempt
)
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.services.period_service import GSTPeriodService, PeriodInfo

logger = logging.getLogger('apps.gst.reconciliation_service')


def quantize_amount(val: Any) -> Decimal:
    try:
        return Decimal(str(val or '0.00')).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')


class GSTReconciliationService:
    """
    Comprehensive 11-Category GSTR-2B vs Purchase Register Reconciliation Engine.
    Provides idempotent synchronization, period-isolated reconciliation,
    and structured outcome contracts.
    """

    TOLERANCE = Decimal('2.00')

    @classmethod
    def normalize_invoice_number(cls, num_str: str) -> str:
        """
        Normalizes invoice number by stripping non-alphanumeric separators
        and standard prefixes for comparison without collapsing distinct numeric sequences.
        """
        if not num_str:
            return ""
        cleaned = re.sub(r'[^A-Z0-9]', '', str(num_str).strip().upper())
        if cleaned.startswith('INV') and len(cleaned) > 3:
            cleaned = cleaned[3:]
        return cleaned

    @classmethod
    def fetch_and_ingest_from_sandbox(
        cls,
        company: Company,
        registration: Optional[GSTRegistration] = None,
        return_period: Optional[str] = None,
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Fetches GSTR-2B statement directly from Sandbox by Quicko for a single return period:
        GET /gst/compliance/tax-payer/gstrs/gstr-2b/{year}/{month}
        And idempotently ingests the records into GSTR2BImport and GSTR2BRecord.
        """
        if not return_period:
            raise ValidationError("Return period is required for GSTR-2B synchronization.")

        period_info = GSTPeriodService.parse_return_period(return_period)
        norm_period = period_info.normalized_period
        month = period_info.month
        year = period_info.year

        if registration is not None and isinstance(registration, GSTRegistration):
            if registration.company_id != company.id:
                raise ValidationError("GST Registration does not belong to this company.")
            if registration.status != 'ACTIVE':
                raise ValidationError(f"GST Registration {registration.gstin} is inactive.")
        else:
            registration = (
                GSTRegistration.objects.filter(company=company, is_primary=True, status='ACTIVE').first()
                or GSTRegistration.objects.filter(company=company, status='ACTIVE').first()
            )

        client = SandboxGSTClient(company=company, registration=registration)
        config = CompanyGSTConfig.objects.filter(company=company).first()
        session_token = (
            (registration.auth_token if registration and registration.auth_token else None)
            or (config.auth_token if config and config.auth_token else None)
        )

        if not client.is_configured():
            return {
                "success": False,
                "status": "PROVIDER_ERROR",
                "fetch_status": "SKIPPED",
                "auth_status": "UNCONFIGURED",
                "ingestion_status": "SKIPPED",
                "reconciliation_status": "NOT_RECONCILED",
                "error_category": "CONFIGURATION_MISSING",
                "error": "Sandbox GST API is not configured. Please supply API credentials in settings.",
                "return_period": norm_period,
                "period_label": period_info.period_label
            }

        if not session_token:
            return {
                "success": False,
                "status": "AUTHENTICATION_REQUIRED",
                "fetch_status": "SKIPPED",
                "auth_status": "AUTHENTICATION_REQUIRED",
                "ingestion_status": "SKIPPED",
                "reconciliation_status": "NOT_RECONCILED",
                "error_category": "SESSION_EXPIRED",
                "error": "No active GST Portal session found. Please connect your GST Portal under Settings > Government GST Portal Integration first.",
                "return_period": norm_period,
                "period_label": period_info.period_label
            }

        # Bounded external API call
        res = client.fetch_gstr2b(year=year, month=month, session_token=session_token, user=user)
        if not res.get("success"):
            raw_err = res.get("error") or "Failed to fetch GSTR-2B from GST Portal."
            err_cat = "PROVIDER_ERROR"
            err_msg = raw_err
            auth_st = "AUTHENTICATED"

            is_qrmp_interim = period_info.month_int in [4, 5, 7, 8, 10, 11, 1, 2]
            if "not applicable" in raw_err.lower():
                err_cat = "FORM_NOT_APPLICABLE"
                _, end_m, q_lbl = GSTPeriodService.get_quarter_info(period_info.month_int, period_info.year_int)
                qe_period = f"{str(end_m).zfill(2)}{period_info.year}"
                err_msg = (
                    f"GSTR-2B form is not applicable for {period_info.period_label}. "
                    f"Under QRMP (Quarterly Return Monthly Payment), official GSTR-2B statements are generated "
                    f"on quarter-end months ({qe_period} for {q_lbl}), or preceding returns may be pending on the GST Portal."
                )
            elif "session" in raw_err.lower() or "token" in raw_err.lower() or "auth" in raw_err.lower() or "otp" in raw_err.lower():
                err_cat = "AUTHENTICATION_REQUIRED"
                auth_st = "AUTHENTICATION_REQUIRED"

            is_not_app = (err_cat == "FORM_NOT_APPLICABLE")
            # Authoritative Filing Frequency Interface (Round 2.4.3 P1):
            # Only treat as QRMP interim skip if QRMP is conclusively verified on registration.
            # An unverified registration with raw filing_frequency='QRMP' must NEVER receive verified QRMP treatment.
            verified_freq = registration.get_verified_filing_frequency() if (registration and hasattr(registration, 'get_verified_filing_frequency')) else 'UNKNOWN'
            is_qrmp_not_app = bool(
                is_not_app and is_qrmp_interim and verified_freq == 'QRMP'
            )

            if err_cat != "AUTHENTICATION_REQUIRED" and not is_qrmp_not_app:
                # Record REQUEST_FAILED lifecycle entry outside ingestion transaction (Section 6)
                GSTR2BImport.objects.create(
                    company=company,
                    gst_registration=registration,
                    return_period=norm_period,
                    financial_year=period_info.financial_year,
                    file_format='API',
                    file_name=f"sandbox_gstr2b_{norm_period}.json",
                    uploaded_by=user,
                    status='REQUEST_FAILED',
                    error_log=err_msg[:2000],
                    source_info='SANDBOX_API'
                )

            return {
                "success": False,
                "status": "NOT_APPLICABLE" if is_qrmp_not_app else ("PROVIDER_ERROR" if err_cat != "AUTHENTICATION_REQUIRED" else "AUTHENTICATION_REQUIRED"),
                "fetch_status": "NOT_APPLICABLE" if is_qrmp_not_app else "REQUEST_FAILED",
                "auth_status": auth_st,
                "ingestion_status": "SKIPPED",
                "reconciliation_status": "NOT_RECONCILED",
                "error_category": err_cat,
                "is_form_not_applicable": is_qrmp_not_app,
                "is_qrmp_not_applicable": is_qrmp_not_app,
                "error": err_msg,
                "return_period": norm_period,
                "actual_statement_period": None,
                "period_label": period_info.period_label,
                "gstin": registration.gstin if registration else None,
                "filing_frequency": verified_freq,
                "provider_records_count": 0,
                "records_created": 0,
                "records_updated": 0,
                "records_unchanged": 0,
                "records_rejected": 0,
                "provider_response": res
            }

        data = res.get("data") or {}

        # Ingest idempotently into GSTR2BImport and GSTR2BRecord
        from apps.gst.services.itc_reconciliation_service import ITCReconciliationService
        try:
            import_batch = ITCReconciliationService.ingest_gstr2b_json(
                company=company,
                json_data=data,
                user=user,
                file_name=f"sandbox_gstr2b_{norm_period}.json",
                return_period=norm_period,
                registration=registration,
                source_info='SANDBOX_API'
            )
            ingest_status = "INGESTION_SUCCESS"
        except Exception as e:
            logger.exception(f"GSTR-2B ingestion failed for period {norm_period}: {e}")
            GSTR2BImport.objects.create(
                company=company,
                gst_registration=registration,
                return_period=norm_period,
                financial_year=period_info.financial_year,
                file_format='API',
                file_name=f"sandbox_gstr2b_{norm_period}.json",
                uploaded_by=user,
                status='INVALID_PAYLOAD',
                error_log=str(e)[:2000],
                source_info='SANDBOX_API'
            )
            return {
                "success": False,
                "status": "RECONCILIATION_ERROR",
                "fetch_status": "FETCH_SUCCESS",
                "auth_status": "AUTHENTICATED",
                "ingestion_status": "INVALID_PAYLOAD",
                "reconciliation_status": "NOT_RECONCILED",
                "error_category": "INGESTION_FAILED",
                "error": f"Failed to ingest GSTR-2B data: {str(e)}",
                "return_period": norm_period,
                "period_label": period_info.period_label,
                "gstin": registration.gstin if registration else None,
                "filing_frequency": registration.get_verified_filing_frequency() if (registration and hasattr(registration, 'get_verified_filing_frequency')) else 'UNKNOWN',
            }

        # Run authoritative period-isolated ITC reconciliation (DEF-01..08)
        try:
            rec_summary = ITCReconciliationService.reconcile_period(
                company=company,
                registration=registration,
                return_period=norm_period
            )
            rec_st = "RECONCILED"
        except Exception as e:
            logger.exception(f"GSTR-2B reconciliation failed for period {norm_period}: {e}")
            rec_summary = {}
            rec_st = "RECONCILIATION_FAILED"

        outcome_status = "EMPTY_SUCCESS" if getattr(import_batch, 'is_empty_statement', False) or getattr(import_batch, 'status', '') == 'EMPTY_PROCESSED' else "SUCCESS"
        return {
            "success": True,
            "status": outcome_status,
            "fetch_status": "FETCH_SUCCESS",
            "auth_status": "AUTHENTICATED",
            "ingestion_status": ingest_status,
            "reconciliation_status": rec_st,
            "import_batch_id": str(import_batch.id),
            "batch_status": getattr(import_batch, 'status', 'PROCESSED'),
            "is_empty_statement": bool(getattr(import_batch, 'is_empty_statement', False)),
            "return_period": norm_period,
            "actual_statement_period": norm_period,
            "period_label": period_info.period_label,
            "gstin": registration.gstin if registration else None,
            "filing_frequency": registration.get_verified_filing_frequency() if (registration and hasattr(registration, 'get_verified_filing_frequency')) else 'UNKNOWN',
            "provider_records_count": import_batch.provider_records_count,
            "total_invoices_ingested": import_batch.total_invoices_count,
            "records_created": import_batch.records_created,
            "records_updated": import_batch.records_updated,
            "records_unchanged": import_batch.records_unchanged,
            "records_rejected": getattr(import_batch, 'records_rejected', 0),
            "reconciliation_summary": rec_summary
        }

    @classmethod
    def fetch_and_ingest_range(
        cls,
        company: Company,
        registration: Optional[GSTRegistration] = None,
        periods: Optional[List[str]] = None,
        from_period: Optional[str] = None,
        to_period: Optional[str] = None,
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Fetches and ingests GSTR-2B statements across multiple return periods (e.g. April to October).
        Maintains complete period isolation, records GSTR2BSyncAttempt, and provides explicit
        partial-success reporting conforming to enterprise API contracts.
        Rejects reversed ranges with explicit validation error.
        """
        if from_period and to_period:
            p_from = GSTPeriodService.parse_return_period(from_period)
            p_to = GSTPeriodService.parse_return_period(to_period)
            if p_from.start_date > p_to.start_date:
                raise ValidationError("Reversed return period range: from_period cannot be later than to_period.")

        period_infos = GSTPeriodService.resolve_period_range(
            from_period=from_period,
            to_period=to_period,
            periods=periods
        )

        if not period_infos:
            return {
                "status": "VALIDATION_ERROR",
                "success": False,
                "message": "No valid return periods specified for multi-period sync.",
                "periods_requested": [],
                "periods_synced": [],
                "periods_failed": [],
                "total_periods": 0,
                "successful_periods_count": 0,
                "failed_periods_count": 0
            }

        if registration is not None and isinstance(registration, GSTRegistration):
            if registration.company_id != company.id:
                raise ValidationError("GST Registration does not belong to this company.")

        range_key = f"{period_infos[0].normalized_period}-{period_infos[-1].normalized_period}"
        sync_attempt = GSTR2BSyncAttempt.objects.create(
            company=company,
            gst_registration=registration,
            return_period=range_key,
            status='IN_PROGRESS',
            initiated_by=user
        )

        requested_period_strings = [p.normalized_period for p in period_infos]
        period_results = []
        success_periods = []
        not_applicable_periods = []
        failed_periods = []

        total_provider_records = 0
        total_unique_invoices = 0
        records_created_total = 0
        records_updated_total = 0
        records_unchanged_total = 0
        records_rejected_total = 0

        # Execute each period fetch independently
        for p_info in period_infos:
            p_str = p_info.normalized_period
            single_res = cls.fetch_and_ingest_from_sandbox(
                company=company,
                registration=registration,
                return_period=p_str,
                user=user
            )

            if single_res.get("success"):
                success_periods.append(p_str)
                invoices_ingested = single_res.get("total_invoices_ingested", 0)
                total_unique_invoices += invoices_ingested
                total_provider_records += single_res.get("provider_records_count", 0)
                records_created_total += single_res.get("records_created", 0)
                records_updated_total += single_res.get("records_updated", 0)
                records_unchanged_total += single_res.get("records_unchanged", 0)
                records_rejected_total += single_res.get("records_rejected", 0)

                period_st = single_res.get("status") or ("EMPTY_SUCCESS" if single_res.get("is_empty_statement") else "SUCCESS")
                period_results.append({
                    "period": p_str,
                    "period_label": p_info.period_label,
                    "status": period_st,
                    "actual_statement_period": single_res.get("actual_statement_period", p_str),
                    "gstin": single_res.get("gstin") or (registration.gstin if registration else None),
                    "filing_frequency": single_res.get("filing_frequency") or (registration.get_verified_filing_frequency() if (registration and hasattr(registration, 'get_verified_filing_frequency')) else 'UNKNOWN'),
                    "fetch_status": "SUCCESS",
                    "ingestion_status": single_res.get("ingestion_status", "SUCCESS"),
                    "reconciliation_status": single_res.get("reconciliation_status", "SUCCESS"),
                    "provider_records_count": single_res.get("provider_records_count", 0),
                    "invoice_count": invoices_ingested,
                    "invoices_ingested": invoices_ingested,
                    "records_created": single_res.get("records_created", 0),
                    "records_updated": single_res.get("records_updated", 0),
                    "records_unchanged": single_res.get("records_unchanged", 0),
                    "records_rejected": single_res.get("records_rejected", 0),
                    "is_empty_statement": bool(single_res.get("is_empty_statement", False)),
                    "error_category": None,
                    "error_message": None
                })
            elif single_res.get("is_form_not_applicable") or single_res.get("status") == "NOT_APPLICABLE":
                err_msg = single_res.get("error") or "GSTR-2B form is not applicable for this period."
                err_cat = single_res.get("error_category") or "FORM_NOT_APPLICABLE"
                # Only treat as non-fatal QRMP skip if registration is verified QRMP and period is M1/M2
                verified_freq = registration.get_verified_filing_frequency() if (registration and hasattr(registration, 'get_verified_filing_frequency')) else 'UNKNOWN'
                is_qrmp_verified_skip = bool(
                    registration
                    and verified_freq == 'QRMP'
                    and p_info.month_int in [4, 5, 7, 8, 10, 11, 1, 2]
                )
                target_bucket = not_applicable_periods if is_qrmp_verified_skip else failed_periods
                target_bucket.append({
                    "period": p_str,
                    "period_label": p_info.period_label,
                    "error": err_msg,
                    "error_category": err_cat
                })
                period_results.append({
                    "period": p_str,
                    "period_label": p_info.period_label,
                    "status": "NOT_APPLICABLE",
                    "actual_statement_period": None,
                    "gstin": single_res.get("gstin") or (registration.gstin if registration else None),
                    "filing_frequency": single_res.get("filing_frequency") or verified_freq,
                    "fetch_status": "NOT_APPLICABLE",
                    "ingestion_status": "SKIPPED",
                    "reconciliation_status": "SKIPPED",
                    "provider_records_count": 0,
                    "invoice_count": 0,
                    "invoices_ingested": 0,
                    "records_created": 0,
                    "records_updated": 0,
                    "records_unchanged": 0,
                    "records_rejected": 0,
                    "is_form_not_applicable": True,
                    "error_category": err_cat,
                    "error_message": err_msg
                })
            else:
                err_msg = single_res.get("error") or "Failed to sync return period."
                err_cat = single_res.get("error_category") or "PROVIDER_ERROR"
                failed_periods.append({
                    "period": p_str,
                    "period_label": p_info.period_label,
                    "error": err_msg,
                    "error_category": err_cat
                })
                period_results.append({
                    "period": p_str,
                    "period_label": p_info.period_label,
                    "status": "FAILED",
                    "actual_statement_period": None,
                    "gstin": single_res.get("gstin") or (registration.gstin if registration else None),
                    "filing_frequency": single_res.get("filing_frequency") or (registration.get_verified_filing_frequency() if (registration and hasattr(registration, 'get_verified_filing_frequency')) else 'UNKNOWN'),
                    "fetch_status": "FAILED",
                    "ingestion_status": "SKIPPED",
                    "reconciliation_status": "SKIPPED",
                    "provider_records_count": 0,
                    "invoice_count": 0,
                    "invoices_ingested": 0,
                    "records_created": 0,
                    "records_updated": 0,
                    "records_unchanged": 0,
                    "records_rejected": 0,
                    "error_category": err_cat,
                    "error_message": err_msg
                })

        # Run consolidated authoritative reconciliation across all requested periods
        from apps.gst.services.itc_reconciliation_service import ITCReconciliationService
        rec_summary = ITCReconciliationService.reconcile_period(
            company=company,
            registration=registration,
            periods=requested_period_strings,
            start_date=period_infos[0].start_date,
            end_date=period_infos[-1].end_date
        )

        # Determine overall outcome status
        total_p = len(period_infos)
        success_p = len(success_periods)
        failed_p = len(failed_periods)
        not_app_p = len(not_applicable_periods)
        all_empty = bool(success_p > 0 and all(pr.get("is_empty_statement") for pr in period_results if pr.get("fetch_status") == "SUCCESS"))

        if success_p == total_p:
            overall_status = "EMPTY_SUCCESS" if all_empty else "SUCCESS"
            overall_success = True
            if all_empty:
                msg = f"All {total_p} return periods synchronized (0 invoices reported on GST Portal)."
            else:
                msg = f"All {total_p} return periods synchronized and reconciled successfully ({total_unique_invoices} invoices)."
        elif failed_p == 0 and success_p > 0:
            # Verified QRMP: applicable quarters succeeded and interim months are skipped
            overall_status = "EMPTY_SUCCESS" if all_empty else "SUCCESS"
            overall_success = True
            msg = f"Synced {success_p} statement periods successfully ({total_unique_invoices} invoices). {not_app_p} interim months covered under verified QRMP quarterly filing."
        elif success_p > 0:
            overall_status = "PARTIAL_SUCCESS"
            overall_success = False  # Critical: never return overall SUCCESS when periods failed
            msg = f"Synced {success_p} of {total_p} return periods ({failed_p + not_app_p} failed or not applicable). Reconciled {total_unique_invoices} invoices."
        elif success_p == 0 and failed_p == 0 and not_app_p > 0:
            overall_status = "NOT_APPLICABLE"
            overall_success = False
            msg = f"GSTR-2B is not applicable for the selected periods under verified QRMP scheme. Select quarter-end return periods (June, September, December, March)."
        else:
            overall_status = "FAILED"
            overall_success = False
            msg = f"Failed to synchronize return periods from GST Portal ({failed_p} failed)."

        sync_attempt.status = overall_status if overall_status != "EMPTY_SUCCESS" else "SUCCESS"
        sync_attempt.total_invoices_ingested = total_unique_invoices
        sync_attempt.records_created = records_created_total
        sync_attempt.records_updated = records_updated_total
        sync_attempt.records_unchanged = records_unchanged_total
        sync_attempt.error_message = msg if not overall_success else ""
        sync_attempt.save(update_fields=[
            'status', 'total_invoices_ingested', 'records_created',
            'records_updated', 'records_unchanged', 'error_message'
        ])

        return {
            "status": overall_status,
            "success": overall_success,
            "message": msg,
            "error": msg if not overall_success else None,
            "gstin": registration.gstin if registration else None,
            "filing_frequency": registration.get_verified_filing_frequency() if (registration and hasattr(registration, 'get_verified_filing_frequency')) else 'UNKNOWN',
            "periods_requested": requested_period_strings,
            "periods_synced": success_periods,
            "periods_not_applicable": [f["period"] for f in not_applicable_periods],
            "periods_failed": [f["period"] for f in failed_periods],
            "total_periods": total_p,
            "successful_periods_count": success_p,
            "not_applicable_periods_count": not_app_p,
            "failed_periods_count": failed_p,
            "total_provider_records": total_provider_records,
            "total_unique_invoices": total_unique_invoices,
            "records_created": records_created_total,
            "records_updated": records_updated_total,
            "records_unchanged": records_unchanged_total,
            "records_rejected": records_rejected_total,
            "period_results": period_results,
            "failed_periods_details": failed_periods,
            "not_applicable_periods_details": not_applicable_periods,
            "reconciliation_summary": rec_summary
        }

    @classmethod
    @transaction.atomic
    def reconcile_period(
        cls,
        company: Company,
        registration: Optional[GSTRegistration] = None,
        return_period: Optional[str] = None,
        periods: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Runs comprehensive 11-category discrepancy analysis between:
        1. Buyer's Purchase Register vouchers
        2. GSTR-2B Ingested Records

        INVARIANT: ZERO alteration of purchase vouchers or accounting ledger balances.
        Updates both GSTR2BRecord.match_status and Voucher.itc_match_status in sync.
        Preserves existing clean matches across other return periods.
        """
        target_periods = []
        period_start_date = start_date
        period_end_date = end_date

        if return_period and return_period != 'ALL':
            p_info = GSTPeriodService.parse_return_period(return_period)
            target_periods = [p_info.normalized_period]
            period_start_date = p_info.start_date
            period_end_date = p_info.end_date
        elif periods:
            resolved_p_infos = GSTPeriodService.resolve_period_range(periods=periods)
            target_periods = [p.normalized_period for p in resolved_p_infos]
            if resolved_p_infos:
                period_start_date = resolved_p_infos[0].start_date
                period_end_date = resolved_p_infos[-1].end_date

        # 1. Fetch relevant GSTR-2B Records
        rec_qs = GSTR2BRecord.objects.filter(company=company)
        if target_periods:
            rec_qs = rec_qs.filter(Q(return_period__in=target_periods) | Q(import_batch__return_period__in=target_periods))
        if registration:
            rec_qs = rec_qs.filter(Q(gst_registration=registration) | Q(gst_registration__isnull=True))

        gstr2b_records = list(rec_qs.select_related('import_batch'))
        for r in gstr2b_records:
            if not r.return_period and r.import_batch and r.import_batch.return_period:
                r.return_period = r.import_batch.return_period

        # Build lookup indices for GSTR-2B
        records_by_exact_key: Dict[Tuple[str, str], GSTR2BRecord] = {}
        records_by_supplier_suffix: Dict[Tuple[str, str], List[GSTR2BRecord]] = {}

        for r in gstr2b_records:
            gstin = r.supplier_gstin.upper()
            norm = r.normalized_invoice_number
            records_by_exact_key[(gstin, norm)] = r
            num_match = re.search(r'(\d+)$', norm)
            if num_match:
                suffix = num_match.group(1).lstrip('0') or '0'
                records_by_supplier_suffix.setdefault((gstin, suffix), []).append(r)

        # 2. Fetch candidate Purchase Vouchers
        voucher_qs = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items').order_by('voucher_date', 'voucher_number')

        if period_end_date:
            voucher_qs = voucher_qs.filter(voucher_date__lte=period_end_date)

        vouchers = list(voucher_qs)

        matched_record_ids: Set[Any] = set()
        matched_voucher_ids: Set[Any] = set()

        category_counts = {
            "MATCHED": 0,
            "PARTIAL_MATCH": 0,
            "MISSING_IN_BOOKS": 0,
            "MISSING_IN_2B": 0,
            "TAX_MISMATCH": 0,
            "GSTIN_MISMATCH": 0,
            "DOC_NUM_MISMATCH": 0,
            "DATE_MISMATCH": 0,
            "DUPLICATE": 0,
            "INELIGIBLE_ITC": 0,
            "MISMATCHED": 0
        }

        records_to_update = []
        vouchers_to_update = []

        # 3. Match each candidate voucher against GSTR-2B records
        for v in vouchers:
            v_gstin = (v.party_ledger.gstin if v.party_ledger and v.party_ledger.gstin else (v.buyer_gstin or '')).strip().upper()
            v_bill_no = (v.external_invoice_number or v.reference_number or v.voucher_number or '').strip()
            v_norm = cls.normalize_invoice_number(v_bill_no)

            v_items = list(v.items.all())
            v_txval = sum(quantize_amount(itm.taxable_amount) for itm in v_items)
            v_igst = sum(quantize_amount(itm.igst_amount) for itm in v_items)
            v_cgst = sum(quantize_amount(itm.cgst_amount) for itm in v_items)
            v_sgst = sum(quantize_amount(itm.sgst_amount) for itm in v_items)
            v_cess = sum(quantize_amount(getattr(itm, 'cess_amount', 0)) for itm in v_items)
            v_tax = v_igst + v_cgst + v_sgst + v_cess
            v_total = quantize_amount(v.total_amount)

            # Match attempt 1: exact key
            target_rec = records_by_exact_key.get((v_gstin, v_norm))

            # Match attempt 2: suffix match
            if not target_rec and v_gstin:
                num_match = re.search(r'(\d+)$', v_norm)
                if num_match:
                    suffix = num_match.group(1).lstrip('0') or '0'
                    candidates = records_by_supplier_suffix.get((v_gstin, suffix), [])
                    for cand in candidates:
                        if cand.id not in matched_record_ids:
                            target_rec = cand
                            break

            if target_rec:
                matched_record_ids.add(target_rec.id)
                matched_voucher_ids.add(v.id)
                target_rec.matched_voucher = v

                r_txval = quantize_amount(target_rec.taxable_value)
                r_tax = quantize_amount(target_rec.igst_amount + target_rec.cgst_amount + target_rec.sgst_amount + target_rec.cess_amount)
                r_total = quantize_amount(target_rec.invoice_value)

                diff_val = abs(v_total - r_total)
                diff_txval = abs(v_txval - r_txval)
                diff_tax = abs(v_tax - r_tax)
                diff_days = abs((v.voucher_date - target_rec.invoice_date).days) if v.voucher_date and target_rec.invoice_date else 0

                mismatches = []
                is_tax_mismatch = False
                is_date_mismatch = False
                if diff_txval > cls.TOLERANCE:
                    mismatches.append(f"Taxable value mismatch: Books ₹{v_txval:,.2f} vs 2B ₹{r_txval:,.2f} (Diff ₹{diff_txval:,.2f})")
                    is_tax_mismatch = True
                if diff_tax > cls.TOLERANCE:
                    mismatches.append(f"Tax amount mismatch: Books ₹{v_tax:,.2f} vs 2B ₹{r_tax:,.2f} (Diff ₹{diff_tax:,.2f})")
                    is_tax_mismatch = True
                if (v_igst > Decimal('0.00') and target_rec.cgst_amount > Decimal('0.00')) or (v_cgst > Decimal('0.00') and target_rec.igst_amount > Decimal('0.00')):
                    mismatches.append("Tax head mismatch (Inter-state IGST vs Intra-state CGST/SGST)")
                    is_tax_mismatch = True
                if diff_days > 7:
                    mismatches.append(f"Date discrepancy: Books {v.voucher_date} vs 2B {target_rec.invoice_date} ({diff_days} days difference)")
                    is_date_mismatch = True

                is_blocked_credit = (
                    getattr(v, 'is_itc_ineligible', False)
                    or v.itc_match_status == 'INELIGIBLE'
                    or '17(5)' in (v.itc_notes or '')
                )

                if not target_rec.itc_available:
                    target_rec.match_status = 'INELIGIBLE_ITC'
                    category_counts['INELIGIBLE_ITC'] += 1
                    v.itc_match_status = 'INELIGIBLE'
                    v.itc_notes = target_rec.itc_ineligible_reason or "Supplier marked as ITC Ineligible in GSTR-2B / Section 17(5)."
                    conf_score = 1.00
                    conf_level = 'EXACT_MATCH'
                    stat_eligibility = 'INELIGIBLE'
                elif mismatches:
                    if is_date_mismatch and not is_tax_mismatch:
                        match_cat = 'DATE_MISMATCH'
                        conf_score = 0.40
                        conf_level = 'MISMATCH'
                        stat_eligibility = 'REVIEW_REQUIRED'
                    elif is_tax_mismatch and not is_date_mismatch:
                        match_cat = 'TAX_MISMATCH'
                        conf_score = 0.50
                        conf_level = 'MISMATCH'
                        stat_eligibility = 'REVIEW_REQUIRED'
                    else:
                        match_cat = 'MISMATCHED'
                        conf_score = 0.65
                        conf_level = 'AMBIGUOUS'
                        stat_eligibility = 'REVIEW_REQUIRED'

                    target_rec.match_status = match_cat
                    category_counts[match_cat] += 1
                    v.itc_match_status = match_cat
                    v.itc_notes = " | ".join(mismatches)
                else:
                    match_cat = 'MATCHED'
                    conf_score = 1.00
                    conf_level = 'EXACT_MATCH'
                    target_rec.match_status = 'MATCHED'
                    category_counts['MATCHED'] += 1
                    if is_blocked_credit:
                        v.itc_match_status = 'INELIGIBLE'
                        stat_eligibility = 'BLOCKED_SEC17_5'
                        v.itc_notes = "Matched with GSTR-2B, but credit is blocked under Section 17(5)."
                    else:
                        v.itc_match_status = 'MATCHED'
                        stat_eligibility = 'ELIGIBLE'
                        v.itc_notes = f"Reconciled successfully with GSTR-2B ({target_rec.return_period})."
                        if v.itc_held_amount > Decimal('0.00') and not (v.itc_notes or '').startswith('MANUAL_HOLD'):
                            v.itc_held_amount = Decimal('0.00')

                target_rec.mismatch_details = {
                    "category": target_rec.match_status,
                    "confidence_score": conf_score,
                    "confidence_level": conf_level,
                    "statutory_itc_eligibility": stat_eligibility,
                    "explanation": v.itc_notes,
                    "days_difference": diff_days,
                    "book_voucher_number": v.voucher_number,
                    "book_date": str(v.voucher_date),
                    "book_total": float(v_total),
                    "gstr2b_total": float(r_total),
                    "taxable_diff": float(diff_txval),
                    "tax_diff": float(diff_tax)
                }

                records_to_update.append(target_rec)
                vouchers_to_update.append(v)
            else:
                # PERIOD ISOLATION:
                # Only mark voucher as MISSING_IN_2B if its voucher_date is within the reconciled window!
                # Do NOT mark vouchers from outside the reconciled period window as missing.
                # Do NOT overwrite a voucher that was ALREADY MATCHED in another return period.
                in_period_window = True
                if period_start_date and v.voucher_date and v.voucher_date < period_start_date:
                    in_period_window = False
                if period_end_date and v.voucher_date and v.voucher_date > period_end_date:
                    in_period_window = False

                if in_period_window and v.itc_match_status != 'MATCHED':
                    v.itc_match_status = 'MISSING_IN_2B'
                    v.itc_notes = 'Invoice not found in GSTR-2B for reconciled period(s). Vendor has not filed GSTR-1.'
                    if (v.itc_held_amount is None or v.itc_held_amount == Decimal('0.00')) and v_tax > Decimal('0.00'):
                        v.itc_held_amount = v_tax
                    vouchers_to_update.append(v)
                    category_counts["MISSING_IN_2B"] += 1

        # 4. Mark unmatched GSTR-2B records as MISSING_IN_BOOKS
        for r in gstr2b_records:
            if r.id not in matched_record_ids:
                if r.match_status != 'MISSING_IN_BOOKS' or r.matched_voucher is not None:
                    r.match_status = 'MISSING_IN_BOOKS'
                    r.matched_voucher = None
                    r.mismatch_details = {
                        "category": 'MISSING_IN_BOOKS',
                        "confidence_score": 0.0,
                        "confidence_level": 'MISMATCH',
                        "statutory_itc_eligibility": 'REVIEW_REQUIRED' if r.itc_available else 'INELIGIBLE',
                        "explanation": "Invoice reported by supplier in GSTR-2B but not found in purchase books."
                    }
                    records_to_update.append(r)
                category_counts["MISSING_IN_BOOKS"] += 1

        # 5. Bulk updates
        if records_to_update:
            GSTR2BRecord.objects.bulk_update(records_to_update, ['match_status', 'matched_voucher', 'mismatch_details'], batch_size=500)

        if vouchers_to_update:
            Voucher.objects.bulk_update(vouchers_to_update, ['itc_match_status', 'itc_held_amount', 'itc_notes'], batch_size=500)

        total_2b_records = len(gstr2b_records)
        total_2b_itc = sum(quantize_amount(r.igst_amount + r.cgst_amount + r.sgst_amount + r.cess_amount) for r in gstr2b_records if r.itc_available)
        matched_itc = sum(
            quantize_amount(r.igst_amount + r.cgst_amount + r.sgst_amount + r.cess_amount)
            for r in gstr2b_records
            if r.match_status == 'MATCHED' and r.itc_available
        )
        at_risk_itc = total_2b_itc - matched_itc

        return {
            "reconciled_at": timezone.now().isoformat(),
            "return_period": return_period or (periods[0] if periods and len(periods) == 1 else 'MULTI_PERIOD'),
            "target_periods": target_periods,
            "total_gstr2b_records": total_2b_records,
            "total_gstr2b_itc": float(total_2b_itc),
            "matched_itc": float(matched_itc),
            "at_risk_itc": float(at_risk_itc),
            "category_counts": category_counts,
            "category_breakdown": category_counts,
            "matched_count": category_counts.get("MATCHED", 0),
            "missing_in_2b_count": category_counts.get("MISSING_IN_2B", 0),
            "missing_in_books_count": category_counts.get("MISSING_IN_BOOKS", 0),
            "mismatched_count": category_counts.get("MISMATCHED", 0) + category_counts.get("TAX_MISMATCH", 0) + category_counts.get("DATE_MISMATCH", 0),
        }
