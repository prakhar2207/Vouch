import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import Voucher, LedgerEntry, FinancialYear

TALLY_GROUP_MAPPINGS = {
    # Tally Group -> (Vouch Nature, Vouch Default Group Name, Ledger Type)
    "sundry debtors": ("ASSET", "Sundry Debtors", "CUSTOMER"),
    "sundry creditors": ("LIABILITY", "Sundry Creditors", "SUPPLIER"),
    "bank accounts": ("ASSET", "Bank Accounts", "BANK"),
    "bank od a/c": ("LIABILITY", "Bank OD Accounts", "BANK"),
    "bank occ a/c": ("LIABILITY", "Bank OD Accounts", "BANK"),
    "cash-in-hand": ("ASSET", "Cash-in-Hand", "CASH"),
    "sales accounts": ("INCOME", "Sales Accounts", "SALES"),
    "purchase accounts": ("EXPENSE", "Purchase Accounts", "PURCHASE"),
    "duties & taxes": ("LIABILITY", "Duties & Taxes", "TAX"),
    "direct expenses": ("EXPENSE", "Direct Expenses", "EXPENSE"),
    "indirect expenses": ("EXPENSE", "Indirect Expenses", "EXPENSE"),
    "direct incomes": ("INCOME", "Direct Incomes", "INCOME"),
    "indirect incomes": ("INCOME", "Indirect Incomes", "INCOME"),
    "capital account": ("EQUITY", "Capital Account", "EQUITY"),
    "current assets": ("ASSET", "Current Assets", "ASSET"),
    "current liabilities": ("LIABILITY", "Current Liabilities", "LIABILITY"),
    "fixed assets": ("ASSET", "Fixed Assets", "ASSET"),
    "investments": ("ASSET", "Investments", "ASSET"),
    "loans (liability)": ("LIABILITY", "Loans (Liability)", "LIABILITY"),
    "secured loans": ("LIABILITY", "Secured Loans", "LIABILITY"),
    "unsecured loans": ("LIABILITY", "Unsecured Loans", "LIABILITY"),
    "stock-in-hand": ("ASSET", "Stock-in-Hand", "ASSET"),
}

TALLY_VOUCHER_TYPE_MAP = {
    "sales": "SALES",
    "purchase": "PURCHASE",
    "receipt": "RECEIPT",
    "payment": "PAYMENT",
    "contra": "CONTRA",
    "journal": "JOURNAL",
    "credit note": "CREDIT_NOTE",
    "debit note": "DEBIT_NOTE",
}

