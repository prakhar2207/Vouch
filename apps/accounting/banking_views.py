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
from apps.accounts.permissions import get_authorized_company

class BankStatementUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Uploads and parses a bank statement (CSV, XLSX, XLS, PDF, Image).
        Accepts multipart/form-data 'file' or JSON 'file_base64' + 'filename'.
        """
        company = get_authorized_company(request)

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

        custom_api_key = request.headers.get('X-Gemini-Key') or request.data.get('gemini_api_key')

        try:
            summary = BankStatementService.parse_statement(
                company=company,
                bank_ledger=bank_ledger,
                file_bytes=file_bytes,
                filename=filename,
                user=request.user,
                custom_api_key=custom_api_key
            )
            res_status = status.HTTP_200_OK if summary.get("is_duplicate_file") else status.HTTP_201_CREATED
            return Response(summary, status=res_status)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Statement parsing failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class BankTransactionListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)

        qs = BankTransaction.objects.filter(company=company).select_related('bank_ledger', 'matched_party', 'matched_voucher')

        # Filter by status
        st = request.query_params.get('status')
        if st:
            raw_statuses = [s.strip().upper() for s in st.split(',') if s.strip()]
            resolved_statuses = []
            for s in raw_statuses:
                if s == 'NEEDS_REVIEW':
                    resolved_statuses.extend(['MATCHED_SUGGESTED', 'NEEDS_REVIEW'])
                elif s == 'MATCHED':
                    resolved_statuses.extend(['MATCHED_AUTO', 'RECONCILED'])
                elif s == 'UNRESOLVED':
                    resolved_statuses.extend(['UNRESOLVED', 'UNPROCESSED'])
                else:
                    resolved_statuses.append(s)
            qs = qs.filter(status__in=list(set(resolved_statuses)))

        # Filter by bank ledger
        bank_ledger_id = request.query_params.get('bank_ledger_id')
        if bank_ledger_id and str(bank_ledger_id).strip().lower() not in ['null', 'undefined', 'all', 'none', '']:
            try:
                import uuid
                uuid.UUID(str(bank_ledger_id).strip())
                qs = qs.filter(bank_ledger_id=str(bank_ledger_id).strip())
            except (ValueError, TypeError, AttributeError):
                pass

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
        company = get_authorized_company(request)
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
        company = get_authorized_company(request)

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
        company = get_authorized_company(request)
        mapping = get_object_or_404(PartyMapping, id=pk, company=company)
        mapping.delete()
        return Response({"status": "SUCCESS", "message": "Learned mapping deleted."}, status=status.HTTP_200_OK)


class BankSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)

        bank_ledger_id = request.query_params.get('bank_ledger_id')
        if bank_ledger_id and str(bank_ledger_id).strip().lower() in ['null', 'undefined', 'all', 'none', '']:
            bank_ledger_id = None
        elif bank_ledger_id:
            try:
                import uuid
                uuid.UUID(str(bank_ledger_id).strip())
                bank_ledger_id = str(bank_ledger_id).strip()
            except (ValueError, TypeError, AttributeError):
                bank_ledger_id = None

        summary = BankReconciliationService.get_reconciliation_summary(company, bank_ledger_id)
        return Response(summary, status=status.HTTP_200_OK)


class BankTransactionDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        """
        Deletes an individual bank transaction from the server.
        Safely rolls back any generated reconciliation voucher.
        """
        company = get_authorized_company(request)
        tx = get_object_or_404(BankTransaction, id=pk, company=company)
        try:
            BankReconciliationService.delete_transaction(tx)
            return Response({"status": "SUCCESS", "message": "Transaction deleted successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": f"Failed to delete transaction: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class BankStatementImportListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        Lists all uploaded statements for the company, optionally filtered by bank ledger.
        """
        company = get_authorized_company(request)
        qs = BankStatementImport.objects.filter(company=company).select_related('bank_ledger', 'created_by').order_by('-created_at')

        bank_ledger_id = request.query_params.get('bank_ledger_id')
        if bank_ledger_id and str(bank_ledger_id).strip().lower() not in ['null', 'undefined', 'all', 'none', '']:
            try:
                import uuid
                uuid.UUID(str(bank_ledger_id).strip())
                qs = qs.filter(bank_ledger_id=str(bank_ledger_id).strip())
            except (ValueError, TypeError, AttributeError):
                pass

        data = []
        for imp in qs[:50]:
            data.append({
                "id": str(imp.id),
                "source_file_name": imp.source_file_name,
                "file_format": imp.file_format,
                "status": imp.status,
                "total_rows": imp.total_rows,
                "successful_rows": imp.successful_rows,
                "failed_rows": imp.failed_rows,
                "opening_balance": str(imp.opening_balance) if imp.opening_balance is not None else None,
                "closing_balance": str(imp.closing_balance) if imp.closing_balance is not None else None,
                "balance_chain_valid": imp.balance_chain_valid,
                "bank_ledger": {
                    "id": str(imp.bank_ledger.id),
                    "name": imp.bank_ledger.name
                },
                "created_at": imp.created_at.isoformat()
            })
        return Response(data, status=status.HTTP_200_OK)


class BankStatementImportDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        """
        Deletes a statement import and all associated bank transactions from the server.
        """
        company = get_authorized_company(request)
        statement_import = get_object_or_404(BankStatementImport, id=pk, company=company)
        file_name = statement_import.source_file_name
        try:
            deleted_count = BankReconciliationService.delete_statement_import(statement_import)
            return Response({
                "status": "SUCCESS",
                "message": f"Statement '{file_name}' and {deleted_count} imported transactions were deleted from the server."
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": f"Failed to delete statement: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
