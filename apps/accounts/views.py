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
    permission_classes = [] # Allow any
    
    def post(self, request):
        from .models import User
        from apps.companies.models import Company, UserCompany, CompanySettings
        from rest_framework_simplejwt.tokens import RefreshToken
        
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not email or not password:
            return Response({"success": False, "error": "Email and password required"}, status=400)
            
        if User.objects.filter(email=email).exists():
            return Response({"success": False, "error": "Email already exists"}, status=400)
            
        # Create user
        user = User.objects.create_user(email=email, password=password)
        
        # Create company
        company = Company.objects.create(
            name=request.data.get('name', 'My Firm'),
            legal_name=request.data.get('name', 'My Firm'),
            gstin=request.data.get('gstin', ''),
            phone=request.data.get('phone', ''),
            email=request.data.get('company_email', email),
            address=request.data.get('address', ''),
            state_code=request.data.get('state_code', ''),
            financial_year_start=request.data.get('financial_year_start', '2024-04-01')
        )
        
        # Map user
        UserCompany.objects.create(user=user, company=company, role='OWNER')
        CompanySettings.objects.create(company=company)
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            "success": True,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "message": "Registration successful"
        })
