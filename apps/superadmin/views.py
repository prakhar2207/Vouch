import datetime
from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import django

from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.accounting.models import Voucher
from apps.accounting.models_proforma import ProformaInvoice
from apps.inventory.models import Product
from apps.ledgers.models import Ledger
from apps.audit.models import AuditLog
from .permissions import IsSuperAdminOrStaff


class SuperadminMetricsView(APIView):
    """
    Platform-wide high-level telemetry and metrics for Superadmins.
    """
    permission_classes = [IsSuperAdminOrStaff]

    def get(self, request):
        now = timezone.now()
        thirty_days_ago = now - datetime.timedelta(days=30)
        seven_days_ago = (now - datetime.timedelta(days=6)).date()

        # Company metrics
        total_companies = Company.objects.count()
        active_companies = Company.objects.filter(is_active=True).count()
        new_companies_30d = Company.objects.filter(created_at__gte=thirty_days_ago).count()

        # User metrics
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        staff_users = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).count()
        new_users_30d = User.objects.filter(created_at__gte=thirty_days_ago).count()

        # Voucher / Transaction metrics
        all_vouchers = Voucher.objects.all()
        total_vouchers = all_vouchers.count()
        sales_vouchers = all_vouchers.filter(voucher_type='SALES').count()
        purchase_vouchers = all_vouchers.filter(voucher_type='PURCHASE').count()
        
        gross_volume = all_vouchers.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')
        sales_volume = all_vouchers.filter(voucher_type='SALES').aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')
        new_vouchers_30d = all_vouchers.filter(created_at__gte=thirty_days_ago).count()

        # Inventory & Ledger metrics
        total_products = Product.objects.count()
        total_ledgers = Ledger.objects.count()
        total_proformas = ProformaInvoice.objects.count()

        # Last 7 Days Activity Trend
        chart_data = []
        for i in range(7):
            day_date = seven_days_ago + datetime.timedelta(days=i)
            day_start = datetime.datetime.combine(day_date, datetime.time.min, tzinfo=datetime.timezone.utc)
            day_end = datetime.datetime.combine(day_date, datetime.time.max, tzinfo=datetime.timezone.utc)
            
            day_qs = all_vouchers.filter(created_at__range=(day_start, day_end))
            day_count = day_qs.count()
            day_amount = day_qs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')

            chart_data.append({
                "date": day_date.strftime("%d %b"),
                "count": day_count,
                "amount": float(day_amount)
            })

        return Response({
            "success": True,
            "data": {
                "companies": {
                    "total": total_companies,
                    "active": active_companies,
                    "inactive": total_companies - active_companies,
                    "new_last_30_days": new_companies_30d
                },
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "staff": staff_users,
                    "new_last_30_days": new_users_30d
                },
                "vouchers": {
                    "total": total_vouchers,
                    "sales": sales_vouchers,
                    "purchases": purchase_vouchers,
                    "other": total_vouchers - (sales_vouchers + purchase_vouchers),
                    "new_last_30_days": new_vouchers_30d,
                    "gross_volume": float(gross_volume),
                    "sales_volume": float(sales_volume)
                },
                "catalog": {
                    "total_products": total_products,
                    "total_ledgers": total_ledgers,
                    "total_proformas": total_proformas
                },
                "chart_data": chart_data,
                "system": {
                    "status": "healthy",
                    "django_version": django.get_version(),
                    "server_time": now.isoformat(),
                    "environment": "production" if not django.conf.settings.DEBUG else "development"
                }
            }
        })


class SuperadminCompaniesView(APIView):
    """
    List all companies across the platform with filtering, pagination, and summary telemetry.
    """
    permission_classes = [IsSuperAdminOrStaff]

    def get(self, request):
        search = (request.query_params.get('search') or '').strip()
        status_filter = (request.query_params.get('status') or '').strip().lower()
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))

        qs = Company.objects.all().order_by('-created_at')

        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_active=False)

        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(gstin__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )

        total_count = qs.count()
        results = qs[offset:offset + limit]

        data = []
        for c in results:
            users_qs = UserCompany.objects.filter(company=c).select_related('user')
            members_count = users_qs.count()
            owner_uc = users_qs.filter(role='OWNER').first() or users_qs.first()
            owner_info = {
                "name": f"{owner_uc.user.first_name} {owner_uc.user.last_name}".strip() or owner_uc.user.email,
                "email": owner_uc.user.email
            } if owner_uc and owner_uc.user else None

            vouchers_qs = Voucher.objects.filter(company=c)
            vouchers_count = vouchers_qs.count()
            sales_volume = vouchers_qs.filter(voucher_type='SALES').aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')
            products_count = Product.objects.filter(company=c).count()

            data.append({
                "id": str(c.id),
                "name": c.name,
                "gstin": c.gstin or "",
                "pan": getattr(c, 'pan', '') or (c.gstin[2:12] if c.gstin and len(c.gstin) >= 12 else ""),
                "state_code": getattr(c, 'state_code', '') or "",
                "email": c.email or "",
                "phone": c.phone or "",
                "address": c.address or "",
                "is_active": c.is_active,
                "created_at": c.created_at.isoformat() if hasattr(c, 'created_at') and c.created_at else None,
                "members_count": members_count,
                "vouchers_count": vouchers_count,
                "sales_volume": float(sales_volume),
                "products_count": products_count,
                "owner": owner_info
            })

        return Response({
            "success": True,
            "data": data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset
        })


