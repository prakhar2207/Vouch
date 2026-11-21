import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone as dt_timezone
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


@dataclass
class PositiveFilingEvidenceValidationResult:
    """
    Structured, type-safe result of statutory positive filing evidence validation under Rule 37A.
    Eliminates reliance on raw booleans and unauthenticated status strings.
    """
    is_valid: bool
    filing_status: str
    supplier_gstin: str
    return_period: str
    company_id: Optional[str]
    evidence_source: str
    evidence_record_id: Optional[str]
    filing_date: Optional[date]
    filing_arn: str
    verification_timestamp: Optional[datetime]
    document_ref: str
    manual_verification_reason: str
    validation_errors: List[str]
    validation_reason: str
    evidence_hash: str = ""
    evidence_record: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "filing_status": self.filing_status,
            "supplier_status": self.filing_status,
            "supplier_gstin": self.supplier_gstin,
            "return_period": self.return_period,
            "supplier_return_period": self.return_period,
            "company_id": self.company_id,
            "evidence_source": self.evidence_source,
            "evidence_record_id": self.evidence_record_id,
            "filing_date": self.filing_date,
            "filing_arn": self.filing_arn,
            "arn": self.filing_arn,
            "verification_timestamp": self.verification_timestamp,
            "document_ref": self.document_ref,
            "manual_verification_reason": self.manual_verification_reason,
            "validation_errors": list(self.validation_errors),
            "validation_reason": self.validation_reason,
            "evidence_hash": self.evidence_hash,
            "evidence_record": self.evidence_record,
        }


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

                if supp_record.status == 'VERIFIED_FILED':
                    # Affirmative positive filing proof requires verified ARN & filing date
                    if not supp_record.arn or not supp_record.filing_date:
                        supp_eval = {
                            "status": "DATA_UNAVAILABLE",
                            "supplier_gstr3b_filed": False,
                            "is_stale": False,
                            "filing_date": None,
                            "arn": "",
                            "source": supp_record.verification_source or "SUPPLIER_RECORD",
                            "timestamp": supp_record.verified_at,
                            "record": supp_record,
                            "document_ref": supp_record.evidence_document_ref,
                            "note": "Supplier record has status VERIFIED_FILED but lacks verified filing date or ARN."
                        }
                    else:
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
                elif supp_record.status == 'MANUALLY_CONFIRMED':
                    # Manual confirmation requires documentary reference, verifying user, and timestamp
                    doc_ref = supp_record.evidence_document_ref or supp_record.arn
                    if not doc_ref or not supp_record.verified_by or not supp_record.verified_at:
                        supp_eval = {
                            "status": "DATA_UNAVAILABLE",
                            "supplier_gstr3b_filed": False,
                            "is_stale": False,
                            "filing_date": None,
                            "arn": "",
                            "source": "MANUAL",
                            "timestamp": supp_record.verified_at,
                            "record": supp_record,
                            "document_ref": doc_ref or "",
                            "note": "Manual confirmation record lacks documentary reference, verifier user, or verification timestamp."
                        }
                    else:
                        supp_eval = {
                            "status": supp_record.status,
                            "supplier_gstr3b_filed": True,
                            "is_stale": False,
                            "filing_date": supp_record.filing_date,
                            "arn": supp_record.arn,
                            "source": "MANUAL",
                            "timestamp": supp_record.verified_at,
                            "record": supp_record,
                            "document_ref": doc_ref,
                            "note": supp_record.notes or "Manual confirmation by authorized user"
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
        if not verification_timestamp or (isinstance(verification_timestamp, str) and not verification_timestamp.strip()):
            raise ValidationError("Rule 37A reversal requires a verification timestamp.")

        vt = None
        if isinstance(verification_timestamp, datetime):
            vt = verification_timestamp
        elif isinstance(verification_timestamp, date):
            vt = datetime.combine(verification_timestamp, datetime.min.time(), tzinfo=timezone.get_current_timezone())
        elif isinstance(verification_timestamp, str):
            try:
                vt = datetime.fromisoformat(verification_timestamp.strip())
            except (ValueError, TypeError):
                raise ValidationError("Rule 37A reversal requires a valid verification timestamp.")
        else:
            raise ValidationError("Rule 37A reversal requires a valid verification timestamp.")

        if timezone.is_naive(vt):
            vt = timezone.make_aware(vt, timezone.get_current_timezone())

        if vt > timezone.now() + timedelta(minutes=5):
            raise ValidationError("Verification timestamp cannot be in the future.")

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
        if vt:
            age_days = (timezone.now() - vt).days
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
    def validate_positive_filing_evidence(
        cls,
        voucher: Voucher,
        supplier_status: Optional[str] = None,
        supplier_gstin: Optional[str] = None,
        supplier_return_period: Optional[str] = None,
        verification_source: Optional[str] = None,
        verification_reference: Optional[str] = None,
        verification_date: Optional[Union[date, datetime, str]] = None,
        verification_timestamp: Optional[Union[date, datetime, str]] = None,
        gstr3b_filing_date: Optional[Union[date, str]] = None,
        gstr3b_arn: Optional[str] = None,
        user: Optional[Any] = None,
        manual_verification_reason: Optional[str] = None,
        evidence_record: Optional[Any] = None,
        freshness_threshold_days: int = DEFAULT_FRESHNESS_DAYS,
        raise_exception: bool = False
    ) -> PositiveFilingEvidenceValidationResult:
        """
        Authoritative validation of positive supplier GSTR-3B filing evidence under Rule 37A and Section 16(2)(c).
        Enforces:
        - Supplier identity: GSTIN must match invoice supplier GSTIN
        - Tenant & company isolation: Evidence company must match voucher company
        - Exact return period: Must match invoice return period (MMYYYY)
        - Positive filing proof: Verified status, ARN, filing date, active supporting record in DB
        - Manual verification: Verifier identity (user), documentary reference, documented reason, timestamp
        - Evidence conflicts: Contradictory evidence across sources fails closed
        - Type-safe result: Returns PositiveFilingEvidenceValidationResult
        """
        validation_errors: List[str] = []

        # 1. Supplier Identity Validation
        inv_gstin = cls.resolve_supplier_gstin(voucher)
        if not inv_gstin:
            validation_errors.append("Invoice voucher has no supplier GSTIN. Filing evidence cannot be validated.")

        clean_supp_gstin = str(supplier_gstin or "").strip().upper()
        if clean_supp_gstin and inv_gstin and clean_supp_gstin != inv_gstin:
            validation_errors.append(
                f"Rule 37A positive evidence rejected: Evidence supplier GSTIN '{supplier_gstin}' does not match invoice supplier GSTIN '{inv_gstin}'."
            )
        target_gstin = clean_supp_gstin or inv_gstin

        # 2. Return Period Validation
        inv_period = cls.resolve_invoice_return_period(voucher)
        clean_period = None
        if supplier_return_period:
            clean_period = cls.normalize_and_validate_return_period(supplier_return_period)
            if not clean_period:
                validation_errors.append(f"Rule 37A positive evidence rejected: Return period '{supplier_return_period}' is malformed.")
            elif clean_period != inv_period:
                validation_errors.append(
                    f"Rule 37A positive evidence rejected: Evidence return period '{supplier_return_period}' does not match invoice return period '{inv_period}'."
                )
        target_period = clean_period or inv_period

        # 3. Status Validation
        clean_status = str(supplier_status or "").strip().upper()
        if not clean_status:
            validation_errors.append("Rule 37A positive filing evidence requires an explicit supplier filing status.")
        elif clean_status in ('DATA_UNAVAILABLE', 'PENDING', 'UNKNOWN', 'VERIFIED_NOT_FILED'):
            validation_errors.append(
                f"Cannot authorize positive filing: supplier status '{clean_status}' does not establish tax payment or discharge under Section 16(2)(c)."
            )
        elif clean_status not in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED'):
            validation_errors.append(
                f"Cannot authorize positive filing: supplier status '{clean_status}' is not eligible for positive filing authorization."
            )

        # 4. Tenant and Company Isolation & Evidence Record Validation
        if evidence_record is not None:
            rec_comp_id = str(getattr(evidence_record, 'company_id', None) or '')
            if rec_comp_id and rec_comp_id != str(voucher.company_id):
                validation_errors.append(
                    f"Cross-Tenant Evidence Violation: Evidence record company '{rec_comp_id}' does not match voucher company '{voucher.company_id}'."
                )
            if isinstance(evidence_record, SupplierGSTR3BFilingRecord):
                if evidence_record.supplier_gstin.strip().upper() != target_gstin:
                    validation_errors.append(
                        f"Evidence record supplier GSTIN '{evidence_record.supplier_gstin}' does not match invoice supplier GSTIN '{target_gstin}'."
                    )
                if evidence_record.return_period.strip() != target_period:
                    validation_errors.append(
                        f"Evidence record return period '{evidence_record.return_period}' does not match invoice return period '{target_period}'."
                    )
            elif isinstance(evidence_record, GSTR2BRecord):
                if evidence_record.supplier_gstin.strip().upper() != target_gstin:
                    validation_errors.append(
                        f"GSTR-2B evidence record supplier GSTIN '{evidence_record.supplier_gstin}' does not match invoice supplier GSTIN '{target_gstin}'."
                    )
                norm_g2b = cls.normalize_and_validate_return_period(evidence_record.gstr3b_return_period)
                if not norm_g2b or norm_g2b != target_period:
                    validation_errors.append(
                        f"GSTR-2B evidence record return period '{evidence_record.gstr3b_return_period}' does not match invoice return period '{target_period}'."
                    )
                if evidence_record.matched_voucher_id and str(evidence_record.matched_voucher_id) != str(voucher.id):
                    validation_errors.append("GSTR-2B record is matched to an unrelated voucher.")

        # 5. Auto-Lookup Evidence Record if not provided
        if evidence_record is None and target_gstin and target_period:
            supp_rec = SupplierGSTR3BFilingRecord.objects.filter(
                company=voucher.company,
                supplier_gstin=target_gstin,
                return_period=target_period
            ).first()
            g2b_rec = GSTR2BRecord.objects.filter(
                company=voucher.company,
                matched_voucher=voucher
            ).first()

            if supp_rec and supp_rec.status == clean_status:
                evidence_record = supp_rec
            elif g2b_rec and clean_status == 'VERIFIED_FILED' and g2b_rec.gstr3b_status == 'FILED':
                norm_p = cls.normalize_and_validate_return_period(g2b_rec.gstr3b_return_period)
                if norm_p == target_period:
                    evidence_record = g2b_rec

        # 6. Evidence Conflict Check
        if target_gstin and target_period:
            supp_records = list(SupplierGSTR3BFilingRecord.objects.filter(
                company=voucher.company,
                supplier_gstin=target_gstin,
                return_period=target_period
            ))
            statuses = {r.status for r in supp_records}
            if 'VERIFIED_FILED' in statuses and 'VERIFIED_NOT_FILED' in statuses:
                validation_errors.append(
                    f"Contradictory SupplierGSTR3BFilingRecord entries detected for supplier {target_gstin} and period {target_period}."
                )

            g2b_match = GSTR2BRecord.objects.filter(
                company=voucher.company,
                matched_voucher=voucher
            ).first()
            if supp_records and g2b_match:
                active_supp = supp_records[0]
                if (active_supp.status in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED') and g2b_match.gstr3b_status == 'NOT_FILED') or \
                   (active_supp.status == 'VERIFIED_NOT_FILED' and g2b_match.gstr3b_status == 'FILED'):
                    validation_errors.append(
                        f"Conflicting positive and negative filing evidence across portal records and supplier records."
                    )

        # 7. Pathway-Specific Validation
        clean_source = str(verification_source or ("PORTAL" if clean_status == "VERIFIED_FILED" else "MANUAL")).strip().upper()
        clean_arn = str(gstr3b_arn or verification_reference or (getattr(evidence_record, 'arn', '') if isinstance(evidence_record, SupplierGSTR3BFilingRecord) else getattr(evidence_record, 'gstr3b_filing_arn', ''))).strip()
        eff_filing_date = gstr3b_filing_date or (getattr(evidence_record, 'filing_date', None) if isinstance(evidence_record, SupplierGSTR3BFilingRecord) else getattr(evidence_record, 'gstr3b_filing_date', None))
        if isinstance(eff_filing_date, str):
            try:
                eff_filing_date = date.fromisoformat(eff_filing_date.strip())
            except Exception:
                validation_errors.append("Invalid GSTR-3B filing date format.")
                eff_filing_date = None

        v_timestamp = None
        raw_v_date = verification_timestamp or verification_date or getattr(evidence_record, 'verified_at', None) or getattr(evidence_record, 'gstr3b_verified_at', None)
        if raw_v_date:
            if isinstance(raw_v_date, datetime):
                v_timestamp = raw_v_date if timezone.is_aware(raw_v_date) else timezone.make_aware(raw_v_date)
            elif isinstance(raw_v_date, date):
                v_timestamp = timezone.datetime.combine(
                    raw_v_date, timezone.datetime.min.time(), tzinfo=timezone.get_current_timezone()
                )
            elif isinstance(raw_v_date, str):
                try:
                    dt = datetime.fromisoformat(raw_v_date.strip().replace('Z', '+00:00'))
                    v_timestamp = dt if timezone.is_aware(dt) else timezone.make_aware(dt)
                except Exception:
                    validation_errors.append("Invalid verification timestamp format.")

        eff_user = user or getattr(evidence_record, 'verified_by', None)
        eff_doc_ref = str(verification_reference or (getattr(evidence_record, 'evidence_document_ref', '') if isinstance(evidence_record, SupplierGSTR3BFilingRecord) else '') or clean_arn or "").strip()
        eff_reason = str(manual_verification_reason or (getattr(evidence_record, 'notes', '') if isinstance(evidence_record, SupplierGSTR3BFilingRecord) else '') or "").strip()

        if clean_status == 'VERIFIED_FILED':
            if not clean_arn:
                validation_errors.append("Rule 37A reclaim requires verified GSTR-3B filing Application Reference Number (ARN).")
            if not eff_filing_date:
                validation_errors.append("Rule 37A reclaim requires verified GSTR-3B filing date.")
            elif eff_filing_date > timezone.now().date() + timedelta(days=1):
                validation_errors.append(f"Rule 37A positive evidence rejected: GSTR-3B filing date '{eff_filing_date}' cannot be in the future.")

            if not evidence_record:
                validation_errors.append(
                    "Rule 37A positive filing evidence (VERIFIED_FILED) requires a verified, persisted evidence record (SupplierGSTR3BFilingRecord or GSTR2BRecord) in the database."
                )
            else:
                if isinstance(evidence_record, SupplierGSTR3BFilingRecord):
                    if evidence_record.status not in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED'):
                        validation_errors.append(f"SupplierGSTR3BFilingRecord status '{evidence_record.status}' does not establish affirmative filing.")
                elif isinstance(evidence_record, GSTR2BRecord):
                    if evidence_record.gstr3b_status != 'FILED':
                        validation_errors.append(f"GSTR2BRecord status '{evidence_record.gstr3b_status}' does not establish affirmative GSTR-3B filing.")
                    if evidence_record.gstr1_filing_date and not evidence_record.gstr3b_filing_date:
                        validation_errors.append(
                            "Cannot reclaim under Rule 37A: Supplier has filed GSTR-1, but affirmative proof of GSTR-3B return filing (filing date / ARN) is required. GSTR-1 outward declaration does not discharge tax liability under Section 16(2)(c)."
                        )
        elif clean_status == 'MANUALLY_CONFIRMED':
            if not eff_doc_ref:
                validation_errors.append("Rule 37A manual reclaim requires document reference (e.g. CA certificate or challan reference).")
            if not eff_user:
                validation_errors.append("Rule 37A manual reclaim requires verifier identity (user).")
            elif hasattr(eff_user, 'is_active') and not eff_user.is_active:
                validation_errors.append("Rule 37A manual reclaim verifier user is inactive.")
            if not eff_reason:
                validation_errors.append("Rule 37A manual confirmation requires a documented verification reason.")
            if not v_timestamp:
                validation_errors.append("Rule 37A manual reclaim requires verification timestamp.")

        is_valid = len(validation_errors) == 0
        validation_reason = "; ".join(validation_errors) if validation_errors else "Positive supplier filing evidence fully validated."

        evidence_hash = ""
        if is_valid:
            evidence_hash = compute_rule37a_evidence_hash(
                company_id=voucher.company_id,
                voucher_id=voucher.id,
                supplier_gstin=target_gstin,
                return_period=target_period,
                evidence_source=clean_source,
                status=clean_status,
                arn=clean_arn,
                filing_date_str=eff_filing_date.isoformat() if eff_filing_date else "",
                verified_at_str=v_timestamp.isoformat() if v_timestamp else "",
                document_ref=eff_doc_ref
            )

        res = PositiveFilingEvidenceValidationResult(
            is_valid=is_valid,
            filing_status=clean_status,
            supplier_gstin=target_gstin,
            return_period=target_period,
            company_id=str(voucher.company_id),
            evidence_source=clean_source,
            evidence_record_id=str(evidence_record.id) if evidence_record and hasattr(evidence_record, 'id') else None,
            filing_date=eff_filing_date,
            filing_arn=clean_arn,
            verification_timestamp=v_timestamp,
            document_ref=eff_doc_ref,
            manual_verification_reason=eff_reason,
            validation_errors=validation_errors,
            validation_reason=validation_reason,
            evidence_hash=evidence_hash,
            evidence_record=evidence_record
        )

        if raise_exception and not is_valid:
            raise ValidationError(validation_reason)

        return res

    @classmethod
    def validate_reclaim_evidence(
        cls,
        voucher: Voucher,
        supplier_status: Optional[str],
        supplier_gstin: Optional[str],
        supplier_return_period: Optional[str],
        verification_source: Optional[str] = None,
        verification_reference: Optional[str] = None,
        verification_date: Optional[Union[date, datetime, str]] = None,
        gstr3b_filing_date: Optional[Union[date, str]] = None,
        gstr3b_arn: Optional[str] = None,
        user: Optional[Any] = None,
        manual_verification_reason: Optional[str] = None,
        evidence_record: Optional[Any] = None,
        freshness_threshold_days: int = DEFAULT_FRESHNESS_DAYS,
        verification_timestamp: Optional[Union[date, datetime, str]] = None
    ) -> Dict[str, Any]:
        """
        Rigorous validation of evidence for Rule 37A ITC Reclaim under Proviso to Rule 37A.
        Enforces Section 16(2)(c) tax discharge requirements.
        Delegates to authoritative validate_positive_filing_evidence with raise_exception=True.
        """
        res = cls.validate_positive_filing_evidence(
            voucher=voucher,
            supplier_status=supplier_status,
            supplier_gstin=supplier_gstin,
            supplier_return_period=supplier_return_period,
            verification_source=verification_source,
            verification_reference=verification_reference,
            verification_date=verification_date,
            verification_timestamp=verification_timestamp or verification_date,
            gstr3b_filing_date=gstr3b_filing_date,
            gstr3b_arn=gstr3b_arn,
            user=user,
            manual_verification_reason=manual_verification_reason,
            evidence_record=evidence_record,
            freshness_threshold_days=freshness_threshold_days,
            raise_exception=True
        )
        return res.to_dict()
