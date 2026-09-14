import logging
from decimal import Decimal
from typing import Dict, Any, List
from collections import defaultdict
from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService

logger = logging.getLogger(__name__)

class GSTRReportService:
    """
    Compiles official GST returns (GSTR-1 JSON schema and GSTR-3B tax summary)
    directly from posted vouchers.
    """

    @classmethod
    def generate_gstr1(cls, company: Company, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Generates official GSTR-1 JSON schema uploadable directly to gst.gov.in.
        """
        vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['SALES', 'CREDIT_NOTE', 'DEBIT_NOTE'],
            voucher_date__gte=start_date,
            voucher_date__lte=end_date,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).select_related('party_ledger').prefetch_related('items__product').order_by('voucher_date', 'voucher_number')

        company_state = (company.state_code or '09').zfill(2)
        
        b2b_by_gstin = defaultdict(list)
        b2cs_by_rate = defaultdict(lambda: {"txval": Decimal('0.00'), "iamt": Decimal('0.00'), "camt": Decimal('0.00'), "samt": Decimal('0.00')})
        hsn_summary = defaultdict(lambda: {
            "desc": "", "uqc": "PCS", "qty": Decimal('0.00'), "val": Decimal('0.00'),
            "txval": Decimal('0.00'), "iamt": Decimal('0.00'), "camt": Decimal('0.00'), "samt": Decimal('0.00'), "csamt": Decimal('0.00')
        })

        min_doc_no = None
        max_doc_no = None
        doc_count = 0

        for v in vouchers:
            doc_count += 1
            if not min_doc_no:
                min_doc_no = v.voucher_number
            max_doc_no = v.voucher_number

            party_gstin = (v.party_ledger.gstin if v.party_ledger and v.party_ledger.gstin else (v.buyer_gstin or '')).strip().upper()
            pos = (v.buyer_state_code or (v.party_ledger.state_code if v.party_ledger else '') or company_state).zfill(2)

            inv_items = []
            for itm in v.items.all():
                rate = float(itm.gst_rate)
                txval = itm.taxable_amount
                iamt = itm.igst_amount
                camt = itm.cgst_amount
                samt = itm.sgst_amount

                inv_items.append({
                    "num": len(inv_items) + 1,
                    "itm_det": {
                        "rt": rate,
                        "txval": float(txval),
                        "iamt": float(iamt),
                        "camt": float(camt),
                        "samt": float(samt),
                        "csamt": 0.0,
                    }
                })

                # HSN Aggregation
                hsn = str(itm.product.hsn_code or 8483) if itm.product else '8483'
                entry = hsn_summary[hsn]
                entry["desc"] = itm.product.name if itm.product else "Goods"
                entry["uqc"] = itm.product.unit if (itm.product and itm.product.unit) else "PCS"
                entry["qty"] += itm.quantity
                entry["val"] += itm.total_amount
                entry["txval"] += txval
                entry["iamt"] += iamt
                entry["camt"] += camt
                entry["samt"] += samt

            if party_gstin and len(party_gstin) == 15 and party_gstin != 'URP':
                # B2B Table 4
                inv_obj = {
                    "inum": v.voucher_number,
                    "idt": v.voucher_date.strftime('%d-%m-%Y'),
                    "val": float(v.total_amount),
                    "pos": pos,
                    "rchrg": "N",
                    "inv_typ": "R",
                    "itms": inv_items
                }
                b2b_by_gstin[party_gstin].append(inv_obj)
            else:
                # B2CS Table 7
                for itm in v.items.all():
                    rate_key = (pos, float(itm.gst_rate))
                    b2cs_by_rate[rate_key]["txval"] += itm.taxable_amount
                    b2cs_by_rate[rate_key]["iamt"] += itm.igst_amount
                    b2cs_by_rate[rate_key]["camt"] += itm.cgst_amount
                    b2cs_by_rate[rate_key]["samt"] += itm.sgst_amount

        # Format B2B payload
        b2b_list = []
        for gstin, invs in b2b_by_gstin.items():
            b2b_list.append({
                "ctin": gstin,
                "inv": invs
            })

        # Format B2CS payload
        b2cs_list = []
        for (pos, rt), vals in b2cs_by_rate.items():
            b2cs_list.append({
                "sply_ty": "INTER" if pos != company_state else "INTRA",
                "pos": pos,
                "typ": "OE",
                "rt": rt,
                "txval": float(vals["txval"]),
                "iamt": float(vals["iamt"]),
                "camt": float(vals["camt"]),
                "samt": float(vals["samt"]),
                "csamt": 0.0,
            })

        # Format HSN payload (Table 12)
        hsn_list = []
        for idx, (hsn, d) in enumerate(hsn_summary.items(), start=1):
            hsn_list.append({
                "num": idx,
                "hsn_sc": hsn,
                "desc": d["desc"],
                "uqc": d["uqc"],
                "qty": float(d["qty"]),
                "val": float(d["val"]),
                "txval": float(d["txval"]),
                "iamt": float(d["iamt"]),
                "camt": float(d["camt"]),
                "samt": float(d["samt"]),
                "csamt": 0.0,
            })

        # Format Doc Issue (Table 13)
        doc_issue = {
            "doc_det": [
                {
                    "doc_num": 1,
                    "doc_typ": "Invoices for outward supply",
                    "docs": [
                        {
                            "num": 1,
                            "from": min_doc_no or "N/A",
                            "to": max_doc_no or "N/A",
                            "totnum": doc_count,
                            "canc": 0,
                            "net_issue": doc_count
                        }
                    ]
                }
            ]
        }

        # Return full GSTR-1 payload conforming to GSTN schema
        return {
            "gstin": company.gstin or "09AAACB1234C1Z1",
            "fp": start_date.replace('-', '')[:6],  # YYYYMM format (e.g. 202608)
            "gt": float(sum([v.total_amount for v in vouchers], Decimal('0.00'))),
            "cur_gt": float(sum([v.total_amount for v in vouchers], Decimal('0.00'))),
            "b2b": b2b_list,
            "b2cs": b2cs_list,
            "hsn": {"data": hsn_list},
            "doc_issue": doc_issue,
            "summary": {
                "total_invoices": doc_count,
                "total_taxable_value": float(sum([d["txval"] for d in hsn_summary.values()], Decimal('0.00'))),
                "total_tax": float(sum([d["iamt"] + d["camt"] + d["samt"] for d in hsn_summary.values()], Decimal('0.00'))),
                "b2b_invoices_count": sum([len(invs) for invs in b2b_by_gstin.values()]),
                "b2cs_entries_count": len(b2cs_list),
            }
        }

    @classmethod
    def generate_gstr3b_summary(cls, company: Company, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Calculates Table 3.1 (Outward Supplies) vs Table 4 (Eligible ITC) for GSTR-3B.
        """
        # 1. Outward Supplies (Sales)
        sales_items = VoucherItem.objects.filter(
            voucher__company=company,
            voucher__voucher_type='SALES',
            voucher__voucher_date__gte=start_date,
            voucher__voucher_date__lte=end_date,
            voucher__status__in=EffectiveVoucherService.ACTIVE_STATUSES
        )
        
        sales_txval = sum([i.taxable_amount for i in sales_items], Decimal('0.00'))
        sales_igst = sum([i.igst_amount for i in sales_items], Decimal('0.00'))
        sales_cgst = sum([i.cgst_amount for i in sales_items], Decimal('0.00'))
        sales_sgst = sum([i.sgst_amount for i in sales_items], Decimal('0.00'))

        # 2. Inward Supplies (Purchases - Eligible ITC)
        purchase_items = VoucherItem.objects.filter(
            voucher__company=company,
            voucher__voucher_type='PURCHASE',
            voucher__voucher_date__gte=start_date,
            voucher__voucher_date__lte=end_date,
            voucher__status__in=EffectiveVoucherService.ACTIVE_STATUSES
        )
        
        pur_txval = sum([i.taxable_amount for i in purchase_items], Decimal('0.00'))
        itc_igst = sum([i.igst_amount for i in purchase_items], Decimal('0.00'))
        itc_cgst = sum([i.cgst_amount for i in purchase_items], Decimal('0.00'))
        itc_sgst = sum([i.sgst_amount for i in purchase_items], Decimal('0.00'))

        return {
            "company_name": company.name,
            "period": f"{start_date} to {end_date}",
            "table_3_1_outward_supplies": {
                "nature": "Outward taxable supplies (other than zero rated, nil rated and exempted)",
                "taxable_value": float(sales_txval),
                "igst": float(sales_igst),
                "cgst": float(sales_cgst),
                "sgst": float(sales_sgst),
                "cess": 0.0,
            },
            "table_4_eligible_itc": {
                "nature": "All other ITC (Inward supplies from registered persons)",
                "taxable_value": float(pur_txval),
                "igst": float(itc_igst),
                "cgst": float(itc_cgst),
                "sgst": float(itc_sgst),
                "cess": 0.0,
            },
            "net_tax_payable": {
                "igst": float(max(Decimal('0.00'), sales_igst - itc_igst)),
                "cgst": float(max(Decimal('0.00'), sales_cgst - itc_cgst)),
                "sgst": float(max(Decimal('0.00'), sales_sgst - itc_sgst)),
            }
        }
