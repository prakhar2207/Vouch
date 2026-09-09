from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Ledger
from apps.companies.models import Company
from apps.accounts.permissions import IsCompanyMember, CanManageLedgers

class LedgerGroupListView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanManageLedgers()]

    def get(self, request, company_id):
        try:
            from .models import LedgerGroup
            company = Company.objects.get(id=company_id, users__user=request.user)
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
            from .models import LedgerGroup
            company = Company.objects.get(id=company_id, users__user=request.user)
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


class LedgerListView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanManageLedgers()]
    
    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            
            # Enforce strict GST separation & auto-heal historical entries
            from apps.accounting.services.sales_service import SalesInvoiceService
            SalesInvoiceService.reassign_misallocated_tax_entries(company)

            ledgers = Ledger.objects.filter(company=company).select_related('group').only(
                'id', 'name', 'group_id', 'group__name', 'group__nature', 'ledger_type',
                'gstin', 'state_code', 'phone', 'email', 'address', 'current_balance',
                'opening_balance', 'opening_balance_type', 'discount_percent', 'is_active'
            ).order_by('name')
            data = [
                {
                    "id": str(l.id),
                    "name": l.name,
                    "group_id": str(l.group_id) if l.group_id else None,
                    "group": l.group.name if l.group else "",
                    "nature": l.group.nature if l.group else "ASSET",
                    "ledger_type": l.ledger_type,
                    "gstin": l.gstin or "",
                    "state_code": l.state_code or "",
                    "phone": l.phone or "",
                    "email": l.email or "",
                    "address": l.address or "",
                    "current_balance": l.current_balance,
                    "opening_balance": float(l.opening_balance or 0),
                    "opening_balance_type": l.opening_balance_type,
                    "discount_percent": float(l.discount_percent or 0),
                    "is_active": l.is_active,
                } for l in ledgers
            ]
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def post(self, request, company_id):
        try:
            from decimal import Decimal
            company = Company.objects.get(id=company_id, users__user=request.user)
            data = request.data
            
            name = str(data.get('name') or '').strip()
            gstin = str(data.get('gstin') or '').strip().upper()
            group_name = str(data.get('group_name') or 'Sundry Creditors').strip()
            
            if not name:
                return Response({"success": False, "error": "Party/Ledger name is required."}, status=400)

            # Deduplication: check if party with same GSTIN or same Name already exists in this company
            existing = None
            if gstin:
                existing = Ledger.objects.filter(company=company, gstin__iexact=gstin).first()
            if not existing and name:
                existing = Ledger.objects.filter(company=company, name__iexact=name).first()

            if existing:
                # Update missing details if provided in request
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
                        "gstin": existing.gstin or "",
                        "discount_percent": float(existing.discount_percent or 0)
                    },
                    "already_exists": True,
                    "message": f"Party '{existing.name}' already exists. Reused existing ledger."
                })

            # Find or create the group
            from .models import LedgerGroup
            group = None
            if data.get('group_id'):
                group = LedgerGroup.objects.filter(company=company, id=data.get('group_id')).first()
            if not group:
                group = LedgerGroup.objects.filter(company=company, name__iexact=group_name).first() or \
                        LedgerGroup.objects.filter(company=company, name__icontains=group_name).first()
            if not group:
                # Default nature mapping based on common groups
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

            # Create ledger
            ledger = Ledger.objects.create(
                company=company,
                group=group,
                name=name,
                ledger_type=data.get('ledger_type', 'GENERAL'),
                gstin=gstin,
                state_code=data.get('state_code', ''),
                phone=data.get('phone', ''),
                email=data.get('email', ''),
                address=data.get('address', ''),
                discount_percent=discount_percent,
                opening_balance=op_balance,
                current_balance=op_balance,
                opening_balance_type=data.get('opening_balance_type', 'DEBIT')
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
                    "gstin": ledger.gstin or "",
                    "discount_percent": float(ledger.discount_percent or 0),
                    "opening_balance": float(ledger.opening_balance or 0),
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
            data = {
                "id": str(l.id),
                "name": l.name,
                "group_id": str(l.group_id) if l.group_id else None,
                "group": l.group.name if l.group else "",
                "nature": l.group.nature if l.group else "ASSET",
                "ledger_type": l.ledger_type,
                "gstin": l.gstin or "",
                "state_code": l.state_code or "",
                "phone": l.phone or "",
                "email": l.email or "",
                "address": l.address or "",
                "current_balance": float(l.current_balance or 0),
                "opening_balance": float(l.opening_balance or 0),
                "opening_balance_type": l.opening_balance_type,
                "discount_percent": float(l.discount_percent or 0),
                "is_active": l.is_active,
            }
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def patch(self, request, company_id, ledger_id):
        try:
            from decimal import Decimal
            from .models import LedgerGroup
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
            if 'opening_balance_type' in data: ledger.opening_balance_type = data['opening_balance_type']
            
            if 'group_id' in data and data['group_id']:
                grp = LedgerGroup.objects.filter(company=company, id=data['group_id']).first()
                if grp:
                    ledger.group = grp

            if 'opening_balance' in data and data.get('opening_balance') is not None and str(data.get('opening_balance')).strip() != '':
                try:
                    ledger.opening_balance = Decimal(str(data['opening_balance']))
                except Exception:
                    pass

            if 'discount_percent' in data and data.get('discount_percent') is not None and str(data.get('discount_percent')).strip() != '':
                try:
                    ledger.discount_percent = Decimal(str(data['discount_percent']))
                except Exception:
                    pass

            ledger.save()
            return Response({
                "success": True, 
                "data": {
                    "id": str(ledger.id), 
                    "name": ledger.name,
                    "group": ledger.group.name if ledger.group else "",
                    "nature": ledger.group.nature if ledger.group else "ASSET",
                    "discount_percent": float(ledger.discount_percent or 0),
                    "is_active": ledger.is_active
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def delete(self, request, company_id, ledger_id):
        try:
            from django.db.models import ProtectedError
            from apps.accounting.models import Voucher, LedgerEntry
            company = Company.objects.get(id=company_id, users__user=request.user)
            ledger = Ledger.objects.get(id=ledger_id, company=company)

            vouchers_count = Voucher.objects.filter(company=company, party_ledger=ledger).count()
            entries_count = LedgerEntry.objects.filter(ledger=ledger).count()

            if vouchers_count > 0 or entries_count > 0:
                return Response({
                    "success": False, 
                    "error": f"Cannot delete '{ledger.name}' because it has {vouchers_count} linked vouchers and {entries_count} accounting ledger entries. Please delete or reassign them first."
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


class PartyCleanupView(APIView):
    permission_classes = [IsAuthenticated, CanManageLedgers]

    def post(self, request, company_id):
        try:
            from decimal import Decimal
            from apps.accounting.models import Voucher, LedgerEntry, LedgerBalance
            company = Company.objects.get(id=company_id, users__user=request.user)

            apex_deleted = 0
            apex_ledgers = list(Ledger.objects.filter(company=company, name__icontains='Apex'))
            for apex in apex_ledgers:
                for v in Voucher.objects.filter(party_ledger=apex):
                    v.items.all().delete()
                    v.ledger_entries.all().delete()
                    v.delete()
                LedgerEntry.objects.filter(ledger=apex).delete()
                LedgerBalance.objects.filter(ledger=apex).delete()
                apex.delete()
                apex_deleted += 1

            satyam_consolidated = 0
            satyam_ledgers = list(Ledger.objects.filter(company=company, name__icontains='Satyam').order_by('created_at'))
            if satyam_ledgers:
                canonical = satyam_ledgers[0]
                for l in satyam_ledgers:
                    if l.gstin and not canonical.gstin:
                        canonical = l
                        break

                canonical.name = 'Satyam & Co.'
                canonical.ledger_type = 'SUPPLIER'

                for dup in satyam_ledgers:
                    if dup.id == canonical.id:
                        continue
                    if dup.gstin and not canonical.gstin:
                        canonical.gstin = dup.gstin
                    if dup.address and not canonical.address:
                        canonical.address = dup.address
                    if dup.phone and not canonical.phone:
                        canonical.phone = dup.phone
                    if dup.email and not canonical.email:
                        canonical.email = dup.email
                    if dup.state_code and not canonical.state_code:
                        canonical.state_code = dup.state_code

                    Voucher.objects.filter(party_ledger=dup).update(party_ledger=canonical)
                    LedgerEntry.objects.filter(ledger=dup).update(ledger=canonical)
                    LedgerBalance.objects.filter(ledger=dup).delete()
                    dup.delete()
                    satyam_consolidated += 1

                entries = LedgerEntry.objects.filter(ledger=canonical)
                total_dr = sum(Decimal(str(e.debit_amount or 0)) for e in entries)
                total_cr = sum(Decimal(str(e.credit_amount or 0)) for e in entries)
                op = Decimal(str(canonical.opening_balance or 0))

                if canonical.opening_balance_type == 'DEBIT':
                    canonical.current_balance = op + total_dr - total_cr
                else:
                    canonical.current_balance = op + total_cr - total_dr

                canonical.save()

            return Response({
                "success": True,
                "message": f"Cleanup completed. Apex ledgers removed: {apex_deleted}, Satyam duplicate ledgers merged: {satyam_consolidated}."
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