class TallyMigrationService:
    """
    Enterprise TallyPrime / Tally.ERP 9 Migration Pipeline.
    Supports:
    1. XML Export parsing (Masters, Stock Items, Opening Balances, Vouchers).
    2. Intelligent Group & Nature mapping.
    3. Mathematical equilibrium check (Opening Debits == Opening Credits).
    4. Validation & Migration Preview.
    5. Atomic Execution & Migration Audit Report generation.
    """

    @classmethod
    def parse_tally_xml(cls, xml_content: str | bytes) -> Dict[str, Any]:
        """Parses Tally XML envelope into normalized Python dictionaries."""
        if isinstance(xml_content, bytes):
            xml_content = xml_content.decode('utf-8', errors='replace')

        root = ET.fromstring(xml_content)
        
        groups = []
        ledgers = []
        stock_items = []
        vouchers = []

        # Find all TALLYMESSAGE elements
        for msg in root.findall(".//TALLYMESSAGE"):
            # 1. Groups
            group_el = msg.find("GROUP")
            if group_el is not None:
                name = group_el.get("NAME") or (group_el.findtext("NAME") or "").strip()
                parent = (group_el.findtext("PARENT") or "").strip()
                if name:
                    groups.append({"name": name, "parent": parent})

            # 2. Ledgers
            ledger_el = msg.find("LEDGER")
            if ledger_el is not None:
                name = ledger_el.get("NAME") or (ledger_el.findtext("NAME") or "").strip()
                parent = (ledger_el.findtext("PARENT") or "").strip()
                op_bal_raw = (ledger_el.findtext("OPENINGBALANCE") or "0").strip()
                is_deemed_pos = (ledger_el.findtext("ISDEEMEDPOSITIVE") or "").strip().lower() == "yes"
                gstin = (ledger_el.findtext("PARTYGSTIN") or "").strip()
                pan = (ledger_el.findtext("INCOMETAXNUMBER") or "").strip()
                phone = (ledger_el.findtext("LEDGERPHONE") or "").strip()
                email = (ledger_el.findtext("EMAIL") or "").strip()
                address = (ledger_el.findtext("ADDRESS") or "").strip()

                # Parse Tally opening balance (negative is DR, positive is CR in Tally convention, or ISDEEMEDPOSITIVE)
                try:
                    op_val = Decimal(op_bal_raw)
                    if op_val < 0:
                        op_balance = abs(op_val)
                        balance_type = "DEBIT"
                    elif op_val > 0:
                        op_balance = op_val
                        balance_type = "DEBIT" if is_deemed_pos else "CREDIT"
                    else:
                        op_balance = Decimal('0.00')
                        balance_type = "DEBIT"
                except InvalidOperation:
                    op_balance = Decimal('0.00')
                    balance_type = "DEBIT"

                if name:
                    ledgers.append({
                        "name": name,
                        "parent_group": parent,
                        "opening_balance": op_balance,
                        "balance_type": balance_type,
                        "gstin": gstin,
                        "pan": pan,
                        "phone": phone,
                        "email": email,
                        "address": address
                    })

            # 3. Stock Items
            stock_el = msg.find("STOCKITEM")
            if stock_el is not None:
                s_name = stock_el.get("NAME") or (stock_el.findtext("NAME") or "").strip()
                s_unit = (stock_el.findtext("BASEUNITS") or "PCS").strip()
                s_op_qty = Decimal(stock_el.findtext("OPENINGBALANCE") or "0")
                s_op_val = Decimal(stock_el.findtext("OPENINGVALUE") or "0")
                s_rate = (s_op_val / s_op_qty) if s_op_qty > 0 else Decimal('0.00')
                if s_name:
                    stock_items.append({
                        "name": s_name,
                        "unit": s_unit,
                        "opening_quantity": abs(s_op_qty),
                        "opening_value": abs(s_op_val),
                        "rate": abs(s_rate)
                    })

            # 4. Vouchers
            vch_el = msg.find("VOUCHER")
            if vch_el is not None:
                v_type_raw = vch_el.get("VCHTYPE") or (vch_el.findtext("VOUCHERTYPENAME") or "").strip()
                v_type = TALLY_VOUCHER_TYPE_MAP.get(v_type_raw.lower(), "JOURNAL")
                v_num = (vch_el.findtext("VOUCHERNUMBER") or "").strip()
                v_date_str = (vch_el.findtext("DATE") or "").strip()
                party_name = (vch_el.findtext("PARTYLEDGERNAME") or "").strip()

                # Parse date (format YYYYMMDD or YYYY-MM-DD)
                v_date = None
                if v_date_str:
                    try:
                        if len(v_date_str) == 8 and v_date_str.isdigit():
                            v_date = datetime.strptime(v_date_str, "%Y%m%d").date()
                        else:
                            v_date = datetime.strptime(v_date_str[:10], "%Y-%m-%d").date()
                    except ValueError:
                        v_date = datetime.now().date()
                else:
                    v_date = datetime.now().date()

                entries = []
                for entry_el in vch_el.findall(".//ALLLEDGERENTRIES.LIST") + vch_el.findall(".//LEDGERENTRIES.LIST"):
                    ldr_name = (entry_el.findtext("LEDGERNAME") or "").strip()
                    amt_raw = (entry_el.findtext("AMOUNT") or "0").strip()
                    is_pos = (entry_el.findtext("ISDEEMEDPOSITIVE") or "").strip().lower() == "yes"
                    try:
                        amt_dec = Decimal(amt_raw)
                        # Negative is Debit in Tally, Positive is Credit
                        if amt_dec < 0 or is_pos:
                            dr = abs(amt_dec)
                            cr = Decimal('0.00')
                        else:
                            dr = Decimal('0.00')
                            cr = abs(amt_dec)
                    except InvalidOperation:
                        dr = Decimal('0.00')
                        cr = Decimal('0.00')

                    if ldr_name and (dr > 0 or cr > 0):
                        entries.append({"ledger_name": ldr_name, "debit": dr, "credit": cr})

                if v_num and entries:
                    vouchers.append({
                        "voucher_type": v_type,
                        "voucher_number": v_num,
                        "voucher_date": v_date,
                        "party_name": party_name,
                        "entries": entries
                    })

        return {
            "groups": groups,
            "ledgers": ledgers,
            "stock_items": stock_items,
            "vouchers": vouchers
        }

    @classmethod
    def validate_and_preview(cls, parsed_data: Dict[str, Any], company: Company) -> Dict[str, Any]:
        """
        Validates parsed data and generates a migration preview and equilibrium audit.
        """
        ledgers = parsed_data.get("ledgers", [])
        stock_items = parsed_data.get("stock_items", [])
        vouchers = parsed_data.get("vouchers", [])

        # 1. Opening Balance Equilibrium Audit
        total_op_dr = Decimal('0.00')
        total_op_cr = Decimal('0.00')
        for l in ledgers:
            if l["balance_type"] == "DEBIT":
                total_op_dr += l["opening_balance"]
            else:
                total_op_cr += l["opening_balance"]

        op_diff = total_op_dr - total_op_cr
        op_balanced = (op_diff == Decimal('0.00'))

        # 2. Vouchers Double-Entry Equilibrium Audit
        valid_vouchers = 0
        imbalanced_vouchers = []
        for v in vouchers:
            v_dr = sum((e["debit"] for e in v["entries"]), Decimal('0.00'))
            v_cr = sum((e["credit"] for e in v["entries"]), Decimal('0.00'))
            if v_dr == v_cr and v_dr > Decimal('0.00'):
                valid_vouchers += 1
            else:
                imbalanced_vouchers.append({
                    "voucher_number": v["voucher_number"],
                    "type": v["voucher_type"],
                    "dr": float(v_dr),
                    "cr": float(v_cr),
                    "diff": float(v_dr - v_cr)
                })

        # 3. Party GSTIN Check
        invalid_gstins = []
        for l in ledgers:
            g = l.get("gstin")
            if g and (len(g) != 15 or not g[:2].isdigit()):
                invalid_gstins.append({"ledger": l["name"], "gstin": g})

        return {
            "summary": {
                "total_ledgers": len(ledgers),
                "total_stock_items": len(stock_items),
                "total_vouchers": len(vouchers),
                "valid_vouchers": valid_vouchers,
                "imbalanced_vouchers_count": len(imbalanced_vouchers),
            },
            "opening_balances": {
                "total_debits": float(total_op_dr),
                "total_credits": float(total_op_cr),
                "imbalance": float(op_diff),
                "is_balanced": op_balanced
            },
            "validation_issues": {
                "opening_balance_imbalance": float(op_diff) if not op_balanced else 0.0,
                "imbalanced_vouchers": imbalanced_vouchers[:10],
                "invalid_gstins": invalid_gstins[:10]
            },
            "status": "READY" if op_balanced and len(imbalanced_vouchers) == 0 else "WARNINGS_DETECTED"
        }

    @classmethod
    @transaction.atomic
    def execute_migration(
        cls,
        parsed_data: Dict[str, Any],
        company: Company,
        user: User,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Executes atomic migration of all Tally masters, inventory, and vouchers.
        Generates an immutable Migration Audit Report.
        """
        preview = cls.validate_and_preview(parsed_data, company)
        if dry_run:
            return {"success": True, "dry_run": True, "preview": preview}

        created_groups = 0
        created_ledgers = 0
        created_products = 0
        created_vouchers = 0
        created_entries = 0

        # Cache existing groups
        group_cache: Dict[str, LedgerGroup] = {
            g.name.lower(): g for g in LedgerGroup.objects.filter(company=company)
        }

        def get_or_create_group(name: str, fallback_nature="ASSET") -> LedgerGroup:
            nonlocal created_groups
            norm_name = name.strip()
            lookup_key = norm_name.lower()
            if lookup_key in group_cache:
                return group_cache[lookup_key]

            mapping = TALLY_GROUP_MAPPINGS.get(lookup_key)
            nature = mapping[0] if mapping else fallback_nature
            grp = LedgerGroup.objects.create(company=company, name=norm_name, nature=nature)
            group_cache[lookup_key] = grp
            created_groups += 1
            return grp

        # 1. Migrate Ledgers
        ledger_cache: Dict[str, Ledger] = {}
        for l_data in parsed_data.get("ledgers", []):
            parent_name = l_data.get("parent_group") or "Current Assets"
            mapping = TALLY_GROUP_MAPPINGS.get(parent_name.lower())
            nature = mapping[0] if mapping else "ASSET"
            l_type = mapping[2] if mapping else "GENERAL"

            group = get_or_create_group(parent_name, fallback_nature=nature)
            
            ldr, created = Ledger.objects.get_or_create(
                company=company,
                name=l_data["name"],
                defaults={
                    "group": group,
                    "ledger_type": l_type,
                    "opening_balance": l_data["opening_balance"],
                    "opening_balance_type": l_data["balance_type"],
                    "current_balance": l_data["opening_balance"],
                    "gstin": l_data.get("gstin") or None,
                    "email": l_data.get("email") or None,
                    "phone": l_data.get("phone") or None,
                    "address": l_data.get("address") or None
                }
            )
            ledger_cache[ldr.name.lower()] = ldr
            if created:
                created_ledgers += 1

        # 2. Migrate Stock Items
        cat, _ = ProductCategory.objects.get_or_create(company=company, name="General Imported Inventory")
        for s_data in parsed_data.get("stock_items", []):
            prod, created = Product.objects.get_or_create(
                company=company,
                sku=f"SKU-{s_data['name'][:30].upper().replace(' ', '-')}",
                defaults={
                    "name": s_data["name"],
                    "category": cat,
                    "unit": s_data.get("unit", "PCS"),
                    "stock_quantity": s_data["opening_quantity"],
                    "purchase_price": s_data["rate"],
                    "selling_price": s_data["rate"] * Decimal('1.25')
                }
            )
            if created:
                created_products += 1

        # 3. Migrate Vouchers
        for v_data in parsed_data.get("vouchers", []):
            v_dr = sum((e["debit"] for e in v_data["entries"]), Decimal('0.00'))
            v_cr = sum((e["credit"] for e in v_data["entries"]), Decimal('0.00'))
            if v_dr != v_cr or v_dr == Decimal('0.00'):
                continue  # Skip imbalanced vouchers

            party_ldr = ledger_cache.get(v_data.get("party_name", "").lower())
            
            vch = Voucher.objects.create(
                company=company,
                voucher_type=v_data["voucher_type"],
                voucher_number=v_data["voucher_number"],
                voucher_date=v_data["voucher_date"],
                party_ledger=party_ldr,
                created_by=user,
                total_amount=v_dr,
                status='POSTED'
            )
            created_vouchers += 1

            for e_data in v_data["entries"]:
                ldr = ledger_cache.get(e_data["ledger_name"].lower())
                if not ldr:
                    # Dynamically create missing ledger under General
                    grp = get_or_create_group("Suspense / General", fallback_nature="ASSET")
                    ldr = Ledger.objects.create(company=company, group=grp, name=e_data["ledger_name"], ledger_type="GENERAL")
                    ledger_cache[ldr.name.lower()] = ldr
                    created_ledgers += 1

                LedgerEntry.objects.create(
                    company=company,
                    voucher=vch,
                    ledger=ldr,
                    debit_amount=e_data["debit"],
                    credit_amount=e_data["credit"]
                )
                created_entries += 1

        # 4. Generate Migration Audit Report
        audit_report = {
            "company_name": company.name,
            "migrated_by": user.email,
            "timestamp": datetime.now().isoformat(),
            "records_created": {
                "groups": created_groups,
                "ledgers": created_ledgers,
                "products": created_products,
                "vouchers": created_vouchers,
                "ledger_entries": created_entries
            },
            "opening_balance_equilibrium": preview["opening_balances"],
            "reconciliation_status": "VERIFIED_EQUILIBRIUM" if preview["opening_balances"]["is_balanced"] else "UNBALANCED_OPENING"
        }

        return {
            "success": True,
            "report": audit_report
        }
