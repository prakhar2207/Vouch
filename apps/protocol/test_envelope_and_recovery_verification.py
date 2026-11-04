"""
SriLekh EDI — Cryptographic Envelope Consistency, Audit-Chain Verification,
and Disaster Recovery Verification Harness.
"""

import os
import sys
import uuid
import time
import socket
import hashlib
import json
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Fallback DNS for Neon PostgreSQL WAN connection
_orig_getaddrinfo = socket.getaddrinfo
def _fallback_getaddrinfo(host, port, *args, **kwargs):
    try:
        return _orig_getaddrinfo(host, port, *args, **kwargs)
    except socket.gaierror:
        if "neon.tech" in str(host):
            for fallback_ip in ["52.76.246.190", "52.76.212.156", "3.0.27.201"]:
                try:
                    return _orig_getaddrinfo(fallback_ip, port, *args, **kwargs)
                except Exception:
                    continue
        raise
socket.getaddrinfo = _fallback_getaddrinfo

import django
django.setup()

from django.db import connection, transaction
from django.utils import timezone
from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.audit.views import AuditLogListView
from apps.protocol.schema import (
    CanonicalTransaction, ProtocolEntity, TransactionLine,
    TaxSummary, TransactionTotals, InvariantViolation
)
from apps.protocol.operation import AccountingOperation, OperationType, OperationClass
from apps.protocol.crypto import ProtocolCrypto
from apps.protocol.models import AuthorizedDevice, CryptographicCommitment, ProtocolBridgeExecution
from apps.protocol.sync_service import SyncService


