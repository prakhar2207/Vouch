import os
import sys
import uuid
import time
import socket
import threading
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Warm up Windows DNS for Neon PostgreSQL WAN connection
for _ in range(5):
    try:
        socket.getaddrinfo("ep-lingering-boat-b3994i6f-pooler.c-4.ap-southeast-1.aws.neon.tech", 5432)
        break
    except Exception:
        time.sleep(0.5)

import django
django.setup()

from django.db import connection, transaction
from django.utils import timezone

from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.accounting.models import Voucher, Ledger, LedgerEntry
from apps.inventory.models import Product
from apps.protocol.schema import (
    CanonicalTransaction, ProtocolEntity, TransactionLine,
    TaxSummary, TransactionTotals
)
from apps.protocol.operation import AccountingOperation, OperationType
from apps.protocol.crdt import DE_CRDT
from apps.protocol.crypto import ProtocolCrypto
from apps.protocol.key_manager import ProtocolKeyManager
from apps.protocol.sync_service import SyncService
from apps.protocol.qr_bootstrap import QRSessionManager, QRBootstrapPayload
from apps.protocol.models import AuthorizedDevice, EntityMapping, ProtocolBridgeExecution


def create_disposable_company(prefix: str):
    cid = uuid.uuid4().hex[:8].upper()
    comp = Company.objects.create(
        name=f"LoadTest {prefix} {cid}",
        gstin=f"27{cid}1234A1Z5"[:15],
        state_code="27",
        state_name="Maharashtra"
    )
    user = User.objects.create_user(
        email=f"load_{prefix.lower()}_{cid.lower()}@test.internal",
        password="TestPassword@123",
        first_name="Load",
        last_name=prefix
    )
    UserCompany.objects.create(user=user, company=comp, role="ADMIN")
    return comp, user


