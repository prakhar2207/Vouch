import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Ledger, LedgerGroup
from apps.companies.models import Company
from apps.accounting.models import Voucher, LedgerEntry, FinancialYear
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService
from apps.accounting.services.party_balance_service import PartyBalanceService
from apps.accounts.permissions import IsCompanyMember, CanManageLedgers, get_authorized_company
from apps.audit.services.audit_service import AuditService
from apps.ledgers.services.opening_balance_service import OpeningBalanceService
from apps.ledgers.services.party_merge_service import PartyMergeService

class LedgerGroupListView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanManageLedgers()]

    def get(self, request, company_id):
        try:
            company = get_authorized_company(request, company_id)
            groups = LedgerGroup.objects.filter(company=company).order_by('nature', 'name')
            data = [
                {
                    "id": str(g.id),
                    "name": g.name,
                    "nature": g.nature,
                    "parent_group_id": str(g.parent_group_id) if g.parent_group_id else None,
                    "parent_group_name": g.parent_group.name if g.parent_group else None,
                }
                for g in groups
            ]
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def post(self, request, company_id):
        try:
            company = get_authorized_company(request, company_id)
            data = request.data
            name = str(data.get('name') or '').strip()
            nature = str(data.get('nature') or 'ASSET').strip().upper()
            parent_id = data.get('parent_group_id')
            
            if not name:
                return Response({"success": False, "error": "Group name is required."}, status=400)
            
            parent_group = None
            if parent_id:
                parent_group = LedgerGroup.objects.filter(id=parent_id, company=company).first()
                if parent_group:
                    nature = parent_group.nature
                    
            group, created = LedgerGroup.objects.get_or_create(
                company=company,
                name=name,
                defaults={'nature': nature, 'parent_group': parent_group}
            )
            return Response({
                "success": True,
                "data": {
                    "id": str(group.id),
                    "name": group.name,
                    "nature": group.nature,
                    "parent_group_id": str(group.parent_group_id) if group.parent_group_id else None
                },
                "created": created
            }, status=201 if created else 200)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


def resolve_fy_dates(request, company):
    fy_id = request.query_params.get('financial_year_id') or request.headers.get('X-Financial-Year-ID')
    start_param = request.query_params.get('start_date')
    end_param = request.query_params.get('end_date') or request.query_params.get('as_of_date')

    start_date = None
    end_date = None

    if fy_id:
        fy = FinancialYear.objects.filter(id=fy_id, company=company).first()
        if fy:
            start_date = fy.start_date
            end_date = fy.end_date

    if start_param:
        try:
            start_date = datetime.datetime.strptime(str(start_param).strip(), '%Y-%m-%d').date()
        except ValueError:
            pass

    if end_param:
        try:
            end_date = datetime.datetime.strptime(str(end_param).strip(), '%Y-%m-%d').date()
        except ValueError:
            pass

    return start_date, end_date


