"""
SriLekh ITC Explanation & Statutory Trace Service.
Provides a dual-lens explanation for any invoice's Input Tax Credit (ITC) lifecycle:
1. Business Owner View: Simple, plain-English status, financial impact, risk level, and next steps.
2. Professional Auditor View: Deep statutory citations, Section 16/17 analysis, chronological event lineage,
   reversal-to-reclaim graph, and cryptographic/statutory audit trail.
"""

import logging
from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from django.utils import timezone

from apps.accounting.models import Voucher
from apps.gst.models import (
    GSTReportingAllocation,
    GSTR2BRecord,
    SupplierGSTR3BFilingRecord,
    GSTReversalReclaimLineage,
    GSTFilingRecord
)
from apps.gst.services.allocation_service import GSTAllocationService, quantize_amount

logger = logging.getLogger(__name__)


class ITCTraceService:
    """
    Independent ITC Explanation & Audit Service for MSMEs and Tax Auditors.
    """

    @classmethod
    def trace_invoice_itc_lifecycle(cls, voucher: Voucher) -> Dict[str, Any]:
        """
        Produces a dual-lens ITC report containing both Business Owner View
        and Professional Auditor View.
        """
        bo_view = cls.get_business_owner_explanation(voucher)
        auditor_view = cls.get_professional_auditor_trace(voucher)

        return {
            "voucher_id": str(voucher.id),
            "voucher_number": voucher.voucher_number,
            "voucher_date": voucher.voucher_date.isoformat(),
            "business_owner_view": bo_view,
            "professional_auditor_view": auditor_view,
        }

    @classmethod
    def get_business_owner_explanation(cls, voucher: Voucher) -> Dict[str, Any]:
        """
        Generates intuitive, actionable plain-English explanation for business owners.
        """
        summary = GSTAllocationService.compute_voucher_monetary_summary(voucher)
        total_tax = summary["total_tax"]
        today = timezone.now().date()
        v_date = voucher.voucher_date
        fy = GSTAllocationService.get_financial_year(v_date)

        # Inward vs non-inward check
        if voucher.voucher_type != 'PURCHASE':
            return {
                "headline": "Not an Inward Supply",
                "risk_level": "SAFE",
                "status_badge": "NOT_APPLICABLE",
                "summary": f"Voucher #{voucher.voucher_number} is a {voucher.voucher_type} voucher, not a purchase invoice. ITC rules do not apply.",
                "financials": {
                    "invoice_total": voucher.total_amount,
                    "total_tax": total_tax,
                    "itc_availed": Decimal('0.00'),
                    "itc_reversed": Decimal('0.00'),
                    "itc_reclaimed": Decimal('0.00'),
                    "net_effective_itc": Decimal('0.00'),
                    "estimated_interest": Decimal('0.00'),
                },
                "actionable_recommendations": [],
                "important_deadlines": {}
            }

        # Check Section 17(5) blocked
        is_sec17_5 = (
            getattr(voucher, 'is_section_17_5_blocked', False) or
            GSTReportingAllocation.objects.filter(voucher=voucher, event_type='ITC_REVERSAL_SEC_17_5', is_active=True).exists()
        )
        if is_sec17_5:
            return {
                "headline": "Ineligible Blocked Credit (Section 17(5))",
                "risk_level": "CRITICAL",
                "status_badge": "BLOCKED_CREDIT",
                "summary": (
                    f"GST law (Section 17(5)) permanently blocks tax credit for this purchase "
                    f"(e.g. motor vehicles, catering, employee perks, or goods lost/stolen). Tax of ₹{total_tax} cannot be claimed."
                ),
                "financials": {
                    "invoice_total": voucher.total_amount,
                    "total_tax": total_tax,
                    "itc_availed": Decimal('0.00'),
                    "itc_reversed": Decimal('0.00'),
                    "itc_reclaimed": Decimal('0.00'),
                    "net_effective_itc": Decimal('0.00'),
                    "estimated_interest": Decimal('0.00'),
                },
                "actionable_recommendations": [
                    "Do not include this invoice in GSTR-3B Table 4(A) eligible ITC.",
                    "Expense the entire invoice amount including GST to your profit & loss account."
                ],
                "important_deadlines": {}
            }

        # Check receipt confirmation under Section 16(2)(b)
        alloc_inward = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='INWARD_ITC',
            is_active=True
        ).first()

        receipt_pending = (alloc_inward is not None and not alloc_inward.is_receipt_confirmed)
        partial_receipt = (alloc_inward is not None and alloc_inward.partial_received_fraction < Decimal('1.0000'))

        # Check Rule 37 (180 days non-payment)
        r37_status = GSTAllocationService.evaluate_rule37_status(voucher, check_date=today)
        unpaid = r37_status["unpaid_amount"]
        payment_deadline = r37_status["payment_deadline"]
        is_payment_overdue = r37_status["is_payment_overdue"]

        # Check Rule 37A (Supplier GSTR-3B default)
        party_gstin = (
            voucher.party_ledger.gstin
            if getattr(voucher, 'party_ledger', None) and voucher.party_ledger.gstin
            else getattr(voucher, 'party_gstin', '') or getattr(voucher, 'buyer_gstin', '') or ''
        ).strip().upper()

        inv_period = voucher.voucher_date.strftime('%m%Y')
        supp_record = SupplierGSTR3BFilingRecord.objects.filter(
            company=voucher.company,
            supplier_gstin=party_gstin,
            return_period=inv_period
        ).first() if party_gstin else None

        g2b_rec = GSTR2BRecord.objects.filter(
            company=voucher.company,
            matched_voucher=voucher
        ).first()

        supp_status = 'UNKNOWN'
        supp_date = None
        supp_filed = False
        is_stale = supp_record.is_stale() if supp_record else False

        if supp_record:
            if is_stale:
                supp_status = 'DATA_UNAVAILABLE'
                supp_filed = False
            else:
                supp_status = supp_record.status
                supp_filed = (supp_record.status in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED'))
                supp_date = supp_record.filing_date
        elif g2b_rec:
            if g2b_rec.gstr3b_status == 'FILED' and g2b_rec.gstr3b_filing_arn:
                supp_status = 'VERIFIED_FILED'
                supp_filed = True
                supp_date = g2b_rec.gstr3b_filing_date
            elif g2b_rec.gstr3b_status == 'NOT_FILED':
                supp_status = 'VERIFIED_NOT_FILED'
            elif g2b_rec.gstr3b_status == 'PENDING':
                supp_status = 'PENDING'
            else:
                supp_status = 'DATA_UNAVAILABLE'

        r37a_status = GSTAllocationService.evaluate_rule37a_status(
            voucher=voucher,
            check_date=today,
            supplier_gstr3b_filed=supp_filed,
            supplier_filing_date=supp_date,
            supplier_status=supp_status,
            supplier_return_period=inv_period,
            is_stale_evidence=is_stale
        )

        # Allocations summary
        all_allocs = GSTReportingAllocation.objects.filter(voucher=voucher, is_active=True)
        availed_tax = quantize_amount(sum(a.total_tax for a in all_allocs if a.event_type == 'INWARD_ITC' and a.is_statutorily_eligible))
        reversed_37 = quantize_amount(sum(a.total_tax for a in all_allocs if a.event_type == 'ITC_REVERSAL_RULE_37'))
        reversed_37a = quantize_amount(sum(a.total_tax for a in all_allocs if a.event_type == 'ITC_REVERSAL_RULE_37A'))
        total_reversed = reversed_37 + reversed_37a
        reclaimed_tax = quantize_amount(sum(a.total_tax for a in all_allocs if a.event_type == 'ITC_RECLAIM'))
        net_effective = quantize_amount(max(Decimal('0.00'), availed_tax - total_reversed + reclaimed_tax))

        # Interest exposure
        est_interest = Decimal('0.00')
        if r37_status["interest_applicable"] and r37_status.get("interest_details"):
            est_interest += r37_status["interest_details"]["interest_amount"]
        if r37a_status["interest_applicable"] and r37a_status.get("interest_details"):
            est_interest += r37a_status["interest_details"]["interest_amount"]

        # Formulate intuitive status & recommendations
        recommendations = []
        headline = "ITC Safe & On Track"
        risk_level = "SAFE"
        badge = "CLAIMABLE"

        if receipt_pending:
            headline = "Action Required: Confirm Goods/Services Receipt"
            risk_level = "ATTENTION"
            badge = "RECEIPT_PENDING"
            recommendations.append("Upload or link the Goods Receipt Note (GRN) or Delivery Challan to unlock ITC claim.")
        elif r37_status["reversal_required"]:
            headline = "Action Required: Pay Supplier or Reverse ITC (Rule 37)"
            risk_level = "HIGH" if is_payment_overdue else "ATTENTION"
            badge = "PAYMENT_OVERDUE" if is_payment_overdue else "180_DAYS_APPROACHING"
            if is_payment_overdue:
                recommendations.append(
                    f"Payment of ₹{unpaid} is overdue past the 180-day deadline ({payment_deadline.strftime('%d-%m-%Y')}). "
                    f"Reverse ₹{r37_status['required_reversal_tax']} in GSTR-3B Table 4(B)(2) to stop 18% annual interest accumulation."
                )
            else:
                days_left = (payment_deadline - today).days
                recommendations.append(
                    f"Pay remaining ₹{unpaid} to supplier before {payment_deadline.strftime('%d-%m-%Y')} ({days_left} days left) "
                    f"to avoid mandatory ITC reversal under Rule 37."
                )
        elif r37a_status["is_supplier_default"]:
            headline = "At Risk: Supplier Did Not File GSTR-3B (Rule 37A)"
            risk_level = "HIGH" if r37a_status["is_reversal_overdue"] else "ATTENTION"
            badge = "SUPPLIER_DEFAULT"
            rev_dl = r37a_status["recipient_reversal_deadline"]
            if r37a_status["is_reversal_overdue"]:
                recommendations.append(
                    f"Supplier failed to pay tax by 30-Sep. Your reversal deadline ({rev_dl.strftime('%d-%m-%Y')}) has passed. "
                    f"Reverse ₹{total_tax} in GSTR-3B immediately. Interest under Section 50 applies."
                )
            else:
                recommendations.append(
                    f"Supplier has not filed GSTR-3B. Follow up with supplier immediately. If not filed by {rev_dl.strftime('%d-%m-%Y')}, "
                    f"reverse ₹{total_tax} in your GSTR-3B return."
                )
        elif reversed_37 > Decimal('0.00') and r37_status["reclaimable_balance"] > Decimal('0.00'):
            headline = "Reversed ITC Available for Reclaim"
            risk_level = "SAFE"
            badge = "RECLAIMABLE"
            recommendations.append(
                f"₹{r37_status['reclaimable_balance']} previously reversed is ready to be reclaimed in GSTR-3B Table 4(D)(1) "
                f"upon payment to vendor. There is NO expiry deadline for reclaiming Rule 37 credit."
            )
        elif reversed_37a > Decimal('0.00') and r37a_status["reclaim_eligible"]:
            headline = "Supplier Filed Return: Ready to Reclaim ITC (Rule 37A)"
            risk_level = "SAFE"
            badge = "RECLAIMABLE"
            recommendations.append(
                f"Supplier has now furnished GSTR-3B. Reclaim ₹{reversed_37a} in GSTR-3B Table 4(D)(1). "
                f"Rule 37A reclaims are exempt from Section 16(4) time-limits."
            )
        elif supp_status in ('DATA_UNAVAILABLE', 'PENDING', 'UNKNOWN'):
            headline = "Pending Verification: Supplier GSTR-3B Evidence Unavailable"
            risk_level = "ATTENTION"
            badge = "PENDING_VERIFICATION"
            recommendations.append(
                f"Supplier GSTR-3B tax payment evidence is currently {supp_status.lower().replace('_', ' ')} from the GST portal. "
                "Default cannot be presumed without verified affirmative proof. Re-query GSTN or obtain manual challan confirmation."
            )
        else:
            recommendations.append("All statutory compliance checks passed. Invoice is eligible for full ITC claim.")

        return {
            "headline": headline,
            "risk_level": risk_level,
            "status_badge": badge,
            "summary": (
                f"Purchase invoice of ₹{voucher.total_amount} with ₹{total_tax} GST. "
                f"Effective ITC available: ₹{net_effective}."
            ),
            "financials": {
                "invoice_total": voucher.total_amount,
                "total_tax": total_tax,
                "itc_availed": availed_tax,
                "itc_reversed": total_reversed,
                "itc_reclaimed": reclaimed_tax,
                "net_effective_itc": net_effective,
                "unpaid_amount": unpaid,
                "estimated_interest": est_interest,
            },
            "actionable_recommendations": recommendations,
            "important_deadlines": {
                "rule_37_180_day_deadline": payment_deadline.isoformat(),
                "rule_37a_supplier_default_date": r37a_status["supplier_default_date"].isoformat(),
                "rule_37a_reversal_deadline": r37a_status["recipient_reversal_deadline"].isoformat(),
                "section_16_4_cutoff": GSTAllocationService.get_statutory_cutoff_date(v_date, company=voucher.company, return_type='INWARD_ITC').isoformat()
            }
        }

    @classmethod
    def get_professional_auditor_trace(cls, voucher: Voucher) -> Dict[str, Any]:
        """
        Generates deep, exhaustive statutory audit trail and lineage graph for Tax Auditors & CAs.
        """
        summary = GSTAllocationService.compute_voucher_monetary_summary(voucher)
        total_tax = summary["total_tax"]
        v_date = voucher.voucher_date
        fy = GSTAllocationService.get_financial_year(v_date)
        today = timezone.now().date()

        party_gstin = (
            voucher.party_ledger.gstin
            if getattr(voucher, 'party_ledger', None) and voucher.party_ledger.gstin
            else getattr(voucher, 'party_gstin', '') or getattr(voucher, 'buyer_gstin', '') or ''
        ).strip().upper()

        # 1. Section 16(2)(a) Valid Tax Document
        sec16_2_a = {
            "provision": "CGST Act Section 16(2)(a) & Rule 36(1)",
            "is_satisfied": bool(voucher.voucher_number and v_date and party_gstin),
            "details": {
                "voucher_number": voucher.voucher_number,
                "invoice_date": v_date.isoformat(),
                "supplier_gstin": party_gstin,
                "recipient_gstin": getattr(voucher.gst_registration, 'gstin', None) if getattr(voucher, 'gst_registration', None) else None,
                "taxable_value": summary["taxable_value"],
                "total_tax": total_tax
            }
        }

        # 2. Section 16(2)(b) Receipt of Goods or Services
        alloc_inward = GSTReportingAllocation.objects.filter(voucher=voucher, event_type='INWARD_ITC', is_active=True).first()
        sec16_2_b = {
            "provision": "CGST Act Section 16(2)(b) & First Proviso",
            "is_satisfied": bool(alloc_inward and alloc_inward.is_receipt_confirmed),
            "details": {
                "is_receipt_confirmed": alloc_inward.is_receipt_confirmed if alloc_inward else False,
                "receipt_type": alloc_inward.receipt_type if alloc_inward else "SINGLE",
                "receipt_document_type": alloc_inward.receipt_document_type if alloc_inward else "NONE",
                "receipt_document_number": alloc_inward.receipt_document_number if alloc_inward else "",
                "goods_received_date": alloc_inward.goods_received_date.isoformat() if (alloc_inward and alloc_inward.goods_received_date) else None,
                "partial_received_fraction": str(alloc_inward.partial_received_fraction) if alloc_inward else "1.0000",
                "receipt_confirmed_at": alloc_inward.receipt_confirmed_at.isoformat() if (alloc_inward and alloc_inward.receipt_confirmed_at) else None
            }
        }

        # 3. Section 16(2)(c) Tax Payment Proof
        g2b_rec = GSTR2BRecord.objects.filter(company=voucher.company, matched_voucher=voucher).first()
        supp_rec = SupplierGSTR3BFilingRecord.objects.filter(
            company=voucher.company,
            supplier_gstin=party_gstin
        ).order_by('-return_period').first() if party_gstin else None

        sec16_2_c = {
            "provision": "CGST Act Section 16(2)(c) & Rule 37A",
            "gstr1_filing_status": "FILED" if (g2b_rec and g2b_rec.gstr1_filing_date) else "UNVERIFIED",
            "gstr1_filing_date": g2b_rec.gstr1_filing_date.isoformat() if (g2b_rec and g2b_rec.gstr1_filing_date) else None,
            "gstr3b_status": supp_rec.status if supp_rec else (g2b_rec.gstr3b_status if g2b_rec else "UNKNOWN"),
            "gstr3b_filing_date": supp_rec.filing_date.isoformat() if (supp_rec and supp_rec.filing_date) else (g2b_rec.gstr3b_filing_date.isoformat() if (g2b_rec and g2b_rec.gstr3b_filing_date) else None),
            "gstr3b_arn": supp_rec.arn if supp_rec else (g2b_rec.gstr3b_filing_arn if g2b_rec else ""),
            "verification_source": supp_rec.verification_source if supp_rec else (g2b_rec.gstr3b_verification_source if g2b_rec else "UNKNOWN"),
            "statutory_note": (
                "GSTR-1 outward declaration reflects invoice details only. Section 16(2)(c) tax payment "
                "is evidenced solely by GSTR-3B return discharge and valid Filing ARN."
            )
        }

        # 4. Rule 37 Consideration Payment Analysis
        r37_eval = GSTAllocationService.evaluate_rule37_status(voucher, check_date=today)
        sec16_2_second_proviso = {
            "provision": "Second Proviso to Section 16(2) & CGST Rules Rule 37",
            "payment_deadline_180_days": r37_eval["payment_deadline"].isoformat(),
            "is_payment_overdue": r37_eval["is_payment_overdue"],
            "unpaid_amount": r37_eval["unpaid_amount"],
            "total_invoice_amount": r37_eval["total_invoice_amount"],
            "proportionate_reversal_tax": r37_eval["required_reversal_tax"],
            "interest_details": r37_eval["interest_details"] if r37_eval["interest_applicable"] else None
        }

        # 5. Section 16(4) / 16(5) / 16(6) Statutory Cutoffs
        sec16_status = GSTAllocationService.evaluate_section_16_status(voucher, check_date=today)
        cutoff_date = GSTAllocationService.get_statutory_cutoff_date(v_date, company=voucher.company, return_type='INWARD_ITC')
        statutory_cutoffs = {
            "financial_year": fy,
            "statutory_cutoff_date": cutoff_date.isoformat(),
            "status_verdict": sec16_status["status"],
            "is_eligible": sec16_status["is_eligible"],
            "notes": sec16_status["notes"]
        }

        # 6. Chronological Allocations Trail
        allocations = GSTReportingAllocation.objects.filter(voucher=voucher).order_type = ['created_at']
        raw_allocs = GSTReportingAllocation.objects.filter(voucher=voucher).order_by('created_at')
        events_trail = []
        for a in raw_allocs:
            events_trail.append({
                "allocation_id": str(a.id),
                "event_type": a.event_type,
                "assigned_period": a.assigned_period,
                "original_period": a.original_period,
                "status": a.status,
                "is_active": a.is_active,
                "taxable_value": a.taxable_value,
                "igst": a.igst_amount,
                "cgst": a.cgst_amount,
                "sgst": a.sgst_amount,
                "cess": a.cess_amount,
                "total_tax": a.total_tax,
                "idempotency_key": a.idempotency_key,
                "source_reversal_id": str(a.source_reversal_id) if a.source_reversal_id else None,
                "payment_event_id": a.payment_event_id,
                "payment_reference": a.payment_reference,
                "created_at": a.created_at.isoformat()
            })

        # 7. Lineage Graph (Reversal -> Reclaim)
        lineages = GSTReversalReclaimLineage.objects.filter(voucher=voucher).order_by('created_at')
        lineage_graph = []
        for l in lineages:
            lineage_graph.append({
                "lineage_id": str(l.id),
                "reversal_allocation_id": str(l.reversal_allocation_id),
                "reclaim_allocation_id": str(l.reclaim_allocation_id),
                "reclaimed_tax": l.reclaimed_tax,
                "igst_reclaimed": l.igst_reclaimed,
                "cgst_reclaimed": l.cgst_reclaimed,
                "sgst_reclaimed": l.sgst_reclaimed,
                "cess_reclaimed": l.cess_reclaimed,
                "statutory_rule": l.statutory_rule,
                "created_at": l.created_at.isoformat()
            })

        # 8. Cryptographic and Mathematical Invariants
        component_sum = summary["igst_amount"] + summary["cgst_amount"] + summary["sgst_amount"] + summary["cess_amount"]
        is_balanced = (component_sum == total_tax)

        return {
            "statutory_provisions_evaluated": {
                "section_16_2_a_tax_invoice": sec16_2_a,
                "section_16_2_b_goods_services_receipt": sec16_2_b,
                "section_16_2_c_tax_payment_proof": sec16_2_c,
                "section_16_2_second_proviso_rule_37": sec16_2_second_proviso,
                "section_16_4_time_bar": statutory_cutoffs
            },
            "lifecycle_events_trail": events_trail,
            "reversal_reclaim_lineage_graph": lineage_graph,
            "audit_integrity_verdict": {
                "mathematical_equilibrium": is_balanced,
                "has_orphaned_reclaims": bool(any(a["event_type"] == "ITC_RECLAIM" and not a["source_reversal_id"] for a in events_trail)),
                "statutory_compliance_status": sec16_status["status"]
            }
        }
