import io
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from apps.companies.models import Company, UserCompany
from apps.accounting.services.universal_import_service import UniversalImportService


class UniversalImportPreviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company_id = request.data.get("company_id") or request.headers.get("X-Company-ID")
        if not company_id:
            user_company = UserCompany.objects.filter(user=request.user).first()
            if not user_company:
                return Response({"error": "No associated company found."}, status=status.HTTP_400_BAD_REQUEST)
            company = user_company.company
        else:
            company = get_object_or_404(Company, id=company_id)
            if not UserCompany.objects.filter(user=request.user, company=company).exists():
                return Response({"error": "Unauthorized access to company."}, status=status.HTTP_403_FORBIDDEN)

        # Check if file uploaded
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"error": "Please select a file to import (.xlsx, .csv, or Tally .xml)."}, status=status.HTTP_400_BAD_REQUEST)

        filename = uploaded_file.name
        try:
            file_content = uploaded_file.read()
            parsed_info = UniversalImportService.detect_and_parse_file(file_content, filename)
            if "error" in parsed_info:
                return Response({"error": parsed_info["error"]}, status=status.HTTP_400_BAD_REQUEST)

            preview_data = UniversalImportService.generate_preview(parsed_info, company)
            
            # Remove giant raw dataset from preview response to keep JSON payload lightweight
            raw_data = parsed_info.pop("data", None)

            return Response({
                "success": True,
                "parsed_info": parsed_info,
                "preview": preview_data,
                "cached_token": True
            })
        except Exception as e:
            return Response({"error": f"Failed to process file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UniversalImportExecuteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company_id = request.data.get("company_id") or request.headers.get("X-Company-ID")
        if not company_id:
            user_company = UserCompany.objects.filter(user=request.user).first()
            if not user_company:
                return Response({"error": "No associated company found."}, status=status.HTTP_400_BAD_REQUEST)
            company = user_company.company
        else:
            company = get_object_or_404(Company, id=company_id)
            if not UserCompany.objects.filter(user=request.user, company=company).exists():
                return Response({"error": "Unauthorized access to company."}, status=status.HTTP_403_FORBIDDEN)

        uploaded_file = request.FILES.get("file")
        parsed_payload = request.data.get("parsed_payload")
        custom_mappings = request.data.get("custom_mappings")
        duplicate_strategy = request.data.get("duplicate_strategy", "MERGE")

        try:
            if uploaded_file:
                file_content = uploaded_file.read()
                parsed_info = UniversalImportService.detect_and_parse_file(file_content, uploaded_file.name)
            elif parsed_payload:
                parsed_info = parsed_payload
            else:
                return Response({"error": "Missing import file or parsed data payload."}, status=status.HTTP_400_BAD_REQUEST)

            if "error" in parsed_info:
                return Response({"error": parsed_info["error"]}, status=status.HTTP_400_BAD_REQUEST)

            res = UniversalImportService.execute_import(
                parsed_info=parsed_info,
                company=company,
                user=request.user,
                custom_mappings=custom_mappings,
                duplicate_strategy=duplicate_strategy
            )

            return Response(res, status=status.HTTP_200_OK if res.get("success") else status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Import execution failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UniversalImportTemplateAPIView(APIView):
    """
    Generates beautifully styled, standardized Excel templates with validation instructions.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        template_type = request.query_params.get("type", "parties").lower()

        wb = openpyxl.Workbook()
        ws = wb.active

        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1")
        )

        if template_type == "parties":
            ws.title = "Parties_Import_Template"
            headers = ["Party Name*", "Phone", "Email", "GSTIN", "PAN", "Address", "State", "Opening Balance", "Balance Type (Dr/Cr)"]
            sample_rows = [
                ["Apex Industrial Supplies", "9876543210", "accounts@apex.in", "27AAAAA0000A1Z5", "AAAAA0000A", "Plot 12, MIDC Industrial Area, Pune", "Maharashtra", "150000.00", "Dr (Receivable)"],
                ["Bharat Rubber Works", "9822012345", "billing@bharatrubber.com", "27BBBBB1111B1Z2", "BBBBB1111B", "Survey 45, GIDC Estate, Vapi", "Gujarat", "75000.00", "Cr (Payable)"],
                ["Om Hardware Stores", "9819000000", "", "", "", "Shop 4, Station Road, Mumbai", "Maharashtra", "25000.00", "Dr (Receivable)"]
            ]
        elif template_type == "inventory":
            ws.title = "Stock_Items_Template"
            headers = ["Item Name*", "Item Code / SKU", "Category", "Unit", "HSN Code", "Tax Rate (GST %)", "Sale Price", "Purchase Price", "Opening Stock Qty"]
            sample_rows = [
                ["V-Belt C 89 Industrial", "SKU-VB-C89", "Power Transmission Belts", "PCS", "40103999", "18.0", "450.00", "320.00", "120"],
                ["Timing Belt 800-8M-30", "SKU-TB-800", "Industrial Timing Belts", "PCS", "40103999", "18.0", "1250.00", "890.00", "45"],
                ["Conveyor Belt 3-Ply 600mm", "SKU-CB-600", "Heavy Duty Conveyors", "MTR", "40101290", "18.0", "850.00", "600.00", "300"]
            ]
        else:
            ws.title = "Opening_Balances_Template"
            headers = ["Ledger Name*", "Parent Group*", "Opening Debit Amount (₹)", "Opening Credit Amount (₹)"]
            sample_rows = [
                ["HDFC Current Account", "Bank Accounts", "450000.00", "0.00"],
                ["Cash-in-Hand", "Cash-in-Hand", "35000.00", "0.00"],
                ["Capital Account - Partner A", "Capital Account", "0.00", "485000.00"]
            ]

        # Write headers
        ws.append(headers)
        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = 24

        # Write sample data
        for r in sample_rows:
            ws.append(r)
            row_idx = ws.max_row
            for col_num in range(1, len(r) + 1):
                c = ws.cell(row=row_idx, column=col_num)
                c.border = border
                c.alignment = Alignment(vertical="center")

        out = io.BytesIO()
        wb.save(out)
        out.seek(0)

        response = HttpResponse(out.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="Vouch_{template_type.title()}_Template.xlsx"'
        return response
