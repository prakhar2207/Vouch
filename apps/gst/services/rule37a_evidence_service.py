import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounting.models import Voucher
from apps.gst.models import GSTR2BRecord, SupplierGSTR3BFilingRecord


def compute_rule37a_evidence_hash(
    company_id: Any,
    voucher_id: Any,
    supplier_gstin: str,
    return_period: str,
    evidence_source: str,
    status: str,
    arn: str = "",
    filing_date_str: str = "",
    verified_at_str: str = "",
    document_ref: str = ""
) -> str:
    """
    Computes a canonical SHA-256 fingerprint for Rule 37A statutory evidence.
    Creates an immutable cryptographic audit record under Section 155.
    """
    raw_payload = (
        f"{str(company_id)}|{str(voucher_id)}|{supplier_gstin.strip().upper()}|"
        f"{return_period.strip()}|{evidence_source.strip().upper()}|{status.strip().upper()}|"
        f"{arn.strip()}|{filing_date_str.strip()}|{verified_at_str.strip()}|{document_ref.strip()}"
    )
    return hashlib.sha256(raw_payload.encode('utf-8')).hexdigest()


class Rule37AEvidenceService:
    """
    Statutory Evidence Resolution & Validation Service for Rule 37A (Supplier GSTR-3B Default & Reclaim).
    Enforces the core invariant:
    Absence of evidence must never be interpreted as affirmative evidence of supplier non-filing.
    A Rule 37A reversal requires verified, invoice-period-specific, supplier-specific, fresh evidence.
    """

    DEFAULT_FRESHNESS_DAYS = 30

    @classmethod
    def resolve_supplier_gstin(cls, voucher: Voucher) -> str:
        """
        Resolves the invoice's actual supplier GSTIN from the ledger or voucher party attributes.
        """
        p_gstin = ""
        if getattr(voucher, 'party_ledger', None) and getattr(voucher.party_ledger, 'gstin', None):
            p_gstin = voucher.party_ledger.gstin
        if not p_gstin:
            p_gstin = getattr(voucher, 'party_gstin', '') or getattr(voucher, 'buyer_gstin', '') or ''
        return str(p_gstin).strip().upper()

    @classmethod
    def resolve_invoice_return_period(cls, voucher: Voucher) -> str:
        """
        Derives the invoice return period in MMYYYY format from voucher date.
        """
        return voucher.voucher_date.strftime('%m%Y')

    @classmethod
    def resolve_voucher_evidence(
        cls,
        voucher: Voucher,
        freshness_threshold_days: int = DEFAULT_FRESHNESS_DAYS
    ) -> Dict[str, Any]:
        """
        Resolves and validates supplier GSTR-3B evidence for an invoice voucher.
        P0 Safeguards:
        - Resolves exact supplier GSTIN from party ledger / voucher
        - Resolves exact invoice return period (MMYYYY)
        - Queries SupplierGSTR3BFilingRecord with company, GSTIN, return_period
        - Queries GSTR2BRecord fallback strictly matching company, matched_voucher, GSTIN, and return period
        - Applies freshness validation (default 30 days) to all evidence sources
        - Rejects stale evidence, converting to DATA_UNAVAILABLE
        - Never uses GSTR-1 filing date as proof of GSTR-3B filing
        - Detects conflicting evidence across sources and returns DATA_UNAVAILABLE
        - Fails closed: missing evidence returns UNKNOWN or DATA_UNAVAILABLE
        """
        supplier_gstin = cls.resolve_supplier_gstin(voucher)
        inv_period = cls.resolve_invoice_return_period(voucher)

        if not supplier_gstin:
            return {
                "status": "DATA_UNAVAILABLE",
                "supplier_gstr3b_filed": False,
                "is_stale": False,
                "supplier_gstin": "",
                "return_period": inv_period,
                "filing_date": None,
                "arn": "",
                "evidence_source": "NONE",
                "verification_timestamp": None,
                "evidence_record": None,
                "document_ref": "",
                "provenance": {
                    "source": "NONE",
                    "reason": "Invoice has no supplier GSTIN. Filing evidence cannot be resolved."
                },
                "errors": ["Missing supplier GSTIN on voucher"]
            }

        # 1. Primary Evidence Source: SupplierGSTR3BFilingRecord
        supp_record = SupplierGSTR3BFilingRecord.objects.filter(
            company=voucher.company,
            supplier_gstin=supplier_gstin,
            return_period=inv_period
        ).first()

        supp_eval = None
        if supp_record:
            is_supp_stale = supp_record.is_stale(threshold_days=freshness_threshold_days)
            if is_supp_stale:
                supp_eval = {
                    "status": "DATA_UNAVAILABLE",
                    "supplier_gstr3b_filed": False,
                    "is_stale": True,
                    "filing_date": None,
                    "arn": "",
                    "source": supp_record.verification_source or "SUPPLIER_RECORD",
                    "timestamp": supp_record.verified_at,
                    "record": supp_record,
                    "document_ref": supp_record.evidence_document_ref,
                    "note": f"Supplier filing record is stale (verified >{freshness_threshold_days} days ago). Re-verification required."
                }
            else:
                is_filed = supp_record.status in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED')
                supp_eval = {
                    "status": supp_record.status,
                    "supplier_gstr3b_filed": is_filed,
                    "is_stale": False,
                    "filing_date": supp_record.filing_date,
                    "arn": supp_record.arn,
                    "source": supp_record.verification_source or "SUPPLIER_RECORD",
                    "timestamp": supp_record.verified_at,
                    "record": supp_record,
                    "document_ref": supp_record.evidence_document_ref,
                    "note": supp_record.notes or "Authoritative SupplierGSTR3BFilingRecord"
                }

        # 2. Fallback Evidence Source: GSTR2BRecord
        gstr2b_matches = list(GSTR2BRecord.objects.filter(
            company=voucher.company,
            matched_voucher=voucher
        ))

        g2b_eval = None
        for g2b in gstr2b_matches:
            # Statutory Guard: Must match exact supplier GSTIN
            if g2b.supplier_gstin.strip().upper() != supplier_gstin:
                continue

            # Statutory Guard: Must match exact invoice return period
            g2b_period = (g2b.gstr3b_return_period or "").strip()
            if g2b_period and g2b_period != inv_period:
                continue

            # Check staleness on GSTR2BRecord
            is_g2b_stale = g2b.is_gstr3b_stale(threshold_days=freshness_threshold_days)

            # Evaluate GSTR-3B filing evidence
            if g2b.gstr3b_status == 'FILED' and g2b.gstr3b_filing_arn and g2b.gstr3b_filing_date:
                g2b_eval = {
                    "status": "VERIFIED_FILED",
                    "supplier_gstr3b_filed": True,
                    "is_stale": False,
                    "filing_date": g2b.gstr3b_filing_date,
                    "arn": g2b.gstr3b_filing_arn,
                    "source": g2b.gstr3b_verification_source or "GSTR2B",
                    "timestamp": g2b.gstr3b_verified_at,
                    "record": g2b,
                    "document_ref": "",
                    "note": f"GSTR-2B GSTR-3B filing verified with ARN {g2b.gstr3b_filing_arn}"
                }
                break
            elif g2b.gstr3b_status == 'NOT_FILED':
                if is_g2b_stale:
                    g2b_eval = {
                        "status": "DATA_UNAVAILABLE",
                        "supplier_gstr3b_filed": False,
                        "is_stale": True,
                        "filing_date": None,
                        "arn": "",
                        "source": g2b.gstr3b_verification_source or "GSTR2B",
                        "timestamp": g2b.gstr3b_verified_at,
                        "record": g2b,
                        "document_ref": "",
                        "note": f"GSTR-2B non-filing record is stale (verified >{freshness_threshold_days} days ago). Re-verification required."
                    }
                else:
                    g2b_eval = {
                        "status": "VERIFIED_NOT_FILED",
                        "supplier_gstr3b_filed": False,
                        "is_stale": False,
                        "filing_date": None,
                        "arn": "",
                        "source": g2b.gstr3b_verification_source or "GSTR2B",
                        "timestamp": g2b.gstr3b_verified_at,
                        "record": g2b,
                        "document_ref": "",
                        "note": "GSTR-2B indicates GSTR-3B NOT_FILED for exact return period"
                    }
                break
            elif g2b.gstr3b_status == 'PENDING':
                g2b_eval = {
                    "status": "PENDING",
                    "supplier_gstr3b_filed": False,
                    "is_stale": False,
                    "filing_date": None,
                    "arn": "",
                    "source": g2b.gstr3b_verification_source or "GSTR2B",
                    "timestamp": g2b.gstr3b_verified_at,
                    "record": g2b,
                    "document_ref": "",
                    "note": "GSTR-2B indicates supplier verification is PENDING from GST portal"
                }
                break
            elif g2b.gstr1_filing_date and not g2b.gstr3b_filing_date:
                # GSTR-1 outward date present, but GSTR-3B not discharged
                g2b_eval = {
                    "status": "DATA_UNAVAILABLE",
                    "supplier_gstr3b_filed": False,
                    "is_stale": False,
                    "filing_date": None,
                    "arn": "",
                    "source": "GSTR2B",
                    "timestamp": g2b.gstr3b_verified_at,
                    "record": g2b,
                    "document_ref": "",
                    "note": "Supplier filed GSTR-1, but GSTR-3B tax payment is unverified. GSTR-1 date cannot establish GSTR-3B filing."
                }
                break

        # 3. Detect and Reconcile Conflicts Across Sources
        if supp_eval and g2b_eval:
            supp_filed = supp_eval["supplier_gstr3b_filed"]
            g2b_filed = g2b_eval["supplier_gstr3b_filed"]
            # Conflict: One says filed and the other says not filed
            if (supp_eval["status"] in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED') and g2b_eval["status"] == 'VERIFIED_NOT_FILED') or \
               (supp_eval["status"] == 'VERIFIED_NOT_FILED' and g2b_eval["status"] in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED')):
                return {
                    "status": "DATA_UNAVAILABLE",
                    "supplier_gstr3b_filed": False,
                    "is_stale": False,
                    "supplier_gstin": supplier_gstin,
                    "return_period": inv_period,
                    "filing_date": None,
                    "arn": "",
                    "evidence_source": "CONFLICTING_SOURCES",
                    "verification_timestamp": timezone.now(),
                    "evidence_record": None,
                    "document_ref": "",
                    "provenance": {
                        "source": "CONFLICTING_SOURCES",
                        "supp_record_status": supp_eval["status"],
                        "gstr2b_status": g2b_eval["status"],
                        "reason": f"Conflicting evidence between SupplierGSTR3BFilingRecord ({supp_eval['status']}) and GSTR2BRecord ({g2b_eval['status']}). Reconcile before evaluating."
                    },
                    "errors": ["Conflicting supplier filing evidence across records"]
                }

        # 4. Authoritative selection (prefer primary SupplierGSTR3BFilingRecord over fallback GSTR2BRecord)
        chosen = supp_eval or g2b_eval

        if not chosen:
            return {
                "status": "UNKNOWN",
                "supplier_gstr3b_filed": False,
                "is_stale": False,
                "supplier_gstin": supplier_gstin,
                "return_period": inv_period,
                "filing_date": None,
                "arn": "",
                "evidence_source": "NONE",
                "verification_timestamp": None,
                "evidence_record": None,
                "document_ref": "",
                "provenance": {
                    "source": "NONE",
                    "reason": f"No GSTR-3B filing evidence found for supplier {supplier_gstin} and period {inv_period}."
                },
                "errors": []
            }

        return {
            "status": chosen["status"],
            "supplier_gstr3b_filed": chosen["supplier_gstr3b_filed"],
            "is_stale": chosen["is_stale"],
            "supplier_gstin": supplier_gstin,
            "return_period": inv_period,
            "filing_date": chosen["filing_date"],
            "arn": chosen["arn"],
            "evidence_source": chosen["source"],
            "verification_timestamp": chosen["timestamp"] or timezone.now(),
            "evidence_record": chosen["record"],
            "document_ref": chosen.get("document_ref", ""),
            "provenance": {
                "source": chosen["source"],
                "status": chosen["status"],
                "note": chosen["note"],
                "is_stale": chosen["is_stale"]
            },
            "errors": []
        }

    @classmethod
    def validate_reversal_evidence(
        cls,
        voucher: Voucher,
        supplier_status: Optional[str],
        supplier_gstin: Optional[str],
        supplier_return_period: Optional[str],
        evidence_source: Optional[str],
        verification_timestamp: Optional[datetime],
        evidence_record: Optional[Any] = None,
        evidence_document_ref: Optional[str] = None,
        manual_verification_reason: Optional[str] = None,
        is_stale_evidence: Optional[bool] = None,
        user: Optional[Any] = None,
        freshness_threshold_days: int = DEFAULT_FRESHNESS_DAYS
    ) -> Dict[str, Any]:
        """
        Rigorous validation of evidence for Rule 37A ITC Reversal under Table 4(B)(2).
        Enforces all 12 statutory negative cases.
        """
        # 1. Require explicit supplier status
        if not supplier_status or not str(supplier_status).strip():
            raise ValidationError("Rule 37A reversal requires an explicit supplier status.")

        clean_status = str(supplier_status).strip().upper()

        # 2. Require explicit supplier GSTIN
        if not supplier_gstin or not str(supplier_gstin).strip():
            raise ValidationError("Rule 37A reversal requires an explicit supplier GSTIN.")
        clean_gstin = str(supplier_gstin).strip().upper()

        # 3. Require explicit supplier return period
        if not supplier_return_period or not str(supplier_return_period).strip():
            raise ValidationError("Rule 37A reversal requires an explicit supplier return period.")
        clean_period = str(supplier_return_period).strip().replace('-', '').replace('/', '')

        # 4. Require evidence source
        if not evidence_source or not str(evidence_source).strip():
            raise ValidationError("Rule 37A reversal requires an evidence source.")
        clean_source = str(evidence_source).strip().upper()

        # 5. Require verification timestamp
        if not verification_timestamp:
            raise ValidationError("Rule 37A reversal requires a verification timestamp.")

        # 6. Reject inconclusive or unknown statuses
        if clean_status == 'DATA_UNAVAILABLE':
            raise ValidationError(
                f"Cannot execute Rule 37A reversal: Supplier filing data is DATA_UNAVAILABLE for invoice #{voucher.voucher_number}. "
                "Statute requires affirmative non-filing default before reversal."
            )
        if clean_status == 'PENDING':
            raise ValidationError(
                f"Cannot execute Rule 37A reversal: Supplier GSTR-3B verification is PENDING from GST portal for invoice #{voucher.voucher_number}. "
                "Default cannot be presumed."
            )
        if clean_status in ('UNKNOWN', ''):
            raise ValidationError(
                f"Cannot execute Rule 37A reversal: Supplier status is UNKNOWN for invoice #{voucher.voucher_number}. "
                "Affirmative proof of supplier non-filing is required under Rule 37A."
            )

        # 7. Reject if supplier actually filed
        if clean_status in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED'):
            raise ValidationError(
                f"Cannot execute Rule 37A reversal: Supplier has filed GSTR-3B for invoice #{voucher.voucher_number}."
            )

        # 8. Must be affirmatively VERIFIED_NOT_FILED
        if clean_status != 'VERIFIED_NOT_FILED':
            raise ValidationError(f"Invalid status '{clean_status}' for Rule 37A reversal.")

        # 9. Stale evidence rejection
        if is_stale_evidence:
            raise ValidationError(
                "Cannot execute Rule 37A reversal: Supplier filing evidence is stale (>30 days old). Re-verification required from GSTN."
            )
        if verification_timestamp:
            age_days = (timezone.now() - verification_timestamp).days
            if age_days > freshness_threshold_days:
                raise ValidationError(
                    f"Cannot execute Rule 37A reversal: Verification timestamp is {age_days} days old (exceeds {freshness_threshold_days}-day threshold). "
                    "Re-verification required from GSTN."
                )

        # 10. Exact supplier GSTIN validation
        inv_gstin = cls.resolve_supplier_gstin(voucher)
        if inv_gstin and clean_gstin != inv_gstin:
            raise ValidationError(
                f"Cannot execute Rule 37A reversal: Evidence supplier GSTIN '{clean_gstin}' does not match invoice supplier GSTIN '{inv_gstin}'."
            )

        # 11. Exact return period validation
        inv_period = cls.resolve_invoice_return_period(voucher)
        if clean_period != inv_period:
            raise ValidationError(
                f"Cannot execute Rule 37A reversal: Evidence return period '{clean_period}' does not match invoice return period '{inv_period}' for invoice #{voucher.voucher_number}."
            )

        # 12. Supplying VERIFIED_NOT_FILED without actual supporting evidence
        # A caller must not be able to manufacture a verified status merely by passing a string.
        has_real_evidence = False
        evidence_doc = str(evidence_document_ref or "").strip()
        manual_reason = str(manual_verification_reason or "").strip()

        if evidence_record:
            if isinstance(evidence_record, SupplierGSTR3BFilingRecord):
                if evidence_record.company_id == voucher.company_id and \
                   evidence_record.supplier_gstin.strip().upper() == clean_gstin and \
                   evidence_record.return_period.strip() == clean_period and \
                   evidence_record.status == 'VERIFIED_NOT_FILED' and \
                   not evidence_record.is_stale(threshold_days=freshness_threshold_days):
                    has_real_evidence = True
            elif isinstance(evidence_record, GSTR2BRecord):
                if evidence_record.company_id == voucher.company_id and \
                   evidence_record.supplier_gstin.strip().upper() == clean_gstin and \
                   evidence_record.gstr3b_return_period.strip() == clean_period and \
                   evidence_record.gstr3b_status == 'NOT_FILED' and \
                   not evidence_record.is_gstr3b_stale(threshold_days=freshness_threshold_days):
                    has_real_evidence = True
        elif evidence_doc and manual_reason and user:
            # Explicitly documented manual verification
            has_real_evidence = True

        if not has_real_evidence:
            raise ValidationError(
                "Cannot execute Rule 37A reversal: 'VERIFIED_NOT_FILED' status requires actual supporting evidence "
                "(a valid, fresh SupplierGSTR3BFilingRecord/GSTR2BRecord, or documented manual verification with document ref and reason). "
                "Manufactured string status is rejected."
            )

        evidence_hash = compute_rule37a_evidence_hash(
            company_id=voucher.company_id,
            voucher_id=voucher.id,
            supplier_gstin=clean_gstin,
            return_period=clean_period,
            evidence_source=clean_source,
            status=clean_status,
            document_ref=evidence_doc,
            verified_at_str=verification_timestamp.isoformat()
        )

        return {
            "supplier_status": clean_status,
            "supplier_gstin": clean_gstin,
            "supplier_return_period": clean_period,
            "evidence_source": clean_source,
            "verification_timestamp": verification_timestamp,
            "evidence_document_ref": evidence_doc,
            "manual_verification_reason": manual_reason,
            "evidence_hash": evidence_hash,
            "evidence_record": evidence_record
        }

    @classmethod
    def validate_reclaim_evidence(
        cls,
        voucher: Voucher,
        supplier_status: Optional[str],
        supplier_gstin: Optional[str],
        supplier_return_period: Optional[str],
        verification_source: Optional[str],
        verification_reference: Optional[str] = None,
        verification_date: Optional[Union[date, datetime]] = None,
        gstr3b_filing_date: Optional[date] = None,
        gstr3b_arn: Optional[str] = None,
        user: Optional[Any] = None,
        manual_verification_reason: Optional[str] = None,
        evidence_record: Optional[Any] = None,
        freshness_threshold_days: int = DEFAULT_FRESHNESS_DAYS
    ) -> Dict[str, Any]:
        """
        Rigorous validation of evidence for Rule 37A ITC Reclaim under Proviso to Rule 37A.
        Enforces Section 16(2)(c) tax discharge requirements.
        """
        if not supplier_status or not str(supplier_status).strip():
            raise ValidationError("Rule 37A reclaim requires an explicit supplier filing status.")

        clean_status = str(supplier_status).strip().upper()

        if clean_status in ('DATA_UNAVAILABLE', 'PENDING', 'UNKNOWN', 'VERIFIED_NOT_FILED'):
            raise ValidationError(
                f"Cannot reclaim under Rule 37A: Supplier filing status '{clean_status}' does not establish tax payment for invoice #{voucher.voucher_number}."
            )

        if clean_status not in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED'):
            raise ValidationError(
                f"Cannot reclaim under Rule 37A: Supplier status '{clean_status}' is not eligible for reclaim on invoice #{voucher.voucher_number}."
            )

        inv_gstin = cls.resolve_supplier_gstin(voucher)
        if supplier_gstin and inv_gstin and supplier_gstin.strip().upper() != inv_gstin:
            raise ValidationError(
                f"Rule 37A reclaim rejected: Evidence supplier GSTIN '{supplier_gstin}' does not match invoice supplier GSTIN '{inv_gstin}'."
            )

        inv_period = cls.resolve_invoice_return_period(voucher)
        if supplier_return_period:
            clean_period = str(supplier_return_period).strip().replace('-', '').replace('/', '')
            if clean_period != inv_period:
                raise ValidationError(
                    f"Rule 37A reclaim rejected: Evidence return period '{supplier_return_period}' does not match invoice return period '{inv_period}'."
                )

        clean_source = str(verification_source or ("PORTAL" if clean_status == "VERIFIED_FILED" else "MANUAL")).strip().upper()
        clean_arn = str(gstr3b_arn or verification_reference or "").strip()
        g3b_date = gstr3b_filing_date

        if clean_status == 'VERIFIED_FILED':
            if not clean_arn:
                raise ValidationError("Rule 37A reclaim requires verified GSTR-3B filing Application Reference Number (ARN).")
            if not g3b_date:
                raise ValidationError("Rule 37A reclaim requires verified GSTR-3B filing date.")
        elif clean_status == 'MANUALLY_CONFIRMED':
            if not clean_arn and not verification_reference:
                raise ValidationError("Rule 37A manual reclaim requires document reference (e.g. CA certificate or challan reference).")
            if not user:
                raise ValidationError("Rule 37A manual reclaim requires verifier identity (user).")
            if not verification_date:
                raise ValidationError("Rule 37A manual reclaim requires verification timestamp.")

        v_timestamp = verification_date if isinstance(verification_date, datetime) else (
            timezone.datetime.combine(verification_date, timezone.datetime.min.time(), tzinfo=timezone.get_current_timezone())
            if isinstance(verification_date, date) else timezone.now()
        )

        evidence_hash = compute_rule37a_evidence_hash(
            company_id=voucher.company_id,
            voucher_id=voucher.id,
            supplier_gstin=inv_gstin,
            return_period=inv_period,
            evidence_source=clean_source,
            status=clean_status,
            arn=clean_arn,
            filing_date_str=g3b_date.isoformat() if g3b_date else "",
            verified_at_str=v_timestamp.isoformat(),
            document_ref=str(verification_reference or "").strip()
        )

        return {
            "supplier_status": clean_status,
            "supplier_gstin": inv_gstin,
            "supplier_return_period": inv_period,
            "evidence_source": clean_source,
            "verification_timestamp": v_timestamp,
            "filing_date": g3b_date,
            "arn": clean_arn,
            "document_ref": str(verification_reference or "").strip(),
            "manual_verification_reason": str(manual_verification_reason or "").strip(),
            "evidence_hash": evidence_hash,
            "evidence_record": evidence_record
        }
