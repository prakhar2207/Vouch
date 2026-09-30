import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def dispatch_invoice_notification_task(self, voucher_id: str):
    """
    Celery background worker task to render PDF and dispatch tax invoice
    notifications via email and WhatsApp payload generation asynchronously.
    Guarantees sub-second voucher save times by completely offloading PDF rendering
    and SMTP network communication to background workers.
    """
    from apps.accounting.models import Voucher
    from apps.accounting.services.invoice_notification_service import InvoiceNotificationService
    from apps.accounting.services.invoice_pdf_service import InvoicePDFService

    try:
        voucher = Voucher.objects.select_related('company', 'party_ledger').get(id=voucher_id)
        pdf_bytes = InvoicePDFService.generate_invoice_pdf(voucher)
        success = InvoiceNotificationService.send_invoice_email(voucher, pdf_bytes=pdf_bytes)
        logger.info(f"[Celery] Invoice email dispatch result for {voucher.voucher_number}: {success}")
        return {
            "success": success,
            "voucher_id": str(voucher_id),
            "voucher_number": voucher.voucher_number
        }
    except Voucher.DoesNotExist:
        logger.warning(f"[Celery] Voucher ID {voucher_id} not found in database. Notification aborted.")
        return {"success": False, "error": "Voucher not found"}
    except Exception as exc:
        logger.exception(f"[Celery] Transient error dispatching invoice {voucher_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def rebuild_company_balances_task(self, company_id: str, user_id: str = None):
    """
    Asynchronous Celery task for bulk reconstruction of all ledger current_balance fields.
    Prevents HTTP timeout on large ledger sets by running in background worker.
    """
    from apps.companies.models import Company
    from apps.accounts.models import User
    from apps.accounting.services.balance_rebuild import BalanceRebuildService

    try:
        company = Company.objects.get(id=company_id)
        user = User.objects.filter(id=user_id).first() if user_id else None
        logger.info(f"[Celery] Starting async balance rebuild for {company.name} ({company_id})")
        result = BalanceRebuildService.rebuild_company_ledger_balances(company, user=user)
        logger.info(f"[Celery] Balance rebuild completed for {company.name}: {result.get('rebuilt_ledgers_count')} ledgers")
        return result
    except Company.DoesNotExist:
        logger.error(f"[Celery] Company {company_id} not found for balance rebuild.")
        return {"success": False, "error": "Company not found"}
    except Exception as exc:
        logger.exception(f"[Celery] Error rebuilding balances for {company_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def ocr_invoice_extract_task(self, file_base64: str, mime_type: str = 'image/png', custom_api_key: str = None, scan_mode: str = 'auto'):
    """
    Asynchronous Celery task for AI Bill Scanner (Gemini OCR).
    Offloads heavy multimodal computer vision and structured entity extraction.
    """
    from apps.accounting.services.ocr_service import InvoiceOCRService

    try:
        logger.info(f"[Celery] Executing async OCR bill extraction (mode={scan_mode})")
        extracted_data = InvoiceOCRService.extract_from_base64(
            file_base64,
            mime_type=mime_type,
            custom_api_key=custom_api_key,
            scan_mode=scan_mode
        )
        return {
            "success": True,
            "data": extracted_data
        }
    except Exception as exc:
        logger.exception(f"[Celery] Async OCR extraction error: {exc}")
        return {
            "success": False,
            "error": str(exc)
        }


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def close_financial_year_task(self, company_id: str, current_fy_id: str, next_fy_id: str = None, user_id: str = None):
    """
    Asynchronous Celery task for year-end closing and balance roll-forward.
    Carries forward P&L and updates ledger opening balances in background.
    """
    from apps.accounting.services.year_end_service import YearEndClosingService

    try:
        logger.info(f"[Celery] Executing async FY close for company={company_id}, fy={current_fy_id}")
        result = YearEndClosingService.close_and_roll_forward(company_id, current_fy_id, next_fy_id)
        return result
    except Exception as exc:
        logger.exception(f"[Celery] Error closing financial year {current_fy_id}: {exc}")
        return {
            "success": False,
            "error": str(exc)
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def automated_nightly_backup_task(self, upload_s3: bool = True, encrypt: bool = True):
    """
    Automated scheduled task for nightly database disaster recovery backup.
    Produces compressed, AES-256 encrypted snapshot and archives to off-site S3 storage.
    """
    from apps.common.services.backup_service import DatabaseBackupService

    try:
        logger.info("[Celery Beat] Executing automated nightly disaster recovery backup...")
        result = DatabaseBackupService.perform_backup(upload_s3=upload_s3, encrypt=encrypt)
        logger.info(f"[Celery Beat] Backup finished: success={result.get('success')}, size={result.get('file_size_mb')} MB, s3={result.get('s3_uploaded')}")
        return result
    except Exception as exc:
        logger.exception(f"[Celery Beat] Nightly database backup failed: {exc}")
        raise self.retry(exc=exc)
