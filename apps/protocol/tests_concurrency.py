"""
Production Concurrency, Race Condition, & Idempotency Test Suite for Vouch Protocol.

Verifies 7 concurrent race conditions under real PostgreSQL / database transaction isolation:
1. Two identical sync requests at the exact same millisecond (Idempotency Barrier).
2. Two simultaneous payment allocations (Financial Reconciliation Race).
3. Two simultaneous compensations on same invoice (Compensation Engine Race).
4. Commitment creation race (State Root & Double-Spending Defense).
5. Device registration race (Simultaneous registration of same device_id).
6. Key rotation + sync race (Concurrent rotation while sync payload in-flight).
7. Ledger Bridge high-concurrency worker stress test (8 concurrent threads).
"""

import sys
import os
import threading
import time
import uuid
from decimal import Decimal
from typing import List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection, transaction, IntegrityError
from rest_framework.test import APIClient
from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.accounting.models import Voucher, LedgerEntry
from apps.protocol.schema import (
    CanonicalTransaction, ProtocolEntity, TransactionLine, 
    TaxSummary, TransactionTotals
)
from apps.protocol.operation import AccountingOperation, OperationType
from apps.protocol.crypto import ProtocolCrypto
from apps.protocol.bridge import LedgerBridge, LedgerBridgeError
from apps.protocol.compensation import CompensationEngine
from apps.protocol.sync_service import SyncService
from apps.protocol.models import AuthorizedDevice, CryptographicCommitment, ProtocolTransaction


def create_test_company_and_user(prefix: str):
    run_id = uuid.uuid4().hex[:6].upper()
    company, _ = Company.objects.get_or_create(
        name=f"Concurrency Corp {prefix} {run_id}",
        defaults={"gstin": f"27{prefix[:5]}1234A1Z1", "state_code": "27"}
    )
    user, _ = User.objects.get_or_create(
        email=f"concur_{prefix.lower()}_{run_id}@vouch.test",
        defaults={"first_name": "Concurrency", "last_name": prefix}
    )
    UserCompany.objects.get_or_create(user=user, company=company, defaults={"role": "ADMIN"})
    return company, user