class SuperadminCompanyToggleStatusView(APIView):
    """
    Toggle active / suspended status for a company tenant.
    """
    permission_classes = [IsSuperAdminOrStaff]

    def post(self, request, pk):
        company = Company.objects.filter(id=pk).first()
        if not company:
            return Response({"error": "Company not found"}, status=404)

        company.is_active = not company.is_active
        company.save(update_fields=['is_active'])

        # Record audit log
        AuditLog.objects.create(
            company=company,
            user=request.user,
            action='UPDATE',
            model_name='Company',
            record_id=str(company.id),
            changes={'is_active': company.is_active}
        )

        return Response({
            "success": True,
            "message": f"Company '{company.name}' status changed to {'Active' if company.is_active else 'Suspended'}.",
            "is_active": company.is_active
        })


class SuperadminUsersView(APIView):
    """
    List all platform users with company affiliations and staff flags.
    """
    permission_classes = [IsSuperAdminOrStaff]

    def get(self, request):
        search = (request.query_params.get('search') or '').strip()
        staff_filter = (request.query_params.get('is_staff') or '').strip().lower()
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))

        qs = User.objects.all().order_by('-created_at')

        if staff_filter == 'true':
            qs = qs.filter(Q(is_staff=True) | Q(is_superuser=True))
        elif staff_filter == 'false':
            qs = qs.filter(is_staff=False, is_superuser=False)

        if search:
            qs = qs.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )

        total_count = qs.count()
        results = qs[offset:offset + limit]

        data = []
        for u in results:
            user_comps = UserCompany.objects.filter(user=u).select_related('company')
            companies = [
                {
                    "id": str(uc.company.id),
                    "name": uc.company.name,
                    "role": uc.role,
                    "is_active": uc.company.is_active
                }
                for uc in user_comps
            ]

            data.append({
                "id": str(u.id),
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "full_name": f"{u.first_name} {u.last_name}".strip() or u.email,
                "role": getattr(u, 'role', 'VIEWER'),
                "is_active": u.is_active,
                "is_staff": u.is_staff,
                "is_superuser": u.is_superuser,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "companies": companies
            })

        return Response({
            "success": True,
            "data": data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset
        })


