import hashlib
from datetime import date, datetime, timezone as dt_timezone
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
    def normalize_and_validate_return_period(cls, period_str: Optional[str]) -> Optional[str]:
        """
        Normalizes and validates a GST return period.
        Strict requirement: Must be a 6-digit MMYYYY string (or MM-YYYY / MM/YYYY normalized).
        Month must be 01..12, Year must be valid 4 digits.
        Returns normalized 'MMYYYY' or None if blank, null, or malformed.
        """
        if not period_str:
            return None
        cleaned = str(period_str).strip().replace('-', '').replace('/', '')
        if len(cleaned) != 6 or not cleaned.isdigit():
            return None
        month = int(cleaned[:2])
        year = int(cleaned[2:])
        if month < 1 or month > 12 or year < 2017 or year > 2099:
            return None
        return cleaned

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
        supp_records = list(SupplierGSTR3BFilingRecord.objects.filter(
            company=voucher.company,
            supplier_gstin=supplier_gstin,
            return_period=inv_period
        ))

        supp_eval = None
        if supp_records:
            # Check internal consistency if multiple records exist
            distinct_statuses = {r.status for r in supp_records}
            if len(distinct_statuses) > 1 and ('VERIFIED_FILED' in distinct_statuses and 'VERIFIED_NOT_FILED' in distinct_statuses):
                # Multiple contradictory records for same period
                supp_eval = {
                    "status": "DATA_UNAVAILABLE",
                    "supplier_gstr3b_filed": False,
                    "is_stale": False,
                    "filing_date": None,
                    "arn": "",
                    "source": "SUPPLIER_RECORD",
                    "timestamp": None,
                    "record": None,
                    "document_ref": "",
                    "note": f"Contradictory SupplierGSTR3BFilingRecord entries for supplier {supplier_gstin} and period {inv_period}."
                }
            else:
                # Deterministically select the latest verified record
                supp_record = sorted(
                    supp_records,
                    key=lambda r: (r.verified_at or datetime.min.replace(tzinfo=dt_timezone.utc)),
                    reverse=True
                )[0]

                is_supp_stale = supp_record.is_stale(threshold_days=freshness_threshold_days)
                is_filed = supp_record.status in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED')

                if is_filed:
                    # Positive filing fact with verified ARN & filing date:
                    # An affirmative filing fact is an immutable historical event on GST portal.
                    # Preserve original source verification timestamp separately from filing date.
                    supp_eval = {
                        "status": supp_record.status,
                        "supplier_gstr3b_filed": True,
                        "is_stale": False,
                        "filing_date": supp_record.filing_date,
                        "arn": supp_record.arn,
                        "source": supp_record.verification_source or "SUPPLIER_RECORD",
                        "timestamp": supp_record.verified_at,
                        "record": supp_record,
                        "document_ref": supp_record.evidence_document_ref,
                        "note": supp_record.notes or "Authoritative SupplierGSTR3BFilingRecord"
                    }
                else:
                    # Negative non-filing evidence: Must have verification timestamp and must be fresh
                    if not supp_record.verified_at:
                        supp_eval = {
                            "status": "DATA_UNAVAILABLE",
                            "supplier_gstr3b_filed": False,
                            "is_stale": True,
                            "filing_date": None,
                            "arn": "",
                            "source": supp_record.verification_source or "SUPPLIER_RECORD",
                            "timestamp": None,
                            "record": supp_record,
                            "document_ref": supp_record.evidence_document_ref,
                            "note": "Negative non-filing evidence has no verification timestamp. Freshness cannot be established."
                        }
                    elif is_supp_stale:
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
                        supp_eval = {
                            "status": supp_record.status,
                            "supplier_gstr3b_filed": False,
                            "is_stale": False,
                            "filing_date": None,
                            "arn": "",
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

        # Filter strictly for matching supplier GSTIN and exact, validated GSTR-3B return period
        valid_g2b_matches = []
        has_matching_supplier_g2b = False
        for g2b in gstr2b_matches:
            # Multi-tenant isolation guard
            if str(g2b.company_id) != str(voucher.company_id):
                continue

            # Statutory Guard: Must match exact supplier GSTIN
            if not g2b.supplier_gstin or g2b.supplier_gstin.strip().upper() != supplier_gstin:
                continue

            has_matching_supplier_g2b = True

            # Statutory Guard: Must have non-empty, valid GSTR-3B return period matching exact invoice period
            # DO NOT infer or fall back to GSTR-2B batch statement period (g2b.return_period)
            raw_period = getattr(g2b, 'gstr3b_return_period', None) or ""
            norm_period = cls.normalize_and_validate_return_period(raw_period)
            if not norm_period or norm_period != inv_period:
                # Blank, null, malformed, or mismatched period: strictly exclude
                continue

            valid_g2b_matches.append(g2b)

        g2b_eval = None
        if not valid_g2b_matches and has_matching_supplier_g2b:
            # GSTR-2B record exists for voucher, but lacks verified exact-period GSTR-3B filing evidence
            g2b_eval = {
                "status": "DATA_UNAVAILABLE",
                "supplier_gstr3b_filed": False,
                "is_stale": False,
                "filing_date": None,
                "arn": "",
                "source": "GSTR2B",
                "timestamp": None,
                "record": None,
                "document_ref": "",
                "note": f"GSTR-2B record present for voucher #{voucher.voucher_number}, but lacks verified GSTR-3B filing evidence for exact period {inv_period}."
            }
        elif valid_g2b_matches:
            # Check for conflicting GSTR-2B records for the same voucher/period
            g2b_statuses = {g.gstr3b_status for g in valid_g2b_matches}
            if 'FILED' in g2b_statuses and 'NOT_FILED' in g2b_statuses:
                g2b_eval = {
                    "status": "DATA_UNAVAILABLE",
                    "supplier_gstr3b_filed": False,
                    "is_stale": False,
                    "filing_date": None,
                    "arn": "",
                    "source": "GSTR2B",
                    "timestamp": None,
                    "record": None,
                    "document_ref": "",
                    "note": f"Contradictory GSTR2BRecord entries for voucher #{voucher.voucher_number} and period {inv_period}."
                }
            else:
                # Deterministically pick the record with latest verification timestamp
                g2b = sorted(
                    valid_g2b_matches,
                    key=lambda r: (r.gstr3b_verified_at or datetime.min.replace(tzinfo=dt_timezone.utc)),
                    reverse=True
                )[0]

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
                elif g2b.gstr3b_status == 'NOT_FILED':
                    if not g2b.gstr3b_verified_at:
                        g2b_eval = {
                            "status": "DATA_UNAVAILABLE",
                            "supplier_gstr3b_filed": False,
                            "is_stale": True,
                            "filing_date": None,
                            "arn": "",
                            "source": g2b.gstr3b_verification_source or "GSTR2B",
                            "timestamp": None,
                            "record": g2b,
                            "document_ref": "",
                            "note": "GSTR-2B non-filing record has no verification timestamp. Freshness cannot be established."
                        }
                    elif is_g2b_stale:
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
                elif g2b.gstr1_filing_date and not g2b.gstr3b_filing_date:
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

        # 3. Detect and Reconcile Conflicts Across Sources
        if supp_eval and g2b_eval:
            # Direct contradiction: One filed, one not filed
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
                    "verification_timestamp": None,
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

            # Ambiguity: One NOT_FILED, other PENDING (cannot automate reversal on ambiguous evidence)
            if (supp_eval["status"] == 'VERIFIED_NOT_FILED' and g2b_eval["status"] == 'PENDING') or \
               (supp_eval["status"] == 'PENDING' and g2b_eval["status"] == 'VERIFIED_NOT_FILED'):
                return {
                    "status": "DATA_UNAVAILABLE",
                    "supplier_gstr3b_filed": False,
                    "is_stale": False,
                    "supplier_gstin": supplier_gstin,
                    "return_period": inv_period,
                    "filing_date": None,
                    "arn": "",
                    "evidence_source": "AMBIGUOUS_SOURCES",
                    "verification_timestamp": None,
                    "evidence_record": None,
                    "document_ref": "",
                    "provenance": {
                        "source": "AMBIGUOUS_SOURCES",
                        "supp_record_status": supp_eval["status"],
                        "gstr2b_status": g2b_eval["status"],
                        "reason": "Ambiguous evidence: One source reports NOT_FILED while another reports PENDING. Reversal requires verified, unambiguous evidence."
                    },
                    "errors": ["Ambiguous supplier filing evidence across records"]
                }

            # Priority to affirmative proof of filing:
            # If one source has affirmative verified filing with ARN and filing date,
            # it is not overridden by another source that merely has PENDING or DATA_UNAVAILABLE.
            if supp_eval["status"] in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED'):
                chosen = supp_eval
            elif g2b_eval["status"] in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED'):
                chosen = g2b_eval
            else:
                chosen = supp_eval or g2b_eval
        else:
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
            "verification_timestamp": chosen["timestamp"],
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
                if str(evidence_record.company_id) == str(voucher.company_id) and \
                   evidence_record.supplier_gstin.strip().upper() == clean_gstin and \
                   evidence_record.return_period.strip() == clean_period and \
                   evidence_record.status == 'VERIFIED_NOT_FILED' and \
                   not evidence_record.is_stale(threshold_days=freshness_threshold_days):
                    has_real_evidence = True
            elif isinstance(evidence_record, GSTR2BRecord):
                if str(evidence_record.company_id) == str(voucher.company_id) and \
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

            # Preserve original verification timestamp without synthesizing fake timezone.now()
            if verification_date:
                v_timestamp = verification_date if isinstance(verification_date, datetime) else timezone.datetime.combine(
                    verification_date, timezone.datetime.min.time(), tzinfo=timezone.get_current_timezone()
                )
            elif evidence_record and getattr(evidence_record, 'verified_at', None):
                v_timestamp = evidence_record.verified_at
            elif evidence_record and getattr(evidence_record, 'gstr3b_verified_at', None):
                v_timestamp = evidence_record.gstr3b_verified_at
            else:
                v_timestamp = None
        elif clean_status == 'MANUALLY_CONFIRMED':
            if not clean_arn and not verification_reference:
                raise ValidationError("Rule 37A manual reclaim requires document reference (e.g. CA certificate or challan reference).")
            if not user:
                raise ValidationError("Rule 37A manual reclaim requires verifier identity (user).")
            if not verification_date:
                raise ValidationError("Rule 37A manual reclaim requires verification timestamp.")

            v_timestamp = verification_date if isinstance(verification_date, datetime) else timezone.datetime.combine(
                verification_date, timezone.datetime.min.time(), tzinfo=timezone.get_current_timezone()
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
            verified_at_str=v_timestamp.isoformat() if v_timestamp else "",
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
