import datetime
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import LedgerEntry
from .services.period_service import PeriodBalanceService
from .services.split_company_service import SplitCompanyService

class PeriodLedgerStatementAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ledger_id):
        """
        Tally-style continuous period ledger statement:
        Opening Balance evaluated on-the-fly for any [from_date, to_date].
        """
        company = Company.objects.filter(users__user=request.user).first()
        if not company:
            return Response({"success": False, "error": "Company not found"}, status=404)

        ledger = Ledger.objects.filter(id=ledger_id, company=company).first()
        if not ledger:
            return Response({"success": False, "error": "Ledger not found"}, status=404)

        from_date_str = request.query_params.get('from_date') or request.query_params.get('start_date')
        to_date_str = request.query_params.get('to_date') or request.query_params.get('end_date')

        d_from = PeriodBalanceService.parse_date(from_date_str) or datetime.date(datetime.date.today().year, 4, 1)
        d_to = PeriodBalanceService.parse_date(to_date_str) or datetime.date(datetime.date.today().year + 1, 3, 31)

        bal_info = PeriodBalanceService.calculate_ledger_period_balance(ledger, d_from, d_to)
        op_bal = Decimal(bal_info['opening_balance'])
        op_type = bal_info['opening_type']

        # Line items within period
        entries_qs = LedgerEntry.objects.filter(
            ledger=ledger,
            voucher__company=company,
            voucher__voucher_date__gte=d_from,
            voucher__voucher_date__lte=d_to,
            voucher__status='POSTED'
        ).select_related('voucher').order_by('voucher__voucher_date', 'created_at')

        running = (op_bal if op_type == 'DR' else -op_bal)
        entries_list = []

        for e in entries_qs:
            dr = e.debit_amount
            cr = e.credit_amount
            running += (dr - cr)

            entries_list.append({
                "id": str(e.id),
                "date": e.voucher.voucher_date.strftime('%Y-%m-%d'),
                "voucher_number": e.voucher.voucher_number,
                "voucher_type": e.voucher.voucher_type,
                "narration": e.narration or e.voucher.narration or "",
                "debit": str(dr),
                "credit": str(cr),
                "running_balance": str(abs(running)),
                "running_type": "DR" if running >= 0 else "CR",
            })

        return Response({
            "success": True,
            "data": {
                "ledger_id": str(ledger.id),
                "ledger_name": ledger.name,
                "group_name": ledger.group.name if ledger.group else "",
                "group_nature": ledger.group.nature if ledger.group else "ASSET",
                "from_date": d_from.strftime('%Y-%m-%d'),
                "to_date": d_to.strftime('%Y-%m-%d'),
                "opening_balance": str(op_bal),
                "opening_type": op_type,
                "period_debit": bal_info['period_debit'],
                "period_credit": bal_info['period_credit'],
                "closing_balance": bal_info['closing_balance'],
                "closing_type": bal_info['closing_type'],
                "entries": entries_list
            }
        })


class PeriodTrialBalanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company_id = request.query_params.get('company_id')
        if not company_id:
            company = Company.objects.filter(users__user=request.user).first()
        else:
            company = Company.objects.filter(id=company_id, users__user=request.user).first()

        if not company:
            return Response({"success": False, "error": "Company not found"}, status=404)

        from_date = request.query_params.get('from_date') or request.query_params.get('start_date')
        to_date = request.query_params.get('to_date') or request.query_params.get('end_date')

        d_from = PeriodBalanceService.parse_date(from_date) or datetime.date(datetime.date.today().year, 4, 1)
        d_to = PeriodBalanceService.parse_date(to_date) or datetime.date(datetime.date.today().year + 1, 3, 31)

        data = PeriodBalanceService.get_period_trial_balance(company, d_from, d_to)
        return Response({"success": True, "data": data})


class SplitCompanyAuditAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = Company.objects.filter(users__user=request.user).first()
        if not company:
            return Response({"success": False, "error": "Company not found"}, status=404)

        split_date = request.query_params.get('split_date')
        if not split_date:
            # Default to upcoming April 1st
            today = datetime.date.today()
            split_year = today.year + 1 if today.month >= 4 else today.year
            split_date = datetime.date(split_year, 4, 1)

        try:
            audit = SplitCompanyService.pre_split_audit(str(company.id), split_date)
            return Response({"success": True, "data": audit})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class SplitCompanyExecuteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company = Company.objects.filter(users__user=request.user).first()
        if not company:
            return Response({"success": False, "error": "Company not found"}, status=404)

        split_date = request.data.get('split_date')
        if not split_date:
            return Response({"success": False, "error": "split_date is required (YYYY-MM-DD)."}, status=400)

        custom_name = request.data.get('new_company_name')

        try:
            res = SplitCompanyService.execute_split_company(
                company_id=str(company.id),
                split_date=split_date,
                new_company_name=custom_name,
                user=request.user
            )
            return Response(res, status=status.HTTP_201_CREATED)
        except ValidationError as ve:
            return Response({"success": False, "error": str(ve.message if hasattr(ve, 'message') else ve)}, status=400)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)
