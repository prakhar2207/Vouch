import datetime
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User
from apps.accounting.models import LedgerEntry, PaymentAllocation, Voucher
from apps.accounting.services.allocation_service import PaymentAllocationService
from apps.accounting.services.financial_statements_service import FinancialStatementsService
from apps.accounting.services.period_service import PeriodBalanceService
from apps.accounting.services.voucher_service import VoucherService
from apps.audit.models import AuditLog
from apps.companies.models import Company, UserCompany
from apps.companies.views import provision_company_defaults
from apps.inventory.models import Product
from apps.ledgers.models import Ledger, LedgerGroup


def _seed_tenant(suffix: str):
    """Creates an isolated synthetic test tenant with OWNER, CA, EMPLOYEE, and VIEWER users."""
    owner = User.objects.create_user(
        email=f"owner_{suffix}@stage412.test", password="Password123!", role="OWNER", email_verified=True
    )
    ca_user = User.objects.create_user(
        email=f"ca_{suffix}@stage412.test", password="Password123!", role="CA", email_verified=True
    )
    employee = User.objects.create_user(
        email=f"emp_{suffix}@stage412.test", password="Password123!", role="EMPLOYEE", email_verified=True
    )
    viewer = User.objects.create_user(
        email=f"viewer_{suffix}@stage412.test", password="Password123!", role="VIEWER", email_verified=True
    )
    company = Company.objects.create(
        name=f"Stage412 Remediation Co {suffix}",
        state_code="27",
        gstin=f"27AABCS{suffix[:4].upper().ljust(4, '1')}F1Z5",
    )
    UserCompany.objects.create(user=owner, company=company, role="OWNER")
    UserCompany.objects.create(user=ca_user, company=company, role="CA")
    UserCompany.objects.create(user=employee, company=company, role="EMPLOYEE")
    UserCompany.objects.create(user=viewer, company=company, role="VIEWER")
    provision_company_defaults(company)

    debtors_grp = LedgerGroup.objects.get(company=company, name="Sundry Debtors")
    creditors_grp = LedgerGroup.objects.get(company=company, name="Sundry Creditors")
    bank_grp = LedgerGroup.objects.get(company=company, name="Bank Accounts")
    indirect_grp = LedgerGroup.objects.get(company=company, name="Indirect Expenses")

    customer = Ledger.objects.create(
        company=company, group=debtors_grp, name=f"Test Customer {suffix}", ledger_type="CUSTOMER", state_code="27"
    )
    supplier = Ledger.objects.create(
        company=company, group=creditors_grp, name=f"Test Supplier {suffix}", ledger_type="SUPPLIER", state_code="27"
    )
    bank = Ledger.objects.create(
        company=company, group=bank_grp, name=f"HDFC Bank {suffix}", ledger_type="BANK", opening_balance=Decimal("100000.00"), opening_balance_type="DEBIT"
    )
    expense = Ledger.objects.create(
        company=company, group=indirect_grp, name=f"Office Expense {suffix}", ledger_type="EXPENSE"
    )
    cash = Ledger.objects.get(company=company, ledger_type="CASH")
    sales_ledger = Ledger.objects.get(company=company, ledger_type="SALES")
    purchase_ledger = Ledger.objects.get(company=company, ledger_type="PURCHASE")

    prod_a = Product.objects.create(
        company=company, name=f"Conveyor Belt A {suffix}", sku=f"BELT-A-{suffix}", unit="MTR",
        hsn_code="4010", gst_rate=Decimal("18.00"), selling_price=Decimal("500.00"),
        purchase_price=Decimal("300.00"), stock_quantity=Decimal("100.00")
    )
    prod_b = Product.objects.create(
        company=company, name=f"Roller Idler B {suffix}", sku=f"ROLL-B-{suffix}", unit="PCS",
        hsn_code="8431", gst_rate=Decimal("18.00"), selling_price=Decimal("500.00"),
        purchase_price=Decimal("300.00"), stock_quantity=Decimal("100.00")
    )
    return {
        "company": company,
        "owner": owner,
        "ca": ca_user,
        "employee": employee,
        "viewer": viewer,
        "customer": customer,
        "supplier": supplier,
        "bank": bank,
        "cash": cash,
        "expense": expense,
        "sales_ledger": sales_ledger,
        "purchase_ledger": purchase_ledger,
        "prod_a": prod_a,
        "prod_b": prod_b,
    }