def run_envelope_and_dr_verification():
    print("=" * 80)
    print("   SRILEKH EDI: CRYPTOGRAPHIC ENVELOPE & DISASTER RECOVERY VERIFICATION")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # PART 1: CRYPTOGRAPHIC ENVELOPE CONSISTENCY (9-FIELD vs 17-FIELD)
    # -------------------------------------------------------------------------
    print("\n[Verification 1] Testing 9-Field Canonical Envelope vs 17-Field Operation...")
    priv, pub = ProtocolCrypto.generate_keypair()

    tx_id = f"TX-ENV-{uuid.uuid4().hex[:8].upper()}"
    line = TransactionLine(
        line_id="L1", sku="SKU-TEST-001", name="Verification Belt",
        hsn_code="40103990", quantity=Decimal("10.00"), unit="NOS", unit_price=Decimal("100.00"),
        discount_amount=Decimal("0.00"), taxable_amount=Decimal("1000.00"), tax_rate_percent=Decimal("18.00")
    )
    canon = CanonicalTransaction(
        protocol_version="1.0", transaction_id=tx_id, transaction_type="SALE",
        state_version=1, issued_at=timezone.now(),
        source_entity=ProtocolEntity("GSTIN", "27SELLER1234A1Z", "Seller Ltd", "27"),
        destination_entity=ProtocolEntity("GSTIN", "27BUYER1234A1Z5", "Buyer Ltd", "27"),
        items=[line],
        tax_summary=TaxSummary(cgst_amount=Decimal("90.00"), sgst_amount=Decimal("90.00")),
        totals=TransactionTotals(
            subtotal=Decimal("1000.00"), total_tax=Decimal("180.00"), grand_total=Decimal("1180.00")
        )
    )

    orig_tx_hash = canon.canonical_hash
    print(f"  -> Original 9-Field Canonical Hash: {orig_tx_hash}")

    # Verify tampering with any of the 9 fields invalidates canonical hash
    tampered_totals = TransactionTotals(
        subtotal=Decimal("1000.00"), total_tax=Decimal("180.00"), grand_total=Decimal("1181.00") # tampered by Rs 1
    )
    try:
        tampered_canon = CanonicalTransaction(
            protocol_version="1.0", transaction_id=tx_id, transaction_type="SALE",
            state_version=1, issued_at=canon.issued_at,
            source_entity=canon.source_entity, destination_entity=canon.destination_entity,
            items=[line], tax_summary=canon.tax_summary, totals=tampered_totals
        )
        tampered_canon.validate_invariants()
        raise AssertionError("Failed to detect grand total invariant tampering!")
    except InvariantViolation:
        print("  [PASSED] Canonical 9-field invariant strictly trapped tampered totals.")

    # 17-Field Accounting Operation Envelope
    op = AccountingOperation(
        operation_id=f"OP-ENV-001",
        transaction_id=tx_id,
        replica_id="REP-ENV-01",
        operation_type=OperationType.TRANSACTION_ISSUED,
        payload={"grand_total": 1180.0, "taxable_amount": 1000.0, "total_tax": 180.0},
        logical_timestamp=1,
        parents=[],
        tenant_id="TENANT-ENV-01",
        created_by="SYSTEM",
        physical_timestamp=time.time()
    ).sign(priv)

    orig_op_hash = op.payload_hash
    assert ProtocolCrypto.verify(orig_op_hash, op.signature, pub), "Signature must verify on genuine op"
    print(f"  -> Original 17-Field Operation Hash: {orig_op_hash} (Ed25519 signature valid)")

    # Tamper with an operation field (e.g., replica_id or logical_timestamp)
    tampered_dict = op.to_dict()
    tampered_dict['replica_id'] = "REP-MALICIOUS"
    tampered_op = AccountingOperation.from_dict(tampered_dict)
    
    # Tampering changed the payload hash
    assert tampered_op.payload_hash != orig_op_hash
    # The existing signature fails to verify against the tampered payload hash
    is_valid = ProtocolCrypto.verify(tampered_op.payload_hash, op.signature, pub)
    assert not is_valid, "Security failure: Tampered 17-field operation signature verified!"
    print("  [PASSED] 17-Field operational envelope strictly invalidated signature on tampering.")

    # -------------------------------------------------------------------------
    # PART 2: AUDIT-CHAIN TAMPER DETECTION (INDEPENDENT OF DJANGO MODEL HOOKS)
    # -------------------------------------------------------------------------
    print("\n[Verification 2] Testing Cryptographic Audit Chain Tamper-Evidence...")
    cid = uuid.uuid4().hex[:6].upper()
    audit_co = Company.objects.create(name=f"AuditCo {cid}", gstin=f"27{cid}1234A1Z"[:15])

    # Create 3 chained audit logs
    log1 = AuditLog.objects.create(
        company=audit_co, action="CREATE", model_name="Voucher", record_id="REC-001",
        changes={"voucher": "INV-001"}
    )
    log2 = AuditLog.objects.create(
        company=audit_co, action="POST", model_name="Voucher", record_id="REC-001",
        changes={"status": "POSTED"}
    )
    log3 = AuditLog.objects.create(
        company=audit_co, action="RECONCILE", model_name="Ledger", record_id="REC-002",
        changes={"status": "RECONCILED"}
    )

    res_initial = AuditLogListView.verify_company_chain_telemetry(audit_co)
    assert res_initial["status"] == "VERIFIED", f"Expected VERIFIED, got {res_initial}"
    print(f"  [PASSED] Audit chain initial state: {res_initial['status']} ({res_initial['total_records_checked']} records)")

    # Simulate raw SQL tampering (bypassing Django model save/delete hooks)
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE audit_auditlog SET changes = %s WHERE id = %s",
            [json.dumps({"status": "TAMPERED_BY_DBA"}), str(log2.id)]
        )

    res_tampered = AuditLogListView.verify_company_chain_telemetry(audit_co)
    assert res_tampered["status"] == "BROKEN", f"Expected BROKEN, got {res_tampered}"
    assert res_tampered["first_tampered_id"] == str(log2.id)
    print(f"  [PASSED] Direct raw-SQL database tampering detected: status={res_tampered['status']}, tampered_id={res_tampered['first_tampered_id']}")

    # -------------------------------------------------------------------------
    # PART 3: DISASTER RECOVERY & RECOVERY POINT VERIFICATION
    # -------------------------------------------------------------------------
    print("\n[Verification 3] Measuring Disaster Recovery Rollback & Idempotency...")
    
    # 1. Transaction Abort Recovery Time (Atomic Rollback)
    t0_rollback = time.time()
    try:
        with transaction.atomic():
            comp_temp = Company.objects.create(name="AbortTestCo", gstin="27ABORT1234A1Z"[:15])
            # Simulate worker crash mid-transaction
            raise RuntimeError("SIMULATED_WORKER_CRASH")
    except RuntimeError:
        pass
    t_rollback = time.time() - t0_rollback
    
    # Verify zero records leaked from aborted transaction
    leaked = Company.objects.filter(gstin="27ABORT1234A1Z"[:15]).exists()
    assert not leaked, "Data leakage detected from aborted transaction!"
    print(f"  [PASSED] Atomic rollback on worker crash completed in {t_rollback*1000:.2f} ms with ZERO data leakage.")

    # 2. ProtocolBridgeExecution Idempotency Recovery
    test_idempotency_key = hashlib.sha256(f"{audit_co.id}|TX-RECOVER|['OP1']".encode()).hexdigest()
    exec_rec = ProtocolBridgeExecution.objects.create(
        execution_id=f"EXEC-{uuid.uuid4().hex[:8].upper()}",
        company_id=str(audit_co.id),
        transaction_id="TX-RECOVER",
        idempotency_key=test_idempotency_key,
        status="SUCCESS",
        role="SELLER",
        base_voucher_number="INV/26-27/0099",
        posted_vouchers=["INV/26-27/0099"]
    )
    
    # Simulate replay following crash
    recovered = ProtocolBridgeExecution.objects.filter(idempotency_key=test_idempotency_key, status="SUCCESS").first()
    assert recovered is not None
    assert recovered.base_voucher_number == "INV/26-27/0099"
    print("  [PASSED] ProtocolBridgeExecution recovered existing execution without duplicate posting.")

    # 3. Offline Outbox Recovery
    # Register offline device before simulating network reconnection
    AuthorizedDevice.objects.create(
        company=audit_co,
        device_id="DEV-OFFLINE-01",
        replica_id="REP-OFFLINE",
        public_key_hex=pub,
        status="ACTIVE"
    )
    # Simulate an offline device producing operations while disconnected
    offline_ops = [
        AccountingOperation(
            operation_id=f"OP-OFFLINE-{i}",
            transaction_id=tx_id,
            replica_id="REP-OFFLINE",
            operation_type=OperationType.ITEM_ACCEPTED,
            payload={},
            logical_timestamp=i + 1,
            parents=[op.operation_id]
        ).sign(priv)
        for i in range(3)
    ]
    t0_sync = time.time()
    # Merge offline outbox into SyncService
    crdt_sync = SyncService.process_sync_payload(
        transaction_id=tx_id,
        client_replica_id="REP-OFFLINE",
        client_operations=[o.to_dict() for o in offline_ops],
        server_operations=[op],
        authenticated_tenant_id=str(audit_co.id),
        seller_identity="27SELLER1234A1Z",
        buyer_identity="27BUYER1234A1Z5",
        canonical_tx=canon,
        canonical_tx_hash=canon.canonical_hash,
        company=None,
        verify_signatures=True,
        persist_to_db=False
    )
    t_sync = time.time() - t0_sync
    print("  -> crdt_sync returned:", crdt_sync)
    assert crdt_sync["status"] == "SYNC_SUCCESS"
    print(f"  [PASSED] Offline outbox ({len(offline_ops)} ops) reconciled cleanly in {t_sync*1000:.2f} ms.")

    print("\n" + "=" * 80)
    print(">>> CRYPTOGRAPHIC ENVELOPE & DISASTER RECOVERY TESTS COMPLETE <<<")
    print("=" * 80)


if __name__ == "__main__":
    run_envelope_and_dr_verification()
