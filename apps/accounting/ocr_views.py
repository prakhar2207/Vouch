from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .services.ocr_service import InvoiceOCRService

class OCRExtractAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Accepts:
        {
            "file_base64": "data:image/png;base64,...",
            "mime_type": "image/png"
        }
        """
        file_base64 = request.data.get('file_base64')
        mime_type = request.data.get('mime_type', 'image/png')

        if not file_base64:
            return Response(
                {"success": False, "error": "file_base64 is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            extracted_data = InvoiceOCRService.extract_from_base64(file_base64, mime_type)
            return Response({
                "success": True,
                "data": extracted_data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