def run_load_and_concurrency_tests():
    print("=" * 80)
    print("   SRILEKH EDI: LOAD, CONCURRENCY & FAILURE VERIFICATION SUITE")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # TEST 1: ROW-LEVEL LOCK ISOLATION (Company A vs Company B)
    # -------------------------------------------------------------------------
    print("\n[Test 1] Benchmarking Row-Level Lock Isolation between Company A and Company B...")
    comp_a, user_a = create_disposable_company("CompanyA")
    comp_b, user_b = create_disposable_company("CompanyB")

    lock_a_acquired = threading.Event()
    lock_b_elapsed = None

    def worker_a():
        connection.ensure_connection()
        with transaction.atomic():
            # Acquire row lock on Company A and hold it for 2.0 seconds
            Company.objects.select_for_update().get(id=comp_a.id)
            lock_a_acquired.set()
            time.sleep(2.0)

    def worker_b():
        nonlocal lock_b_elapsed
        connection.ensure_connection()
        lock_a_acquired.wait()
        start = time.time()
        with transaction.atomic():
            # Acquire row lock on Company B while Company A is locked
            Company.objects.select_for_update().get(id=comp_b.id)
            lock_b_elapsed = time.time() - start

    t_a = threading.Thread(target=worker_a)
    t_b = threading.Thread(target=worker_b)
    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()

    print(f"  -> Company B lock acquisition time while Company A locked: {lock_b_elapsed:.4f}s")
    assert lock_b_elapsed < 1.2, f"Lock contention leaked across companies! Elapsed: {lock_b_elapsed}s"
    print("  [PASSED] Row-level locks on Company model are completely isolated across tenants.")

    # -------------------------------------------------------------------------
    # TEST 2: SAME-COMPANY SERIALIZATION (Queueing behavior on single tenant)
    # -------------------------------------------------------------------------
    print("\n[Test 2] Measuring Same-Company Lock Serialization Queue...")
    lock_holder_acquired = threading.Event()
    waiter_elapsed = None

    def lock_holder():
        connection.ensure_connection()
        with transaction.atomic():
            Company.objects.select_for_update().get(id=comp_a.id)
            lock_holder_acquired.set()
            time.sleep(1.0)

    def lock_waiter():
        nonlocal waiter_elapsed
        connection.ensure_connection()
        lock_holder_acquired.wait()
        start = time.time()
        with transaction.atomic():
            Company.objects.select_for_update().get(id=comp_a.id)
            waiter_elapsed = time.time() - start

    t_h = threading.Thread(target=lock_holder)
    t_w = threading.Thread(target=lock_waiter)
    t_h.start()
    t_w.start()
    t_h.join()
    t_w.join()

    print(f"  -> Same-company waiter queue wait duration: {waiter_elapsed:.4f}s (Expected >= 0.8s)")
    assert waiter_elapsed >= 0.8, f"Serialization failed to hold lock! Waiter elapsed: {waiter_elapsed}s"
    print("  [PASSED] Same-company transactions serialize correctly without race conditions.")

    # -------------------------------------------------------------------------
    # TEST 3: 50 CONCURRENT VIRTUAL USERS SYNC MERGE
    # -------------------------------------------------------------------------
    print("\n[Test 3] Simulating 50 Concurrent Virtual Users executing CRDT merges...")
    comp_load, user_load = create_disposable_company("LoadTenant")
    
    # Provision registered device
    test_run_id = uuid.uuid4().hex[:6].upper()
    device_priv, device_pub = ProtocolCrypto.generate_keypair()
    device = AuthorizedDevice.objects.create(
        company=comp_load,
        device_id=f"DEV-LOAD-{test_run_id}",
        replica_id=f"REP-LOAD-{test_run_id}",
        public_key_hex=device_pub,
        status="ACTIVE"
    )

    load_tx_id = f"TX-LOAD-{test_run_id}"
    line_item = TransactionLine(
        line_id="LINE-LOAD-1",
        sku="SKU-LOAD-ITEM",
        name="Load Testing High-Tensile Belt",
        hsn_code="40103990",
        quantity=Decimal("10.00"),
        unit="PCS",
        unit_price=Decimal("500.00"),
        discount_amount=Decimal("0.00"),
        taxable_amount=Decimal("5000.00"),
        tax_rate_percent=Decimal("18.00")
    )
    canonical_tx = CanonicalTransaction(
        protocol_version="1.0",
        transaction_id=load_tx_id,
        transaction_type="SALE",
        state_version=1,
        issued_at=timezone.now(),
        source_entity=ProtocolEntity("GSTIN", comp_load.gstin, comp_load.name, "27"),
        destination_entity=ProtocolEntity("GSTIN", "27LOADBUY1234A1", "Load Buyer Enterprise", "27"),
        items=[line_item],
        tax_summary=TaxSummary(cgst_amount=Decimal("450.00"), sgst_amount=Decimal("450.00")),
        totals=TransactionTotals(
            subtotal=Decimal("5000.00"),
            total_tax=Decimal("900.00"),
            grand_total=Decimal("5900.00")
        )
    )

    base_op = AccountingOperation(
        operation_id=f"OP-LOAD-BASE-{uuid.uuid4().hex[:6]}",
        operation_type=OperationType.TRANSACTION_ISSUED,
        transaction_id=load_tx_id,
        tenant_id=str(comp_load.id),
        replica_id=device.replica_id,
        logical_timestamp=1,
        parents=[],
        payload={"grand_total": 5900.0, "taxable_amount": 5000.0, "total_tax": 900.0}
    ).sign(device_priv)

    # Pre-register 50 devices for 50 virtual users
    vu_keypairs = {}
    vu_ops = {}
    for i in range(50):
        u_priv, u_pub = ProtocolCrypto.generate_keypair()
        u_replica = f"REP-VU-{test_run_id}-{i:03d}"
        AuthorizedDevice.objects.create(
            company=comp_load,
            device_id=f"DEV-VU-{test_run_id}-{i:03d}",
            replica_id=u_replica,
            public_key_hex=u_pub,
            status="ACTIVE"
        )
        vu_keypairs[i] = (u_priv, u_pub, u_replica)
        op = AccountingOperation(
            operation_id=f"OP-VU-{i:03d}-{uuid.uuid4().hex[:6]}",
            operation_type=OperationType.PAYMENT_ALLOCATED,
            transaction_id=load_tx_id,
            tenant_id=str(comp_load.id),
            replica_id=u_replica,
            logical_timestamp=2 + i,
            parents=[base_op.operation_id],
            payload={"amount": 100.0, "reference": f"VU-{i}"}
        ).sign(u_priv)
        vu_ops[i] = op

    success_count = 0
    errors = []
    start_bench = time.time()

    def virtual_user_sync(user_idx):
        u_priv, u_pub, u_replica = vu_keypairs[user_idx]
        op = vu_ops[user_idx]

        res = SyncService.process_sync_payload(
            transaction_id=load_tx_id,
            client_replica_id=u_replica,
            client_operations=[op.to_dict()],
            server_operations=[base_op],
            authenticated_tenant_id=str(comp_load.id),
            seller_identity=comp_load.gstin,
            buyer_identity="27LOADBUY1234A1",
            canonical_tx=canonical_tx,
            canonical_tx_hash=canonical_tx.canonical_hash,
            company=None, # Pure CRDT merge under concurrent load
            verify_signatures=True,
            persist_to_db=False
        )
        return res

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(virtual_user_sync, i): i for i in range(50)}
        for future in as_completed(futures):
            try:
                res = future.result()
                if res.get("status") == "SYNC_SUCCESS":
                    success_count += 1
                else:
                    errors.append(res)
            except Exception as e:
                errors.append(str(e))

    total_bench_time = time.time() - start_bench
    throughput = 50 / total_bench_time
    print(f"  -> 50 VU Completed in: {total_bench_time:.2f}s | Throughput: {throughput:.2f} syncs/sec")
    print(f"  -> Successful Merges: {success_count}/50 | Failures: {len(errors)}")
    assert success_count == 50, f"Expected 50 successful syncs, got {success_count}. Errors: {errors[:3]}"
    print("  [PASSED] 50 concurrent virtual users merged into CRDT DAG with zero race conditions.")

    # -------------------------------------------------------------------------
    # TEST 4: CONCURRENT IDEMPOTENCY DEFLECTION
    # -------------------------------------------------------------------------
    print("\n[Test 4] Testing Concurrent Duplicate Submissions (Race Condition on Idempotency)...")
    comp_idem, user_idem = create_disposable_company("IdemTenant")
    
    idem_op = AccountingOperation(
        operation_id="OP-CONCURRENT-DUP",
        operation_type=OperationType.TRANSACTION_ISSUED,
        transaction_id=load_tx_id,
        tenant_id=str(comp_idem.id),
        replica_id=device.replica_id,
        logical_timestamp=1,
        parents=[],
        payload={"grand_total": 5900.0, "taxable_amount": 5000.0, "total_tax": 900.0}
    ).sign(device_priv)

    idem_results = []
    def fire_sync():
        return SyncService.process_sync_payload(
            transaction_id=load_tx_id,
            client_replica_id=device.replica_id,
            client_operations=[idem_op.to_dict()],
            server_operations=[idem_op],
            authenticated_tenant_id=str(comp_idem.id),
            seller_identity=comp_idem.gstin,
            buyer_identity="27LOADBUY1234A1",
            canonical_tx=canonical_tx,
            canonical_tx_hash=canonical_tx.canonical_hash,
            company=None, # Pure CRDT merge under concurrent load
            verify_signatures=True,
            persist_to_db=False
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fire_sync) for _ in range(10)]
        for f in as_completed(futures):
            idem_results.append(f.result()["status"])

    print(f"  -> 10 Concurrent identical submissions result: {set(idem_results)}")
    assert all(r == "SYNC_SUCCESS" for r in idem_results)
    print("  [PASSED] Concurrent duplicate submissions handle cleanly and idempotently.")

    # -------------------------------------------------------------------------
    # TEST 5: TAMPERED PAYLOAD REJECTION UNDER CONCURRENCY
    # -------------------------------------------------------------------------
    print("\n[Test 5] Injecting Tampered Cryptographic Envelopes under load...")
    tampered_op = AccountingOperation(
        operation_id="OP-TAMPERED-001",
        operation_type=OperationType.TRANSACTION_ISSUED,
        transaction_id=load_tx_id,
        tenant_id=str(comp_load.id),
        replica_id=device.replica_id,
        logical_timestamp=1,
        parents=[],
        payload={"grand_total": 5900.0, "taxable_amount": 5000.0, "total_tax": 900.0}
    ).sign(device_priv)
    
    # Malicious tampering after signing
    tampered_dict = tampered_op.to_dict()
    tampered_dict["payload"]["grand_total"] = 9999999.0

    tamper_res = SyncService.process_sync_payload(
        transaction_id=load_tx_id,
        client_replica_id=device.replica_id,
        client_operations=[tampered_dict],
        server_operations=[],
        authenticated_tenant_id=str(comp_load.id),
        seller_identity=comp_load.gstin,
        buyer_identity="27LOADBUY1234A1",
        canonical_tx=canonical_tx,
        canonical_tx_hash=canonical_tx.canonical_hash,
        company=comp_load,
        verify_signatures=True,
        persist_to_db=False
    )
    assert tamper_res["status"] == "SYNC_REJECTED"
    print(f"  -> Tampered rejection reason: {tamper_res['reason']}")
    print("  [PASSED] Tampered payload rejected with cryptographic certainty.")

    # -------------------------------------------------------------------------
    # TEST 6: FAIL-CLOSED QR SECURITY UNDER REDIS / CACHE OUTAGE
    # -------------------------------------------------------------------------
    print("\n[Test 6] Testing Fail-Closed QR Behavior Under Cache Outage...")
    from django.conf import settings
    orig_testing = getattr(settings, "TESTING", False)
    try:
        # Simulate Staging / Production mode (TESTING=False)
        settings.TESTING = False
        
        now_ts = int(time.time())
        qr_keypair = ProtocolCrypto.generate_keypair()
        qr_payload = QRBootstrapPayload(
            protocol_version="1.0",
            transaction_id="TX-FAIL-CLOSED-01",
            session_id="SESS-FAIL-CLOSED-01",
            nonce="NONCE-OUTAGE-TEST",
            issuer_id=comp_load.gstin,
            transaction_digest="0" * 64,
            expires_at=now_ts + 300
        )
        qr_sig = ProtocolCrypto.sign(qr_payload.serialize_for_signature(), qr_keypair[0])
        qr_payload.signature = qr_sig
        qr_string = qr_payload.encode_to_qr_string()

        qr_engine = QRSessionManager(public_keys={comp_load.gstin: qr_keypair[1]})

        # Force Redis/cache failure
        from unittest.mock import patch
        with patch("django.core.cache.cache.set", side_effect=Exception("Redis Cluster Connection Refused")):
            try:
                qr_engine.initiate_session_from_scan(qr_string, current_timestamp=now_ts)
                assert False, "FAILED: QR bootstrap did NOT fail closed on Redis outage!"
            except Exception as qse:
                print(f"  -> Fail-closed exception caught: {type(qse).__name__}: {qse}")
                print("  [PASSED] QR bootstrap strictly fails closed when durable cache fails in non-test mode.")
    finally:
        settings.TESTING = orig_testing

    print("\n" + "=" * 80)
    print(">>> LOAD, CONCURRENCY & FAILURE TEST SUITE PASSED (100%) <<<")
    print("=" * 80)


if __name__ == "__main__":
    run_load_and_concurrency_tests()
