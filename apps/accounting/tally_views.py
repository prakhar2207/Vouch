from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from datetime import datetime

from apps.companies.models import Company, UserCompany
from apps.accounting.services.tally_export import TallyXMLExporter


class TallyExportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company_id = request.query_params.get('company_id')
        if not company_id:
            user_company = UserCompany.objects.filter(user=request.user).first()
            if not user_company:
                return Response({"error": "No associated company found."}, status=status.HTTP_400_BAD_REQUEST)
            company = user_company.company
        else:
            company = get_object_or_404(Company, id=company_id)
            if not UserCompany.objects.filter(user=request.user, company=company).exists():
                return Response({"error": "Unauthorized access to this company data."}, status=status.HTTP_403_FORBIDDEN)

        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        export_type = request.query_params.get('type', 'all').lower()  # 'all', 'masters', 'vouchers'
        
        # Voucher types filter (e.g. "SALES,PURCHASE,PAYMENT")
        vch_types_raw = request.query_params.get('voucher_types')
        voucher_types = [v.strip().upper() for v in vch_types_raw.split(',')] if vch_types_raw else None

        try:
            xml_content = TallyXMLExporter.generate_xml(
                company=company,
                from_date=from_date,
                to_date=to_date,
                export_type=export_type,
                voucher_types=voucher_types
            )
        except Exception as e:
            return Response({"error": f"Failed to generate Tally XML: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        filename = f"Tally_Export_{company.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"

        response = HttpResponse(xml_content, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
