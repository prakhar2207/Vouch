import datetime
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Sum

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product, ProductCategory, Warehouse
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry, FinancialYear, VoucherSequence
from .period_service import PeriodBalanceService
from .sequence_service import InvoiceSequenceService

class SplitCompanyService:
    @staticmethod
    def parse_date(date_val):
        if isinstance(date_val, datetime.date):
            return date_val
        return datetime.date.fromisoformat(str(date_val).split('T')[0])

    @staticmethod
    def pre_split_audit(company_id: str, split_date) -> dict:
        """
        Pre-split verification:
        1. All vouchers prior to split_date must be posted (0 unposted drafts).
        2. Double-entry trial balance prior to split_date must be balanced.
        3. Returns audit metrics and proposed target company name.
        """
        company = Company.objects.get(id=company_id)
        d_split = SplitCompanyService.parse_date(split_date)
        d_prior = d_split - datetime.timedelta(days=1)

        unposted_count = Voucher.objects.filter(
            company=company,
            voucher_date__lte=d_prior,
            status__in=['DRAFT', 'VALIDATING']
        ).count()

        prior_agg = LedgerEntry.objects.filter(
            voucher__company=company,
            voucher__voucher_date__lte=d_prior,
            voucher__status='POSTED'
        ).aggregate(
            tot_dr=Sum('debit_amount'),
            tot_cr=Sum('credit_amount')
        )
        tot_dr = prior_agg.get('tot_dr') or Decimal('0.00')
        tot_cr = prior_agg.get('tot_cr') or Decimal('0.00')
        tb_diff = abs(tot_dr - tot_cr)
        is_balanced = tb_diff == Decimal('0.00')

        # Estimated P&L before split
        income_entries = LedgerEntry.objects.filter(
            voucher__company=company,
            voucher__voucher_date__lte=d_prior,
            voucher__status='POSTED',
            ledger__group__nature='INCOME'
        ).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
        tot_income = (income_entries.get('cr') or Decimal('0.00')) - (income_entries.get('dr') or Decimal('0.00'))

        expense_entries = LedgerEntry.objects.filter(
            voucher__company=company,
            voucher__voucher_date__lte=d_prior,
            voucher__status='POSTED',
            ledger__group__nature='EXPENSE'
        ).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
        tot_expense = (expense_entries.get('dr') or Decimal('0.00')) - (expense_entries.get('cr') or Decimal('0.00'))

        net_pl = tot_income - tot_expense

        default_new_name = f"{company.name} (From {d_split.strftime('%d-%b-%Y')})"

        return {
            "source_company_id": str(company.id),
            "source_company_name": company.name,
            "split_date": d_split.strftime('%Y-%m-%d'),
            "closing_date": d_prior.strftime('%Y-%m-%d'),
            "unposted_vouchers_count": unposted_count,
            "is_trial_balance_balanced": is_balanced,
            "trial_balance_difference": str(tb_diff),
            "total_income": str(tot_income),
            "total_expense": str(tot_expense),
            "net_profit_loss": str(net_pl),
            "profit_loss_type": "PROFIT" if net_pl >= 0 else "LOSS",
            "suggested_company_name": default_new_name,
            "can_split": unposted_count == 0 and is_balanced
        }

    @staticmethod
    @transaction.atomic
    def execute_split_company(company_id: str, split_date, new_company_name: str = None, user = None) -> dict:
        """
        Executes Tally-style Company Splitting:
        1. Archives prior financial year in source company.
        2. Spawns standalone company entity for the new period.
        3. Initializes static opening balances for Real/Personal accounts.
        4. Transfers prior P&L into Retained Earnings (Capital).
        5. Sets opening balance for nominal accounts to ₹0.00.
        """
        source_company = Company.objects.select_for_update().get(id=company_id)
        d_split = SplitCompanyService.parse_date(split_date)
        d_prior = d_split - datetime.timedelta(days=1)

        audit = SplitCompanyService.pre_split_audit(company_id, d_split)
        if not audit["can_split"]:
            raise ValidationError(
                f"Cannot split company data: {audit['unposted_vouchers_count']} unposted vouchers exist or trial balance is not balanced."
            )

        target_name = (new_company_name or audit["suggested_company_name"]).strip()

        # 1. Create the new standalone Company entity
        new_company = Company.objects.create(
            name=target_name,
            legal_name=source_company.legal_name or target_name,
            gstin=source_company.gstin,
            pan=source_company.pan,
            state_code=source_company.state_code,
            state_name=source_company.state_name,
            address=source_company.address,
            city=source_company.city,
            pincode=source_company.pincode,
            email=source_company.email,
            phone=source_company.phone,
            financial_year_start=d_split
        )

        from apps.companies.models import CompanySettings
        try:
            old_settings = source_company.settings
            CompanySettings.objects.create(
                company=new_company,
                sales_invoice_prefix=old_settings.sales_invoice_prefix,
                purchase_invoice_prefix=old_settings.purchase_invoice_prefix,
                allow_negative_stock=old_settings.allow_negative_stock,
                complexity_level=old_settings.complexity_level,
                enable_ledger_mapping=old_settings.enable_ledger_mapping,
                enable_manual_invoice_number=old_settings.enable_manual_invoice_number,
                enable_advanced_item_creation=old_settings.enable_advanced_item_creation,
            )
        except Exception:
            CompanySettings.objects.create(company=new_company)

        # 2. Grant admin role to user
        if user:
            UserCompany.objects.get_or_create(user=user, company=new_company, defaults={'role': 'ADMIN'})
        else:
            # Grant all existing users of source company
            for uc in UserCompany.objects.filter(company=source_company):
                UserCompany.objects.get_or_create(user=uc.user, company=new_company, defaults={'role': uc.role})

        # 3. Create default Warehouse
        Warehouse.objects.create(company=new_company, name="Main Godown", is_active=True)

        # 4. Clone Ledger Groups
        group_map = {}
        source_groups = LedgerGroup.objects.filter(company=source_company).order_by('created_at')
        for sg in source_groups:
            ng = LedgerGroup.objects.create(
                company=new_company,
                name=sg.name,
                nature=sg.nature
            )
            group_map[sg.id] = ng

        # Link parent groups
        for sg in source_groups:
            if sg.parent_group and sg.parent_group.id in group_map:
                ng = group_map[sg.id]
                ng.parent_group = group_map[sg.parent_group.id]
                ng.save(update_fields=['parent_group'])

        # 5. Clone Ledgers with Computed Closing Balances
        ledger_map = {}
        source_ledgers = Ledger.objects.filter(company=source_company).select_related('group')
        carried_accounts_count = 0

        for sl in source_ledgers:
            # Dynamically calculate closing balance as of d_prior
            bal_info = PeriodBalanceService.calculate_ledger_period_balance(sl, from_date=None, to_date=d_prior)
            nature = (sl.group.nature or '').upper()

            if nature in ['ASSET', 'LIABILITY', 'EQUITY']:
                op_bal = Decimal(bal_info['closing_balance'])
                op_type = 'DEBIT' if bal_info['closing_type'] == 'DR' else 'CREDIT'
                carried_accounts_count += 1
            else:
                op_bal = Decimal('0.00')
                op_type = 'DEBIT'

            nl = Ledger.objects.create(
                company=new_company,
                group=group_map.get(sl.group.id),
                name=sl.name,
                ledger_type=sl.ledger_type,
                gstin=sl.gstin,
                state_code=sl.state_code,
                opening_balance=op_bal,
                opening_balance_type=op_type,
                opening_date=d_split,
                current_balance=op_bal,
                credit_limit=sl.credit_limit,
                phone=sl.phone,
                email=sl.email,
                address=sl.address,
                is_active=sl.is_active
            )
            ledger_map[sl.id] = nl

        # 6. Settle Profit & Loss into Retained Earnings in new company
        net_pl = Decimal(audit["net_profit_loss"])
        if net_pl != Decimal('0.00'):
            equity_group = LedgerGroup.objects.filter(company=new_company, nature='EQUITY').first()
            if not equity_group:
                equity_group = LedgerGroup.objects.create(company=new_company, name='Reserves & Surplus', nature='EQUITY')

            re_ledger, _ = Ledger.objects.get_or_create(
                company=new_company,
                name='Retained Earnings',
                defaults={
                    'group': equity_group,
                    'ledger_type': 'GENERAL',
                    'opening_balance': Decimal('0.00'),
                    'opening_balance_type': 'CREDIT',
                    'opening_date': d_split
                }
            )

            # Profit increases Credit (Equity); Loss increases Debit
            current_re = re_ledger.opening_balance if re_ledger.opening_balance_type == 'CREDIT' else -re_ledger.opening_balance
            new_re = current_re + net_pl
            re_ledger.opening_balance = abs(new_re)
            re_ledger.opening_balance_type = 'CREDIT' if new_re >= Decimal('0.00') else 'DEBIT'
            re_ledger.current_balance = re_ledger.opening_balance
            re_ledger.save(update_fields=['opening_balance', 'opening_balance_type', 'current_balance'])

        # 7. Clone Product Categories and Stock Catalog
        prod_map = {}
        for sp in Product.objects.filter(company=source_company):
            np = Product.objects.create(
                company=new_company,
                name=sp.name,
                sku=sp.sku,
                hsn_code=sp.hsn_code,
                gst_rate=sp.gst_rate,
                selling_price=sp.selling_price,
                purchase_price=sp.purchase_price,
                stock_quantity=sp.stock_quantity,
                unit=sp.unit,
                is_active=sp.is_active
            )
            prod_map[sp.id] = np

        # 8. Migrate any vouchers created on or after split_date into the new company
        post_split_vouchers = Voucher.objects.filter(
            company=source_company,
            voucher_date__gte=d_split
        )
        for pv in post_split_vouchers:
            pv.company = new_company
            if pv.party_ledger and pv.party_ledger.id in ledger_map:
                pv.party_ledger = ledger_map[pv.party_ledger.id]
            pv.save(update_fields=['company', 'party_ledger'])

            for item in pv.items.all():
                if item.product and item.product.id in prod_map:
                    item.product = prod_map[item.product.id]
                    item.save(update_fields=['product'])

            for entry in pv.ledger_entries.all():
                if entry.ledger and entry.ledger.id in ledger_map:
                    entry.ledger = ledger_map[entry.ledger.id]
                    entry.save(update_fields=['ledger'])

        # 9. Provision Initial Financial Year for New Company
        InvoiceSequenceService.get_or_create_active_fy(new_company, d_split)

        # 10. Mark old Financial Year in source company as split_archived
        FinancialYear.objects.filter(
            company=source_company,
            end_date__lte=d_prior
        ).update(is_split_archived=True, is_closed=True)

        return {
            "success": True,
            "source_company_id": str(source_company.id),
            "new_company_id": str(new_company.id),
            "new_company_name": new_company.name,
            "split_date": d_split.strftime('%Y-%m-%d'),
            "carried_accounts_count": carried_accounts_count,
            "net_profit_loss": str(net_pl),
            "message": f"Successfully created standalone split company '{new_company.name}' with books commencing on {d_split.strftime('%d-%b-%Y')}."
        }