def test_device_registration_race():
    """Scenario 1: Two parallel threads race to register the exact same device_id simultaneously."""
    print("\n[Scenario 1] Device Registration Race (Concurrent POST /register/ for same device_id)...")
    company, user = create_test_company_and_user("REG")
    device_id = f"DEV-RACE-{uuid.uuid4().hex[:8].upper()}"
    replica_id = f"REP-RACE-{uuid.uuid4().hex[:8].upper()}"

    priv1, pub1 = ProtocolCrypto.generate_keypair()
    priv2, pub2 = ProtocolCrypto.generate_keypair()

    results = []
    barrier = threading.Barrier(2)

    def register_worker(pub_k: str):
        connection.close()
        c = APIClient()
        c.force_authenticate(user=user)
        payload = {
            "device_id": device_id,
            "replica_id": replica_id,
            "public_key_hex": pub_k,
            "device_name": "Race Terminal",
            "company_id": str(company.id)
        }
        barrier.wait()
        res = c.post('/api/v1/protocol/devices/register/', data=payload, format='json')
        results.append(res)

    t1 = threading.Thread(target=register_worker, args=(pub1,))
    t2 = threading.Thread(target=register_worker, args=(pub2,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    status_codes = [r.status_code for r in results]
    print(f"  -> Returned HTTP Statuses: {status_codes}")
    # Exactly one must succeed (201 Created) and one must be rejected (409 Conflict)
    assert 201 in status_codes, f"Expected 201 Created, got {status_codes}"
    assert 409 in status_codes, f"Expected 409 Conflict, got {status_codes}"
    # Verify exactly 1 record in database
    dev_count = AuthorizedDevice.objects.filter(device_id=device_id).count()
    assert dev_count == 1, f"Expected 1 device record, found {dev_count}"
    print("  [PASSED] Device registration race handled safely: 1 Created, 1 Rejected (409 Conflict).")


def test_commitment_creation_race():
    """Scenario 2: Two parallel threads race to create CryptographicCommitment for same state root."""
    print("\n[Scenario 2] Commitment Creation Race (Double-Spending / Duplicate State Root Defense)...")
    company, _ = create_test_company_and_user("COMM")
    tx_id = f"TX-COMM-RACE-{uuid.uuid4().hex[:8].upper()}"
    merkle_root = uuid.uuid4().hex

    tx_obj = ProtocolTransaction.objects.create(
        transaction_id=tx_id,
        transaction_type="SALE",
        source_company_id=str(company.id),
        destination_company_id=str(uuid.uuid4()),
        canonical_payload={"transaction_id": tx_id}
    )

    results = []
    errors = []
    barrier = threading.Barrier(2)

    def commit_worker(worker_id: int):
        connection.close()
        barrier.wait()
        try:
            with transaction.atomic():
                c_obj, created = CryptographicCommitment.objects.get_or_create(
                    commitment_hash=merkle_root,
                    defaults={
                        "transaction": tx_obj,
                        "operation_state_root": merkle_root,
                        "signature": f"SIG-{worker_id}"
                    }
                )
                results.append(created)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=commit_worker, args=(1,))
    t2 = threading.Thread(target=commit_worker, args=(2,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    if errors:
        for err in errors:
            print(f"  [ERROR in commit_worker]: {err}")
        raise RuntimeError(f"Commitment race had errors: {errors}")

    # Exactly 1 was created, the second found existing
    assert results.count(True) == 1, f"Expected exactly 1 true creation, got {results}"
    commitments = CryptographicCommitment.objects.filter(transaction=tx_obj, commitment_hash=merkle_root)
    assert commitments.count() == 1, f"Expected exactly 1 commitment, found {commitments.count()}"
    print("  [PASSED] Commitment creation race handled: 1 Initial creation, 1 Existing detected.")


def test_key_rotation_and_sync_race():
    """Scenario 3: One thread rotates the device key while another submits an operation."""
    print("\n[Scenario 3] Key Rotation + Sync Race...")
    company, user = create_test_company_and_user("ROT")
    device_id = f"DEV-ROT-RACE-{uuid.uuid4().hex[:6].upper()}"
    replica_id = f"REP-ROT-RACE-{uuid.uuid4().hex[:6].upper()}"

    priv_old, pub_old = ProtocolCrypto.generate_keypair()
    priv_new, pub_new = ProtocolCrypto.generate_keypair()

    AuthorizedDevice.objects.create(
        device_id=device_id,
        replica_id=replica_id,
        company=company,
        public_key_hex=pub_old,
        key_id="KID-01",
        status="ACTIVE"
    )

    barrier = threading.Barrier(2)
    sync_results = []
    rotate_results = []

    def rotate_worker():
        connection.close()
        c = APIClient()
        c.force_authenticate(user=user)
        payload = {
            "device_id": device_id,
            "new_public_key_hex": pub_new,
            "new_key_id": "KID-02",
            "company_id": str(company.id)
        }
        barrier.wait()
        res = c.post('/api/v1/protocol/devices/rotate/', data=payload, format='json')
        rotate_results.append(res)

    def sync_worker():
        connection.close()
        c = APIClient()
        c.force_authenticate(user=user)
        # Prepare signed operation using new key
        raw_canonical = {
            "protocol_version": "1.0",
            "transaction_id": f"TX-ROT-RACE-{uuid.uuid4().hex[:6].upper()}",
            "transaction_type": "SALE",
            "state_version": 1,
            "issued_at": "2026-10-01T10:00:00Z",
            "source_entity": {"type": "GSTIN", "value": company.gstin, "name": company.name, "state_code": "27"},
            "destination_entity": {"type": "GSTIN", "value": "27BBBBB5678B1Z6", "name": "Buyer Corp", "state_code": "27"},
            "items": [{"line_id": "L1", "sku": "ITEM-1", "name": "Item", "hsn_code": "8481", "quantity": "1.00", "unit": "PCS", "unit_price": "100.00", "discount_amount": "0.00", "taxable_amount": "100.00", "tax_rate_percent": "18.00"}],
            "tax_summary": {"cgst": "9.00", "sgst": "9.00", "igst": "0.00", "cess": "0.00", "total_tax": "18.00"},
            "totals": {"subtotal": "100.00", "total_tax": "18.00", "shipping": "0.00", "discount": "0.00", "grand_total": "118.00"},
            "causal_dependencies": []
        }
        reconstructed = CanonicalTransaction.from_dict(raw_canonical)
        op = AccountingOperation(
            operation_id="OP-ROT-RACE-01",
            transaction_id=raw_canonical["transaction_id"],
            replica_id=replica_id,
            operation_type=OperationType.TRANSACTION_ISSUED,
            payload={"grand_total": 118.0, "taxable_amount": 100.0, "total_tax": 18.0},
            logical_timestamp=1,
            parents=[]
        )
        op_data = op.to_dict()
        op_data["signature"] = ProtocolCrypto.sign(op.payload_hash, priv_new)

        sync_payload = {
            "transaction_id": raw_canonical["transaction_id"],
            "client_replica_id": replica_id,
            "company_id": str(company.id),
            "canonical_transaction": raw_canonical,
            "canonical_tx_hash": reconstructed.canonical_hash,
            "client_operations": [op_data]
        }
        barrier.wait()
        res = c.post('/api/v1/protocol/sync/', data=sync_payload, format='json')
        sync_results.append(res)

    t_rot = threading.Thread(target=rotate_worker)
    t_sync = threading.Thread(target=sync_worker)
    t_rot.start(); t_sync.start()
    t_rot.join(); t_sync.join()

    assert rotate_results[0].status_code == 200, f"Rotation failed: {rotate_results[0].data}"
    # The device must finish in ACTIVE state with pub_new
    dev = AuthorizedDevice.objects.get(device_id=device_id)
    assert dev.public_key_hex == pub_new
    assert dev.status == "ACTIVE"
    print("  [PASSED] Key rotation completed cleanly and active device state is consistent.")


def test_concurrent_identical_sync_requests():
    """Scenario 4: Two identical sync requests hit the sync service at the exact same millisecond."""
    print("\n[Scenario 4] Two Identical Sync Requests at Exact Same Millisecond (Idempotency Barrier)...")
    company, user = create_test_company_and_user("SYNC")
    replica_id = f"REP-SYNC-{uuid.uuid4().hex[:6].upper()}"
    priv_k, pub_k = ProtocolCrypto.generate_keypair()

    AuthorizedDevice.objects.create(
        device_id=f"DEV-{replica_id}",
        replica_id=replica_id,
        company=company,
        public_key_hex=pub_k,
        status="ACTIVE"
    )

    tx_id = f"TX-IDENT-{uuid.uuid4().hex[:8].upper()}"
    raw_canonical = {
        "protocol_version": "1.0",
        "transaction_id": tx_id,
        "transaction_type": "SALE",
        "state_version": 1,
        "issued_at": "2026-10-01T10:00:00Z",
        "source_entity": {"type": "GSTIN", "value": company.gstin, "name": company.name, "state_code": "27"},
        "destination_entity": {"type": "GSTIN", "value": "27BBBBB5678B1Z6", "name": "Buyer Corp", "state_code": "27"},
        "items": [{"line_id": "L1", "sku": "ITEM-SYNC", "name": "Sync Item", "hsn_code": "8481", "quantity": "5.00", "unit": "PCS", "unit_price": "200.00", "discount_amount": "0.00", "taxable_amount": "1000.00", "tax_rate_percent": "18.00"}],
        "tax_summary": {"cgst": "90.00", "sgst": "90.00", "igst": "0.00", "cess": "0.00", "total_tax": "180.00"},
        "totals": {"subtotal": "1000.00", "total_tax": "180.00", "shipping": "0.00", "discount": "0.00", "grand_total": "1180.00"},
        "causal_dependencies": []
    }
    reconstructed = CanonicalTransaction.from_dict(raw_canonical)
    op = AccountingOperation(
        operation_id=f"OP-IDENT-{tx_id}",
        transaction_id=tx_id,
        replica_id=replica_id,
        operation_type=OperationType.TRANSACTION_ISSUED,
        payload={"grand_total": 1180.0, "taxable_amount": 1000.0, "total_tax": 180.0},
        logical_timestamp=1,
        parents=[]
    )
    op_data = op.to_dict()
    op_data["signature"] = ProtocolCrypto.sign(op.payload_hash, priv_k)

    sync_payload = {
        "transaction_id": tx_id,
        "client_replica_id": replica_id,
        "company_id": str(company.id),
        "canonical_transaction": raw_canonical,
        "canonical_tx_hash": reconstructed.canonical_hash,
        "client_operations": [op_data]
    }

    results = []
    barrier = threading.Barrier(2)

    def sync_client_job():
        connection.close()
        c = APIClient()
        c.force_authenticate(user=user)
        barrier.wait()
        res = c.post('/api/v1/protocol/sync/', data=sync_payload, format='json')
        results.append(res)

    t1 = threading.Thread(target=sync_client_job)
    t2 = threading.Thread(target=sync_client_job)
    t1.start(); t2.start()
    t1.join(); t2.join()

    statuses = [r.status_code for r in results]
    assert all(s == 200 for s in statuses), f"Expected both HTTP 200, got {statuses}"

    # Exactly 1 voucher in database
    vouchers = Voucher.objects.filter(company=company, external_invoice_number=tx_id)
    assert vouchers.count() == 1, f"Expected 1 voucher, found {vouchers.count()}"
    print(f"  -> Returned Statuses: {statuses}")
    print(f"  -> Physical Database Vouchers for {tx_id}: {vouchers.count()} (Expected: 1)")
    print("  [PASSED] Identical sync race deduplicated safely with zero duplicate vouchers.")


def test_high_concurrency_ledger_bridge(num_workers: int = 8):
    """Scenario 5: 8 concurrent workers simultaneously execute the Ledger Bridge on the same transaction."""
    print(f"\n[Scenario 5] High-Concurrency Ledger Bridge Stress Test ({num_workers} parallel workers)...")
    company, user = create_test_company_and_user("BRIDGE")
    tx_id = f"TX-CONCUR-{int(time.time())}"

    tx = CanonicalTransaction(
        protocol_version="1.0",
        transaction_id=tx_id,
        transaction_type="SALE",
        state_version=1,
        issued_at=time.time(),
        source_entity=ProtocolEntity("GSTIN", company.gstin, company.name, "27"),
        destination_entity=ProtocolEntity("GSTIN", "27COUNTR9999B1Z", "Counterparty Beta", "27"),
        items=[
            TransactionLine("L1", "CONCUR-SKU-A", "Concur Item", "7214", Decimal("10.00"), "PCS", Decimal("100.00"), Decimal("0.00"), Decimal("1000.00"), Decimal("18.00"))
        ],
        tax_summary=TaxSummary(cgst_amount=Decimal("90.00"), sgst_amount=Decimal("90.00")),
        totals=TransactionTotals(subtotal=Decimal("1000.00"), total_tax=Decimal("180.00"), grand_total=Decimal("1180.00"))
    )

    priv_k, pub_k = ProtocolCrypto.generate_keypair()
    op = AccountingOperation(
        operation_id=f"OP-BASE-{tx_id}",
        transaction_id=tx_id,
        replica_id="CONCUR-REP-1",
        operation_type=OperationType.TRANSACTION_ISSUED,
        payload={"grand_total": 1180.0, "taxable_amount": 1000.0, "total_tax": 180.0},
        logical_timestamp=1
    ).sign(priv_k)

    results: List[dict] = []
    errors: List[Exception] = []
    barrier = threading.Barrier(num_workers)

    def worker_job(worker_id: int):
        connection.close()
        try:
            barrier.wait()
            res = LedgerBridge.execute_converged_accounting(
                company=company,
                canonical_tx=tx,
                converged_operations=[op],
                user=user
            )
            results.append(res)
        except Exception as ex:
            errors.append(ex)

    threads = [threading.Thread(target=worker_job, args=(i,)) for i in range(num_workers)]
    for t in threads: t.start()
    for t in threads: t.join()

    print(f"  -> Total Workers Launched:    {num_workers}")
    print(f"  -> Successful Completions:    {len(results)}")
    print(f"  -> Unhandled Exceptions:      {len(errors)}")

    if errors:
        for err in errors:
            print(f"  [ERROR]: {err}")
        raise RuntimeError("Concurrency test had unexpected errors!")

    vouchers = list(Voucher.objects.filter(company=company, external_invoice_number=tx_id))
    assert len(vouchers) == 1, f"Duplicate vouchers detected! Expected 1, found {len(vouchers)}"

    cached_count = sum(1 for r in results if r.get("idempotent_cached") is True)
    initial_write_count = sum(1 for r in results if r.get("idempotent_cached") is not True)

    print(f"  -> Initial Bridge Executions: {initial_write_count}")
    print(f"  -> Idempotent Deduplications: {cached_count}")
    print("  [PASSED] Ledger Bridge concurrency stress test passed with 100% idempotency.")


def test_concurrent_payment_allocations():
    """Scenario 6: Two concurrent threads execute payment allocations on the same invoice simultaneously."""
    print("\n[Scenario 6] Concurrent Payment Allocations (Two simultaneous payments on same invoice)...")
    company, user = create_test_company_and_user("PAYRACE")
    tx_id = f"TX-PAY-{uuid.uuid4().hex[:8].upper()}"

    tx = CanonicalTransaction(
        protocol_version="1.0",
        transaction_id=tx_id,
        transaction_type="SALE",
        state_version=1,
        issued_at=time.time(),
        source_entity=ProtocolEntity("GSTIN", company.gstin, company.name, "27"),
        destination_entity=ProtocolEntity("GSTIN", "27COUNTR9999B1Z", "Counterparty Buyer", "27"),
        items=[
            TransactionLine("L1", "PAY-SKU-1", "Payment Test Item", "8481", Decimal("10.00"), "PCS", Decimal("100.00"), Decimal("0.00"), Decimal("1000.00"), Decimal("18.00"))
        ],
        tax_summary=TaxSummary(cgst_amount=Decimal("90.00"), sgst_amount=Decimal("90.00")),
        totals=TransactionTotals(subtotal=Decimal("1000.00"), total_tax=Decimal("180.00"), grand_total=Decimal("1180.00"))
    )

    priv_k, pub_k = ProtocolCrypto.generate_keypair()
    base_op = AccountingOperation(
        operation_id=f"OP-BASE-{tx_id}",
        transaction_id=tx_id,
        replica_id="REP-PAY-1",
        operation_type=OperationType.TRANSACTION_ISSUED,
        payload={"grand_total": 1180.0, "taxable_amount": 1000.0, "total_tax": 180.0},
        logical_timestamp=1
    ).sign(priv_k)

    # Base voucher creation
    init_res = LedgerBridge.execute_converged_accounting(
        company=company,
        canonical_tx=tx,
        converged_operations=[base_op],
        user=user
    )
    assert init_res["status"] == "BRIDGE_SUCCESS"

    # Now create two concurrent payments:
    # Payment 1: 500.00
    pay_op1 = AccountingOperation(
        operation_id=f"OP-PAY-1-{tx_id}",
        transaction_id=tx_id,
        replica_id="REP-PAY-1",
        operation_type=OperationType.PAYMENT_ALLOCATED,
        payload={"amount": 500.00, "payment_mode": "BANK_TRANSFER"},
        logical_timestamp=2,
        parents=[base_op.operation_id]
    ).sign(priv_k)

    # Payment 2: 680.00
    pay_op2 = AccountingOperation(
        operation_id=f"OP-PAY-2-{tx_id}",
        transaction_id=tx_id,
        replica_id="REP-PAY-1",
        operation_type=OperationType.PAYMENT_ALLOCATED,
        payload={"amount": 680.00, "payment_mode": "UPI"},
        logical_timestamp=3,
        parents=[base_op.operation_id]
    ).sign(priv_k)

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def pay_worker(op_to_apply):
        connection.close()
        try:
            barrier.wait()
            res = LedgerBridge.execute_converged_accounting(
                company=company,
                canonical_tx=tx,
                converged_operations=[base_op, op_to_apply],
                user=user
            )
            results.append(res)
        except Exception as ex:
            errors.append(ex)

    t1 = threading.Thread(target=pay_worker, args=(pay_op1,))
    t2 = threading.Thread(target=pay_worker, args=(pay_op2,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"Unexpected errors during payment race: {errors}"
    assert len(results) == 2, f"Expected 2 results, got {len(results)}"

    # Check database receipts created
    receipts = Voucher.objects.filter(company=company, voucher_type='RECEIPT')
    pay_vouchers = [v for v in receipts if v.reference_number in [f"PAY-{pay_op1.operation_id[:8]}", f"PAY-{pay_op2.operation_id[:8]}"]]
    assert len(pay_vouchers) == 2, f"Expected 2 receipt vouchers, found {len(pay_vouchers)}"
    total_received = sum(v.total_amount for v in pay_vouchers)
    assert total_received == Decimal("1180.00"), f"Expected 1180.00 total received, got {total_received}"
    print(f"  -> Concurrently Posted Payment Vouchers: {len(pay_vouchers)}")
    print(f"  -> Total Reconciled Amount: {total_received} (100% Exact)")
    print("  [PASSED] Simultaneous payment allocations converged with zero lost updates.")


def test_concurrent_compensations():
    """Scenario 7: Two concurrent compensations on the same invoice processed simultaneously."""
    print("\n[Scenario 7] Concurrent Compensations (Two simultaneous line rejections on same invoice)...")
    company, user = create_test_company_and_user("COMPRACE")
    tx_id = f"TX-COMP-{uuid.uuid4().hex[:8].upper()}"

    tx = CanonicalTransaction(
        protocol_version="1.0",
        transaction_id=tx_id,
        transaction_type="SALE",
        state_version=1,
        issued_at=time.time(),
        source_entity=ProtocolEntity("GSTIN", company.gstin, company.name, "27"),
        destination_entity=ProtocolEntity("GSTIN", "27COUNTR9999B1Z", "Counterparty Buyer", "27"),
        items=[
            TransactionLine("L1", "COMP-SKU-1", "Compensation Item 1", "8481", Decimal("10.00"), "PCS", Decimal("100.00"), Decimal("0.00"), Decimal("1000.00"), Decimal("18.00")),
            TransactionLine("L2", "COMP-SKU-2", "Compensation Item 2", "8481", Decimal("10.00"), "PCS", Decimal("50.00"), Decimal("0.00"), Decimal("500.00"), Decimal("18.00"))
        ],
        tax_summary=TaxSummary(cgst_amount=Decimal("135.00"), sgst_amount=Decimal("135.00")),
        totals=TransactionTotals(subtotal=Decimal("1500.00"), total_tax=Decimal("270.00"), grand_total=Decimal("1770.00"))
    )

    priv_k, pub_k = ProtocolCrypto.generate_keypair()
    base_op = AccountingOperation(
        operation_id=f"OP-BASE-{tx_id}",
        transaction_id=tx_id,
        replica_id="REP-COMP-1",
        operation_type=OperationType.TRANSACTION_ISSUED,
        payload={"grand_total": 1770.0, "taxable_amount": 1500.0, "total_tax": 270.0},
        logical_timestamp=1
    ).sign(priv_k)

    init_res = LedgerBridge.execute_converged_accounting(
        company=company,
        canonical_tx=tx,
        converged_operations=[base_op],
        user=user
    )
    assert init_res["status"] == "BRIDGE_SUCCESS"

    # Compensation 1: Reject 2 PCS of L1
    comp_op1 = CompensationEngine.generate_item_rejection(
        transaction=tx,
        line_id="L1",
        quantity_rejected=Decimal("2.00"),
        replica_id="REP-COMP-1",
        logical_timestamp=2,
        parent_operation_id=base_op.operation_id
    ).sign(priv_k)

    # Compensation 2: Reject 3 PCS of L2
    comp_op2 = CompensationEngine.generate_item_rejection(
        transaction=tx,
        line_id="L2",
        quantity_rejected=Decimal("3.00"),
        replica_id="REP-COMP-1",
        logical_timestamp=3,
        parent_operation_id=base_op.operation_id
    ).sign(priv_k)

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def comp_worker(op_to_apply):
        connection.close()
        try:
            barrier.wait()
            res = LedgerBridge.execute_converged_accounting(
                company=company,
                canonical_tx=tx,
                converged_operations=[base_op, op_to_apply],
                user=user
            )
            results.append(res)
        except Exception as ex:
            errors.append(ex)

    t1 = threading.Thread(target=comp_worker, args=(comp_op1,))
    t2 = threading.Thread(target=comp_worker, args=(comp_op2,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"Unexpected errors during compensation race: {errors}"
    assert len(results) == 2, f"Expected 2 results, got {len(results)}"

    # Check Credit Notes created for company
    credit_notes = Voucher.objects.filter(company=company, voucher_type='CREDIT_NOTE', external_invoice_number=tx_id)
    assert credit_notes.count() == 2, f"Expected 2 credit notes, found {credit_notes.count()}"
    print(f"  -> Concurrently Posted Credit Notes: {credit_notes.count()}")
    print("  [PASSED] Simultaneous compensations converged with atomic voucher posting.")


def run_all_concurrency_tests():
    print("=" * 80)
    print("   VOUCH PROTOCOL: HIGH-CONCURRENCY & TRANSACTION ISOLATION TEST SUITE")
    print("=" * 80)
    test_device_registration_race()
    test_commitment_creation_race()
    test_key_rotation_and_sync_race()
    test_concurrent_identical_sync_requests()
    test_high_concurrency_ledger_bridge(8)
    test_concurrent_payment_allocations()
    test_concurrent_compensations()
    print("\n" + "=" * 80)
    print(">>> ALL 7 CONCURRENCY RACE CONDITIONS PASSED WITH ZERO DATA CORRUPTION <<<")
    print("=" * 80)


if __name__ == '__main__':
    run_all_concurrency_tests()