def compute_scoped_ledger_balances(company, start_date=None, end_date=None, ledger_ids=None, scope_taxes=False):
    """
    Computes ledger balances dynamically scoped to [start_date, end_date].
    - Nominal accounts (INCOME, EXPENSE): entries strictly within [start_date, end_date].
    - Tax accounts (DUTIES & TAXES): if scope_taxes=True, entries strictly within [start_date, end_date].
    - Balance Sheet accounts (ASSET, LIABILITY, EQUITY): entries up to end_date + opening balance.
    """
    qs = Ledger.objects.filter(company=company).select_related('group')
    if ledger_ids:
        qs = qs.filter(id__in=ledger_ids)
    ledgers = list(qs)
    if not ledgers:
        return {}

    target_ids = [l.id for l in ledgers]
    company_filter = Q(company=company) | Q(voucher__company=company)

    # Double-entry opening vouchers
    ledgers_with_opening = set(
        LedgerEntry.objects.filter(
            company_filter,
            ledger_id__in=target_ids,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
            voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
        ).values_list('ledger_id', flat=True).distinct()
    )

    is_tax = lambda l: l.ledger_type == 'TAX' or (l.group and ('duties' in l.group.name.lower() or 'tax' in l.group.name.lower()))
    tax_ids = [l.id for l in ledgers if is_tax(l)] if scope_taxes else []
    nominal_ids = [l.id for l in ledgers if l.group and l.group.nature in ('INCOME', 'EXPENSE')]
    bs_ids = [l.id for l in ledgers if not (l.group and l.group.nature in ('INCOME', 'EXPENSE')) and l.id not in tax_ids]

    nominal_totals = {}
    if nominal_ids:
        nominal_qs = LedgerEntry.objects.filter(
            company_filter,
            ledger_id__in=nominal_ids,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
        )
        if start_date:
            nominal_qs = nominal_qs.filter(voucher__voucher_date__gte=start_date)
        if end_date:
            nominal_qs = nominal_qs.filter(voucher__voucher_date__lte=end_date)
        nominal_totals = {
            row['ledger_id']: row
            for row in nominal_qs.values('ledger_id').annotate(
                total_dr=Sum('debit_amount'),
                total_cr=Sum('credit_amount')
            )
        }

    tax_totals = {}
    if tax_ids:
        tax_qs = LedgerEntry.objects.filter(
            company_filter,
            ledger_id__in=tax_ids,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
        )
        if start_date:
            tax_qs = tax_qs.filter(voucher__voucher_date__gte=start_date)
        if end_date:
            tax_qs = tax_qs.filter(voucher__voucher_date__lte=end_date)
        tax_totals = {
            row['ledger_id']: row
            for row in tax_qs.values('ledger_id').annotate(
                total_dr=Sum('debit_amount'),
                total_cr=Sum('credit_amount')
            )
        }

    bs_totals = {}
    if bs_ids:
        bs_qs = LedgerEntry.objects.filter(
            company_filter,
            ledger_id__in=bs_ids,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
        )
        if end_date:
            bs_qs = bs_qs.filter(voucher__voucher_date__lte=end_date)
        bs_totals = {
            row['ledger_id']: row
            for row in bs_qs.values('ledger_id').annotate(
                total_dr=Sum('debit_amount'),
                total_cr=Sum('credit_amount')
            )
        }

    scoped_map = {}
    for l in ledgers:
        is_nominal = bool(l.group and l.group.nature in ('INCOME', 'EXPENSE'))
        if is_nominal:
            tot = nominal_totals.get(l.id)
            dr = Decimal(str(tot['total_dr'] or '0.00')) if tot else Decimal('0.00')
            cr = Decimal(str(tot['total_cr'] or '0.00')) if tot else Decimal('0.00')
        elif l.id in tax_ids:
            tot = tax_totals.get(l.id)
            dr = Decimal(str(tot['total_dr'] or '0.00')) if tot else Decimal('0.00')
            cr = Decimal(str(tot['total_cr'] or '0.00')) if tot else Decimal('0.00')
        else:
            tot = bs_totals.get(l.id)
            dr = Decimal(str(tot['total_dr'] or '0.00')) if tot else Decimal('0.00')
            cr = Decimal(str(tot['total_cr'] or '0.00')) if tot else Decimal('0.00')
            if l.id not in ledgers_with_opening:
                op_date = l.opening_date
                if not end_date or not op_date or op_date <= end_date:
                    op_bal = Decimal(str(l.opening_balance or '0.00'))
                    if l.opening_balance_type == 'CREDIT':
                        cr += op_bal
                    else:
                        dr += op_bal

        # Stock-in-Hand / Inventory live valuation integration
        is_stock = bool(
            l.ledger_type == 'ASSET' and (
                'STOCK' in l.name.upper() or 'INVENTORY' in l.name.upper() or
                (l.group and ('STOCK' in l.group.name.upper() or 'INVENTORY' in l.group.name.upper()))
            )
        )
        if is_stock and dr == Decimal('0.00') and cr == Decimal('0.00'):
            from apps.accounting.services.financial_statements_service import FinancialStatementsService
            dr = FinancialStatementsService.get_inventory_valuation(company)

        bal_info = PartyBalanceService.get_balance_from_components(
            l.canonical_role, dr, cr, l.normal_balance
        )
        scoped_map[str(l.id)] = {
            'display_amount': float(bal_info['display_amount']),
            'current_balance': float(bal_info['signed_balance']),
            'balance_state': 'DR' if is_stock and bal_info['display_amount'] > 0 else bal_info['balance_state'],
            'balance_direction': 'DEBIT' if is_stock and bal_info['display_amount'] > 0 else bal_info['balance_direction'],
            'explanation': 'Live physical stock in hand' if is_stock else bal_info.get('explanation', ''),
            'owner_headline': 'STOCK IN HAND' if is_stock else bal_info.get('owner_headline', '')
        }

    return scoped_map


