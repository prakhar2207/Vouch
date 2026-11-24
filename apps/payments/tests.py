# apps/payments/tests.py
import hmac
import hashlib
import json
import uuid
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.payments.models import (
    MerchantPaymentAccount,
    PaymentRequest,
    PaymentWebhookEvent,
    UnmatchedPaymentRecord,
    Beneficiary
)
from apps.payments.constants import (
    PaymentStatus,
    PaymentMethod,
    PaymentProviderType,
    SettlementStatus,
    AccountingPostingStatus,
    BeneficiaryType,
    VerificationStatus
)
from apps.payments.services import (
    PaymentOrchestrator,
    AccountingPostingService,
    PaymentWebhookService,
    SettlementReconciliationService,
    BeneficiaryResolutionService,
    BeneficiaryVerificationService
)
from apps.payments.providers import get_payment_provider, SetuPaymentProvider, BankTransferProvider

SANDBOX_COMPANY_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'


class SriLekhPayTestSuite(TestCase):
    """
    Comprehensive test suite for SriLekh Pay infrastructure.
    Guarantees strict double-entry invariants, replay protection, and test isolation.
    """

    def setUp(self):
        # 1. Enforce sandbox test isolation
        self.company, _ = Company.objects.get_or_create(
            id=SANDBOX_COMPANY_ID,
            defaults={"name": "Apex Belting & Industrial Store (Demo)", "gstin": "07AAAAA0000A1Z5"}
        )
        assert str(self.company.id) == SANDBOX_COMPANY_ID, "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"

        self.user = User.objects.create_user(
            email=f"test_{uuid.uuid4().hex[:6]}@srilekh.test",
            password="TestPassword123!"
        )

        # 2. Chart of Accounts setup
        self.supplier_group, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Sundry Creditors",
            defaults={"nature": "LIABILITY"}
        )
        self.bank_group, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Bank Accounts",
            defaults={"nature": "ASSET"}
        )

        self.bank_ledger = Ledger.objects.create(
            company=self.company,
            group=self.bank_group,
            name="Apex Current Account",
            ledger_type="BANK"
        )

        self.supplier_ledger = Ledger.objects.create(
            company=self.company,
            group=self.supplier_group,
            name="Saksham Industrial Belts",
            ledger_type="SUPPLIER"
        )

        self.merchant_account = MerchantPaymentAccount.objects.create(
            company=self.company,
            vpa="apexbelts@icici",
            is_onboarded=True,
            default_settlement_ledger=self.bank_ledger,
            virtual_account_prefix="APEX"
        )

    def test_payment_initiation_upi_and_neft(self):
        """Validates UPI and Bank Transfer payment request initiation."""
        # 1. Initiate UPI Payment
        pr_upi = PaymentOrchestrator.initiate_payment(
            company=self.company,
            amount=Decimal('5000.00'),
            payment_method=PaymentMethod.UPI,
            payer_party=self.supplier_ledger,
            recipient_name="Saksham Industrial Belts",
            recipient_vpa="saksham@upi",
            user=self.user
        )
        self.assertEqual(pr_upi.status, PaymentStatus.INITIATED)
        self.assertEqual(pr_upi.provider, PaymentProviderType.SETU)
        self.assertTrue(pr_upi.srilekh_pay_id.startswith('SLP-'))
        self.assertIsNotNone(pr_upi.qr_data)
        self.assertIn('upi://pay', pr_upi.qr_data)

        # 2. Initiate NEFT Payment
        pr_neft = PaymentOrchestrator.initiate_payment(
            company=self.company,
            amount=Decimal('15000.00'),
            payment_method=PaymentMethod.NEFT,
            payer_party=self.supplier_ledger,
            recipient_name="Saksham Industrial Belts",
            recipient_account_number="91234567890",
            recipient_ifsc="HDFC0001234",
            user=self.user
        )
        self.assertEqual(pr_neft.status, PaymentStatus.INITIATED)
        self.assertEqual(pr_neft.provider, PaymentProviderType.BANK_TRANSFER)

    def test_webhook_hmac_verification_and_replay_protection(self):
        """Verifies cryptographic signature validation and idempotency replay defense."""
        pr = PaymentOrchestrator.initiate_payment(
            company=self.company,
            amount=Decimal('2500.00'),
            payment_method=PaymentMethod.UPI,
            payer_party=self.supplier_ledger,
            recipient_name="Saksham Industrial Belts",
            user=self.user
        )

        event_id = f"EVT_{uuid.uuid4().hex}"
        payload = {
            "id": event_id,
            "event": "BILL_FULFILMENT_STATUS",
            "data": {
                "ref": pr.provider_reference,
                "status": "SUCCESS",
                "utr": "412345678901",
                "amount": {"value": 250000},
                "payer": {"vpa": "customer@upi"}
            }
        }
        raw_body = json.dumps(payload).encode('utf-8')
        sig = hmac.new(b"sandbox_setu_secret", raw_body, hashlib.sha256).hexdigest()

        headers = {"X-Setu-Signature": sig}

        # First webhook arrival
        success, msg, data = PaymentWebhookService.process_incoming_webhook(
            provider_type=PaymentProviderType.SETU,
            raw_body=raw_body,
            headers=headers,
            parsed_json=payload
        )
        self.assertTrue(success)
        self.assertEqual(data.get("status"), "PROCESSED")

        # Verify payment updated
        pr.refresh_from_db()
        self.assertEqual(pr.status, PaymentStatus.SUCCESS)
        self.assertEqual(pr.utr, "412345678901")

        # Second arrival with same event_id (Replay attack simulation)
        success_replay, msg_replay, data_replay = PaymentWebhookService.process_incoming_webhook(
            provider_type=PaymentProviderType.SETU,
            raw_body=raw_body,
            headers=headers,
            parsed_json=payload
        )
        self.assertTrue(success_replay)
        self.assertEqual(data_replay.get("status"), "DUPLICATE")

    def test_double_entry_accounting_posting_equilibrium(self):
        """Guarantees double-entry invariant: Total Debits == Total Credits in posted vouchers."""
        pr = PaymentOrchestrator.initiate_payment(
            company=self.company,
            amount=Decimal('8200.00'),
            payment_method=PaymentMethod.UPI,
            payer_party=self.supplier_ledger,
            recipient_name="Saksham Industrial Belts",
            user=self.user
        )

        # Confirm payment
        confirmed_pr = PaymentOrchestrator.confirm_payment_success(
            payment_request=pr,
            utr="498765432109",
            payer_vpa="payer@upi",
            user=self.user
        )

        self.assertEqual(confirmed_pr.status, PaymentStatus.SUCCESS)
        self.assertIsNotNone(confirmed_pr.payer_voucher)

        voucher = confirmed_pr.payer_voucher
        voucher.refresh_from_db()
        self.assertEqual(voucher.status, 'POSTED')
        self.assertEqual(voucher.voucher_type, 'PAYMENT')

        # Double-entry invariant check
        entries = voucher.ledger_entries.all()
        total_debit = sum(e.debit_amount for e in entries)
        total_credit = sum(e.credit_amount for e in entries)
        self.assertEqual(total_debit, total_credit)
        self.assertEqual(total_debit, Decimal('8200.00'))

    def test_dual_party_cross_company_accounting(self):
        """Verifies symmetric double-entry posting when both businesses are SriLekh SaaS customers."""
        # Provision second company in sandbox
        recip_company = Company.objects.create(
            name="Saksham Belts Staging Co",
            gstin="07BBBBB1111B1Z2"
        )
        recip_bank_grp = LedgerGroup.objects.create(company=recip_company, name="Bank Accounts", nature="ASSET")
        recip_cust_grp = LedgerGroup.objects.create(company=recip_company, name="Sundry Debtors", nature="ASSET")
        
        recip_bank = Ledger.objects.create(company=recip_company, group=recip_bank_grp, name="Saksham ICICI Bank", ledger_type="BANK")
        recip_customer = Ledger.objects.create(company=recip_company, group=recip_cust_grp, name="Apex Belting Store", ledger_type="CUSTOMER", gstin="07AAAAA0000A1Z5")

        MerchantPaymentAccount.objects.create(
            company=recip_company,
            vpa="saksham@icici",
            is_onboarded=True,
            default_settlement_ledger=recip_bank
        )

        # Payer initiates payment directly to recipient company
        pr = PaymentOrchestrator.initiate_payment(
            company=self.company,
            amount=Decimal('12000.00'),
            payment_method=PaymentMethod.UPI,
            payer_party=self.supplier_ledger,
            recipient_company=recip_company,
            recipient_name=recip_company.name,
            recipient_vpa="saksham@icici",
            user=self.user
        )

        # Confirm payment
        confirmed_pr = PaymentOrchestrator.confirm_payment_success(
            payment_request=pr,
            utr="411223344556",
            user=self.user
        )

        self.assertEqual(confirmed_pr.accounting_status, AccountingPostingStatus.POSTED)
        self.assertIsNotNone(confirmed_pr.payer_voucher)
        self.assertIsNotNone(confirmed_pr.recipient_voucher)

        # Payer Voucher Equilibrium
        payer_entries = confirmed_pr.payer_voucher.ledger_entries.all()
        self.assertEqual(sum(e.debit_amount for e in payer_entries), sum(e.credit_amount for e in payer_entries))
        self.assertEqual(sum(e.debit_amount for e in payer_entries), Decimal('12000.00'))

        # Recipient Voucher Equilibrium
        recip_entries = confirmed_pr.recipient_voucher.ledger_entries.all()
        self.assertEqual(sum(e.debit_amount for e in recip_entries), sum(e.credit_amount for e in recip_entries))
        self.assertEqual(sum(e.debit_amount for e in recip_entries), Decimal('12000.00'))

    def test_unmatched_payment_suspense_handling(self):
        """Verifies unmatched receipts are safely held in suspense without corrupting customer books."""
        recip_company = Company.objects.create(
            name="Third Party Recipient Co",
            gstin="07CCCCC2222C1Z3"
        )
        MerchantPaymentAccount.objects.create(
            company=recip_company,
            vpa="thirdparty@icici",
            is_onboarded=True
        )

        # No matching customer ledger exists in recip_company for Apex Belting Store
        pr = PaymentOrchestrator.initiate_payment(
            company=self.company,
            amount=Decimal('4500.00'),
            payment_method=PaymentMethod.UPI,
            payer_party=self.supplier_ledger,
            recipient_company=recip_company,
            recipient_name=recip_company.name,
            user=self.user
        )

        confirmed_pr = PaymentOrchestrator.confirm_payment_success(pr, utr="455667788990")

        self.assertEqual(confirmed_pr.accounting_status, AccountingPostingStatus.UNMATCHED)
        self.assertTrue(UnmatchedPaymentRecord.objects.filter(payment_request=confirmed_pr, is_resolved=False).exists())

    def test_settlement_reconciliation_math(self):
        """Verifies settlement journal equilibrium: Net Deposit + Gateway Fee == Gross Amount."""
        pr = PaymentOrchestrator.initiate_payment(
            company=self.company,
            amount=Decimal('10000.00'),
            payment_method=PaymentMethod.UPI,
            payer_party=self.supplier_ledger,
            recipient_name="Saksham Industrial Belts",
            user=self.user
        )
        PaymentOrchestrator.confirm_payment_success(pr, utr="499887766554")

        # Settle payment with ₹20 gateway fee
        fee_group, _ = LedgerGroup.objects.get_or_create(company=self.company, name="Indirect Expenses", defaults={"nature": "EXPENSE"})
        fee_ledger = Ledger.objects.create(company=self.company, group=fee_group, name="Gateway Charges", ledger_type="EXPENSE")
        clearing_ledger = Ledger.objects.create(company=self.company, group=self.bank_group, name="Payment Clearing", ledger_type="BANK")

        self.merchant_account.gateway_charges_ledger = fee_ledger
        self.merchant_account.payment_clearing_ledger = clearing_ledger
        self.merchant_account.save()

        settled_pr = SettlementReconciliationService.record_settlement(
            payment_request=pr,
            net_amount=Decimal('9980.00'),
            fee_amount=Decimal('20.00'),
            user=self.user
        )

        self.assertEqual(settled_pr.settlement_status, SettlementStatus.SETTLED)
        self.assertEqual(settled_pr.net_settled_amount + settled_pr.gateway_fee, settled_pr.amount)

    def test_beneficiary_discovery_mobile_vpa_qr_ifsc(self):
        """Verifies multi-channel recipient discovery: Mobile Number, VPA, QR, and IFSC."""
        # 1. Mobile discovery
        m_res = BeneficiaryResolutionService.resolve_mobile_number("9876543210")
        self.assertEqual(m_res["mobile_number"], "9876543210")
        self.assertTrue(m_res["is_verified"])
        self.assertEqual(m_res["masked_identifier"], "••••••3210")

        # 2. VPA discovery
        v_res = BeneficiaryResolutionService.resolve_vpa("saksham@icici")
        self.assertEqual(v_res["vpa"], "saksham@icici")

        # 3. QR code parsing & sanitization
        valid_qr = "upi://pay?pa=supplier@icici&pn=Supplier%20Belts&am=1500.00&cu=INR&tn=Invoice%20101"
        qr_res = BeneficiaryResolutionService.parse_upi_qr(valid_qr)
        self.assertEqual(qr_res["vpa"], "supplier@icici")
        self.assertEqual(qr_res["name"], "Supplier Belts")
        self.assertEqual(qr_res["amount"], "1500.00")
        self.assertEqual(qr_res["notes"], "Invoice 101")

        # CRLF injection protection
        with self.assertRaises(Exception):
            BeneficiaryResolutionService.parse_upi_qr("upi://pay?pa=test@upi\r\nSET-COOKIE: malicious=1")

        # 4. Bank IFSC resolution
        ifsc_res = BeneficiaryResolutionService.validate_ifsc("HDFC0001234")
        self.assertTrue(ifsc_res["is_valid"])
        self.assertEqual(ifsc_res["bank_name"], "HDFC Bank")

    def test_beneficiary_crud_and_tenant_isolation(self):
        """Ensures strict multi-tenant beneficiary isolation between companies."""
        other_company = Company.objects.create(name="Other Co", gstin="07DDDDD3333D1Z4")
        
        # Create beneficiary in sandbox company
        b1 = Beneficiary.objects.create(
            company=self.company,
            beneficiary_type=BeneficiaryType.VPA,
            name="Apex Verified Vendor",
            vpa="apexvendor@icici",
            is_favorite=True
        )

        # Create beneficiary in other company
        b2 = Beneficiary.objects.create(
            company=other_company,
            beneficiary_type=BeneficiaryType.BANK_ACCOUNT,
            name="Other Vendor",
            account_number="123456789012",
            ifsc_code="SBIN0001234"
        )

        # Verify tenant queries are strictly isolated
        apex_beneficiaries = Beneficiary.objects.filter(company=self.company)
        self.assertIn(b1, apex_beneficiaries)
        self.assertNotIn(b2, apex_beneficiaries)

        self.assertEqual(b2.masked_account_number, "••••••••9012")

    def test_beneficiary_verification_and_payment_linkage(self):
        """Verifies live verification and automatic stat updates upon payment completion."""
        b = Beneficiary.objects.create(
            company=self.company,
            beneficiary_type=BeneficiaryType.VPA,
            name="Saksham Belts",
            vpa="saksham@icici",
            linked_party=self.supplier_ledger
        )
        self.assertFalse(b.is_verified)

        # Verify beneficiary
        verified_b = BeneficiaryVerificationService.verify_beneficiary(b)
        self.assertTrue(verified_b.is_verified)
        self.assertEqual(verified_b.verification_status, VerificationStatus.VERIFIED)

        # Initiate and confirm payment linked to this beneficiary
        pr = PaymentOrchestrator.initiate_payment(
            company=self.company,
            amount=Decimal('3500.00'),
            payment_method=PaymentMethod.UPI,
            beneficiary=verified_b,
            user=self.user
        )
        self.assertEqual(pr.beneficiary, verified_b)
        self.assertEqual(pr.recipient_vpa, "saksham@icici")

        PaymentOrchestrator.confirm_payment_success(pr, utr="488776655443", user=self.user)

        verified_b.refresh_from_db()
        self.assertEqual(verified_b.total_payments_count, 1)
        self.assertEqual(verified_b.total_paid_amount, Decimal('3500.00'))
        self.assertIsNotNone(verified_b.last_paid_at)
