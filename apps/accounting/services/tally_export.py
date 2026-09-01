import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from typing import Optional, List
from django.db.models import Q
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.inventory.models import Product
from apps.accounting.models import Voucher


class TallyXMLExporter:
    """
    Serializes Company Masters (Ledgers, Stock Items) and Accounting Vouchers
    into standard TallyPrime / Tally.ERP 9 compatible XML format.
    """

    @classmethod
    def generate_xml(
        cls,
        company: Company,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        export_type: str = "all",  # 'all', 'masters', 'vouchers'
        voucher_types: Optional[List[str]] = None,
    ) -> str:
        # 1. Root ENVELOPE
        envelope = ET.Element("ENVELOPE")

        # 2. HEADER
        header = ET.SubElement(envelope, "HEADER")
        tally_request = ET.SubElement(header, "TALLYREQUEST")
        tally_request.text = "Import Data"
        req_type = ET.SubElement(header, "TYPE")
        req_type.text = "Data"
        req_id = ET.SubElement(header, "ID")
        req_id.text = "All Masters and Vouchers"

        # 3. BODY
        body = ET.SubElement(envelope, "BODY")
        import_data = ET.SubElement(body, "IMPORTDATA")

        # Request Desc
        req_desc = ET.SubElement(import_data, "REQUESTDESC")
        report_name = ET.SubElement(req_desc, "REPORTNAME")
        report_name.text = "All Masters"

        static_vars = ET.SubElement(req_desc, "STATICVARIABLES")
        sv_company = ET.SubElement(static_vars, "SVCURRENTCOMPANY")
        sv_company.text = company.name
        sv_format = ET.SubElement(static_vars, "SVEXPORTFORMAT")
        sv_format.text = "$$SysName:XML"

        # Request Data Container
        request_data = ET.SubElement(import_data, "REQUESTDATA")

        # Include Masters if requested
        if export_type in ["all", "masters"]:
            cls._append_ledgers(request_data, company)
            cls._append_stock_items(request_data, company)

        # Include Vouchers if requested
        if export_type in ["all", "vouchers"]:
            cls._append_vouchers(request_data, company, from_date, to_date, voucher_types)

        # Pretty print XML string
        raw_xml = ET.tostring(envelope, encoding="utf-8")
        parsed = minidom.parseString(raw_xml)
        return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")

    @classmethod
    def _append_ledgers(cls, root: ET.Element, company: Company):
        ledgers = Ledger.objects.filter(company=company, is_active=True).select_related("group")
        for ldr in ledgers:
            msg = ET.SubElement(root, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
            ledger_el = ET.SubElement(msg, "LEDGER", {"NAME": ldr.name, "ACTION": "Create"})

            # Name
            name_list = ET.SubElement(ledger_el, "NAME.LIST")
            name_node = ET.SubElement(name_list, "NAME")
            name_node.text = ldr.name

            # Parent Group mapping
            parent_node = ET.SubElement(ledger_el, "PARENT")
            parent_node.text = cls._map_tally_group(ldr)

            # Opening Balance
            if ldr.opening_balance > 0:
                op_bal = ET.SubElement(ledger_el, "OPENINGBALANCE")
                # Tally convention: Debit balances are negative, Credit positive
                is_dr = ldr.opening_balance_type == "DEBIT"
                op_bal.text = f"-{ldr.opening_balance}" if is_dr else str(ldr.opening_balance)

                deemed_pos = ET.SubElement(ledger_el, "ISDEEMEDPOSITIVE")
                deemed_pos.text = "Yes" if is_dr else "No"

            # GSTIN & State
            if ldr.gstin:
                gstin_node = ET.SubElement(ledger_el, "PARTYGSTIN")
                gstin_node.text = ldr.gstin

            if ldr.state_code:
                state_node = ET.SubElement(ledger_el, "LEDSTATENAME")
                state_node.text = ldr.state_code

            # Mailing details
            if ldr.address:
                addr_list = ET.SubElement(ledger_el, "ADDRESS.LIST")
                addr_line = ET.SubElement(addr_list, "ADDRESS")
                addr_line.text = ldr.address

            if ldr.email:
                email_node = ET.SubElement(ledger_el, "EMAIL")
                email_node.text = ldr.email

            if ldr.phone:
                phone_node = ET.SubElement(ledger_el, "LEDGERPHONE")
                phone_node.text = ldr.phone

    @classmethod
    def _append_stock_items(cls, root: ET.Element, company: Company):
        products = Product.objects.filter(company=company, is_active=True)
        for prod in products:
            msg = ET.SubElement(root, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
            item_el = ET.SubElement(msg, "STOCKITEM", {"NAME": prod.name, "ACTION": "Create"})

            name_list = ET.SubElement(item_el, "NAME.LIST")
            name_node = ET.SubElement(name_list, "NAME")
            name_node.text = prod.name

            unit_node = ET.SubElement(item_el, "BASEUNITS")
            unit_node.text = prod.unit or "PCS"

            if prod.hsn_code:
                hsn_node = ET.SubElement(item_el, "HSNCODE")
                hsn_node.text = prod.hsn_code

            if prod.gst_rate > 0:
                gst_list = ET.SubElement(item_el, "GSTRATEDETAILS.LIST")
                rate_node = ET.SubElement(gst_list, "GSTRATE")
                rate_node.text = str(prod.gst_rate)

            if prod.selling_price > 0:
                rate_node = ET.SubElement(item_el, "STANDARDSELLINGPRICE")
                rate_node.text = str(prod.selling_price)

            if prod.purchase_price > 0:
                rate_node = ET.SubElement(item_el, "STANDARDCOST")
                rate_node.text = str(prod.purchase_price)

    @classmethod
    def _append_vouchers(
        cls,
        root: ET.Element,
        company: Company,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        voucher_types: Optional[List[str]] = None,
    ):
        vouchers = Voucher.objects.filter(company=company).select_related("party_ledger")

        if from_date:
            vouchers = vouchers.filter(voucher_date__gte=from_date)
        if to_date:
            vouchers = vouchers.filter(voucher_date__lte=to_date)
        if voucher_types:
            vouchers = vouchers.filter(voucher_type__in=voucher_types)

        for vch in vouchers.prefetch_related("ledger_entries__ledger", "items__product"):
            msg = ET.SubElement(root, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
            tally_vch_type = cls._map_voucher_type(vch.voucher_type)
            vch_el = ET.SubElement(msg, "VOUCHER", {"VCHTYPE": tally_vch_type, "ACTION": "Create"})

            # Basic Header
            date_str = vch.voucher_date.strftime("%Y%m%d")
            d_node = ET.SubElement(vch_el, "DATE")
            d_node.text = date_str

            eff_date = ET.SubElement(vch_el, "EFFECTIVEDATE")
            eff_date.text = date_str

            type_node = ET.SubElement(vch_el, "VOUCHERTYPENAME")
            type_node.text = tally_vch_type

            num_node = ET.SubElement(vch_el, "VOUCHERNUMBER")
            num_node.text = vch.voucher_number

            if vch.reference_number:
                ref_node = ET.SubElement(vch_el, "REFERENCE")
                ref_node.text = vch.reference_number

            if vch.party_ledger:
                party_node = ET.SubElement(vch_el, "PARTYLEDGERNAME")
                party_node.text = vch.party_ledger.name

            if vch.narration:
                nar_node = ET.SubElement(vch_el, "NARRATION")
                nar_node.text = vch.narration

            # Ledger Entries (Accounting)
            for entry in vch.ledger_entries.all():
                entry_el = ET.SubElement(vch_el, "ALLLEDGERENTRIES.LIST")
                l_name = ET.SubElement(entry_el, "LEDGERNAME")
                l_name.text = entry.ledger.name

                is_debit = entry.debit_amount > 0
                deemed_pos = ET.SubElement(entry_el, "ISDEEMEDPOSITIVE")
                deemed_pos.text = "Yes" if is_debit else "No"

                amt_node = ET.SubElement(entry_el, "AMOUNT")
                # In Tally XML, Debits are represented with negative sign, Credits with positive sign
                amt = -entry.debit_amount if is_debit else entry.credit_amount
                amt_node.text = f"{amt:.2f}"

            # Inventory Line Item Entries
            for item in vch.items.all():
                inv_el = ET.SubElement(vch_el, "ALLINVENTORYENTRIES.LIST")
                prod_node = ET.SubElement(inv_el, "STOCKITEMNAME")
                prod_node.text = item.product.name

                is_inward = vch.voucher_type == "PURCHASE"
                inv_deemed = ET.SubElement(inv_el, "ISDEEMEDPOSITIVE")
                inv_deemed.text = "Yes" if is_inward else "No"

                rate_node = ET.SubElement(inv_el, "RATE")
                rate_node.text = f"{item.rate:.2f}/{item.product.unit or 'PCS'}"

                qty_str = f"{item.quantity} {item.product.unit or 'PCS'}"
                act_qty = ET.SubElement(inv_el, "ACTUALQTY")
                act_qty.text = qty_str
                bill_qty = ET.SubElement(inv_el, "BILLEDQTY")
                bill_qty.text = qty_str

                amt_node = ET.SubElement(inv_el, "AMOUNT")
                item_amt = -item.taxable_amount if is_inward else item.taxable_amount
                amt_node.text = f"{item_amt:.2f}"

    @staticmethod
    def _map_tally_group(ledger: Ledger) -> str:
        l_type = (ledger.ledger_type or "").upper()
        g_name = (ledger.group.name or "").lower() if ledger.group else ""

        if "customer" in l_type or "debtor" in g_name:
            return "Sundry Debtors"
        elif "supplier" in l_type or "creditor" in g_name:
            return "Sundry Creditors"
        elif "bank" in l_type or "bank" in g_name:
            return "Bank Accounts"
        elif "cash" in l_type or "cash" in g_name:
            return "Cash-in-Hand"
        elif "tax" in l_type or "duties" in g_name:
            return "Duties & Taxes"
        elif "purchase" in l_type or "purchase" in g_name:
            return "Purchase Accounts"
        elif "sale" in l_type or "sales" in g_name:
            return "Sales Accounts"
        elif ledger.group:
            if ledger.group.nature == "EXPENSE":
                return "Direct Expenses"
            elif ledger.group.nature == "INCOME":
                return "Direct Incomes"
            elif ledger.group.nature == "ASSET":
                return "Current Assets"
            elif ledger.group.nature == "LIABILITY":
                return "Current Liabilities"

        return "Suspense A/c"

    @staticmethod
    def _map_voucher_type(vch_type: str) -> str:
        mapping = {
            "SALES": "Sales",
            "PURCHASE": "Purchase",
            "PAYMENT": "Payment",
            "RECEIPT": "Receipt",
            "CONTRA": "Contra",
            "JOURNAL": "Journal",
        }
        return mapping.get(vch_type, "Journal")
