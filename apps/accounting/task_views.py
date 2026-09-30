import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from celery.result import AsyncResult

logger = logging.getLogger(__name__)

class TaskStatusAPIView(APIView):
    """
    Universal task status checking endpoint for background Celery workers.
    Allows frontend clients to poll long-running asynchronous operations:
    - AI OCR Bill Extraction
    - Bulk Balance Rebuild
    - Year-End Closing & Balance Roll-Forward
    - Database Disaster Recovery Backups
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        res = AsyncResult(task_id)
        response_data = {
            "task_id": task_id,
            "status": res.status,
            "ready": res.ready(),
            "successful": res.successful(),
        }

        if res.ready():
            if res.successful():
                # Check if result is a dictionary or string
                val = res.result
                response_data["result"] = val
            else:
                response_data["error"] = str(res.result)
        else:
            response_data["info"] = str(res.info) if res.info else None

        return Response({"success": True, "data": response_data}, status=status.HTTP_200_OK)
