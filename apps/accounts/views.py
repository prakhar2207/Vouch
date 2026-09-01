from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .serializers import UserSerializer

class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response({
            "success": True,
            "data": serializer.data
        })

class RegisterView(APIView):
    permission_classes = []  # Allow any

    def post(self, request):
        import datetime
        from django.db import transaction
        from .models import User
        from apps.companies.models import Company, UserCompany, CompanySettings
        from apps.ledgers.models import LedgerGroup, Ledger
        from apps.inventory.models import Warehouse
        from rest_framework_simplejwt.tokens import RefreshToken

        email = (request.data.get('email') or '').strip().lower()
        password = request.data.get('password')

        if not email or not password:
            return Response({"success": False, "error": "Email and password are required."}, status=400)

        if User.objects.filter(email__iexact=email).exists():
            return Response({"success": False, "error": f"An account with email '{email}' already exists. Please log in."}, status=400)

        firm_name = (request.data.get('name') or request.data.get('firm_name') or 'My Firm').strip()
        gstin = (request.data.get('gstin') or '').strip().upper()
        pan = request.data.get('pan') or (gstin[2:12] if len(gstin) >= 12 else '')
        state_code = (request.data.get('state_code') or '').strip()
        address = (request.data.get('address') or '').strip()
        phone = (request.data.get('phone') or '').strip()
        company_email = (request.data.get('company_email') or email).strip()
        proprietor_name = (request.data.get('proprietor_name') or '').strip()
        proprietor_phone = (request.data.get('proprietor_phone') or '').strip()
        signature_file = request.FILES.get('signature') or request.FILES.get('proprietor_signature')

        try:
            with transaction.atomic():
                # 1. Create User
                user = User.objects.create_user(email=email, password=password)

                # 2. Create Company
                company = Company.objects.create(
                    name=firm_name,
                    legal_name=firm_name,
                    gstin=gstin,
                    pan=pan,
                    phone=phone,
                    email=company_email,
                    address=address,
                    state_code=state_code,
                    proprietor_name=proprietor_name,
                    proprietor_phone=proprietor_phone,
                    proprietor_signature=signature_file if signature_file else None,
                    financial_year_start=datetime.date(datetime.date.today().year, 4, 1)
                )

                # 3. Link User & Settings
                UserCompany.objects.create(user=user, company=company, role='OWNER')
                CompanySettings.objects.create(company=company)

                # 4. Auto-provision Default Warehouse
                Warehouse.objects.create(
                    company=company,
                    name="Main Godown",
                    address=address
                )

                # 5. Auto-provision Core Chart of Accounts (Ledger Groups)
                debtors_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Sundry Debtors", defaults={"nature": "ASSET"}
                )
                creditors_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Sundry Creditors", defaults={"nature": "LIABILITY"}
                )
                sales_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Sales Accounts", defaults={"nature": "INCOME"}
                )
                purchase_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Purchase Accounts", defaults={"nature": "EXPENSE"}
                )
                duties_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Duties & Taxes", defaults={"nature": "LIABILITY"}
                )
                bank_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Bank Accounts", defaults={"nature": "ASSET"}
                )
                cash_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Cash-in-Hand", defaults={"nature": "ASSET"}
                )

                # 6. Auto-provision Standard Sales, Purchase & Tax Ledgers
                Ledger.objects.create(company=company, group=sales_grp, name="Sales Account", ledger_type="SALES")
                Ledger.objects.create(company=company, group=purchase_grp, name="Purchase Account", ledger_type="PURCHASE")
                Ledger.objects.create(company=company, group=cash_grp, name="Cash", ledger_type="CASH")
                Ledger.objects.create(company=company, group=duties_grp, name="Output CGST", ledger_type="TAX")
                Ledger.objects.create(company=company, group=duties_grp, name="Output SGST", ledger_type="TAX")
                Ledger.objects.create(company=company, group=duties_grp, name="Output IGST", ledger_type="TAX")
                Ledger.objects.create(company=company, group=duties_grp, name="Input CGST", ledger_type="TAX")
                Ledger.objects.create(company=company, group=duties_grp, name="Input SGST", ledger_type="TAX")
                Ledger.objects.create(company=company, group=duties_grp, name="Input IGST", ledger_type="TAX")

                # 7. Generate JWT
                refresh = RefreshToken.for_user(user)

                return Response({
                    "success": True,
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "message": "Registration successful"
                }, status=201)

        except Exception as e:
            return Response({"success": False, "error": f"Registration failed: {str(e)}"}, status=400)

