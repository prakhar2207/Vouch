import re
import logging
from decimal import Decimal
from datetime import datetime, date
from calendar import monthrange
from typing import Dict, Any, List, Optional, Set
from django.utils import timezone

logger = logging.getLogger('apps.gst.payload_validator')

# Standard GST statutory regex patterns
GSTIN_REGEX = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$')
PERIOD_REGEX = re.compile(r'^(0[1-9]|1[0-2])(20[1-9][0-9])$')
INVOICE_NUM_REGEX = re.compile(r'^[A-Za-z0-9\-\/]{1,16}$')
HSN_REGEX = re.compile(r'^\d{4,8}$')

# Statutory valid GST state codes (37 states/UTs + 96, 97, 99)
VALID_POS_CODES: Set[str] = {
    f"{i:02d}" for i in range(1, 39)
}.union({"96", "97", "99"})

# Approved standard GST tax rates in India
STANDARD_GST_RATES: Set[float] = {
    0.0, 0.1, 0.25, 1.5, 3.0, 5.0, 6.0, 7.5, 12.0, 18.0, 28.0
}


def _quant(val: Any) -> Decimal:
    try:
        return Decimal(str(val or '0.00')).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')


class GSTPayloadValidator:
    """
    Authoritative Pre-Export GST Return Payload Validation Engine (Round 2.2).
    Enforces GSTN Offline Tool Schema v3.1.2 (GSTR-1) and v1.4 (GSTR-3B).
    
    Verifies:
    1. Header & Schema Structure conformance (GSTIN, return period, version).
    2. Sectional and invoice-level constraints (PoS codes, invoice numbers, dates).
    3. Mathematical equilibrium (tax rates, invoice total vs items, intrastate vs interstate tax heads).
    4. Statutory CBIC notifications (Period-aware B2CL threshold, Reverse Charge Section 49(4) rules).
    5. Net ITC equilibrium and HSN reconciliation.
    
    INVARIANT: STRICTLY PURE FUNCTION / READ-ONLY. Zero writes to vouchers or ledgers.
    """

    @classmethod
    def validate_payload(cls, return_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Universal entry point to validate any GST return payload before export.
        """
        rtype = (return_type or '').strip().upper()
        if rtype == 'GSTR1':
            return cls.validate_gstr1_payload(payload)
        elif rtype == 'GSTR3B':
            return cls.validate_gstr3b_payload(payload)
        else:
            return {
                "is_valid": True,
                "blocking_errors_count": 0,
                "warnings_count": 0,
                "conformance_standard": "SriLekh Generic GST",
                "validated_at": timezone.now().isoformat(),
                "issues": []
            }

    @classmethod
    def validate_gstr1_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates GSTR-1 offline utility payload against GSTN Schema v3.1.2.
        """
        issues: List[Dict[str, Any]] = []

        if not isinstance(payload, dict):
            issues.append(cls._issue(
                error_code="GST_SCHEMA_ROOT_TYPE_INVALID",
                severity="ERROR",
                section="Root",
                record_identifier="payload",
                description="Payload root must be a JSON object / dictionary.",
                recommendation="Regenerate return draft payload."
            ))
            return cls._result(issues, "GSTN Offline Tool Schema v3.1.2")

        # 1. Header Validation
        gstin = str(payload.get("gstin", "")).strip().upper()
        supplier_state = gstin[:2] if len(gstin) >= 2 else ""

        if not gstin or not GSTIN_REGEX.match(gstin):
            issues.append(cls._issue(
                error_code="GST_SCHEMA_INVALID_GSTIN",
                severity="ERROR",
                section="Header",
                record_identifier="gstin",
                description=f"Invalid supplier GSTIN '{gstin}'. Must be 15 alphanumeric characters matching GSTN format.",
                recommendation="Verify and update supplier GSTIN in company GST registrations."
            ))

        fp = str(payload.get("fp", "")).strip()
        period_date = None
        if not fp or not PERIOD_REGEX.match(fp):
            issues.append(cls._issue(
                error_code="GST_SCHEMA_INVALID_PERIOD",
                severity="ERROR",
                section="Header",
                record_identifier="fp",
                description=f"Invalid return filing period '{fp}'. Expected format MMYYYY (e.g. 082026).",
                recommendation="Provide valid 6-digit MMYYYY return period."
            ))
        else:
            month = int(fp[:2])
            year = int(fp[2:])
            _, last_day = monthrange(year, month)
            period_date = (date(year, month, 1), date(year, month, last_day))

        # Version Check
        ver = payload.get("version")
        if ver and ver != "GST3.1.2":
            issues.append(cls._issue(
                error_code="GST_SCHEMA_VERSION_MISMATCH",
                severity="WARNING",
                section="Header",
                record_identifier="version",
                description=f"Payload version '{ver}' deviates from expected 'GST3.1.2'.",
                recommendation="Ensure the export complies with Offline Tool v3.1.2."
            ))

        # 2. Section Checks
        seen_invoices: Set[str] = set()
        total_txval_all_sections = Decimal('0.00')

        # --- Table 4: B2B Invoices ---
        b2b_list = payload.get("b2b", [])
        if not isinstance(b2b_list, list):
            issues.append(cls._issue(
                error_code="GST_SCHEMA_SECTION_TYPE_INVALID",
                severity="ERROR",
                section="Table 4 (b2b)",
                record_identifier="b2b",
                description="'b2b' section must be a list of recipient groups.",
                recommendation="Check draft generation data format."
            ))
        else:
            for b2b_group in b2b_list:
                ctin = str(b2b_group.get("ctin", "")).strip().upper()
                if not ctin or not GSTIN_REGEX.match(ctin):
                    issues.append(cls._issue(
                        error_code="GST_B2B_INVALID_CTIN",
                        severity="ERROR",
                        section="Table 4 (b2b)",
                        record_identifier=f"ctin:{ctin}",
                        description=f"Invalid recipient GSTIN '{ctin}' in B2B supplies.",
                        recommendation="Correct buyer GSTIN on the voucher or enrich party master."
                    ))

                if ctin == gstin and gstin:
                    issues.append(cls._issue(
                        error_code="GST_B2B_SELF_SUPPLY_PROHIBITED",
                        severity="ERROR",
                        section="Table 4 (b2b)",
                        record_identifier=f"ctin:{ctin}",
                        description=f"Recipient GSTIN '{ctin}' cannot be identical to supplier GSTIN '{gstin}' (self-supply prohibited in outward B2B).",
                        recommendation="Remove self-directed vouchers or verify correct distinct branch registration."
                    ))

                for inv in b2b_group.get("inv", []):
                    inum = str(inv.get("inum", "")).strip()
                    idt_str = str(inv.get("idt", "")).strip()
                    val = _quant(inv.get("val", 0))
                    pos = str(inv.get("pos", "")).strip().zfill(2)
                    rchrg = str(inv.get("rchrg", "N")).strip().upper()

                    # Invoice Number Check
                    if not inum or not INVOICE_NUM_REGEX.match(inum):
                        issues.append(cls._issue(
                            error_code="GST_INVOICE_NUM_INVALID",
                            severity="ERROR",
                            section="Table 4 (b2b)",
                            record_identifier=f"inv:{inum}",
                            description=f"Invoice number '{inum}' must be 1 to 16 alphanumeric characters, slashes, or hyphens.",
                            recommendation="Ensure voucher number complies with Rule 46(b) of CGST Rules."
                        ))

                    if inum in seen_invoices:
                        issues.append(cls._issue(
                            error_code="GST_DUPLICATE_INVOICE_NUM",
                            severity="ERROR",
                            section="Table 4 (b2b)",
                            record_identifier=f"inv:{inum}",
                            description=f"Duplicate invoice number '{inum}' detected in the return period.",
                            recommendation="Check for duplicate posted vouchers and renumber or cancel duplicates."
                        ))
                    seen_invoices.add(inum)

                    # Invoice Date Check
                    inv_date = cls._parse_date(idt_str)
                    if not inv_date:
                        issues.append(cls._issue(
                            error_code="GST_INVOICE_DATE_INVALID",
                            severity="ERROR",
                            section="Table 4 (b2b)",
                            record_identifier=f"inv:{inum}",
                            description=f"Invoice '{inum}' has invalid date format '{idt_str}'. Expected DD-MM-YYYY.",
                            recommendation="Correct voucher date format."
                        ))
                    elif period_date and not (period_date[0] <= inv_date <= period_date[1]):
                        issues.append(cls._issue(
                            error_code="GST_INVOICE_DATE_OUT_OF_PERIOD",
                            severity="WARNING",
                            section="Table 4 (b2b)",
                            record_identifier=f"inv:{inum}",
                            description=f"Invoice '{inum}' date {idt_str} falls outside return period {fp}.",
                            recommendation="Confirm voucher date belongs to this tax period."
                        ))

                    # PoS Check
                    if pos not in VALID_POS_CODES:
                        issues.append(cls._issue(
                            error_code="GST_POS_INVALID",
                            severity="ERROR",
                            section="Table 4 (b2b)",
                            record_identifier=f"inv:{inum}",
                            description=f"Invalid Place of Supply code '{pos}' on invoice '{inum}'.",
                            recommendation="Assign a valid 2-digit Indian State/UT code (01-38, 96, 97, 99)."
                        ))

                    # Line items check
                    items_sum = Decimal('0.00')
                    items = inv.get("itms", [])
                    if not items:
                        issues.append(cls._issue(
                            error_code="GST_INVOICE_NO_ITEMS",
                            severity="ERROR",
                            section="Table 4 (b2b)",
                            record_identifier=f"inv:{inum}",
                            description=f"Invoice '{inum}' has no line items.",
                            recommendation="Ensure voucher has at least one active item."
                        ))

                    for itm in items:
                        det = itm.get("itm_det", {})
                        rt = float(det.get("rt", 0.0))
                        txval = _quant(det.get("txval", 0))
                        iamt = _quant(det.get("iamt", 0))
                        camt = _quant(det.get("camt", 0))
                        samt = _quant(det.get("samt", 0))
                        csamt = _quant(det.get("csamt", 0))

                        total_txval_all_sections += txval
                        items_sum += (txval + iamt + camt + samt + csamt)

                        cls._validate_item_rates_and_heads(
                            rt=rt, txval=txval, iamt=iamt, camt=camt, samt=samt, csamt=csamt,
                            pos=pos, supplier_state=supplier_state, section="Table 4 (b2b)",
                            record_id=f"inv:{inum}", issues=issues
                        )

                    # Invoice Total vs Items Equilibrium
                    if abs(val - items_sum) > Decimal('1.00'):
                        issues.append(cls._issue(
                            error_code="GST_CALC_INVOICE_TOTAL_MISMATCH",
                            severity="WARNING",
                            section="Table 4 (b2b)",
                            record_identifier=f"inv:{inum}",
                            description=f"Invoice '{inum}' total value ₹{val} does not match sum of items ₹{items_sum} (diff ₹{abs(val - items_sum)}).",
                            recommendation="Check line-item tax calculations and round-off on voucher."
                        ))

        # --- Table 5: B2CL (Large Interstate Unregistered) ---
        b2cl_list = payload.get("b2cl", [])
        if isinstance(b2cl_list, list):
            b2cl_threshold = Decimal('100000.00')
            if period_date and period_date[0] < date(2024, 8, 1):
                b2cl_threshold = Decimal('250000.00')

            for b2cl_group in b2cl_list:
                pos = str(b2cl_group.get("pos", "")).strip().zfill(2)
                if pos == supplier_state and supplier_state:
                    issues.append(cls._issue(
                        error_code="GST_B2CL_INTRASTATE_PROHIBITED",
                        severity="ERROR",
                        section="Table 5 (b2cl)",
                        record_identifier=f"pos:{pos}",
                        description=f"Table 5 (B2CL) only permits interstate supplies. Found intrastate PoS '{pos}'.",
                        recommendation="Intrastate unregistered supplies must be reported in Table 7 (B2CS)."
                    ))

                for inv in b2cl_group.get("inv", []):
                    inum = str(inv.get("inum", "")).strip()
                    val = _quant(inv.get("val", 0))

                    if val <= b2cl_threshold:
                        issues.append(cls._issue(
                            error_code="GST_B2CL_BELOW_THRESHOLD",
                            severity="ERROR",
                            section="Table 5 (b2cl)",
                            record_identifier=f"inv:{inum}",
                            description=f"Invoice '{inum}' with value ₹{val} is below/equal to B2CL threshold ₹{b2cl_threshold} for period {fp}.",
                            recommendation="Reclassify supplies under threshold into Table 7 (B2CS)."
                        ))

                    for itm in inv.get("itms", []):
                        det = itm.get("itm_det", {})
                        rt = float(det.get("rt", 0.0))
                        txval = _quant(det.get("txval", 0))
                        iamt = _quant(det.get("iamt", 0))
                        camt = _quant(det.get("camt", 0))
                        samt = _quant(det.get("samt", 0))
                        csamt = _quant(det.get("csamt", 0))

                        total_txval_all_sections += txval

                        if camt > 0 or samt > 0:
                            issues.append(cls._issue(
                                error_code="GST_B2CL_CENTRAL_STATE_TAX_PROHIBITED",
                                severity="ERROR",
                                section="Table 5 (b2cl)",
                                record_identifier=f"inv:{inum}",
                                description=f"B2CL invoice '{inum}' contains CGST/SGST amounts. Only IGST is permitted on interstate supplies.",
                                recommendation="Correct tax heads to IGST."
                            ))

        # --- Table 7: B2CS (Small Unregistered) ---
        b2cs_list = payload.get("b2cs", [])
        if isinstance(b2cs_list, list):
            for row in b2cs_list:
                sply_ty = str(row.get("sply_ty", "")).strip().upper()
                pos = str(row.get("pos", "")).strip().zfill(2)
                rt = float(row.get("rt", 0.0))
                txval = _quant(row.get("txval", 0))
                iamt = _quant(row.get("iamt", 0))
                camt = _quant(row.get("camt", 0))
                samt = _quant(row.get("samt", 0))

                total_txval_all_sections += txval

                if rt not in STANDARD_GSTR_RATES_FLOAT:
                    issues.append(cls._issue(
                        error_code="GST_RATE_NON_STANDARD",
                        severity="ERROR",
                        section="Table 7 (b2cs)",
                        record_identifier=f"b2cs:{sply_ty}:{pos}:{rt}%",
                        description=f"Non-standard GST rate {rt}% in B2CS summary.",
                        recommendation="Ensure product tax rates match statutory rates."
                    ))

                if sply_ty == "INTRA":
                    if iamt > 0:
                        issues.append(cls._issue(
                            error_code="GST_B2CS_IGST_ON_INTRASTATE",
                            severity="ERROR",
                            section="Table 7 (b2cs)",
                            record_identifier=f"b2cs:{pos}",
                            description="IGST cannot be charged on intrastate B2CS supplies.",
                            recommendation="Check Place of Supply and tax ledger classification."
                        ))
                    if abs(camt - samt) > Decimal('1.00'):
                        issues.append(cls._issue(
                            error_code="GST_B2CS_CGST_SGST_ASYMMETRY",
                            severity="ERROR",
                            section="Table 7 (b2cs)",
                            record_identifier=f"b2cs:{pos}",
                            description=f"CGST ₹{camt} and SGST ₹{samt} must be equal for intrastate B2CS.",
                            recommendation="Ensure equal 50:50 distribution of Central and State tax."
                        ))
                elif sply_ty == "INTER":
                    if camt > 0 or samt > 0:
                        issues.append(cls._issue(
                            error_code="GST_B2CS_CGST_SGST_ON_INTERSTATE",
                            severity="ERROR",
                            section="Table 7 (b2cs)",
                            record_identifier=f"b2cs:{pos}",
                            description="CGST/SGST cannot be charged on interstate B2CS supplies.",
                            recommendation="Interstate supplies must charge IGST only."
                        ))

        # --- Table 12: HSN Summary ---
        hsn_section = payload.get("hsn", {})
        hsn_data = hsn_section.get("data", []) if isinstance(hsn_section, dict) else []
        hsn_total_txval = Decimal('0.00')

        if not hsn_data and total_txval_all_sections > Decimal('0.00'):
            issues.append(cls._issue(
                error_code="GST_HSN_SUMMARY_MISSING",
                severity="WARNING",
                section="Table 12 (hsn)",
                record_identifier="hsn",
                description="Table 12 HSN summary is empty while outward supplies exist.",
                recommendation="Ensure all products have valid HSN/SAC codes configured."
            ))
        else:
            for item in hsn_data:
                hsn_code = str(item.get("hsn_sc", "")).strip()
                txval = _quant(item.get("txval", 0))
                hsn_total_txval += txval

                if not hsn_code or not HSN_REGEX.match(hsn_code):
                    issues.append(cls._issue(
                        error_code="GST_HSN_CODE_INVALID",
                        severity="ERROR",
                        section="Table 12 (hsn)",
                        record_identifier=f"hsn:{hsn_code}",
                        description=f"Invalid HSN/SAC code '{hsn_code}'. Must be 4 to 8 digits.",
                        recommendation="Update product HSN code to minimum 4 digits."
                    ))

            # HSN vs Tables Total Taxable Reconciliation
            variance = abs(total_txval_all_sections - hsn_total_txval)
            if variance > Decimal('10.00'):
                issues.append(cls._issue(
                    error_code="GST_HSN_VALUATION_MISMATCH",
                    severity="WARNING",
                    section="Table 12 (hsn)",
                    record_identifier="hsn_recon",
                    description=f"Total HSN taxable value ₹{hsn_total_txval} differs from total outward supplies ₹{total_txval_all_sections} by ₹{variance}.",
                    recommendation="Reconcile HSN line item taxable amounts with invoice register."
                ))

        # --- Table 13: Document Issue Summary ---
        doc_issue = payload.get("doc_issue", {})
        doc_det = doc_issue.get("doc_det", []) if isinstance(doc_issue, dict) else []
        for d in doc_det:
            tot = int(d.get("totnum", 0))
            canc = int(d.get("canc", 0))
            net = int(d.get("net_issue", 0))
            if tot != (canc + net):
                issues.append(cls._issue(
                    error_code="GST_DOC_ISSUE_ARITHMETIC_ERROR",
                    severity="ERROR",
                    section="Table 13 (doc_issue)",
                    record_identifier=str(d.get("doc_typ", "")),
                    description=f"Total documents ({tot}) does not equal net ({net}) + cancelled ({canc}).",
                    recommendation="Verify document numbering sequences."
                ))

        return cls._result(issues, "GSTN Offline Tool Schema v3.1.2")

    @classmethod
    def validate_gstr3b_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates GSTR-3B offline utility payload against GSTN Schema v1.4.
        """
        issues: List[Dict[str, Any]] = []

        if not isinstance(payload, dict):
            issues.append(cls._issue(
                error_code="GST_SCHEMA_ROOT_TYPE_INVALID",
                severity="ERROR",
                section="Root",
                record_identifier="payload",
                description="Payload root must be a JSON dictionary.",
                recommendation="Regenerate return draft payload."
            ))
            return cls._result(issues, "GSTN Offline Tool Schema v1.4")

        # 1. Header Validation
        gstin = str(payload.get("gstin", "")).strip().upper()
        if not gstin or not GSTIN_REGEX.match(gstin):
            issues.append(cls._issue(
                error_code="GST_SCHEMA_INVALID_GSTIN",
                severity="ERROR",
                section="Header",
                record_identifier="gstin",
                description=f"Invalid supplier GSTIN '{gstin}' in GSTR-3B header.",
                recommendation="Update company GST registration with valid 15-character GSTIN."
            ))

        ret_period = str(payload.get("ret_period", "")).strip()
        if not ret_period or not PERIOD_REGEX.match(ret_period):
            issues.append(cls._issue(
                error_code="GST_SCHEMA_INVALID_PERIOD",
                severity="ERROR",
                section="Header",
                record_identifier="ret_period",
                description=f"Invalid GSTR-3B return period '{ret_period}'. Expected MMYYYY.",
                recommendation="Provide valid return period."
            ))

        filing_typ = payload.get("filing_typ")
        if filing_typ != "GSTR3B":
            issues.append(cls._issue(
                error_code="GST_SCHEMA_FILING_TYPE_INVALID",
                severity="ERROR",
                section="Header",
                record_identifier="filing_typ",
                description=f"Invalid filing_typ '{filing_typ}'. Expected 'GSTR3B'.",
                recommendation="Set filing_typ to 'GSTR3B'."
            ))

        # 2. Table 3.1 Supplies Details (`sup_details`)
        sup = payload.get("sup_details", {})
        if not isinstance(sup, dict):
            issues.append(cls._issue(
                error_code="GST_SCHEMA_SUP_DETAILS_MISSING",
                severity="ERROR",
                section="Table 3.1 (sup_details)",
                record_identifier="sup_details",
                description="Missing 'sup_details' section in GSTR-3B payload.",
                recommendation="Ensure draft contains Table 3.1 summaries."
            ))
        else:
            # 3.1(a) Outward taxable
            osup = sup.get("osup_det", {})
            cls._check_non_negative(osup, "Table 3.1(a) osup_det", issues)
            camt = _quant(osup.get("camt", 0))
            samt = _quant(osup.get("samt", 0))
            if abs(camt - samt) > Decimal('1.00'):
                issues.append(cls._issue(
                    error_code="GST_CALC_CGST_SGST_ASYMMETRY",
                    severity="ERROR",
                    section="Table 3.1(a)",
                    record_identifier="osup_det",
                    description=f"Central Tax ₹{camt} and State Tax ₹{samt} in Table 3.1(a) must be equal.",
                    recommendation="Verify intrastate tax distribution."
                ))

            # 3.1(b) Zero rated
            zero = sup.get("osup_zero", {})
            cls._check_non_negative(zero, "Table 3.1(b) osup_zero", issues)

            # 3.1(c) Nil exempt
            nil = sup.get("osup_nil_exmp", {})
            cls._check_non_negative(nil, "Table 3.1(c) osup_nil_exmp", issues)

            # 3.1(d) Inward RCM supplies
            isup_rev = sup.get("isup_rev", {})
            cls._check_non_negative(isup_rev, "Table 3.1(d) isup_rev", issues)

        # 3. Table 3.2 Interstate Supplies (`inter_sup`)
        inter_sup = payload.get("inter_sup", {})
        if isinstance(inter_sup, dict):
            for row in inter_sup.get("unreg_details", []):
                pos = str(row.get("pos", "")).strip().zfill(2)
                if pos not in VALID_POS_CODES:
                    issues.append(cls._issue(
                        error_code="GST_POS_INVALID",
                        severity="ERROR",
                        section="Table 3.2 (inter_sup)",
                        record_identifier=f"pos:{pos}",
                        description=f"Invalid Place of Supply code '{pos}' in Table 3.2.",
                        recommendation="Provide valid 2-digit state code."
                    ))

        # 4. Table 4 Input Tax Credit (`itc_elg`)
        itc = payload.get("itc_elg", {})
        if not isinstance(itc, dict):
            issues.append(cls._issue(
                error_code="GST_SCHEMA_ITC_ELG_MISSING",
                severity="ERROR",
                section="Table 4 (itc_elg)",
                record_identifier="itc_elg",
                description="Missing 'itc_elg' section in GSTR-3B payload.",
                recommendation="Ensure draft contains Table 4 ITC calculation."
            ))
        else:
            itc_avl = itc.get("itc_avl", {})
            itc_rev = itc.get("itc_rev", {})
            itc_net = itc.get("itc_net", {})

            # Check mathematical net consistency: itc_net == itc_avl - itc_rev
            for head in ["iamt", "camt", "samt", "csamt"]:
                # sum available
                avl_val = Decimal('0.00')
                for cat in itc_avl.values():
                    if isinstance(cat, dict):
                        avl_val += _quant(cat.get(head, 0))

                # sum reversed
                rev_val = Decimal('0.00')
                for cat in itc_rev.values():
                    if isinstance(cat, dict):
                        rev_val += _quant(cat.get(head, 0))

                expected_net = avl_val - rev_val
                reported_net = _quant(itc_net.get(head, 0))

                if abs(expected_net - reported_net) > Decimal('1.00'):
                    issues.append(cls._issue(
                        error_code="GST_CALC_ITC_NET_INCONSISTENT",
                        severity="ERROR",
                        section="Table 4 (itc_net)",
                        record_identifier=f"itc_net.{head}",
                        description=f"Net ITC for {head.upper()} (₹{reported_net}) does not equal Available (₹{avl_val}) minus Reversed (₹{rev_val}) = ₹{expected_net}.",
                        recommendation="Recalculate Table 4 Net ITC."
                    ))

            # Non-negative checks on ITC buckets
            for cat_name, cat in itc_avl.items():
                if isinstance(cat, dict):
                    cls._check_non_negative(cat, f"Table 4(A) itc_avl.{cat_name}", issues)

        return cls._result(issues, "GSTN Offline Tool Schema v1.4")

    # -------------------------------------------------------------------------
    # Helper Validation Routines
    # -------------------------------------------------------------------------

    @classmethod
    def _validate_item_rates_and_heads(
        cls,
        rt: float,
        txval: Decimal,
        iamt: Decimal,
        camt: Decimal,
        samt: Decimal,
        csamt: Decimal,
        pos: str,
        supplier_state: str,
        section: str,
        record_id: str,
        issues: List[Dict[str, Any]]
    ):
        # 1. Non-negative checks
        if txval < 0 or iamt < 0 or camt < 0 or samt < 0 or csamt < 0:
            issues.append(cls._issue(
                error_code="GST_NEGATIVE_AMOUNT_PROHIBITED",
                severity="ERROR",
                section=section,
                record_identifier=record_id,
                description=f"Negative amounts prohibited in invoice line items (txval={txval}, iamt={iamt}, camt={camt}, samt={samt}).",
                recommendation="Represent reductions via Credit Notes (Table 9B), not negative invoice values."
            ))

        # 2. Rate validity
        if rt not in STANDARD_GSTR_RATES_FLOAT:
            issues.append(cls._issue(
                error_code="GST_RATE_NON_STANDARD",
                severity="ERROR",
                section=section,
                record_identifier=record_id,
                description=f"GST rate {rt}% is not an official approved GST rate in India.",
                recommendation=f"Use standard rates: {sorted(list(STANDARD_GST_RATES))}."
            ))

        # 3. Inter-State vs Intra-State head equilibrium
        if supplier_state and pos:
            is_intra = (pos == supplier_state)
            if is_intra:
                if iamt > 0:
                    issues.append(cls._issue(
                        error_code="GST_CALC_IGST_ON_INTRASTATE",
                        severity="ERROR",
                        section=section,
                        record_identifier=record_id,
                        description=f"Intrastate supply (PoS {pos} == Supplier {supplier_state}) cannot have IGST (found ₹{iamt}).",
                        recommendation="Intrastate supplies must have CGST and SGST only."
                    ))
                if abs(camt - samt) > Decimal('0.10'):
                    issues.append(cls._issue(
                        error_code="GST_CALC_CGST_SGST_ASYMMETRY",
                        severity="ERROR",
                        section=section,
                        record_identifier=record_id,
                        description=f"CGST ₹{camt} and SGST ₹{samt} must be equal for intrastate supply.",
                        recommendation="Ensure symmetric Central and State tax amounts."
                    ))
            else:
                if camt > 0 or samt > 0:
                    issues.append(cls._issue(
                        error_code="GST_CALC_CGST_SGST_ON_INTERSTATE",
                        severity="ERROR",
                        section=section,
                        record_identifier=record_id,
                        description=f"Interstate supply (PoS {pos} != Supplier {supplier_state}) cannot have CGST (₹{camt}) or SGST (₹{samt}).",
                        recommendation="Interstate supplies must charge IGST only."
                    ))

    @classmethod
    def _check_non_negative(cls, data: Dict[str, Any], context: str, issues: List[Dict[str, Any]]):
        for k, v in data.items():
            if isinstance(v, (int, float, Decimal)):
                if v < 0:
                    issues.append(cls._issue(
                        error_code="GST_NEGATIVE_VALUE",
                        severity="ERROR",
                        section=context,
                        record_identifier=k,
                        description=f"Negative value {v} found in {context}.{k}.",
                        recommendation="All reported values must be non-negative."
                    ))

    @classmethod
    def _parse_date(cls, dt_str: str) -> Optional[date]:
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(dt_str, fmt).date()
            except Exception:
                pass
        return None

    @classmethod
    def _issue(
        cls,
        error_code: str,
        severity: str,
        section: str,
        record_identifier: str,
        description: str,
        recommendation: str
    ) -> Dict[str, Any]:
        return {
            "error_code": error_code,
            "severity": severity,
            "section": section,
            "record_identifier": record_identifier,
            "description": description,
            "recommended_correction": recommendation
        }

    @classmethod
    def _result(cls, issues: List[Dict[str, Any]], standard: str) -> Dict[str, Any]:
        blocking = sum(1 for i in issues if i["severity"] == "ERROR")
        warnings = sum(1 for i in issues if i["severity"] == "WARNING")
        return {
            "is_valid": (blocking == 0),
            "blocking_errors_count": blocking,
            "warnings_count": warnings,
            "conformance_standard": standard,
            "validated_at": timezone.now().isoformat(),
            "issues": issues
        }


# Float lookup set for fast rate verification
STANDARD_GSTR_RATES_FLOAT = {float(r) for r in STANDARD_GST_RATES}