class SuperadminUserToggleStaffView(APIView):
    """
    Grant or revoke staff/admin access to a user.
    """
    permission_classes = [IsSuperAdminOrStaff]

    def post(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Only superusers can grant or revoke admin staff privileges."}, status=403)

        target_user = User.objects.filter(id=pk).first()
        if not target_user:
            return Response({"error": "User not found"}, status=404)

        if target_user.id == request.user.id:
            return Response({"error": "You cannot revoke your own superuser privileges."}, status=400)

        target_user.is_staff = not target_user.is_staff
        if not target_user.is_staff:
            target_user.is_superuser = False
        target_user.save(update_fields=['is_staff', 'is_superuser'])

        return Response({
            "success": True,
            "message": f"User '{target_user.email}' staff privileges updated.",
            "is_staff": target_user.is_staff,
            "is_superuser": target_user.is_superuser
        })


class SuperadminUserToggleActiveView(APIView):
    """
    Activate or deactivate a user account.
    """
    permission_classes = [IsSuperAdminOrStaff]

    def post(self, request, pk):
        target_user = User.objects.filter(id=pk).first()
        if not target_user:
            return Response({"error": "User not found"}, status=404)

        if target_user.id == request.user.id:
            return Response({"error": "You cannot deactivate your own account."}, status=400)

        target_user.is_active = not target_user.is_active
        target_user.save(update_fields=['is_active'])

        return Response({
            "success": True,
            "message": f"User '{target_user.email}' is now {'Active' if target_user.is_active else 'Deactivated'}.",
            "is_active": target_user.is_active
        })


class SuperadminAuditLogsView(APIView):
    """
    Recent platform-wide audit log activity.
    """
    permission_classes = [IsSuperAdminOrStaff]

    def get(self, request):
        limit = int(request.query_params.get('limit', 50))
        logs = AuditLog.objects.select_related('user', 'company').order_by('-created_at')[:limit]

        data = [
            {
                "id": str(log.id),
                "company_name": log.company.name if log.company else "Global",
                "company_id": str(log.company_id) if log.company_id else None,
                "user_email": log.user.email if log.user else "System",
                "action": log.action,
                "model_name": log.model_name,
                "record_id": log.record_id,
                "changes": log.changes,
                "timestamp": log.created_at.isoformat() if getattr(log, 'created_at', None) else None,
            }
            for log in logs
        ]

        return Response({
            "success": True,
            "data": data,
            "total_count": len(data)
        })


class SuperadminImpersonateCompanyView(APIView):
    """
    Impersonation disabled to strictly protect tenant business privacy and data isolation.
    """
    permission_classes = [IsSuperAdminOrStaff]

    def post(self, request, pk):
        return Response(
            {"error": "Access denied: Platform administrators are isolated from customer business data and cannot impersonate tenant companies."},
            status=status.HTTP_403_FORBIDDEN
        )


class SuperadminCompanyDeleteView(APIView):
    """
    Permanently delete a company and all associated records (vouchers, items, ledgers, products).
    """
    permission_classes = [IsSuperAdminOrStaff]

    def delete(self, request, pk):
        from django.db import transaction
        from apps.companies.models import Company, UserCompany, CompanySettings
        from apps.accounting.models import (
            Voucher, VoucherItem, LedgerEntry, PaymentAllocation, PaymentAllocationTask,
            BankStatementImport, BankTransaction, InwardVoucherRequest, FinancialYear,
            VoucherSequence, LedgerBalance, PartyMapping, AccountingFinding, SyncEvent,
            OfflineCommand
        )
        from apps.accounting.models_proforma import ProformaInvoice, ProformaItem
        from apps.inventory.models import InventoryEntry, Product, ProductCategory, Warehouse
        from apps.ledgers.models import Ledger, LedgerGroup
        from apps.gst.models import (
            CompanyGSTConfig, EWayBillRecord, EInvoiceRecord,
            GSTR2BImport, GSTR2BRecord, GSTFilingRecord
        )
        from apps.documents.models import DocumentAuditEvent, DocumentSnapshot, EDIDocument, EDIExchange
        from apps.protocol.models import AuthorizedDevice, DeviceKeyRotationAudit
        from apps.audit.models import AuditLog

        company = Company.objects.filter(id=pk).first()
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        company_name = company.name
        company_id = str(company.id)

        try:
            with transaction.atomic():
                # 1. Audit logs: RAW DELETE so no Python delete() or signal is triggered
                try:
                    AuditLog.objects.filter(company=company)._raw_delete(using='default')
                except Exception:
                    pass

                # 2. Protocol models
                try:
                    devices = AuthorizedDevice.objects.filter(company=company)
                    DeviceKeyRotationAudit.objects.filter(device__in=devices).delete()
                    devices.delete()
                except Exception:
                    pass

                # 3. EDI, GST, and Documents records
                try:
                    EDIExchange.objects.filter(target_company=company).delete()
                    EDIDocument.objects.filter(sender_company=company).delete()
                    InwardVoucherRequest.objects.filter(source_company=company).delete()
                    InwardVoucherRequest.objects.filter(target_company=company).delete()
                    DocumentAuditEvent.objects.filter(company=company).delete()
                    DocumentSnapshot.objects.filter(company=company).delete()
                    EWayBillRecord.objects.filter(company=company).delete()
                    EInvoiceRecord.objects.filter(company=company).delete()
                    GSTR2BRecord.objects.filter(company=company).delete()
                    GSTR2BImport.objects.filter(company=company).delete()
                    GSTFilingRecord.objects.filter(company=company).delete()
                    CompanyGSTConfig.objects.filter(company=company).delete()
                except Exception:
                    pass

                # 4. Bank transactions, imports, party mappings, findings, sync events, tasks, offline commands
                try:
                    BankTransaction.objects.filter(company=company).delete()
                    BankStatementImport.objects.filter(company=company).delete()
                    PartyMapping.objects.filter(company=company).delete()
                    AccountingFinding.objects.filter(company=company).delete()
                    SyncEvent.objects.filter(company=company).delete()
                    PaymentAllocationTask.objects.filter(company=company).delete()
                    OfflineCommand.objects.filter(company=company).delete()
                except Exception:
                    pass

                # 5. Payment allocations
                try:
                    PaymentAllocation.objects.filter(company=company).delete()
                except Exception:
                    pass

                # 6. Proformas and Proforma items
                try:
                    ProformaItem.objects.filter(proforma__company=company).delete()
                    ProformaInvoice.objects.filter(company=company).delete()
                except Exception:
                    pass

                # 7. Voucher Items, Ledger Entries, and Vouchers (nullify revision chains first)
                try:
                    VoucherItem.objects.filter(voucher__company=company).delete()
                    LedgerEntry.objects.filter(voucher__company=company).delete()
                    Voucher.objects.filter(company=company).update(revision_of=None)
                    Voucher.objects.filter(company=company).delete()
                except Exception:
                    pass

                # 8. Inventory: Entries, Products, Categories, Warehouses
                try:
                    InventoryEntry.objects.filter(company=company).delete()
                    InventoryEntry.objects.filter(product__company=company).delete()
                    Product.objects.filter(company=company).delete()
                    ProductCategory.objects.filter(company=company).delete()
                    Warehouse.objects.filter(company=company).delete()
                except Exception:
                    pass

                # 9. Ledger balances, Sequences, Ledgers, and Groups
                try:
                    LedgerBalance.objects.filter(ledger__company=company).delete()
                    VoucherSequence.objects.filter(company=company).delete()
                    Ledger.objects.filter(company=company).delete()
                    LedgerGroup.objects.filter(company=company).delete()
                except Exception:
                    pass

                # 10. Financial Years
                try:
                    FinancialYear.objects.filter(company=company).delete()
                except Exception:
                    pass

                # 11. User memberships & Settings
                try:
                    UserCompany.objects.filter(company=company).delete()
                    CompanySettings.objects.filter(company=company).delete()
                except Exception:
                    pass

                # 12. Delete the Company record
                company.delete()

                # Safe platform audit logging
                try:
                    AuditLog.objects.create(
                        user=request.user,
                        action='DELETE',
                        model_name='Company',
                        record_id=company_id,
                        changes={'deleted_company_name': company_name}
                    )
                except Exception:
                    pass

            return Response({
                "success": True,
                "message": f"Company '{company_name}' ({company_id[:8]}...) was permanently deleted.",
                "deleted_id": company_id
            })
        except Exception as e:
            return Response(
                {"error": f"Failed to delete company: {str(e)}", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SuperadminUserDeleteView(APIView):
    """
    Permanently delete a user account and clean up their company associations.
    """
    permission_classes = [IsSuperAdminOrStaff]

    def delete(self, request, pk):
        from django.db import transaction
        from apps.accounts.models import User
        from apps.accounting.models import Voucher
        from apps.accounting.models_proforma import ProformaInvoice
        from apps.companies.models import UserCompany
        from apps.audit.models import AuditLog

        target_user = User.objects.filter(id=pk).first()
        if not target_user:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        if str(target_user.id) == str(request.user.id):
            return Response({"error": "You cannot delete your own superadmin account."}, status=status.HTTP_400_BAD_REQUEST)

        if target_user.is_superuser and not request.user.is_superuser:
            return Response({"error": "Only superusers can delete another superuser account."}, status=status.HTTP_403_FORBIDDEN)

        user_email = target_user.email
        user_id = str(target_user.id)

        try:
            with transaction.atomic():
                # Reassign vouchers/proformas created by this user to acting superadmin to satisfy PROTECT foreign key
                Voucher.objects.filter(created_by=target_user).update(created_by=request.user)
                ProformaInvoice.objects.filter(created_by=target_user).update(created_by=request.user)

                # Remove company affiliations
                UserCompany.objects.filter(user=target_user).delete()

                # Unlink audit logs
                AuditLog.objects.filter(user=target_user).update(user=None)

                # Delete the user
                target_user.delete()

                # Record global platform audit log
                try:
                    AuditLog.objects.create(
                        user=request.user,
                        action='DELETE',
                        model_name='User',
                        record_id=user_id,
                        changes={'deleted_user_email': user_email}
                    )
                except Exception:
                    pass

            return Response({
                "success": True,
                "message": f"User '{user_email}' was permanently deleted.",
                "deleted_id": user_id
            })
        except Exception as e:
            return Response(
                {"error": f"Failed to delete user: {str(e)}", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

