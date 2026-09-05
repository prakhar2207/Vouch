from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Ledger
from apps.companies.models import Company

class LedgerListView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            ledgers = Ledger.objects.filter(company=company).select_related('group').order_by('name')
            data = [
                {
                    "id": str(l.id),
                    "name": l.name,
                    "group": l.group.name if l.group else "",
                    "ledger_type": l.ledger_type,
                    "gstin": l.gstin or "",
                    "state_code": l.state_code or "",
                    "phone": l.phone or "",
                    "email": l.email or "",
                    "address": l.address or "",
                    "current_balance": l.current_balance,
                    "opening_balance_type": l.opening_balance_type,
                } for l in ledgers
            ]
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def post(self, request, company_id):
        try:
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
                if updated:
                    existing.save()

                return Response({
                    "success": True, 
                    "data": {
                        "id": str(existing.id), 
                        "name": existing.name,
                        "group": existing.group.name if existing.group else "",
                        "ledger_type": existing.ledger_type,
                        "gstin": existing.gstin or ""
                    },
                    "already_exists": True,
                    "message": f"Party '{existing.name}' already exists. Reused existing ledger."
                })

            # Find or create the group
            from .models import LedgerGroup
            group = LedgerGroup.objects.filter(company=company, name__icontains=group_name).first()
            if not group:
                # Default nature mapping based on common groups
                nature = 'ASSET'
                if 'Creditor' in group_name or 'Capital' in group_name or 'Loan' in group_name:
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
                opening_balance_type=data.get('opening_balance_type', 'DEBIT')
            )
            return Response({
                "success": True, 
                "data": {
                    "id": str(ledger.id), 
                    "name": ledger.name,
                    "group": ledger.group.name if ledger.group else "",
                    "ledger_type": ledger.ledger_type,
                    "gstin": ledger.gstin or ""
                }
            }, status=201)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class LedgerDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id, ledger_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            l = Ledger.objects.select_related('group').get(id=ledger_id, company=company)
            data = {
                "id": str(l.id),
                "name": l.name,
                "group": l.group.name,
                "gstin": l.gstin or "",
                "state_code": l.state_code or "",
                "phone": l.phone or "",
                "email": l.email or "",
                "address": l.address or "",
                "current_balance": l.current_balance,
                "opening_balance": l.opening_balance,
                "opening_balance_type": l.opening_balance_type,
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

            ledger.save()
            return Response({"success": True, "data": {"id": str(ledger.id), "name": ledger.name}})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def delete(self, request, company_id, ledger_id):
        try:
            from django.db.models import ProtectedError
            from apps.accounting.models import Voucher, LedgerEntry
            company = Company.objects.get(id=company_id, users__user=request.user)
            ledger = Ledger.objects.get(id=ledger_id, company=company)

            vouchers_count = Voucher.objects.filter(company=company, party_ledger=ledger).count()
            entries_count = LedgerEntry.objects.filter(company=company, ledger=ledger).count()

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
