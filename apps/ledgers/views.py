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
            ledgers = Ledger.objects.filter(company=company)
            data = [
                {
                    "id": str(l.id),
                    "name": l.name,
                    "group": l.group.name,
                    "current_balance": l.current_balance,
                    "opening_balance_type": l.opening_balance_type,
                    "state_code": l.state_code
                } for l in ledgers
            ]
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def post(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            data = request.data
            
            # Find or create the group
            from .models import LedgerGroup
            group_name = data.get('group_name')
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
                name=data.get('name'),
                ledger_type=data.get('ledger_type', 'GENERAL'),
                gstin=data.get('gstin', ''),
                state_code=data.get('state_code', ''),
                phone=data.get('phone', ''),
                email=data.get('email', ''),
                address=data.get('address', ''),
                opening_balance_type=data.get('opening_balance_type', 'DEBIT')
            )
            return Response({"success": True, "data": {"id": str(ledger.id), "name": ledger.name}})
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

            if 'name' in data: ledger.name = data['name']
            if 'gstin' in data: ledger.gstin = data['gstin']
            if 'state_code' in data: ledger.state_code = data['state_code']
            if 'phone' in data: ledger.phone = data['phone']
            if 'email' in data: ledger.email = data['email']
            if 'address' in data: ledger.address = data['address']

            ledger.save()
            return Response({"success": True, "data": {"id": str(ledger.id), "name": ledger.name}})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)
