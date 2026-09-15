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


from decimal import Decimal
from django.db.models import Q
import json
import ast

class BankTransactionListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)

        qs = BankTransaction.objects.filter(company=company).select_related(
            'bank_ledger', 'matched_party', 'matched_voucher'
        ).only(
            'id', 'transaction_date', 'value_date', 'description', 'normalized_narration',
            'reference_number', 'debit_amount', 'credit_amount', 'balance', 'status',
            'is_excluded', 'exclusion_reason', 'excluded_at',
            'match_confidence', 'match_notes',
            'bank_ledger__id', 'bank_ledger__name',
            'matched_party__id', 'matched_party__name', 'matched_party__ledger_type',
            'matched_voucher__id', 'matched_voucher__voucher_number',
        )

        # Status filter
        st = request.query_params.get('status')
        raw_statuses = []
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

        # Excluded filter
        is_excluded_param = request.query_params.get('is_excluded')
        if is_excluded_param is not None:
            is_exc = is_excluded_param.strip().lower() in ['true', '1']
            qs = qs.filter(is_excluded=is_exc)
        elif 'EXCLUDED' in raw_statuses:
            qs = qs.filter(is_excluded=True)
        else:
            qs = qs.filter(is_excluded=False)

        # Direction filter (Money IN vs Money OUT)
        direction = request.query_params.get('direction', '').strip().upper()
        if direction in ['IN', 'CREDIT']:
            qs = qs.filter(credit_amount__gt=Decimal('0.00'))
        elif direction in ['OUT', 'DEBIT']:
            qs = qs.filter(debit_amount__gt=Decimal('0.00'))

        # Date range filters
        start_date = request.query_params.get('start_date')
        if start_date:
            qs = qs.filter(transaction_date__gte=start_date)
        end_date = request.query_params.get('end_date')
        if end_date:
            qs = qs.filter(transaction_date__lte=end_date)

        # Bank ledger filter
        bank_ledger_id = request.query_params.get('bank_ledger_id')
        if bank_ledger_id and str(bank_ledger_id).strip().lower() not in ['null', 'undefined', 'all', 'none', '']:
            try:
                import uuid
                uuid.UUID(str(bank_ledger_id).strip())
                qs = qs.filter(bank_ledger_id=str(bank_ledger_id).strip())
            except (ValueError, TypeError, AttributeError):
                pass

        # Multi-field search (narration, description, reference, party name, or amount)
        search = request.query_params.get('search')
        if search and search.strip():
            s = search.strip()
            search_filter = (
                Q(normalized_narration__icontains=s) |
                Q(description__icontains=s) |
                Q(reference_number__icontains=s) |
                Q(matched_party__name__icontains=s)
            )
            # Check if search is numeric amount
            clean_amt = s.replace(',', '').replace('₹', '').replace(' ', '')
            try:
                amt_val = Decimal(clean_amt)
                search_filter |= Q(debit_amount=amt_val) | Q(credit_amount=amt_val)
            except Exception:
                pass
            qs = qs.filter(search_filter)

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
            # Clean match_notes to guarantee a valid dict
            raw_notes = tx.match_notes
            if isinstance(raw_notes, str):
                try:
                    notes = json.loads(raw_notes)
                except Exception:
                    try:
                        notes = ast.literal_eval(raw_notes)
                    except Exception:
                        notes = {"notes": raw_notes}
            elif isinstance(raw_notes, dict):
                notes = raw_notes
            else:
                notes = {}

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
                "is_excluded": tx.is_excluded,
                "exclusion_reason": tx.exclusion_reason,
                "excluded_at": tx.excluded_at.isoformat() if tx.excluded_at else None,
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
                "match_notes": notes
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
        Action types:
        - MATCH_PARTY / RECORD_PAYMENT / CONFIRM_RECEIPT / CONFIRM_PAYMENT
        - CONFIRM_CUSTOMER_RECEIPT / CONFIRM_SUPPLIER_PAYMENT
        - CONFIRM_SUPPLIER_REFUND / CONFIRM_CUSTOMER_REFUND
        - RECORD_EXPENSE / RECORD_TRANSFER / OWNER_DRAWING
        - IGNORE / EXCLUDE
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

    def post(self, request, pk, *args, **kwargs):
        """
        Excludes an individual bank transaction with an audit reason.
        If a voucher was generated, canonically reverses it.
        """
        company = get_authorized_company(request)
        tx = get_object_or_404(BankTransaction, id=pk, company=company)
        reason = request.data.get('reason', 'User requested transaction exclusion')
        try:
            res = BankReconciliationService.exclude_transaction(tx, reason=reason, user=request.user)
            return Response(res, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": f"Failed to exclude transaction: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, *args, **kwargs):
        """
        Safe non-destructive exclusion handler for DELETE requests.
        """
        company = get_authorized_company(request)
        tx = get_object_or_404(BankTransaction, id=pk, company=company)
        reason = request.query_params.get('reason') or request.data.get('reason', 'User requested transaction exclusion')
        try:
            res = BankReconciliationService.exclude_transaction(tx, reason=reason, user=request.user)
            return Response(res, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": f"Failed to exclude transaction: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class BankStatementImportListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        Lists uploaded statements for the company, excluding voided/excluded statements unless requested.
        """
        company = get_authorized_company(request)
        qs = BankStatementImport.objects.filter(company=company).select_related('bank_ledger', 'created_by').order_by('-created_at')

        include_excluded = request.query_params.get('include_excluded', 'false').lower() in ['true', '1']
        if not include_excluded:
            qs = qs.filter(is_excluded=False)

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
                "is_excluded": imp.is_excluded,
                "exclusion_reason": imp.exclusion_reason,
                "statement_start_date": imp.statement_start_date.isoformat() if imp.statement_start_date else None,
                "statement_end_date": imp.statement_end_date.isoformat() if imp.statement_end_date else None,
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

    def post(self, request, pk, *args, **kwargs):
        """
        Excludes an entire statement import with audit reason, reversing any generated vouchers.
        """
        company = get_authorized_company(request)
        statement_import = get_object_or_404(BankStatementImport, id=pk, company=company)
        reason = request.data.get('reason', 'User requested statement exclusion')
        try:
            count = BankReconciliationService.exclude_statement_import(statement_import, reason=reason, user=request.user)
            return Response({
                "status": "SUCCESS",
                "message": f"Statement '{statement_import.source_file_name}' and {count} transactions excluded.",
                "excluded_count": count
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": f"Failed to exclude statement: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, *args, **kwargs):
        """
        Safe non-destructive exclusion handler for DELETE requests.
        """
        company = get_authorized_company(request)
        statement_import = get_object_or_404(BankStatementImport, id=pk, company=company)
        reason = request.query_params.get('reason') or request.data.get('reason', 'User requested statement exclusion')
        try:
            count = BankReconciliationService.exclude_statement_import(statement_import, reason=reason, user=request.user)
            return Response({
                "status": "SUCCESS",
                "message": f"Statement '{statement_import.source_file_name}' and {count} transactions excluded.",
                "excluded_count": count
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": f"Failed to exclude statement: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class BankTransactionToggleDirectionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        """
        Allows the user to flip or explicitly set transaction direction between
        Withdrawal (Debit) and Deposit (Credit) if AI or statement parser classified it incorrectly.
        Re-evaluates party/expense matching heuristics accordingly.
        """
        company = get_authorized_company(request)
        tx = get_object_or_404(BankTransaction, id=pk, company=company)

        if tx.status in ['MATCHED', 'RECONCILED']:
            return Response(
                {"error": "Cannot flip direction of an already reconciled transaction. Exclude or unmatch it first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        requested_dir = request.data.get('direction')
        old_debit = tx.debit_amount
        old_credit = tx.credit_amount

        if requested_dir == 'DEBIT':
            if tx.debit_amount > Decimal('0.00') and tx.credit_amount == Decimal('0.00'):
                pass  # Already debit
            else:
                amt = tx.credit_amount if tx.credit_amount > Decimal('0.00') else tx.debit_amount
                tx.debit_amount = amt
                tx.credit_amount = Decimal('0.00')
        elif requested_dir == 'CREDIT':
            if tx.credit_amount > Decimal('0.00') and tx.debit_amount == Decimal('0.00'):
                pass  # Already credit
            else:
                amt = tx.debit_amount if tx.debit_amount > Decimal('0.00') else tx.credit_amount
                tx.credit_amount = amt
                tx.debit_amount = Decimal('0.00')
        else:
            # Simple toggle
            if tx.credit_amount > Decimal('0.00'):
                tx.debit_amount = tx.credit_amount
                tx.credit_amount = Decimal('0.00')
            else:
                tx.credit_amount = tx.debit_amount
                tx.debit_amount = Decimal('0.00')

        # Re-evaluate heuristics with the new direction
        from apps.accounting.services.party_intelligence_service import PartyIntelligenceService
        match_res = PartyIntelligenceService.match_transaction(
            company=company,
            narration=tx.normalized_narration or tx.description,
            debit_amount=tx.debit_amount,
            credit_amount=tx.credit_amount
        )
        tx.matched_party = match_res.get('matched_party')
        tx.matched_invoice = match_res.get('matched_invoice')
        tx.match_confidence = match_res.get('confidence', 0.0)
        notes = tx.match_notes if isinstance(tx.match_notes, dict) else {}
        notes['signals'] = match_res.get('signals', [])
        notes['suggested_matches'] = match_res.get('suggested_matches', [])
        notes['is_bank_expense'] = match_res.get('is_bank_expense', False)
        tx.match_notes = notes

        if tx.matched_party and tx.status == 'UNRESOLVED':
            tx.status = 'NEEDS_REVIEW'

        tx.save(update_fields=['debit_amount', 'credit_amount', 'matched_party', 'matched_invoice', 'match_confidence', 'match_notes', 'status', 'updated_at'])

        # Audit log entry
        from apps.audit.models import AuditLog
        new_direction = "DEBIT" if tx.debit_amount > Decimal('0.00') else "CREDIT"
        AuditLog.objects.create(
            company=company,
            user=request.user if request.user.is_authenticated else None,
            action='UPDATE',
            model_name='BankTransaction',
            record_id=str(tx.id),
            changes={
                "action": "TOGGLE_DIRECTION",
                "old_debit": str(old_debit),
                "old_credit": str(old_credit),
                "new_debit": str(tx.debit_amount),
                "new_credit": str(tx.credit_amount),
                "direction": new_direction,
                "narration": tx.description
            }
        )

        direction_label = "Withdrawal (Debit)" if new_direction == "DEBIT" else "Deposit (Credit)"
        confidence_val = int(tx.match_confidence * 100) if tx.match_confidence <= 1.0 else int(tx.match_confidence)

        return Response({
            "status": "SUCCESS",
            "message": f"Switched to {direction_label}",
            "transaction": {
                "id": str(tx.id),
                "transaction_date": str(tx.transaction_date),
                "value_date": str(tx.value_date) if tx.value_date else None,
                "description": tx.description,
                "normalized_narration": tx.normalized_narration,
                "reference_number": tx.reference_number,
                "debit_amount": str(tx.debit_amount),
                "credit_amount": str(tx.credit_amount),
                "balance": str(tx.balance) if tx.balance else None,
                "status": tx.status,
                "is_excluded": tx.is_excluded,
                "exclusion_reason": tx.exclusion_reason,
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
                "match_confidence": confidence_val,
                "match_notes": tx.match_notes
            }
        }, status=status.HTTP_200_OK)