class Stage412DEF01PaymentDuplicateTests(APITestCase):
    """Regression suite for DEF-01: Payment/Receipt duplicate override & RBAC + Audit + Idempotency."""

    def setUp(self):
        self.env = _seed_tenant(uuid.uuid4().hex[:6])
        self.client = APIClient()
        self.today = datetime.date.today().isoformat()

        # Create an unpaid Sales invoice of ₹11,800 so allocations can be verified accurately
        self.client.force_authenticate(user=self.env["owner"])
        inv_res = self.client.post(
            "/api/v1/accounting/sales-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "reference_number": "PO-INIT-001",
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 20, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(inv_res.status_code, status.HTTP_201_CREATED, inv_res.data)
        self.invoice_id = inv_res.data["voucher_id"]

    def _receipt_payload(self, **overrides):
        base = {
            "company_id": str(self.env["company"].id),
            "voucher_type": "RECEIPT",
            "party_ledger_id": str(self.env["customer"].id),
            "payment_ledger_id": str(self.env["bank"].id),
            "amount": "2000.00",
            "voucher_date": self.today,
            "narration": "Advance installment",
        }
        base.update(overrides)
        return base

    def test_duplicate_receipt_blocks_by_default_allows_authorized_override_and_blocks_employee_and_string_false(self):
        # 1. First receipt succeeds normally
        r1 = self.client.post("/api/v1/accounting/payment-receipt/", self._receipt_payload(), format="json")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)

        # 2. Exact repeat without override is blocked with 409 + requires_confirmation
        r2 = self.client.post("/api/v1/accounting/payment-receipt/", self._receipt_payload(), format="json")
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT, r2.data)
        self.assertTrue(r2.data["is_duplicate"])
        self.assertTrue(r2.data["requires_confirmation"])

        # 3. String "false" MUST NOT bypass duplicate protection (parse_bool_flag safety)
        r_str_false = self.client.post(
            "/api/v1/accounting/payment-receipt/",
            self._receipt_payload(allow_duplicate="false", force_create="false"),
            format="json",
        )
        self.assertEqual(r_str_false.status_code, status.HTTP_409_CONFLICT, r_str_false.data)

        # 4. allow_statutory_override MUST NOT accidentally bypass duplicate protection
        r_stat = self.client.post(
            "/api/v1/accounting/payment-receipt/",
            self._receipt_payload(allow_statutory_override=True),
            format="json",
        )
        self.assertEqual(r_stat.status_code, status.HTTP_409_CONFLICT, r_stat.data)

        # 5. Unauthorized EMPLOYEE attempting duplicate override gets 403 Forbidden (and no voucher created)
        self.client.force_authenticate(user=self.env["employee"])
        r_emp = self.client.post(
            "/api/v1/accounting/payment-receipt/",
            self._receipt_payload(allow_duplicate=True),
            format="json",
        )
        self.assertEqual(r_emp.status_code, status.HTTP_403_FORBIDDEN, r_emp.data)

        # 6. VIEWER cannot post at all -> 403
        self.client.force_authenticate(user=self.env["viewer"])
        r_view = self.client.post("/api/v1/accounting/payment-receipt/", self._receipt_payload(), format="json")
        self.assertEqual(r_view.status_code, status.HTTP_403_FORBIDDEN, r_view.data)

        # 7. Authorized CA with allow_duplicate=True succeeds 201, writes single balanced entry pair, logs DUPLICATE_OVERRIDE
        self.client.force_authenticate(user=self.env["ca"])
        r_override = self.client.post(
            "/api/v1/accounting/payment-receipt/",
            self._receipt_payload(allow_duplicate=True, override_reason="Second same-day installment verified by bank UTR"),
            format="json",
        )
        self.assertEqual(r_override.status_code, status.HTTP_201_CREATED, r_override.data)
        v_id = r_override.data["voucher"]["id"]
        v_obj = Voucher.objects.get(id=v_id)
        self.assertEqual(v_obj.status, "POSTED")
        self.assertEqual(LedgerEntry.objects.filter(voucher=v_obj).count(), 2)
        audit = AuditLog.objects.filter(company=self.env["company"], action="DUPLICATE_OVERRIDE", record_id=v_obj.id).first()
        self.assertIsNotNone(audit)
        self.assertIn("Second same-day installment", str(audit.changes))

        # 8. Authorized OWNER with force_create=True also succeeds
        self.client.force_authenticate(user=self.env["owner"])
        r_force = self.client.post(
            "/api/v1/accounting/payment-receipt/",
            self._receipt_payload(force_create=True, override_reason="Third installment"),
            format="json",
        )
        self.assertEqual(r_force.status_code, status.HTTP_201_CREATED, r_force.data)
        inv = Voucher.objects.get(id=self.invoice_id)
        paid_total = sum(
            a.allocated_amount for a in PaymentAllocation.objects.filter(invoice_voucher=inv)
        )
        self.assertEqual(paid_total, Decimal("6000.00"))
        self.assertLessEqual(paid_total, inv.total_amount)

    def test_distinct_reference_and_idempotency_retry_replay(self):
        self.client.force_authenticate(user=self.env["owner"])
        idem_key = f"idem-rcp-{uuid.uuid4().hex}"

        r1 = self.client.post(
            "/api/v1/accounting/payment-receipt/",
            self._receipt_payload(amount="1500.00", reference_number="UTR-DAY-01"),
            format="json",
            HTTP_X_IDEMPOTENCY_KEY=idem_key,
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)
        first_vnum = r1.data["voucher_number"]

        # Network retry with identical X-Idempotency-Key replays cached 201 without creating a duplicate or 409
        r_replay = self.client.post(
            "/api/v1/accounting/payment-receipt/",
            self._receipt_payload(amount="1500.00", reference_number="UTR-DAY-01"),
            format="json",
            HTTP_X_IDEMPOTENCY_KEY=idem_key,
        )
        replay_body = r_replay.data if hasattr(r_replay, "data") else r_replay.json()
        self.assertEqual(r_replay.status_code, status.HTTP_201_CREATED, replay_body)
        self.assertEqual(replay_body["voucher_number"], first_vnum)
        self.assertEqual(
            Voucher.objects.filter(company=self.env["company"], voucher_type="RECEIPT", total_amount=Decimal("1500.00")).count(),
            1,
        )

        # Distinct commercial reference on same day for same party/amount is NOT flagged as duplicate
        r_distinct = self.client.post(
            "/api/v1/accounting/payment-receipt/",
            self._receipt_payload(amount="1500.00", reference_number="UTR-DAY-02"),
            format="json",
        )
        self.assertEqual(r_distinct.status_code, status.HTTP_201_CREATED, r_distinct.data)
        self.assertEqual(
            Voucher.objects.filter(company=self.env["company"], voucher_type="RECEIPT", total_amount=Decimal("1500.00")).count(),
            2,
        )


