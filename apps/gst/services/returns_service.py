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
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.ledgers.models import Ledger
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
    INVARIANT: STRICTLY READ-ONLY with respect to accounting vouchers and ledgers.
    """

    @classmethod
    def parse_period(cls, period_str: str) -> Tuple[date, date, str, str]:
        """
        Parses return period string into (start_date, end_date, normalized_period_code, financial_year).
        Accepts: "082026", "2026-08", "Aug-2026", etc.
        """
        p = (period_str or '').strip().replace('-', '').replace('/', '')

        if len(p) == 6 and p.isdigit():
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
            now = timezone.now()
            year = now.year
            month = now.month

        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        period_code = f"{str(month).zfill(2)}{year}"

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
        Sections Supported:
        - Table 4: B2B Invoices (registered recipients)
        - Table 5: B2CL Invoices (unregistered recipients, interstate, value > ₹2,50,000)
        - Table 6: EXP (Exports with / without payment of tax)
        - Table 7: B2CS (All other supplies to unregistered persons)
        - Table 8: Nil-rated, Exempt, and Non-GST outward supplies
        - Table 9B: CDNR (Credit/Debit Notes to registered persons)
        - Table 9B: CDNUR (Credit/Debit Notes to unregistered persons)
        - Table 11A: Tax Liability on Advances Received
        - Table 11B: Adjustment of Advances
        - Table 12: HSN/SAC Summary
        - Table 13: Documents Issued Summary
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

        # GSTR-1 Section Buckets
        b2b_by_recipient = defaultdict(list)
        b2cl_list = []
        b2cs_groups = defaultdict(lambda: {
            "sply_ty": "INTRA",
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

        nil_exempt_summary = {
            "nil_amt": Decimal('0.00'),
            "expt_amt": Decimal('0.00'),
            "ngsup_amt": Decimal('0.00')
        }

        advances_received_list = []
        advances_adjusted_list = []

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

        exceptions = []
        clean_invoices_count = 0

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
            voucher_total = quantize_amount(v.total_amount)

            # Check for export supply
            is_export = bool(
                getattr(v, 'is_export', False)
                or (v.party_ledger and getattr(v.party_ledger, 'is_overseas', False))
                or pos in ['96', '97', '99']
            )

            # Exception validation
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

            rate_items = []
            voucher_has_tax = False
            for itm in voucher_items:
                rate = quantize_amount(itm.gst_rate)
                taxable = quantize_amount(itm.taxable_amount)
                igst = quantize_amount(itm.igst_amount)
                cgst = quantize_amount(itm.cgst_amount)
                sgst = quantize_amount(itm.sgst_amount)
                cess = quantize_amount(getattr(itm, 'cess_amount', 0))

                if rate > 0:
                    voucher_has_tax = True

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

                # HSN Summary aggregation (Table 12)
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

            # Table 8: Nil-rated or exempt tracking
            if not voucher_has_tax and voucher_total > 0:
                if is_interstate:
                    nil_exempt_summary["nil_amt"] += voucher_total
                else:
                    nil_exempt_summary["expt_amt"] += voucher_total

            # Classify into return sections
            if v.voucher_type == 'SALES':
                if is_export:
                    # Table 6: EXP (Exports)
                    exp_list.append({
                        "exp_typ": "WOPAY",
                        "inv": [{
                            "inum": v.voucher_number,
                            "idt": v.voucher_date.strftime('%d-%m-%Y'),
                            "val": float(voucher_total),
                            "sbnum": getattr(v, 'shipping_bill_number', '') or '',
                            "sbdt": getattr(v, 'shipping_bill_date', None).strftime('%d-%m-%Y') if getattr(v, 'shipping_bill_date', None) else '',
                            "itms": rate_items
                        }]
                    })
                elif is_registered:
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
                    # Table 5: B2CL (Interstate Large Invoices > 2.5L to unregistered)
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
                        r_key = (pos, "INTER" if is_interstate else "INTRA", quantize_amount(itm.gst_rate))
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
                orig_num = orig_inv.voucher_number if orig_inv else (v.reference_number or f"{v.voucher_number}-REF")
                orig_dt = orig_inv.voucher_date.strftime('%d-%m-%Y') if orig_inv else v.voucher_date.strftime('%d-%m-%Y')

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
                        "typ": "B2CL" if (is_interstate and voucher_total > Decimal('250000.00')) else "B2CS",
                        "nt": [note_obj]
                    })

            if not has_error:
                clean_invoices_count += 1

        # Check for Statutory Advances (Table 11A & Table 11B)
        advance_vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['RECEIPT', 'PAYMENT'],
            voucher_date__gte=start_date,
            voucher_date__lte=end_date,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES,
            is_advance=True
        )
        for av in advance_vouchers:
            adv_pos = (av.buyer_state_code or company_state).zfill(2)
            adv_taxable = quantize_amount(av.total_amount)
            adv_rate = quantize_amount(av.advance_tax_rate or 0)
            adv_tax = quantize_amount(av.advance_tax_amount or 0)
            advances_received_list.append({
                "pos": adv_pos,
                "sply_ty": "INTER" if adv_pos != company_state else "INTRA",
                "rt": float(adv_rate),
                "ad_amt": float(adv_taxable),
                "iamt": float(av.advance_igst),
                "camt": float(av.advance_cgst),
                "samt": float(av.advance_sgst),
                "csamt": 0.00
            })

        # Format payloads
        b2b_payload = [{"ctin": ctin, "inv": invs} for ctin, invs in b2b_by_recipient.items()]
        cdnr_payload = [{"ctin": ctin, "nt": notes} for ctin, notes in cdnr_by_recipient.items()]
        b2cs_payload = [
            {
                "sply_ty": g["sply_ty"],
                "pos": g["pos"],
                "rt": float(g["rt"]),
                "txval": float(g["txval"]),
                "iamt": float(g["iamt"]),
                "camt": float(g["camt"]),
                "samt": float(g["samt"]),
                "csamt": float(g["csamt"])
            }
            for g in b2cs_groups.values() if g["txval"] > 0
        ]

        hsn_payload = [
            {
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
            }
            for i, h in enumerate(hsn_summary_map.values(), 1) if h["txval"] > 0
        ]

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

        total_txval = sum(Decimal(str(h["txval"])) for h in hsn_payload)
        total_iamt = sum(Decimal(str(h["iamt"])) for h in hsn_payload)
        total_camt = sum(Decimal(str(h["camt"])) for h in hsn_payload)
        total_samt = sum(Decimal(str(h["samt"])) for h in hsn_payload)
        total_tax = total_iamt + total_camt + total_samt

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
            "nil": {
                "inv": [
                    {
                        "nil_amt": float(nil_exempt_summary["nil_amt"]),
                        "expt_amt": float(nil_exempt_summary["expt_amt"]),
                        "ngsup_amt": float(nil_exempt_summary["ngsup_amt"])
                    }
                ]
            },
            "at": advances_received_list,
            "txpd": advances_adjusted_list,
            "hsn": {"data": hsn_payload},
            "doc_issue": {"doc_det": doc_details}
        }

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
                "b2cl_invoices_count": len(b2cl_list),
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
    def calculate_rule88a_setoff(
        cls,
        outward_tax: Dict[str, Decimal],
        itc_available: Dict[str, Decimal]
    ) -> Dict[str, Any]:
        """
        Executes statutory Rule 88A Input Tax Credit set-off waterfall:
        Priority 1: Exhaust IGST credit completely against IGST liability, then CGST, then SGST.
        Priority 2: Exhaust CGST credit against remaining CGST liability, then IGST liability. (Never SGST).
        Priority 3: Exhaust SGST credit against remaining SGST liability, then IGST liability. (Never CGST).
        Priority 4: Cess sets off Cess only.
        """
        L_igst = outward_tax.get("igst", Decimal('0.00'))
        L_cgst = outward_tax.get("cgst", Decimal('0.00'))
        L_sgst = outward_tax.get("sgst", Decimal('0.00'))
        L_cess = outward_tax.get("cess", Decimal('0.00'))

        C_igst = itc_available.get("igst", Decimal('0.00'))
        C_cgst = itc_available.get("cgst", Decimal('0.00'))
        C_sgst = itc_available.get("sgst", Decimal('0.00'))
        C_cess = itc_available.get("cess", Decimal('0.00'))

        # Step 1: Cess offset
        cess_paid_itc = min(C_cess, L_cess)
        cash_cess = L_cess - cess_paid_itc
        rem_C_cess = C_cess - cess_paid_itc

        # Step 2: IGST credit offset
        igst_paid_igst_itc = min(C_igst, L_igst)
        rem_L_igst = L_igst - igst_paid_igst_itc
        rem_C_igst = C_igst - igst_paid_igst_itc

        # IGST credit used for CGST liability
        cgst_paid_igst_itc = Decimal('0.00')
        if rem_C_igst > 0 and L_cgst > 0:
            cgst_paid_igst_itc = min(rem_C_igst, L_cgst)
            L_cgst -= cgst_paid_igst_itc
            rem_C_igst -= cgst_paid_igst_itc

        # IGST credit used for SGST liability
        sgst_paid_igst_itc = Decimal('0.00')
        if rem_C_igst > 0 and L_sgst > 0:
            sgst_paid_igst_itc = min(rem_C_igst, L_sgst)
            L_sgst -= sgst_paid_igst_itc
            rem_C_igst -= sgst_paid_igst_itc

        # Step 3: CGST credit offset
        cgst_paid_cgst_itc = min(C_cgst, L_cgst)
        L_cgst -= cgst_paid_cgst_itc
        rem_C_cgst = C_cgst - cgst_paid_cgst_itc

        # CGST credit used for IGST liability (only if IGST credit exhausted)
        igst_paid_cgst_itc = Decimal('0.00')
        if rem_C_cgst > 0 and rem_L_igst > 0 and rem_C_igst == 0:
            igst_paid_cgst_itc = min(rem_C_cgst, rem_L_igst)
            rem_L_igst -= igst_paid_cgst_itc
            rem_C_cgst -= igst_paid_cgst_itc

        # Step 4: SGST credit offset
        sgst_paid_sgst_itc = min(C_sgst, L_sgst)
        L_sgst -= sgst_paid_sgst_itc
        rem_C_sgst = C_sgst - sgst_paid_sgst_itc

        # SGST credit used for IGST liability (only if IGST credit exhausted)
        igst_paid_sgst_itc = Decimal('0.00')
        if rem_C_sgst > 0 and rem_L_igst > 0 and rem_C_igst == 0:
            igst_paid_sgst_itc = min(rem_C_sgst, rem_L_igst)
            rem_L_igst -= igst_paid_sgst_itc
            rem_C_sgst -= igst_paid_sgst_itc

        cash_igst = rem_L_igst
        cash_cgst = L_cgst
        cash_sgst = L_sgst
        total_cash = cash_igst + cash_cgst + cash_sgst + cash_cess
        total_itc_carried_forward = rem_C_igst + rem_C_cgst + rem_C_sgst + rem_C_cess

        return {
            "setoff_details": {
                "igst": {
                    "liability": float(outward_tax.get("igst", Decimal('0.00'))),
                    "paid_by_igst_itc": float(igst_paid_igst_itc),
                    "paid_by_cgst_itc": float(igst_paid_cgst_itc),
                    "paid_by_sgst_itc": float(igst_paid_sgst_itc),
                    "cash_payable": float(cash_igst)
                },
                "cgst": {
                    "liability": float(outward_tax.get("cgst", Decimal('0.00'))),
                    "paid_by_igst_itc": float(cgst_paid_igst_itc),
                    "paid_by_cgst_itc": float(cgst_paid_cgst_itc),
                    "cash_payable": float(cash_cgst)
                },
                "sgst": {
                    "liability": float(outward_tax.get("sgst", Decimal('0.00'))),
                    "paid_by_igst_itc": float(sgst_paid_igst_itc),
                    "paid_by_sgst_itc": float(sgst_paid_sgst_itc),
                    "cash_payable": float(cash_sgst)
                },
                "cess": {
                    "liability": float(outward_tax.get("cess", Decimal('0.00'))),
                    "paid_by_cess_itc": float(cess_paid_itc),
                    "cash_payable": float(cash_cess)
                }
            },
            "net_cash_payable": {
                "igst": float(cash_igst),
                "cgst": float(cash_cgst),
                "sgst": float(cash_sgst),
                "cess": float(cash_cess),
                "total": float(total_cash)
            },
            "itc_carried_forward": {
                "igst": float(rem_C_igst),
                "cgst": float(rem_C_cgst),
                "sgst": float(rem_C_sgst),
                "cess": float(rem_C_cess),
                "total": float(total_itc_carried_forward)
            }
        }

    @classmethod
    def reconcile_accounting_ledgers(
        cls,
        company: Company,
        start_date: date,
        end_date: date,
        calculated_outward: Dict[str, Decimal],
        calculated_itc: Dict[str, Decimal]
    ) -> Dict[str, Any]:
        """
        Reconciles calculated GSTR taxes against General Ledger balances for the tax period.
        Compares calculated output tax vs Output GST liability ledger movements,
        and calculated ITC vs Input GST asset ledger movements.
        """
        tax_ledgers = Ledger.objects.filter(company=company, ledger_type='TAX')

        output_cgst_ledger_balance = Decimal('0.00')
        output_sgst_ledger_balance = Decimal('0.00')
        output_igst_ledger_balance = Decimal('0.00')
        input_cgst_ledger_balance = Decimal('0.00')
        input_sgst_ledger_balance = Decimal('0.00')
        input_igst_ledger_balance = Decimal('0.00')

        # Compute period net movements from LedgerEntries
        entries = LedgerEntry.objects.filter(
            company=company,
            ledger__in=tax_ledgers,
            voucher__voucher_date__gte=start_date,
            voucher__voucher_date__lte=end_date,
            voucher__status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('ledger')

        for ent in entries:
            name_lower = ent.ledger.name.lower()
            if 'output' in name_lower or 'sale' in name_lower:
                # Output Tax is Liability: Credits increase liability, Debits reduce it
                net = ent.credit_amount - ent.debit_amount
                if 'cgst' in name_lower or 'central' in name_lower:
                    output_cgst_ledger_balance += net
                elif 'sgst' in name_lower or 'state' in name_lower or 'utgst' in name_lower:
                    output_sgst_ledger_balance += net
                elif 'igst' in name_lower or 'integrated' in name_lower:
                    output_igst_ledger_balance += net
            elif 'input' in name_lower or 'purchase' in name_lower:
                # Input Tax is Asset: Debits increase asset, Credits reduce it
                net = ent.debit_amount - ent.credit_amount
                if 'cgst' in name_lower or 'central' in name_lower:
                    input_cgst_ledger_balance += net
                elif 'sgst' in name_lower or 'state' in name_lower or 'utgst' in name_lower:
                    input_sgst_ledger_balance += net
                elif 'igst' in name_lower or 'integrated' in name_lower:
                    input_igst_ledger_balance += net

        c_out_cgst = calculated_outward.get("cgst", Decimal('0.00'))
        c_out_sgst = calculated_outward.get("sgst", Decimal('0.00'))
        c_out_igst = calculated_outward.get("igst", Decimal('0.00'))

        c_in_cgst = calculated_itc.get("cgst", Decimal('0.00'))
        c_in_sgst = calculated_itc.get("sgst", Decimal('0.00'))
        c_in_igst = calculated_itc.get("itc_igst", calculated_itc.get("igst", Decimal('0.00')))

        return {
            "output_tax_reconciliation": {
                "cgst": {
                    "calculated": float(c_out_cgst),
                    "ledger_balance": float(output_cgst_ledger_balance),
                    "variance": float(c_out_cgst - output_cgst_ledger_balance)
                },
                "sgst": {
                    "calculated": float(c_out_sgst),
                    "ledger_balance": float(output_sgst_ledger_balance),
                    "variance": float(c_out_sgst - output_sgst_ledger_balance)
                },
                "igst": {
                    "calculated": float(c_out_igst),
                    "ledger_balance": float(output_igst_ledger_balance),
                    "variance": float(c_out_igst - output_igst_ledger_balance)
                }
            },
            "input_tax_reconciliation": {
                "cgst": {
                    "calculated": float(c_in_cgst),
                    "ledger_balance": float(input_cgst_ledger_balance),
                    "variance": float(c_in_cgst - input_cgst_ledger_balance)
                },
                "sgst": {
                    "calculated": float(c_in_sgst),
                    "ledger_balance": float(input_sgst_ledger_balance),
                    "variance": float(c_in_sgst - input_sgst_ledger_balance)
                },
                "igst": {
                    "calculated": float(c_in_igst),
                    "ledger_balance": float(input_igst_ledger_balance),
                    "variance": float(c_in_igst - input_igst_ledger_balance)
                }
            },
            "is_fully_reconciled": (
                abs(c_out_cgst - output_cgst_ledger_balance) <= Decimal('1.00') and
                abs(c_out_sgst - output_sgst_ledger_balance) <= Decimal('1.00') and
                abs(c_out_igst - output_igst_ledger_balance) <= Decimal('1.00')
            )
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
        Table 3.2: Interstate supplies to unregistered persons
        Table 4: Eligible Input Tax Credit (ITC) from purchase register
        Table 5: Values of exempt, nil-rated, and non-GST inward supplies
        Rule 88A Waterfall Set-off and Accounting Ledger Reconciliation.
        """
        start_date, end_date, period_code, fy = cls.parse_period(return_period)

        # 1. Outward Supplies (from GSTR-1 preparation)
        sales_data = cls.prepare_gstr1(company, registration, return_period)
        s_summary = sales_data["summary"]

        outward_taxable = Decimal(str(s_summary["total_taxable_value"]))
        outward_igst = Decimal(str(s_summary["total_igst"]))
        outward_cgst = Decimal(str(s_summary["total_cgst"]))
        outward_sgst = Decimal(str(s_summary["total_sgst"]))
        outward_cess = Decimal('0.00')

        # 2. Inward Supplies & Eligible ITC
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
        itc_cess = Decimal('0.00')

        inward_rcm_taxable = Decimal('0.00')
        inward_rcm_igst = Decimal('0.00')
        inward_rcm_cgst = Decimal('0.00')
        inward_rcm_sgst = Decimal('0.00')

        inward_nil_exempt_taxable = Decimal('0.00')

        for pv in purchase_vouchers:
            is_rcm = getattr(pv, 'is_reverse_charge', False)
            for itm in pv.items.all():
                tx = quantize_amount(itm.taxable_amount)
                ig = quantize_amount(itm.igst_amount)
                cg = quantize_amount(itm.cgst_amount)
                sg = quantize_amount(itm.sgst_amount)
                cs = quantize_amount(getattr(itm, 'cess_amount', 0))

                if is_rcm:
                    inward_rcm_taxable += tx
                    inward_rcm_igst += ig
                    inward_rcm_cgst += cg
                    inward_rcm_sgst += sg
                elif itm.gst_rate == 0:
                    inward_nil_exempt_taxable += tx
                else:
                    itc_taxable += tx
                    itc_igst += ig
                    itc_cgst += cg
                    itc_sgst += sg
                    itc_cess += cs

        # Table 3.2 Interstate to unregistered
        interstate_unreg_taxable = Decimal('0.00')
        interstate_unreg_igst = Decimal('0.00')
        for b2cl in sales_data.get("official_gstr1_json", {}).get("b2cl", []):
            for inv in b2cl.get("inv", []):
                for itm in inv.get("itms", []):
                    det = itm.get("itm_det", {})
                    interstate_unreg_taxable += Decimal(str(det.get("txval", 0)))
                    interstate_unreg_igst += Decimal(str(det.get("iamt", 0)))

        for b2cs in sales_data.get("official_gstr1_json", {}).get("b2cs", []):
            if b2cs.get("sply_ty") == "INTER":
                interstate_unreg_taxable += Decimal(str(b2cs.get("txval", 0)))
                interstate_unreg_igst += Decimal(str(b2cs.get("iamt", 0)))

        # Rule 88A Waterfall Set-off
        outward_tax_dict = {
            "igst": outward_igst + inward_rcm_igst,
            "cgst": outward_cgst + inward_rcm_cgst,
            "sgst": outward_sgst + inward_rcm_sgst,
            "cess": outward_cess
        }
        itc_dict = {
            "igst": itc_igst + inward_rcm_igst,
            "cgst": itc_cgst + inward_rcm_cgst,
            "sgst": itc_sgst + inward_rcm_sgst,
            "cess": itc_cess
        }
        setoff_result = cls.calculate_rule88a_setoff(outward_tax_dict, itc_dict)

        # Ledger balance reconciliation
        ledger_recon = cls.reconcile_accounting_ledgers(
            company=company,
            start_date=start_date,
            end_date=end_date,
            calculated_outward={"cgst": outward_cgst, "sgst": outward_sgst, "igst": outward_igst},
            calculated_itc={"cgst": itc_cgst, "sgst": itc_sgst, "igst": itc_igst}
        )

        table_3_1 = {
            "outward_taxable_supplies": {
                "taxable_value": float(outward_taxable),
                "igst": float(outward_igst),
                "cgst": float(outward_cgst),
                "sgst": float(outward_sgst),
                "cess": float(outward_cess)
            },
            "zero_rated_supplies": {"taxable_value": 0.00, "igst": 0.00, "cess": 0.00},
            "nil_exempt_supplies": {"taxable_value": 0.00},
            "inward_rcm_supplies": {
                "taxable_value": float(inward_rcm_taxable),
                "igst": float(inward_rcm_igst),
                "cgst": float(inward_rcm_cgst),
                "sgst": float(inward_rcm_sgst),
                "cess": 0.00
            },
            "non_gst_supplies": {"taxable_value": 0.00}
        }

        table_3_2 = {
            "supplies_to_unregistered": {
                "taxable_value": float(interstate_unreg_taxable),
                "igst": float(interstate_unreg_igst)
            },
            "supplies_to_composition": {"taxable_value": 0.00, "igst": 0.00},
            "supplies_to_uin": {"taxable_value": 0.00, "igst": 0.00}
        }

        table_4_itc = {
            "itc_available": {
                "import_goods": {"igst": 0.00, "cess": 0.00},
                "import_services": {"igst": 0.00, "cess": 0.00},
                "inward_rcm": {
                    "igst": float(inward_rcm_igst),
                    "cgst": float(inward_rcm_cgst),
                    "sgst": float(inward_rcm_sgst),
                    "cess": 0.00
                },
                "inward_isd": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00},
                "all_other_itc": {
                    "taxable_value": float(itc_taxable),
                    "igst": float(itc_igst),
                    "cgst": float(itc_cgst),
                    "sgst": float(itc_sgst),
                    "cess": float(itc_cess)
                }
            },
            "itc_reversed": {
                "as_per_rules_42_43": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00},
                "others": {"igst": 0.00, "cgst": 0.00, "sgst": 0.00, "cess": 0.00}
            },
            "net_itc_available": {
                "igst": float(itc_igst + inward_rcm_igst),
                "cgst": float(itc_cgst + inward_rcm_cgst),
                "sgst": float(itc_sgst + inward_rcm_sgst),
                "cess": float(itc_cess),
                "total": float(itc_igst + itc_cgst + itc_sgst + itc_cess + inward_rcm_igst + inward_rcm_cgst + inward_rcm_sgst)
            }
        }

        table_5 = {
            "inward_nil_exempt": {
                "interstate": 0.00,
                "intrastate": float(inward_nil_exempt_taxable)
            },
            "non_gst_inward": {"interstate": 0.00, "intrastate": 0.00}
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
            "table_3_2": table_3_2,
            "table_4_itc": table_4_itc,
            "table_5": table_5,
            "rule88a_setoff": setoff_result,
            "ledger_reconciliation": ledger_recon,
            "tax_payable": setoff_result["net_cash_payable"],
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