class LedgerListView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanManageLedgers()]
    
    def get(self, request, company_id):
        try:
            company = get_authorized_company(request, company_id)
            
            # Enforce strict GST separation & auto-heal historical entries
            # REMOVED: SalesInvoiceService.reassign_misallocated_tax_entries(company)

            qs = Ledger.objects.filter(company=company).select_related('group')
            
            # Archival filtering
            show_archived = request.query_params.get('show_archived', 'false').lower()
            if show_archived == 'true':
                pass # show all
            elif show_archived == 'only':
                qs = qs.filter(is_archived=True)
            else:
                qs = qs.filter(is_archived=False)

            ledgers = qs.order_by('name')

            # Financial Year Scoping
            start_date, end_date = resolve_fy_dates(request, company)
            scope_taxes = request.query_params.get('scope_taxes', '').lower() in ('1', 'true', 'yes')
            scoped_balances = None
            if start_date or end_date:
                scoped_balances = compute_scoped_ledger_balances(company, start_date, end_date, scope_taxes=scope_taxes)

            data = []
            for l in ledgers:
                s_bal = scoped_balances.get(str(l.id)) if scoped_balances else None
                cur_bal = s_bal['current_balance'] if s_bal else float(l.current_balance or 0)
                disp_amt = s_bal['display_amount'] if s_bal else float(l.display_amount)
                bal_state = s_bal['balance_state'] if s_bal else l.balance_state
                bal_dir = s_bal['balance_direction'] if s_bal else l.balance_direction

                is_stock = bool(
                    l.ledger_type == 'ASSET' and (
                        'STOCK' in l.name.upper() or 'INVENTORY' in l.name.upper() or
                        (l.group and ('STOCK' in l.group.name.upper() or 'INVENTORY' in l.group.name.upper()))
                    )
                )
                if is_stock and cur_bal == 0 and disp_amt == 0:
                    from apps.accounting.services.financial_statements_service import FinancialStatementsService
                    inv_val = float(FinancialStatementsService.get_inventory_valuation(company))
                    cur_bal = inv_val
                    disp_amt = inv_val
                    bal_dir = 'DEBIT'
                    bal_state = 'DR'

                data.append({
                    "id": str(l.id),
                    "name": l.name,
                    "group_id": str(l.group_id) if l.group_id else None,
                    "group": l.group.name if l.group else "",
                    "nature": l.group.nature if l.group else "ASSET",
                    "ledger_type": l.ledger_type,
                    "canonical_role": l.canonical_role,
                    "balance_state": bal_state,
                    "balance_direction": bal_dir,
                    "normal_balance": l.normal_balance,
                    "display_amount": disp_amt,
                    "gstin": l.gstin or "",
                    "state_code": l.state_code or "",
                    "phone": l.phone or "",
                    "email": l.email or "",
                    "address": l.address or "",
                    "current_balance": cur_bal,
                    "opening_balance": float(l.opening_balance or 0),
                    "opening_balance_type": l.opening_balance_type,
                    "opening_date": str(l.opening_date) if l.opening_date else None,
                    "credit_limit": float(l.credit_limit) if l.credit_limit else None,
                    "credit_period_days": l.credit_period_days,
                    "discount_percent": float(l.discount_percent or 0),
                    "is_active": l.is_active,
                    "is_archived": l.is_archived,
                })
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def post(self, request, company_id):
        try:
            company = get_authorized_company(request, company_id)
            data = request.data
            
            name = str(data.get('name') or '').strip()
            gstin = str(data.get('gstin') or '').strip().upper()
            requested_type = str(data.get('ledger_type') or 'GENERAL').strip().upper()
            group_name = str(data.get('group_name') or '').strip()
            if not group_name:
                if requested_type == 'CUSTOMER':
                    group_name = 'Sundry Debtors'
                else:
                    group_name = 'Sundry Creditors'
            role_action = str(data.get('role_action') or '').strip().upper() # 'CREATE_SEPARATE', 'UPGRADE_TO_BOTH'
            
            if not name:
                return Response({"success": False, "error": "Party/Ledger name is required."}, status=400)

            # Deduplication & Party Identity Logic
            existing = None
            if gstin:
                existing = Ledger.objects.filter(company=company, gstin__iexact=gstin, is_archived=False).first()
            if not existing and name:
                existing = Ledger.objects.filter(company=company, name__iexact=name, is_archived=False).first()

            if existing:
                existing_role = existing.canonical_role
                if requested_type == 'BOTH':
                    requested_role = 'BOTH'
                elif requested_type == 'CUSTOMER' or 'debtor' in group_name.lower():
                    requested_role = 'CUSTOMER'
                elif requested_type == 'SUPPLIER' or 'creditor' in group_name.lower():
                    requested_role = 'SUPPLIER'
                else:
                    requested_role = 'OTHER'

                if requested_type == 'BOTH' and existing_role != 'BOTH':
                    existing.ledger_type = 'BOTH'
                    existing.save(update_fields=['ledger_type'])
                    existing_role = 'BOTH'
                
                # Check if role conflicts (e.g. existing is SUPPLIER, requested is CUSTOMER)
                if requested_role in ['CUSTOMER', 'SUPPLIER'] and existing_role in ['CUSTOMER', 'SUPPLIER'] and existing_role != requested_role:
                    if role_action == 'CREATE_SEPARATE':
                        # Explicit user confirmation: create separate account
                        existing = None
                    elif role_action == 'UPGRADE_TO_BOTH':
                        existing.ledger_type = 'BOTH'
                        existing.save(update_fields=['ledger_type'])
                        return Response({
                            "success": True,
                            "data": {
                                "id": str(existing.id),
                                "name": existing.name,
                                "ledger_type": existing.ledger_type,
                                "canonical_role": existing.canonical_role,
                                "current_balance": float(existing.current_balance or 0)
                            },
                            "message": f"Updated '{existing.name}' to act as BOTH Customer and Supplier."
                        })
                    else:
                        # Prevent accidental merge! Notify user of existing entity
                        return Response({
                            "success": False,
                            "conflict_type": "ROLE_DIFFERENCE",
                            "existing_party": {
                                "id": str(existing.id),
                                "name": existing.name,
                                "gstin": existing.gstin or "",
                                "role": existing_role
                            },
                            "message": f"This business already exists as a {existing_role}. You can use the existing business, mark it as BOTH, or create a separate {requested_role} account."
                        }, status=409)

                if existing:
                    # Update missing non-critical details if provided
                    updated = False
                    if gstin and not existing.gstin:
                        existing.gstin = gstin
                        updated = True
                    if data.get('state_code') and not existing.state_code:
                        existing.state_code = str(data.get('state_code')).strip()
                        updated = True
                    if data.get('phone') and not existing.phone:
                        existing.phone = str(data.get('phone')).strip()
                        updated = True
                    if data.get('address') and not existing.address:
                        existing.address = str(data.get('address')).strip()
                        updated = True
                    if 'discount_percent' in data and data.get('discount_percent') is not None and str(data.get('discount_percent')).strip() != '':
                        try:
                            existing.discount_percent = Decimal(str(data.get('discount_percent')))
                            updated = True
                        except Exception:
                            pass
                    if updated:
                        existing.save()

                    return Response({
                        "success": True, 
                        "data": {
                            "id": str(existing.id), 
                            "name": existing.name,
                            "group": existing.group.name if existing.group else "",
                            "ledger_type": existing.ledger_type,
                            "canonical_role": existing.canonical_role,
                            "gstin": existing.gstin or "",
                            "current_balance": float(existing.current_balance or 0),
                            "discount_percent": float(existing.discount_percent or 0)
                        },
                        "already_exists": True,
                        "message": f"Party '{existing.name}' already exists. Reused existing ledger."
                    })

            # Find or create the group
            group = None
            if data.get('group_id'):
                group = LedgerGroup.objects.filter(company=company, id=data.get('group_id')).first()
            if not group:
                group = LedgerGroup.objects.filter(company=company, name__iexact=group_name).first() or                         LedgerGroup.objects.filter(company=company, name__icontains=group_name).first()
            if not group:
                nature = 'ASSET'
                if 'Creditor' in group_name or 'Capital' in group_name or 'Loan' in group_name or 'Duties' in group_name or 'Taxes' in group_name or 'Liability' in group_name:
                    nature = 'LIABILITY'
                elif 'Income' in group_name or 'Sales' in group_name:
                    nature = 'INCOME'
                elif 'Expense' in group_name or 'Purchase' in group_name:
                    nature = 'EXPENSE'
                    
                group = LedgerGroup.objects.create(
                    company=company,
                    name=group_name,
                    nature=nature
                )

            discount_percent = Decimal('0.00')
            if 'discount_percent' in data and data.get('discount_percent') is not None and str(data.get('discount_percent')).strip() != '':
                try:
                    discount_percent = Decimal(str(data.get('discount_percent')))
                except Exception:
                    pass

            op_balance = Decimal('0.00')
            if 'opening_balance' in data and data.get('opening_balance') is not None and str(data.get('opening_balance')).strip() != '':
                try:
                    op_balance = Decimal(str(data.get('opening_balance')))
                except Exception:
                    pass

            credit_limit = None
            if 'credit_limit' in data and data.get('credit_limit') is not None and str(data.get('credit_limit')).strip() != '':
                try:
                    credit_limit = Decimal(str(data.get('credit_limit')))
                except Exception:
                    pass

            credit_period_days = 0
            if 'credit_period_days' in data and data.get('credit_period_days') is not None and str(data.get('credit_period_days')).strip() != '':
                try:
                    credit_period_days = int(data.get('credit_period_days'))
                except Exception:
                    pass

            # Opening date default to active FY start date
            opening_date = data.get('opening_date')
            if not opening_date:
                active_fy = FinancialYear.objects.filter(company=company, is_closed=False).order_by('-start_date').first()
                if active_fy:
                    opening_date = active_fy.start_date
                else:
                    today = timezone.now().date()
                    year = today.year if today.month >= 4 else today.year - 1
                    opening_date = datetime.date(year, 4, 1)
            elif isinstance(opening_date, str):
                opening_date = datetime.date.fromisoformat(opening_date.split('T')[0])

            # Determine opening balance type: DEBIT for Customer / Asset, CREDIT for Supplier / Liability
            op_type = data.get('opening_balance_type')
            if not op_type:
                if requested_type == 'CUSTOMER' or 'debtor' in group.name.lower():
                    op_type = 'DEBIT'
                else:
                    op_type = 'CREDIT'

            ledger = Ledger.objects.create(
                company=company,
                group=group,
                name=name,
                ledger_type=requested_type,
                gstin=gstin,
                state_code=data.get('state_code', ''),
                phone=data.get('phone', ''),
                email=data.get('email', ''),
                address=data.get('address', ''),
                discount_percent=discount_percent,
                credit_limit=credit_limit,
                credit_period_days=credit_period_days,
                opening_balance=op_balance,
                current_balance=Decimal('0.00'),
                opening_balance_type=op_type,
                opening_date=opening_date
            )

            # Record Opening Balance via strict Double-Entry Accounting
            if op_balance > Decimal('0.00'):
                OpeningBalanceService.record_opening_balance(
                    ledger=ledger,
                    amount=op_balance,
                    balance_type=op_type,
                    opening_date=opening_date,
                    pending_invoices=data.get('pending_invoices'),
                    user=request.user
                )

            return Response({
                "success": True, 
                "data": {
                    "id": str(ledger.id), 
                    "name": ledger.name,
                    "group_id": str(ledger.group_id) if ledger.group_id else None,
                    "group": ledger.group.name if ledger.group else "",
                    "nature": ledger.group.nature if ledger.group else "ASSET",
                    "ledger_type": ledger.ledger_type,
                    "canonical_role": ledger.canonical_role,
                    "balance_state": ledger.balance_state,
                    "display_amount": float(ledger.display_amount),
                    "gstin": ledger.gstin or "",
                    "discount_percent": float(ledger.discount_percent or 0),
                    "credit_limit": float(ledger.credit_limit) if ledger.credit_limit else None,
                    "credit_period_days": ledger.credit_period_days,
                    "opening_balance": float(ledger.opening_balance or 0),
                    "opening_balance_type": ledger.opening_balance_type,
                    "opening_date": str(ledger.opening_date) if ledger.opening_date else None,
                    "current_balance": float(ledger.current_balance or 0),
                }
            }, status=201)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class LedgerDetailView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanManageLedgers()]

    def get(self, request, company_id, ledger_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            l = Ledger.objects.select_related('group').get(id=ledger_id, company=company)

            start_date, end_date = resolve_fy_dates(request, company)
            s_bal = None
            if start_date or end_date:
                scoped_balances = compute_scoped_ledger_balances(company, start_date, end_date, ledger_ids=[l.id])
                s_bal = scoped_balances.get(str(l.id))

            cur_bal = s_bal['current_balance'] if s_bal else float(l.current_balance or 0)
            disp_amt = s_bal['display_amount'] if s_bal else float(l.display_amount)
            bal_state = s_bal['balance_state'] if s_bal else l.balance_state
            bal_dir = s_bal['balance_direction'] if s_bal else l.balance_direction

            is_stock = bool(
                l.ledger_type == 'ASSET' and (
                    'STOCK' in l.name.upper() or 'INVENTORY' in l.name.upper() or
                    (l.group and ('STOCK' in l.group.name.upper() or 'INVENTORY' in l.group.name.upper()))
                )
            )
            if is_stock and cur_bal == 0 and disp_amt == 0:
                from apps.accounting.services.financial_statements_service import FinancialStatementsService
                inv_val = float(FinancialStatementsService.get_inventory_valuation(company))
                cur_bal = inv_val
                disp_amt = inv_val
                bal_dir = 'DEBIT'
                bal_state = 'DR'

            data = {
                "id": str(l.id),
                "name": l.name,
                "group_id": str(l.group_id) if l.group_id else None,
                "group": l.group.name if l.group else "",
                "nature": l.group.nature if l.group else "ASSET",
                "ledger_type": l.ledger_type,
                "canonical_role": l.canonical_role,
                "balance_state": bal_state,
                "balance_direction": bal_dir,
                "normal_balance": l.normal_balance,
                "display_amount": disp_amt,
                "gstin": l.gstin or "",
                "state_code": l.state_code or "",
                "phone": l.phone or "",
                "email": l.email or "",
                "address": l.address or "",
                "current_balance": cur_bal,
                "opening_balance": float(l.opening_balance or 0),
                "opening_balance_type": l.opening_balance_type,
                "opening_date": str(l.opening_date) if l.opening_date else None,
                "credit_limit": float(l.credit_limit) if l.credit_limit else None,
                "credit_period_days": l.credit_period_days,
                "discount_percent": float(l.discount_percent or 0),
                "is_active": l.is_active,
                "is_archived": l.is_archived,
            }
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def patch(self, request, company_id, ledger_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            ledger = Ledger.objects.get(id=ledger_id, company=company)
            data = request.data

            if 'name' in data: ledger.name = str(data['name']).strip()
            if 'gstin' in data: ledger.gstin = str(data['gstin']).strip().upper()
            if 'state_code' in data: ledger.state_code = data['state_code']
            if 'phone' in data: ledger.phone = data['phone']
            if 'email' in data: ledger.email = data['email']
            if 'address' in data: ledger.address = data['address']
            if 'ledger_type' in data: ledger.ledger_type = data['ledger_type']
            if 'is_active' in data: ledger.is_active = bool(data['is_active'])
            if 'is_archived' in data: ledger.is_archived = bool(data['is_archived'])
            
            if 'credit_period_days' in data and data.get('credit_period_days') is not None and str(data.get('credit_period_days')).strip() != '':
                try: ledger.credit_period_days = int(data['credit_period_days'])
                except Exception: pass

            if 'credit_limit' in data:
                if data.get('credit_limit') is not None and str(data.get('credit_limit')).strip() != '':
                    try: ledger.credit_limit = Decimal(str(data['credit_limit']))
                    except Exception: pass
                else:
                    ledger.credit_limit = None

            if 'group_id' in data and data['group_id']:
                grp = LedgerGroup.objects.filter(company=company, id=data['group_id']).first()
                if grp:
                    ledger.group = grp

            if 'discount_percent' in data and data.get('discount_percent') is not None and str(data.get('discount_percent')).strip() != '':
                try:
                    ledger.discount_percent = Decimal(str(data['discount_percent']))
                except Exception:
                    pass

            ledger.save()

            # Opening balance modifications must go through OpeningBalanceService
            if 'opening_balance' in data or 'opening_balance_type' in data:
                raw_op = data.get('opening_balance', ledger.opening_balance)
                if raw_op is None or str(raw_op).strip() == '':
                    raw_op = Decimal('0.00')
                new_op = Decimal(str(raw_op))
                new_type = data.get('opening_balance_type', ledger.opening_balance_type)
                if not new_type:
                    new_type = 'DEBIT' if (ledger.group and ledger.group.nature == 'ASSET') else 'CREDIT'
                OpeningBalanceService.adjust_opening_balance(
                    ledger=ledger,
                    new_amount=new_op,
                    new_balance_type=new_type,
                    user=request.user,
                    reason=data.get('reason', 'Opening balance modification')
                )

            return Response({
                "success": True, 
                "data": {
                    "id": str(ledger.id), 
                    "name": ledger.name,
                    "group": ledger.group.name if ledger.group else "",
                    "nature": ledger.group.nature if ledger.group else "ASSET",
                    "ledger_type": ledger.ledger_type,
                    "canonical_role": ledger.canonical_role,
                    "balance_state": ledger.balance_state,
                    "display_amount": float(ledger.display_amount),
                    "current_balance": float(ledger.current_balance or 0),
                    "opening_balance": float(ledger.opening_balance or 0),
                    "opening_balance_type": ledger.opening_balance_type,
                    "discount_percent": float(ledger.discount_percent or 0),
                    "credit_limit": float(ledger.credit_limit) if ledger.credit_limit else None,
                    "credit_period_days": ledger.credit_period_days,
                    "is_active": ledger.is_active,
                    "is_archived": ledger.is_archived,
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def delete(self, request, company_id, ledger_id):
        try:
            from django.db.models import ProtectedError
            company = Company.objects.get(id=company_id, users__user=request.user)
            ledger = Ledger.objects.get(id=ledger_id, company=company)

            vouchers_count = Voucher.objects.filter(company=company, party_ledger=ledger).count()
            entries_count = LedgerEntry.objects.filter(ledger=ledger).count()

            if vouchers_count > 0 or entries_count > 0:
                return Response({
                    "success": False, 
                    "error": f"Cannot delete '{ledger.name}' because it has {vouchers_count} linked vouchers and {entries_count} accounting ledger entries. Party accounts with financial transactions cannot be deleted to preserve accounting integrity."
                }, status=400)

            party_name = ledger.name
            ledger.delete()
            return Response({"success": True, "message": f"Party '{party_name}' deleted successfully."})
        except Ledger.DoesNotExist:
            return Response({"success": False, "error": "Party not found."}, status=404)
        except ProtectedError:
            return Response({"success": False, "error": f"Cannot delete '{ledger.name}' as it is protected by existing financial transactions."}, status=400)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class PartyArchiveView(APIView):
    permission_classes = [IsAuthenticated, CanManageLedgers]

    def post(self, request, company_id, ledger_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            ledger = Ledger.objects.get(id=ledger_id, company=company)
            action = request.data.get('action', 'archive').lower()

            if action == 'unarchive':
                ledger.is_archived = False
                ledger.is_active = True
                msg = f"Party '{ledger.name}' has been restored from archive."
            else:
                ledger.is_archived = True
                ledger.is_active = False
                msg = f"Party '{ledger.name}' has been safely archived."

            ledger.save(update_fields=['is_archived', 'is_active'])

            AuditService.log_action(
                company=company,
                user=request.user,
                action='UPDATE',
                model_name='PartyArchive',
                record_id=ledger.id,
                changes={'is_archived': ledger.is_archived, 'is_active': ledger.is_active}
            )

            return Response({"success": True, "message": msg, "is_archived": ledger.is_archived})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class PartyMergePreviewView(APIView):
    permission_classes = [IsAuthenticated, CanManageLedgers]

    def post(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            source_id = request.data.get('source_id')
            target_id = request.data.get('target_id')
            preview = PartyMergeService.preview_merge(company, source_id, target_id)
            return Response({"success": True, "data": preview})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class PartyMergeExecuteView(APIView):
    permission_classes = [IsAuthenticated, CanManageLedgers]

    def post(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            source_id = request.data.get('source_id')
            target_id = request.data.get('target_id')
            result = PartyMergeService.execute_merge(company, source_id, target_id, user=request.user)
            return Response(result)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class PartyKhataView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id, ledger_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            ledger = Ledger.objects.select_related('group').get(id=ledger_id, company=company)
            
            from apps.accounting.services.allocation_service import PaymentAllocationService
            unpaid_invoices = PaymentAllocationService.get_unpaid_invoices_for_party(company, ledger)
            
            today = timezone.now().date()
            overdue_total = Decimal('0.00')
            due_soon_total = Decimal('0.00')
            not_due_total = Decimal('0.00')

            overdue_items = []
            due_soon_items = []
            not_due_items = []

            for inv in unpaid_invoices:
                rem = Decimal(str(inv.get('remaining_amount', 0)))
                vch = Voucher.objects.get(id=inv['voucher_id'])
                d_date = vch.due_date or vch.voucher_date
                
                item_data = {
                    **inv,
                    "due_date": str(d_date),
                    "days_diff": (d_date - today).days
                }
                
                if d_date < today:
                    overdue_total += rem
                    overdue_items.append(item_data)
                elif d_date <= today + datetime.timedelta(days=7):
                    due_soon_total += rem
                    due_soon_items.append(item_data)
                else:
                    not_due_total += rem
                    not_due_items.append(item_data)

            # Business-friendly terminology
            start_date, end_date = resolve_fy_dates(request, company)
            if start_date or end_date:
                scoped_balances = compute_scoped_ledger_balances(company, start_date, end_date, ledger_ids=[ledger.id])
                s_bal = scoped_balances.get(str(ledger.id))
                if s_bal:
                    bal_info = {
                        'display_amount': Decimal(str(s_bal['display_amount'])),
                        'signed_balance': Decimal(str(s_bal['current_balance'])),
                        'balance_state': s_bal['balance_state'],
                        'balance_direction': s_bal['balance_direction'],
                    }
                else:
                    bal_info = PartyBalanceService.get_party_balance(ledger)
            else:
                bal_info = PartyBalanceService.get_party_balance(ledger)

            # Map the semantic state back to the UI labels
            state_label_map = {
                'TO_COLLECT': 'To Collect',
                'ADVANCE_RECEIVED': 'Advance Received',
                'TO_PAY': 'To Pay',
                'ADVANCE_PAID': 'Advance Paid',
                'SETTLED': 'Settled',
                'DR': 'Debit',
                'CR': 'Credit'
            }
            balance_label = state_label_map.get(bal_info['balance_state'], bal_info['balance_state'])

            return Response({
                "success": True,
                "data": {
                    "party_id": str(ledger.id),
                    "name": ledger.name,
                    "gstin": ledger.gstin or "",
                    "phone": ledger.phone or "",
                    "role": ledger.canonical_role,
                    "current_balance": str(bal_info['display_amount']),
                    "raw_balance": str(bal_info['signed_balance']),
                    "balance_label": balance_label,
                    "balance_type": bal_info['balance_direction'],
                    "semantic_state": bal_info['balance_state'],
                    "credit_limit": str(ledger.credit_limit) if ledger.credit_limit else None,
                    "credit_period_days": ledger.credit_period_days,
                    "aging": {
                        "overdue_total": str(overdue_total),
                        "due_soon_total": str(due_soon_total),
                        "not_due_total": str(not_due_total),
                        "overdue_count": len(overdue_items),
                        "due_soon_count": len(due_soon_items),
                        "not_due_count": len(not_due_items),
                        "unpaid_invoices": unpaid_invoices
                    }
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class PartyCleanupView(APIView):
    """
    Generic party duplicate cleanup. Replaces old hardcoded Apex/Satyam logic.
    Finds exact GSTIN duplicates within the company and safely merges them into the canonical record.
    """
    permission_classes = [IsAuthenticated, CanManageLedgers]

    def post(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            from django.db.models import Count
            
            # Find GSTIN duplicates with >= 2 active parties
            dup_gstins = Ledger.objects.filter(
                company=company, 
                is_archived=False, 
                gstin__isnull=False
            ).exclude(gstin='').values('gstin').annotate(cnt=Count('id')).filter(cnt__gt=1)

            merged_count = 0
            for item in dup_gstins:
                g = item['gstin']
                parties = list(Ledger.objects.filter(company=company, gstin__iexact=g, is_archived=False).order_by('created_at'))
                if len(parties) >= 2:
                    canonical = parties[0]
                    for dup in parties[1:]:
                        PartyMergeService.execute_merge(company, dup.id, canonical.id, user=request.user)
                        merged_count += 1

            return Response({
                "success": True,
                "message": f"Generic consolidation completed. Safely merged {merged_count} duplicate accounts.",
                "merged_count": merged_count
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)
