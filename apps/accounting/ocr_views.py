import base64
import uuid
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.core.exceptions import ValidationError
from django.core.cache import cache

from .services.ocr_service import InvoiceOCRService
from apps.accounts.permissions import get_authorized_company, IsCompanyMember

logger = logging.getLogger(__name__)

MAX_OCR_BASE64_LENGTH = 20 * 1024 * 1024  # 20 MB base64 string
MAX_OCR_DECODED_BYTES = 15 * 1024 * 1024  # 15 MB binary payload
ALLOWED_OCR_MIME_TYPES = {
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp',
    'application/pdf',
}

class OCRExtractAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def post(self, request):
        """
        Accepts:
        {
            "file_base64": "data:image/png;base64,...",
            "mime_type": "image/png",
            "scan_mode": "auto" | "fast" | "deep"
        }
        Strictly enforces multi-tenant authorization, file signature verification,
        size ceilings, rate limiting, and sanitized error reporting.
        """
        # 1. VSA-06 / SEC-02: Authorize company membership BEFORE either sync or async OCR runs
        company = get_authorized_company(request)

        file_base64 = request.data.get('file_base64')
        raw_mime = request.data.get('mime_type', 'image/png')
        mime_type = str(raw_mime or 'image/png').strip().lower()

        if not file_base64 or not isinstance(file_base64, str):
            return Response(
                {"success": False, "error": "file_base64 string is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Enforce base64 string size ceiling
        if len(file_base64) > MAX_OCR_BASE64_LENGTH:
            return Response(
                {"success": False, "error": "OCR document payload exceeds the 15MB size limit."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Validate allowed MIME type
        if mime_type not in ALLOWED_OCR_MIME_TYPES:
            return Response(
                {"success": False, "error": f"Unsupported MIME type '{mime_type}'. Allowed types: JPEG, PNG, WebP, and PDF."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Decode and validate base64 integrity and magic bytes
        clean_b64 = file_base64
        if ',' in clean_b64:
            clean_b64 = clean_b64.split(',', 1)[1]

        try:
            raw_bytes = base64.b64decode(clean_b64)
        except Exception:
            return Response(
                {"success": False, "error": "Invalid base64 encoding provided."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(raw_bytes) > MAX_OCR_DECODED_BYTES:
            return Response(
                {"success": False, "error": f"Decoded document size ({len(raw_bytes) / (1024*1024):.1f}MB) exceeds 15MB limit."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify magic bytes / file signature
        if mime_type == 'application/pdf' and not raw_bytes.startswith(b'%PDF'):
            return Response({"success": False, "error": "File signature mismatch: expected valid PDF document."}, status=status.HTTP_400_BAD_REQUEST)
        elif mime_type in ('image/png',) and not raw_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            return Response({"success": False, "error": "File signature mismatch: expected valid PNG image."}, status=status.HTTP_400_BAD_REQUEST)
        elif mime_type in ('image/jpeg', 'image/jpg') and not raw_bytes.startswith(b'\xff\xd8\xff'):
            return Response({"success": False, "error": "File signature mismatch: expected valid JPEG image."}, status=status.HTTP_400_BAD_REQUEST)
        elif mime_type == 'image/webp' and not (raw_bytes[:4] == b'RIFF' and raw_bytes[8:12] == b'WEBP'):
            return Response({"success": False, "error": "File signature mismatch: expected valid WebP image."}, status=status.HTTP_400_BAD_REQUEST)

        # 5. Rate limiting per (company, user): max 30 OCR extractions per minute
        ocr_rate_key = f"ocr_rate:{company.id}:{request.user.id}"
        current_reqs = cache.get(ocr_rate_key, 0)
        if current_reqs >= 30:
            return Response(
                {"success": False, "error": "OCR rate limit exceeded. Please wait a minute before submitting additional documents."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        cache.set(ocr_rate_key, current_reqs + 1, timeout=60)

        scan_mode = request.data.get('scan_mode', 'auto')
        is_async = (request.data.get('async') is True or request.query_params.get('async', '').lower() == 'true')

        if is_async:
            from .tasks import ocr_invoice_extract_task
            task = ocr_invoice_extract_task.delay(
                file_base64,
                mime_type=mime_type,
                scan_mode=scan_mode,
                company_id=str(company.id),
                user_id=str(request.user.id)
            )
            return Response({
                "success": True,
                "async": True,
                "task_id": task.id,
                "message": "OCR scanning task dispatched to background worker."
            }, status=status.HTTP_202_ACCEPTED)

        buyer_state_code = company.state_code or (company.gstin[:2] if company.gstin else "")

        try:
            extracted_data = InvoiceOCRService.extract_from_base64(
                file_base64, 
                mime_type, 
                scan_mode=scan_mode,
                buyer_state_code=buyer_state_code
            )
            return Response({
                "success": True,
                "data": extracted_data
            }, status=status.HTTP_200_OK)
        except (ValidationError, DRFValidationError) as e:
            msg = e.message if hasattr(e, 'message') else (e.detail if hasattr(e, 'detail') else str(e))
            return Response({"success": False, "error": str(msg)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # VSA-09 / SEC-05: Return generic error with correlation ID, logging sanitized diagnostic server-side
            correlation_id = str(uuid.uuid4())[:8]
            logger.exception("OCR extraction failed [ref=%s]: %s", correlation_id, e)
            return Response(
                {
                    "success": False,
                    "error": "An internal error occurred while processing document OCR.",
                    "correlation_id": correlation_id
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