class Stage412DEF02PostedPatchTests(APITestCase):
    """Regression suite for DEF-02: OCC metadata PATCH across all posted voucher types + safety guards."""

    def setUp(self):
        self.env = _seed_tenant(uuid.uuid4().hex[:6])
        self.other_env = _seed_tenant(uuid.uuid4().hex[:6])
        self.client = APIClient()
        self.client.force_authenticate(user=self.env["owner"])
        self.today = datetime.date.today().isoformat()

        # Seed POSTED SALES, PURCHASE, PAYMENT, RECEIPT, JOURNAL, CREDIT_NOTE
        s_res = self.client.post(
            "/api/v1/accounting/sales-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 2, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(s_res.status_code, 201, s_res.data)
        self.sales_v = Voucher.objects.get(id=s_res.data["voucher_id"])

        p_res = self.client.post(
            "/api/v1/accounting/purchase-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["supplier"].id),
                "voucher_date": self.today,
                "supplier_invoice_number": "SUP-BILL-01",
                "items": [{"product_id": str(self.env["prod_b"].id), "quantity": 2, "rate": "300.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(p_res.status_code, 201, p_res.data)
        self.purchase_v = Voucher.objects.get(id=p_res.data["voucher_id"])

        rcp_res = self.client.post(
            "/api/v1/accounting/payment-receipt/",
            {
                "company_id": str(self.env["company"].id),
                "voucher_type": "RECEIPT",
                "party_ledger_id": str(self.env["customer"].id),
                "payment_ledger_id": str(self.env["bank"].id),
                "amount": "500.00",
                "voucher_date": self.today,
            },
            format="json",
        )
        self.assertEqual(rcp_res.status_code, 201, rcp_res.data)
        self.receipt_v = Voucher.objects.get(id=rcp_res.data["voucher"]["id"])

        pmt_res = self.client.post(
            "/api/v1/accounting/payment-receipt/",
            {
                "company_id": str(self.env["company"].id),
                "voucher_type": "PAYMENT",
                "party_ledger_id": str(self.env["supplier"].id),
                "payment_ledger_id": str(self.env["bank"].id),
                "amount": "400.00",
                "voucher_date": self.today,
            },
            format="json",
        )
        self.assertEqual(pmt_res.status_code, 201, pmt_res.data)
        self.payment_v = Voucher.objects.get(id=pmt_res.data["voucher"]["id"])

        jrn_res = self.client.post(
            "/api/v1/accounting/vouchers/",
            {
                "company_id": str(self.env["company"].id),
                "voucher_type": "JOURNAL",
                "voucher_date": self.today,
                "narration": "Initial journal narration",
                "entries": [
                    {"ledger_id": str(self.env["expense"].id), "debit_amount": "250.00", "credit_amount": "0.00"},
                    {"ledger_id": str(self.env["cash"].id), "debit_amount": "0.00", "credit_amount": "250.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(jrn_res.status_code, 201, jrn_res.data)
        self.journal_v = Voucher.objects.get(id=jrn_res.data["voucher_id"])

        cn_res = self.client.post(
            "/api/v1/accounting/vouchers/",
            {
                "company_id": str(self.env["company"].id),
                "voucher_type": "CREDIT_NOTE",
                "party_ledger_id": str(self.env["customer"].id),
                "original_invoice_id": str(self.sales_v.id),
                "voucher_date": self.today,
                "narration": "Partial sales return",
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 1, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(cn_res.status_code, 201, cn_res.data)
        self.credit_note_v = Voucher.objects.get(id=cn_res.data["voucher_id"])

    def test_metadata_patch_succeeds_for_all_posted_voucher_types_without_reposting(self):
        new_due = (datetime.date.today() + datetime.timedelta(days=15)).isoformat()
        for v in (self.sales_v, self.purchase_v, self.payment_v, self.receipt_v, self.journal_v, self.credit_note_v):
            entry_count_before = LedgerEntry.objects.filter(voucher=v).count()
            stock_before = Product.objects.get(id=self.env["prod_a"].id).stock_quantity
            res = self.client.patch(
                f"/api/v1/accounting/vouchers/detail/{v.id}/",
                {
                    "version": v.version,
                    "narration": f"Updated metadata for {v.voucher_type}",
                    "reference_number": f"META-{v.voucher_type[:3]}",
                    "due_date": new_due,
                },
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_200_OK, f"{v.voucher_type} failed: {res.data}")
            self.assertEqual(res.data["voucher"]["version"], v.version + 1)
            self.assertIn("ETag", res)
            self.assertEqual(res["X-Voucher-Version"], str(v.version + 1))

            v.refresh_from_db()
            self.assertEqual(v.narration, f"Updated metadata for {v.voucher_type}")
            self.assertEqual(v.reference_number, f"META-{v.voucher_type[:3]}")
            self.assertEqual(str(v.due_date), new_due)
            self.assertEqual(LedgerEntry.objects.filter(voucher=v).count(), entry_count_before)
            self.assertEqual(Product.objects.get(id=self.env["prod_a"].id).stock_quantity, stock_before)
            self.assertTrue(
                AuditLog.objects.filter(company=self.env["company"], action="UPDATE", record_id=v.id).exists()
            )

    def test_prohibited_financial_fields_terminal_statuses_and_cross_tenant_blocked(self):
        # Prohibited fields on POSTED vouchers -> 400
        for bad_payload in (
            {"version": self.sales_v.version, "total_amount": "99999.00"},
            {"version": self.sales_v.version, "taxable_amount": "100.00"},
            {"version": self.sales_v.version, "status": "DRAFT"},
            {"version": self.sales_v.version, "entries": []},
            {"version": self.journal_v.version, "amount": "999.00"},
            {"version": self.journal_v.version, "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 1, "rate": "10"}]},
        ):
            target_id = self.journal_v.id if ("amount" in bad_payload or "items" in bad_payload) else self.sales_v.id
            r = self.client.patch(f"/api/v1/accounting/vouchers/detail/{target_id}/", bad_payload, format="json")
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, f"Should block {bad_payload}: {r.data}")

        # Terminal statuses CANCELLED / REVERSED / SUPERSEDED -> 400
        for terminal_status in ("CANCELLED", "REVERSED", "SUPERSEDED"):
            Voucher.objects.filter(id=self.journal_v.id).update(status=terminal_status)
            r_term = self.client.patch(
                f"/api/v1/accounting/vouchers/detail/{self.journal_v.id}/",
                {"version": self.journal_v.version, "narration": "Should fail"},
                format="json",
            )
            self.assertEqual(r_term.status_code, status.HTTP_400_BAD_REQUEST)
        Voucher.objects.filter(id=self.journal_v.id).update(status="POSTED")

        # Cross-tenant PATCH -> 403
        self.client.force_authenticate(user=self.other_env["owner"])
        r_idor = self.client.patch(
            f"/api/v1/accounting/vouchers/detail/{self.sales_v.id}/",
            {"version": self.sales_v.version, "narration": "IDOR attempt"},
            format="json",
        )
        self.assertEqual(r_idor.status_code, status.HTTP_403_FORBIDDEN)


class Stage412DEF02ConcurrentRaceTests(TransactionTestCase):
    """Concurrent OCC race verification on PostgreSQL for DEF-02 metadata PATCH."""

    def test_concurrent_metadata_patch_same_version_returns_200_and_409(self):
        env = _seed_tenant(uuid.uuid4().hex[:6])
        client = APIClient()
        client.force_authenticate(user=env["owner"])
        s_res = client.post(
            "/api/v1/accounting/sales-invoice/",
            {
                "company_id": str(env["company"].id),
                "party_ledger_id": str(env["customer"].id),
                "voucher_date": datetime.date.today().isoformat(),
                "items": [{"product_id": str(env["prod_a"].id), "quantity": 1, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(s_res.status_code, 201)
        vid = s_res.data["voucher_id"]
        initial_ver = Voucher.objects.get(id=vid).version

        def do_patch(idx: int):
            close_old_connections()
            c = APIClient()
            c.force_authenticate(user=env["owner"] if idx == 0 else env["ca"])
            resp = c.patch(
                f"/api/v1/accounting/vouchers/detail/{vid}/",
                {"version": initial_ver, "narration": f"Concurrent Edit {idx}"},
                format="json",
            )
            close_old_connections()
            return resp.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(list(pool.map(do_patch, [0, 1])))
        self.assertEqual(statuses, [200, 409])
        v = Voucher.objects.get(id=vid)
        self.assertEqual(v.version, initial_ver + 1)


class Stage412DEF03SalesPurchaseDupTests(APITestCase):
    """Regression suite for DEF-03: Sales/Purchase/Universal distinct item basket + ref vs exact duplicate."""

    def setUp(self):
        self.env = _seed_tenant(uuid.uuid4().hex[:6])
        self.client = APIClient()
        self.today = datetime.date.today().isoformat()

    def test_sales_distinct_items_and_distinct_refs_allowed_exact_duplicate_blocked_and_override_audited(self):
        self.client.force_authenticate(user=self.env["owner"])

        # 1. Invoice A (prod_a, ₹1,000 + 18% = ₹1,180)
        r1 = self.client.post(
            "/api/v1/accounting/sales-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 2, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(r1.status_code, 201, r1.data)

        # 2. Invoice B (prod_b, exact same total ₹1,180, same day, same party -> different item basket MUST succeed)
        r_diff_item = self.client.post(
            "/api/v1/accounting/sales-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "items": [{"product_id": str(self.env["prod_b"].id), "quantity": 2, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(r_diff_item.status_code, 201, r_diff_item.data)

        # 3. Invoice C (same prod_a basket as r1, but explicit distinct commercial reference PO-900 -> MUST succeed)
        r_diff_ref = self.client.post(
            "/api/v1/accounting/sales-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "reference_number": "PO-900",
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 2, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(r_diff_ref.status_code, 201, r_diff_ref.data)

        # 4. Exact repeat of r1 (no ref, same items, same party, same day) -> 409 Conflict & ZERO orphaned DRAFTs
        before_count = Voucher.objects.filter(company=self.env["company"]).count()
        r_dup = self.client.post(
            "/api/v1/accounting/sales-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 2, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(r_dup.status_code, status.HTTP_409_CONFLICT, r_dup.data)
        self.assertTrue(r_dup.data["requires_confirmation"])
        self.assertEqual(Voucher.objects.filter(company=self.env["company"]).count(), before_count)

        # 5. String "allow_duplicate": "false" still blocked 409
        r_str_false = self.client.post(
            "/api/v1/accounting/sales-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "allow_duplicate": "false",
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 2, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(r_str_false.status_code, status.HTTP_409_CONFLICT)

        # 6. EMPLOYEE attempting override -> 403 Forbidden
        self.client.force_authenticate(user=self.env["employee"])
        r_emp = self.client.post(
            "/api/v1/accounting/sales-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "allow_duplicate": True,
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 2, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(r_emp.status_code, status.HTTP_403_FORBIDDEN)

        # 7. CA override succeeds 201 + logs DUPLICATE_OVERRIDE
        self.client.force_authenticate(user=self.env["ca"])
        r_override = self.client.post(
            "/api/v1/accounting/sales-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "allow_duplicate": True,
                "override_reason": "Second identical truck dispatched separately",
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 2, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(r_override.status_code, 201, r_override.data)
        self.assertTrue(
            AuditLog.objects.filter(
                company=self.env["company"], action="DUPLICATE_OVERRIDE", record_id=r_override.data["voucher_id"]
            ).exists()
        )

    def test_purchase_and_universal_voucher_duplicate_checks(self):
        self.client.force_authenticate(user=self.env["owner"])

        # Purchase without external_invoice_number repeated -> 409; distinct supplier_invoice_number -> 201
        pr1 = self.client.post(
            "/api/v1/accounting/purchase-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["supplier"].id),
                "voucher_date": self.today,
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 2, "rate": "300.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(pr1.status_code, 201, pr1.data)

        pr_dup = self.client.post(
            "/api/v1/accounting/purchase-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["supplier"].id),
                "voucher_date": self.today,
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 2, "rate": "300.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(pr_dup.status_code, 409, pr_dup.data)

        pr_ext = self.client.post(
            "/api/v1/accounting/purchase-invoice/",
            {
                "company_id": str(self.env["company"].id),
                "party_ledger_id": str(self.env["supplier"].id),
                "voucher_date": self.today,
                "supplier_invoice_number": "BILL-UNIQUE-77",
                "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 2, "rate": "300.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(pr_ext.status_code, 201, pr_ext.data)

        # UniversalVoucherAPIView SALES Case 1 duplicate blocked 409 + Case 2 JOURNAL not falsely blocked
        u1 = self.client.post(
            "/api/v1/accounting/vouchers/",
            {
                "company_id": str(self.env["company"].id),
                "voucher_type": "SALES",
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "items": [{"product_id": str(self.env["prod_b"].id), "quantity": 3, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(u1.status_code, 201, u1.data)
        self.assertIn("version", u1.data["voucher"])

        u_dup = self.client.post(
            "/api/v1/accounting/vouchers/",
            {
                "company_id": str(self.env["company"].id),
                "voucher_type": "SALES",
                "party_ledger_id": str(self.env["customer"].id),
                "voucher_date": self.today,
                "items": [{"product_id": str(self.env["prod_b"].id), "quantity": 3, "rate": "500.00", "gst_rate": "18.00"}],
            },
            format="json",
        )
        self.assertEqual(u_dup.status_code, 409, u_dup.data)

        # Distinct same-day JOURNAL entries of identical amount must both succeed
        for idx in (1, 2):
            j_res = self.client.post(
                "/api/v1/accounting/vouchers/",
                {
                    "company_id": str(self.env["company"].id),
                    "voucher_type": "JOURNAL",
                    "voucher_date": self.today,
                    "narration": f"Expense {idx}",
                    "entries": [
                        {"ledger_id": str(self.env["expense"].id), "debit_amount": "150.00", "credit_amount": "0.00"},
                        {"ledger_id": str(self.env["cash"].id), "debit_amount": "0.00", "credit_amount": "150.00"},
                    ],
                },
                format="json",
            )
            self.assertEqual(j_res.status_code, 201, j_res.data)
            self.assertIn("version", j_res.data["voucher"])


class Stage412PhaseFQueryOptimizationTests(APITestCase):
    """Verifies constant-query batched reporting and mathematical bit-for-bit parity."""

    def setUp(self):
        self.env = _seed_tenant(uuid.uuid4().hex[:6])
        self.client = APIClient()
        self.client.force_authenticate(user=self.env["owner"])
        company = self.env["company"]
        debtors_grp = LedgerGroup.objects.get(company=company, name="Sundry Debtors")

        # Seed equal Opening Capital Credit (100,000 Bank + 12,000 Customer Receivables = 112,000 Equity)
        equity_grp = LedgerGroup.objects.create(company=company, name="Capital Account", nature="EQUITY")
        Ledger.objects.create(
            company=company,
            group=equity_grp,
            name="Proprietor Capital",
            ledger_type="GENERAL",
            opening_balance=Decimal("112000.00"),
            opening_balance_type="CREDIT",
        )

        # Create 15 extra customer ledgers + 15 sales invoices + 5 receipts (20+ ledgers/vouchers total)
        today = datetime.date.today()
        prior = today - datetime.timedelta(days=40)
        customers = []
        for i in range(15):
            cust = Ledger.objects.create(
                company=company,
                group=debtors_grp,
                name=f"Batch Cust {i}",
                ledger_type="CUSTOMER",
                state_code="27",
                opening_balance=Decimal(str(100 * (i + 1))),
                opening_balance_type="DEBIT",
            )
            customers.append(cust)
            r = self.client.post(
                "/api/v1/accounting/sales-invoice/",
                {
                    "company_id": str(company.id),
                    "party_ledger_id": str(cust.id),
                    "voucher_date": (prior if i < 5 else today).isoformat(),
                    "items": [{"product_id": str(self.env["prod_a"].id), "quantity": 1 + (i % 3), "rate": "500.00", "gst_rate": "18.00"}],
                },
                format="json",
            )
            self.assertEqual(r.status_code, 201)

    def test_batched_balances_match_per_ledger_and_eliminate_n_plus_1(self):
        company = self.env["company"]
        today = datetime.date.today()
        fy_start = FinancialStatementsService.get_fiscal_year_start(today)
        ledgers = list(Ledger.objects.filter(company=company, is_active=True).select_related("group"))

        # 1. Exact parity check across ranged [fy_start, today] AND cumulative (None, today)
        batched_range = PeriodBalanceService.calculate_all_ledger_period_balances(company, fy_start, today, ledgers=ledgers)
        batched_cum = PeriodBalanceService.calculate_all_ledger_period_balances(company, None, today, ledgers=ledgers)
        for l in ledgers:
            single_range = PeriodBalanceService.calculate_ledger_period_balance(l, fy_start, today)
            single_cum = PeriodBalanceService.calculate_ledger_period_balance(l, None, today)
            self.assertEqual(batched_range[l.id], single_range, f"Range mismatch on ledger {l.name}")
            self.assertEqual(batched_cum[l.id], single_cum, f"Cumulative mismatch on ledger {l.name}")

        # 2. Constant query-count verification (independent of N=20+ ledgers/invoices)
        with CaptureQueriesContext(connection) as pl_ctx:
            pl = FinancialStatementsService.generate_profit_and_loss(company, fy_start, today)
        self.assertLessEqual(len(pl_ctx), 15, f"P&L executed {len(pl_ctx)} queries!")
        self.assertIn("profit_and_loss", pl)

        with CaptureQueriesContext(connection) as bs_ctx:
            bs = FinancialStatementsService.generate_balance_sheet(company, today)
        self.assertLessEqual(len(bs_ctx), 25, f"Balance Sheet executed {len(bs_ctx)} queries!")
        self.assertTrue(bs["is_balanced"])

        with CaptureQueriesContext(connection) as ag_ctx:
            aging = PaymentAllocationService.get_aging_analysis(company, "CUSTOMER", as_of_date=today)
        self.assertLessEqual(len(ag_ctx), 8, f"Receivables Aging executed {len(ag_ctx)} queries!")
        self.assertEqual(len(aging["parties"]), 15)
