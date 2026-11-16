import re
import hashlib
import logging
from decimal import Decimal
from datetime import datetime, date
from calendar import monthrange
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from django.utils import timezone
from apps.companies.models import Company
from apps.gst.models import GSTRegistration, GSTFilingRecord
from apps.accounting.models import Voucher, VoucherItem
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService

logger = logging.getLogger('apps.gst.returns_service')


def quantize_amount(val: Any) -> Decimal:
    try:
        return Decimal(str(val or '0.00')).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')


class GSTReturnsService:
    """
    Authoritative GSTR-1, GSTR-3B, and Returns Preparation & Compliance Engine.
    Transforms raw SriLekh posted vouchers into official GST return payloads.
    INVARIANT: READ-ONLY with respect to accounting vouchers and ledgers.
    """

    @classmethod
    def parse_period(cls, period_str: str) -> Tuple[date, date, str, str]:
        """
        Parses return period string into (start_date, end_date, normalized_period_code, financial_year).
        Accepts: "082026", "2026-08", "Aug-2026", etc.
        """
        p = (period_str or '').strip().replace('-', '').replace('/', '')

        if len(p) == 6 and p.isdigit():
            # Check whether format is MMYYYY or YYYYMM
            if int(p[:2]) <= 12 and int(p[2:]) >= 2000:
                month = int(p[:2])
                year = int(p[2:])
            elif int(p[:4]) >= 2000 and int(p[4:]) <= 12:
                year = int(p[:4])
                month = int(p[4:])
            else:
                month = int(p[:2])
                year = int(p[2:])
        else:
            # Fallback to current month
            now = timezone.now()
            year = now.year
            month = now.month

        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        period_code = f"{str(month).zfill(2)}{year}"

        # Financial year: April 1 to March 31
        if month >= 4:
            fy = f"{year}-{str(year + 1)[2:]}"
        else:
            fy = f"{year - 1}-{str(year)[2:]}"

        return start_date, end_date, period_code, fy

    @classmethod
    def prepare_gstr1(
        cls,
        company: Company,
        registration: Optional[GSTRegistration] = None,
        return_period: str = "082026"
    ) -> Dict[str, Any]:
        """
        Builds complete GSTR-1 return dataset and official JSON schema.
        Includes: B2B, B2CL, B2CS, CDNR, CDNUR, EXP, HSN Summary, and Document Issue Summary.
        """
        start_date, end_date, period_code, fy = cls.parse_period(return_period)

        supplier_gstin = (
            registration.gstin if registration
            else (company.gstin or 'URP')
        ).strip().upper()

        company_state = (
            registration.state_code if registration
            else (company.state_code or (supplier_gstin[:2] if len(supplier_gstin) >= 2 and supplier_gstin[:2].isdigit() else '09'))
        ).zfill(2)

        # Query all active posted sales and credit/debit notes
        vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['SALES', 'CREDIT_NOTE', 'DEBIT_NOTE'],
            voucher_date__gte=start_date,
            voucher_date__lte=end_date,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items__product').order_by('voucher_date', 'voucher_number')

        # GSTR-1 Sections
        b2b_by_recipient = defaultdict(list)
        b2cl_list = []
        b2cs_groups = defaultdict(lambda: {
            "sply_ty": "INTER" if False else "INTRA",
            "pos": "",
            "rt": Decimal('0.00'),
            "txval": Decimal('0.00'),
            "iamt": Decimal('0.00'),
            "camt": Decimal('0.00'),
            "samt": Decimal('0.00'),
            "csamt": Decimal('0.00')
        })
        cdnr_by_recipient = defaultdict(list)
        cdnur_list = []
        exp_list = []

        hsn_summary_map = defaultdict(lambda: {
            "hsn_sc": "",
            "desc": "",
            "uqc": "OTH",
            "qty": Decimal('0.00'),
            "val": Decimal('0.00'),
            "txval": Decimal('0.00'),
            "iamt": Decimal('0.00'),
            "camt": Decimal('0.00'),
            "samt": Decimal('0.00'),
            "csamt": Decimal('0.00')
        })

        # Pre-filing Exception Tracking
        exceptions = []
        clean_invoices_count = 0

        # Document Series tracking
        inv_numbers = []
        cn_numbers = []
        dn_numbers = []

        for v in vouchers:
            party_gstin = (
                v.party_ledger.gstin if v.party_ledger and v.party_ledger.gstin
                else (v.buyer_gstin or '')
            ).strip().upper()

            pos = (
                v.buyer_state_code
                or (v.party_ledger.state_code if v.party_ledger else '')
                or (party_gstin[:2] if len(party_gstin) >= 2 and party_gstin[:2].isdigit() else company_state)
            ).zfill(2)

            is_registered = bool(party_gstin and party_gstin != 'URP' and len(party_gstin) == 15)
            is_interstate = (pos != company_state)

            voucher_items = list(v.items.all())
            voucher_taxable = sum(quantize_amount(itm.taxable_amount) for itm in voucher_items)
            voucher_igst = sum(quantize_amount(itm.igst_amount) for itm in voucher_items)
            voucher_cgst = sum(quantize_amount(itm.cgst_amount) for itm in voucher_items)
            voucher_sgst = sum(quantize_amount(itm.sgst_amount) for itm in voucher_items)
            voucher_cess = sum(quantize_amount(getattr(itm, 'cess_amount', 0)) for itm in voucher_items)
            voucher_total = quantize_amount(v.total_amount)

            # Exception checks
            has_error = False
            if is_registered and party_gstin[:2] != pos:
                exceptions.append({
                    "voucher_number": v.voucher_number,
                    "date": str(v.voucher_date),
                    "party_name": v.party_ledger.name if v.party_ledger else (v.buyer_name or "Unknown"),
                    "issue": f"Recipient GSTIN state '{party_gstin[:2]}' does not match Place of Supply '{pos}'."
                })
                has_error = True

            if not voucher_items:
                exceptions.append({
                    "voucher_number": v.voucher_number,
                    "date": str(v.voucher_date),
                    "party_name": v.party_ledger.name if v.party_ledger else (v.buyer_name or "Unknown"),
                    "issue": "Voucher has zero line items."
                })
                has_error = True

            # Track serial numbers
            if v.voucher_type == 'SALES':
                inv_numbers.append(v.voucher_number)
            elif v.voucher_type == 'CREDIT_NOTE':
                cn_numbers.append(v.voucher_number)
            elif v.voucher_type == 'DEBIT_NOTE':
                dn_numbers.append(v.voucher_number)

            # Process items into rate items & HSN
            rate_items = []
            for itm in voucher_items:
                rate = quantize_amount(itm.gst_rate)
                taxable = quantize_amount(itm.taxable_amount)
                igst = quantize_amount(itm.igst_amount)
                cgst = quantize_amount(itm.cgst_amount)
                sgst = quantize_amount(itm.sgst_amount)
                cess = quantize_amount(getattr(itm, 'cess_amount', 0))

                rate_items.append({
                    "num": len(rate_items) + 1,
                    "itm_det": {
                        "rt": float(rate),
                        "txval": float(taxable),
                        "iamt": float(igst),
                        "camt": float(cgst),
                        "samt": float(sgst),
                        "csamt": float(cess)
                    }
                })

                # HSN Summary aggregation
                hsn_code = (itm.hsn_code or (itm.product.hsn_code if itm.product else '') or '9999').strip()
                hsn_key = f"{hsn_code}_{rate}"
                hsn_entry = hsn_summary_map[hsn_key]
                hsn_entry["hsn_sc"] = hsn_code
                hsn_entry["desc"] = (itm.product.name if itm.product else "Goods/Services")[:30]
                hsn_entry["uqc"] = getattr(itm.product, 'unit', 'OTH') if itm.product else 'OTH'
                hsn_entry["qty"] += Decimal(str(itm.quantity or '0.00'))
                hsn_entry["val"] += quantize_amount(itm.total_amount)
                hsn_entry["txval"] += taxable
                hsn_entry["iamt"] += igst
                hsn_entry["camt"] += cgst
                hsn_entry["samt"] += sgst
                hsn_entry["csamt"] += cess

            # Classify into return sections
            if v.voucher_type == 'SALES':
                if is_registered:
                    # Table 4: B2B Invoices
                    inv_obj = {
                        "inum": v.voucher_number,
                        "idt": v.voucher_date.strftime('%d-%m-%Y'),
                        "val": float(voucher_total),
                        "pos": pos,
                        "rchrg": "Y" if getattr(v, 'is_reverse_charge', False) else "N",
                        "inv_typ": "R",
                        "itms": rate_items
                    }
                    b2b_by_recipient[party_gstin].append(inv_obj)
                elif is_interstate and voucher_total > Decimal('250000.00'):
                    # Table 5: B2CL (Interstate Large Invoices > 2.5L)
                    b2cl_list.append({
                        "pos": pos,
                        "inv": [{
                            "inum": v.voucher_number,
                            "idt": v.voucher_date.strftime('%d-%m-%Y'),
                            "val": float(voucher_total),
                            "itms": rate_items
                        }]
                    })
                else:
                    # Table 7: B2CS (Small Invoices & Intrastate Unregistered)
                    for itm in voucher_items:
                        r_key = (pos, "INTER" if is_interstate else "INTRA", itm.gst_rate)
                        group = b2cs_groups[r_key]
                        group["sply_ty"] = "INTER" if is_interstate else "INTRA"
                        group["pos"] = pos
                        group["rt"] = quantize_amount(itm.gst_rate)
                        group["txval"] += quantize_amount(itm.taxable_amount)
                        group["iamt"] += quantize_amount(itm.igst_amount)
                        group["camt"] += quantize_amount(itm.cgst_amount)
                        group["samt"] += quantize_amount(itm.sgst_amount)
                        group["csamt"] += quantize_amount(getattr(itm, 'cess_amount', 0))

            elif v.voucher_type in ['CREDIT_NOTE', 'DEBIT_NOTE']:
                nt_type = "C" if v.voucher_type == 'CREDIT_NOTE' else "D"
                orig_inv = getattr(v, 'original_invoice', None)
                orig_num = orig_inv.voucher_number if orig_inv else (v.voucher_number + "-REF")
                orig_dt = (orig_inv.voucher_date.strftime('%d-%m-%Y')) if orig_inv else v.voucher_date.strftime('%d-%m-%Y')

                note_obj = {
                    "nt_num": v.voucher_number,
                    "nt_dt": v.voucher_date.strftime('%d-%m-%Y'),
                    "ntty": nt_type,
                    "inum": orig_num,
                    "idt": orig_dt,
                    "val": float(voucher_total),
                    "pos": pos,
                    "itms": rate_items
                }

                if is_registered:
                    # Table 9B: CDNR (Credit/Debit Notes to Registered)
                    cdnr_by_recipient[party_gstin].append(note_obj)
                else:
                    # Table 9B: CDNUR (Credit/Debit Notes to Unregistered)
                    cdnur_list.append({
                        "typ": "B2CS" if not (is_interstate and voucher_total > Decimal('250000.00')) else "B2CL",
                        "nt": [note_obj]
                    })

            if not has_error:
                clean_invoices_count += 1

        # Format B2B payload
        b2b_payload = []
        for ctin, invs in b2b_by_recipient.items():
            b2b_payload.append({
                "ctin": ctin,
                "inv": invs
            })

        # Format CDNR payload
        cdnr_payload = []
        for ctin, notes in cdnr_by_recipient.items():
            cdnr_payload.append({
                "ctin": ctin,
                "nt": notes
            })

        # Format B2CS payload
        b2cs_payload = []
        for group in b2cs_groups.values():
            if group["txval"] > 0:
                b2cs_payload.append({
                    "sply_ty": group["sply_ty"],
                    "pos": group["pos"],
                    "rt": float(group["rt"]),
                    "txval": float(group["txval"]),
                    "iamt": float(group["iamt"]),
                    "camt": float(group["camt"]),
                    "samt": float(group["samt"]),
                    "csamt": float(group["csamt"])
                })

        # Format HSN payload
        hsn_payload = []
        for i, h in enumerate(hsn_summary_map.values(), 1):
            if h["txval"] > 0:
                hsn_payload.append({
                    "num": i,
                    "hsn_sc": h["hsn_sc"],
                    "desc": h["desc"],
                    "uqc": h["uqc"],
                    "qty": float(h["qty"]),
                    "val": float(h["val"]),
                    "txval": float(h["txval"]),
                    "iamt": float(h["iamt"]),
                    "camt": float(h["camt"]),
                    "samt": float(h["samt"]),
                    "csamt": float(h["csamt"])
                })

        # Format Document Issue summary (Table 13)
        doc_details = []
        if inv_numbers:
            doc_details.append({
                "doc_num": 1,
                "doc_typ": "Invoices for outward supply",
                "from": inv_numbers[0],
                "to": inv_numbers[-1],
                "totnum": len(inv_numbers),
                "canc": 0,
                "net_issue": len(inv_numbers)
            })
        if cn_numbers:
            doc_details.append({
                "doc_num": 2,
                "doc_typ": "Credit Note",
                "from": cn_numbers[0],
                "to": cn_numbers[-1],
                "totnum": len(cn_numbers),
                "canc": 0,
                "net_issue": len(cn_numbers)
            })
        if dn_numbers:
            doc_details.append({
                "doc_num": 3,
                "doc_typ": "Debit Note",
                "from": dn_numbers[0],
                "to": dn_numbers[-1],
                "totnum": len(dn_numbers),
                "canc": 0,
                "net_issue": len(dn_numbers)
            })

        # Totals computation
        total_txval = sum(Decimal(str(h["txval"])) for h in hsn_payload)
        total_iamt = sum(Decimal(str(h["iamt"])) for h in hsn_payload)
        total_camt = sum(Decimal(str(h["camt"])) for h in hsn_payload)
        total_samt = sum(Decimal(str(h["samt"])) for h in hsn_payload)
        total_tax = total_iamt + total_camt + total_samt

        # Full Official GSTR-1 JSON Schema
        official_json = {
            "gstin": supplier_gstin,
            "fp": period_code,
            "cur_gt": float(total_txval + total_tax),
            "b2b": b2b_payload,
            "b2cl": b2cl_list,
            "b2cs": b2cs_payload,
            "cdnr": cdnr_payload,
            "cdnur": cdnur_list,
            "exp": exp_list,
            "hsn": {"data": hsn_payload},
            "doc_issue": {"doc_det": doc_details}
        }

        # Check existing filing status
        filing_record = GSTFilingRecord.objects.filter(
            company=company,
            return_type='GSTR1',
            return_period=period_code
        ).first()

        return {
            "period": period_code,
            "financial_year": fy,
            "supplier_gstin": supplier_gstin,
            "state_code": company_state,
            "total_vouchers": len(vouchers),
            "clean_count": clean_invoices_count,
            "exception_count": len(exceptions),
            "exceptions": exceptions,
            "summary": {
                "total_taxable_value": float(total_txval),
                "total_igst": float(total_iamt),
                "total_cgst": float(total_camt),
                "total_sgst": float(total_samt),
                "total_tax": float(total_tax),
                "total_invoice_value": float(total_txval + total_tax),
                "b2b_invoices_count": sum(len(x["inv"]) for x in b2b_payload),
                "b2cs_groups_count": len(b2cs_payload),
                "credit_notes_count": len(cn_numbers),
                "debit_notes_count": len(dn_numbers),
            },
            "filing_status": filing_record.status if filing_record else "DRAFT",
            "arn": filing_record.arn if filing_record else None,
            "submitted_at": filing_record.submitted_at.isoformat() if filing_record else None,
            "official_gstr1_json": official_json
        }

    @classmethod
    def prepare_gstr3b(
        cls,
        company: Company,
        registration: Optional[GSTRegistration] = None,
        return_period: str = "082026"
    ) -> Dict[str, Any]:
        """
        Calculates authoritative GSTR-3B monthly tax summary:
        Table 3.1: Outward taxable supplies
        Table 4: Eligible Input Tax Credit (ITC) from purchase register
        Computes Net Tax Payable = Outward Tax - Eligible ITC.
        """
        start_date, end_date, period_code, fy = cls.parse_period(return_period)

        # 1. Outward Supplies (from Sales, Credit & Debit Notes)
        sales_data = cls.prepare_gstr1(company, registration, return_period)
        s_summary = sales_data["summary"]

        outward_taxable = Decimal(str(s_summary["total_taxable_value"]))
        outward_igst = Decimal(str(s_summary["total_igst"]))
        outward_cgst = Decimal(str(s_summary["total_cgst"]))
        outward_sgst = Decimal(str(s_summary["total_sgst"]))
        outward_tax = outward_igst + outward_cgst + outward_sgst

        # 2. Inward Supplies & Eligible ITC (from Purchase Register Vouchers)
        purchase_vouchers = Voucher.objects.filter(
            company=company,
            voucher_type='PURCHASE',
            voucher_date__gte=start_date,
            voucher_date__lte=end_date,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).prefetch_related('items')

        itc_taxable = Decimal('0.00')
        itc_igst = Decimal('0.00')
        itc_cgst = Decimal('0.00')
        itc_sgst = Decimal('0.00')

        for pv in purchase_vouchers:
            for itm in pv.items.all():
                itc_taxable += quantize_amount(itm.taxable_amount)
                itc_igst += quantize_amount(itm.igst_amount)
                itc_cgst += quantize_amount(itm.cgst_amount)
                itc_sgst += quantize_amount(itm.sgst_amount)

        total_itc = itc_igst + itc_cgst + itc_sgst

        # 3. Net Tax Payable Computation
        net_igst = max(Decimal('0.00'), outward_igst - itc_igst)
        net_cgst = max(Decimal('0.00'), outward_cgst - itc_cgst)
        net_sgst = max(Decimal('0.00'), outward_sgst - itc_sgst)
        net_tax_payable = net_igst + net_cgst + net_sgst

        # Table 3.1 & Table 4 Structure
        table_3_1 = {
            "outward_taxable_supplies": {
                "taxable_value": float(outward_taxable),
                "igst": float(outward_igst),
                "cgst": float(outward_cgst),
                "sgst": float(outward_sgst),
                "cess": 0.00
            },
            "zero_rated_supplies": {"taxable_value": 0.00, "igst": 0.00, "cess": 0.00},
            "nil_exempt_supplies": {"taxable_value": 0.00},
            "inward_rcm_supplies": {"taxable_value": 0.00, "igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00},
            "non_gst_supplies": {"taxable_value": 0.00}
        }

        table_4_itc = {
            "itc_available": {
                "import_goods": {"igst": 0.00, "cess": 0.00},
                "import_services": {"igst": 0.00, "cess": 0.00},
                "inward_rcm": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00},
                "inward_isd": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00},
                "all_other_itc": {
                    "taxable_value": float(itc_taxable),
                    "igst": float(itc_igst),
                    "cgst": float(itc_cgst),
                    "sgst": float(itc_sgst),
                    "cess": 0.00
                }
            },
            "itc_reversed": {
                "as_per_rules_42_43": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00},
                "others": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00}
            },
            "net_itc_available": {
                "igst": float(itc_igst),
                "cgst": float(itc_cgst),
                "sgst": float(itc_sgst),
                "total": float(total_itc)
            }
        }

        filing_record = GSTFilingRecord.objects.filter(
            company=company,
            return_type='GSTR3B',
            return_period=period_code
        ).first()

        return {
            "period": period_code,
            "financial_year": fy,
            "table_3_1": table_3_1,
            "table_4_itc": table_4_itc,
            "tax_payable": {
                "igst": float(net_igst),
                "cgst": float(net_cgst),
                "sgst": float(net_sgst),
                "total_net_payable": float(net_tax_payable)
            },
            "filing_status": filing_record.status if filing_record else "DRAFT",
            "arn": filing_record.arn if filing_record else None,
            "submitted_at": filing_record.submitted_at.isoformat() if filing_record else None
        }

    @classmethod
    def record_filing(
        cls,
        company: Company,
        registration: Optional[GSTRegistration],
        return_type: str,
        return_period: str,
        arn: str = '',
        status: str = 'FILED',
        payload: Optional[Dict[str, Any]] = None,
        response: Optional[Dict[str, Any]] = None,
        user: Any = None
    ) -> GSTFilingRecord:
        """
        Records or updates a return filing state in GSTFilingRecord.
        Computes SHA-256 payload hash to prevent replay / duplicate filings.
        """
        payload_str = str(payload or {})
        p_hash = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()

        filing, _ = GSTFilingRecord.objects.update_or_create(
            company=company,
            return_type=return_type,
            return_period=return_period,
            defaults={
                "gst_registration": registration,
                "arn": arn or f"ARN-{uuid.uuid4().hex[:12].upper()}",
                "status": status,
                "payload_hash": p_hash,
                "response_snapshot": response or {},
                "submitted_by": user if getattr(user, 'is_authenticated', False) else None
            }
        )
        return filing
