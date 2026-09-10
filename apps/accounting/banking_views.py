import base64
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import BankStatementImport, BankTransaction, PartyMapping
from apps.accounting.services.bank_statement_service import BankStatementService
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService

class BankStatementUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Uploads and parses a bank statement (CSV, XLSX, XLS, PDF, Image).
        Accepts multipart/form-data 'file' or JSON 'file_base64' + 'filename'.
        """
        company_id = request.headers.get('X-Company-ID') or request.data.get('company_id')
        if not company_id:
            return Response({"error": "X-Company-ID header is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_object_or_404(Company, id=company_id)

        bank_ledger_id = request.data.get('bank_ledger_id')
        if not bank_ledger_id:
            return Response({"error": "bank_ledger_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        bank_ledger = get_object_or_404(Ledger, id=bank_ledger_id, company=company)

        file_bytes = None
        filename = "statement.csv"

        if 'file' in request.FILES:
            uploaded_file = request.FILES['file']
            file_bytes = uploaded_file.read()
            filename = uploaded_file.name
        elif 'file_base64' in request.data:
            b64_str = request.data['file_base64']
            if ',' in b64_str:
                b64_str = b64_str.split(',', 1)[1]
            file_bytes = base64.b64decode(b64_str)
            filename = request.data.get('filename', 'statement.csv')
        else:
            return Response({"error": "No file uploaded. Provide 'file' multipart or 'file_base64'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            summary = BankStatementService.parse_statement(
                company=company,
                bank_ledger=bank_ledger,
                file_bytes=file_bytes,
                filename=filename,
                user=request.user
            )
            return Response(summary, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Statement parsing failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BankTransactionListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company_id = request.headers.get('X-Company-ID') or request.query_params.get('company_id')
        if not company_id:
            return Response({"error": "X-Company-ID header is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_object_or_404(Company, id=company_id)

        qs = BankTransaction.objects.filter(company=company).select_related('bank_ledger', 'matched_party', 'matched_voucher')

        # Filter by status
        st = request.query_params.get('status')
        if st:
            statuses = [s.strip().upper() for s in st.split(',')]
            qs = qs.filter(status__in=statuses)

        # Filter by bank ledger
        bank_ledger_id = request.query_params.get('bank_ledger_id')
        if bank_ledger_id:
            qs = qs.filter(bank_ledger_id=bank_ledger_id)

        # Search query
        search = request.query_params.get('search')
        if search:
            qs = qs.filter(normalized_narration__icontains=search.strip().upper())

        # Pagination
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(100, max(1, int(request.query_params.get('page_size', 50))))
        except ValueError:
            page = 1
            page_size = 50

        total_count = qs.count()
        offset = (page - 1) * page_size
        results = qs[offset:offset + page_size]

        data = []
        for tx in results:
            data.append({
                "id": str(tx.id),
                "transaction_date": tx.transaction_date.isoformat(),
                "value_date": tx.value_date.isoformat() if tx.value_date else None,
                "description": tx.description,
                "normalized_narration": tx.normalized_narration,
                "reference_number": tx.reference_number,
                "debit_amount": str(tx.debit_amount),
                "credit_amount": str(tx.credit_amount),
                "balance": str(tx.balance) if tx.balance is not None else None,
                "status": tx.status,
                "bank_ledger": {
                    "id": str(tx.bank_ledger.id),
                    "name": tx.bank_ledger.name
                },
                "matched_party": {
                    "id": str(tx.matched_party.id),
                    "name": tx.matched_party.name,
                    "ledger_type": tx.matched_party.ledger_type
                } if tx.matched_party else None,
                "matched_voucher": {
                    "id": str(tx.matched_voucher.id),
                    "voucher_number": tx.matched_voucher.voucher_number
                } if tx.matched_voucher else None,
                "match_confidence": tx.match_confidence,
                "match_notes": tx.match_notes
            })

        return Response({
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "results": data
        }, status=status.HTTP_200_OK)


class BankTransactionResolveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        """
        Executes an action to reconcile/resolve a bank transaction.
        Action types: MATCH_PARTY, RECORD_PAYMENT, RECORD_EXPENSE, RECORD_TRANSFER, OWNER_DRAWING, IGNORE.
        """
        company_id = request.headers.get('X-Company-ID') or request.data.get('company_id')
        if not company_id:
            return Response({"error": "X-Company-ID header is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_object_or_404(Company, id=company_id)

        tx = get_object_or_404(BankTransaction, id=pk, company=company)
        action = request.data.get('action')
        payload = request.data.get('payload', {})

        if not action:
            return Response({"error": "'action' is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            res = BankReconciliationService.resolve_transaction(
                bank_tx=tx,
                action_type=action,
                payload=payload,
                user=request.user
            )
            return Response(res, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Resolution failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PartyMappingListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company_id = request.headers.get('X-Company-ID') or request.query_params.get('company_id')
        if not company_id:
            return Response({"error": "X-Company-ID header is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_object_or_404(Company, id=company_id)

        mappings = PartyMapping.objects.filter(company=company).select_related('party').order_by('-usage_count', '-last_used')
        data = [
            {
                "id": str(m.id),
                "pattern": m.pattern,
                "normalized_pattern": m.normalized_pattern,
                "mapping_type": m.mapping_type,
                "party": {
                    "id": str(m.party.id),
                    "name": m.party.name,
                    "ledger_type": m.party.ledger_type
                },
                "confirmed_by_user": m.confirmed_by_user,
                "confidence": m.confidence,
                "usage_count": m.usage_count,
                "last_used": m.last_used.isoformat()
            } for m in mappings
        ]
        return Response(data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        company_id = request.headers.get('X-Company-ID') or request.query_params.get('company_id')
        company = get_object_or_404(Company, id=company_id)
        mapping = get_object_or_404(PartyMapping, id=pk, company=company)
        mapping.delete()
        return Response({"status": "SUCCESS", "message": "Learned mapping deleted."}, status=status.HTTP_200_OK)


class BankSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company_id = request.headers.get('X-Company-ID') or request.query_params.get('company_id')
        if not company_id:
            return Response({"error": "X-Company-ID header is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_object_or_404(Company, id=company_id)

        bank_ledger_id = request.query_params.get('bank_ledger_id')
        summary = BankReconciliationService.get_reconciliation_summary(company, bank_ledger_id)
        return Response(summary, status=status.HTTP_200_OK)
