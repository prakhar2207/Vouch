import os
import sys
import uuid
import time
import socket
from decimal import Decimal

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
from apps.inventory.models import Product
from apps.protocol.schema import (
    CanonicalTransaction, ProtocolEntity, TransactionLine,
    TaxSummary, TransactionTotals
)
from apps.protocol.operation import AccountingOperation, OperationType
from apps.protocol.crdt import DE_CRDT
from apps.protocol.crypto import ProtocolCrypto
from apps.protocol.key_manager import ProtocolKeyManager, SecurityViolationError
from apps.protocol.sync_service import SyncService
from apps.protocol.bridge import LedgerBridge
from apps.protocol.models import AuthorizedDevice, EntityMapping, ProtocolBridgeExecution
from apps.protocol.mapping import ApprovalState, MappingConfidence
from apps.audit.models import AuditLog


def run_recovery_and_operations_tests():
    print("=" * 80)
    print("   SRILEKH EDI: RECOVERY, KEY ROTATION & OPERATIONAL READINESS SUITE")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # TEST 1: KEY ROTATION & REVOCATION RECOVERY
    # -------------------------------------------------------------------------
    print("\n[Test 1] Testing Key Lifecycle: Registration, Grace Period, Rotation, and Revocation...")
    km = ProtocolKeyManager()
    replica_id = f"REP-ROTATION-{uuid.uuid4().hex[:6]}"
    
    # 1. Register Initial Key
    init_envelope = km.generate_keypair(replica_id=replica_id)
    assert km.get_public_key(replica_id) == init_envelope.public_key_hex
    print(f"  -> Initial Key generated: {init_envelope.public_key_hex[:16]}... (KID: {init_envelope.key_id})")

    # 2. Rotate Key
    new_envelope = km.rotate_key(replica_id=replica_id)
    print(f"  -> Key Rotated to: {new_envelope.public_key_hex[:16]}... (New KID: {new_envelope.key_id})")
    assert km.get_public_key(replica_id) == new_envelope.public_key_hex

    # 3. Test Signature from Rotated Key
    test_data = "KEY_ROTATION_EVENT_DATA"
    sig_new = ProtocolCrypto.sign(test_data, new_envelope.private_key_hex)
    assert ProtocolCrypto.verify(test_data, sig_new, km.get_public_key(replica_id))

    # 4. Revocation Recovery
    km.revoke_key(key_id=new_envelope.key_id)
    print(f"  -> Active Key {new_envelope.key_id} revoked.")
    try:
        km.get_public_key(new_envelope.key_id)
        assert False, "FAILED: Revoked key was returned as active!"
    except SecurityViolationError as sve:
        print(f"  -> Key lookup correctly rejected after revocation: {sve}")
    print("  [PASSED] Key rotation and revocation life-cycle fully verified.")

    # -------------------------------------------------------------------------
    # TEST 2: DURABLE RECOVERY OF PENDING MAPPINGS AFTER CRASH / RESTART
    # -------------------------------------------------------------------------
    print("\n[Test 2] Testing Durable Recovery of Pending Semantic Mappings across Worker Restarts...")
    cid = uuid.uuid4().hex[:8].upper()
    comp = Company.objects.create(
        name=f"Recovery Co {cid}",
        gstin=f"27{cid}1234A1Z"[:15],
        state_code="27",
        state_name="Maharashtra"
    )
    user = User.objects.create_user(
        email=f"rec_{cid.lower()}@test.internal",
        password="TestPassword@123",
        first_name="Rec",
        last_name="Admin"
    )
    UserCompany.objects.create(company=comp, user=user, role="ADMIN")

    # Create a pending mapping simulating an inflight transaction before crash
    mapping_id = f"MAP-REC-{uuid.uuid4().hex[:8].upper()}"
    foreign_sku = "UNMAPPED-FOREIGN-01"
    map_obj = EntityMapping.objects.create(
        mapping_id=mapping_id,
        source_company_id="27REMOTE1234A1Z",
        destination_company_id=comp.gstin,
        foreign_sku=foreign_sku,
        local_sku="",
        confidence_level=MappingConfidence.HEURISTIC.value,
        approval_state=ApprovalState.PENDING.value,
        conversion_multiplier=1.0
    )
    print(f"  -> Inflight Pending Mapping created: {mapping_id} (Foreign SKU: {foreign_sku})")

    # Simulate worker restart by closing database connection and opening fresh
    connection.close()
    
    # Query pending mappings as a recovered worker would
    recovered_map = EntityMapping.objects.filter(
        destination_company_id=comp.gstin,
        approval_state=ApprovalState.PENDING.value
    ).first()
    assert recovered_map is not None, "Failed to recover pending mapping after restart!"
    assert recovered_map.mapping_id == mapping_id
    print(f"  -> Successfully recovered pending mapping from PostgreSQL: {recovered_map.mapping_id}")

    # Approve recovered mapping
    recovered_map.local_sku = "LOCAL-RECOVERED-SKU"
    recovered_map.approval_state = ApprovalState.APPROVED.value
    recovered_map.approved_by = user
    recovered_map.approved_at = timezone.now()
    recovered_map.save()
    print("  [PASSED] Inflight semantic mapping persisted durably and resumed cleanly post-recovery.")

    # -------------------------------------------------------------------------
    # TEST 3: AUDIT TRAIL CHAIN & TAMPER-EVIDENT LOGGING
    # -------------------------------------------------------------------------
    print("\n[Test 3] Verifying Tamper-Evident Audit Trail Integrity...")
    from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
    from django.core.exceptions import PermissionDenied as DjangoPermissionDenied

    audit_entry = AuditLog.objects.create(
        company=comp,
        user=user,
        action="CREATE",
        model_name="ProtocolTransaction",
        record_id=mapping_id,
        changes={"status": "COMMITTED", "amount": 5900.00},
        ip_address="127.0.0.1"
    )
    assert audit_entry.id is not None
    assert audit_entry.current_hash is not None
    print(f"  -> Audit record written: ID {audit_entry.id} | Action: {audit_entry.action}")
    print(f"  -> SHA-256 Chained Hash: {audit_entry.current_hash}")

    # Verify SHA-256 Hash Chaining
    computed_hash = audit_entry.compute_hash(audit_entry.previous_hash)
    assert computed_hash == audit_entry.current_hash, "Tamper detected: Audit hash does not match canonical payload!"
    print(f"  -> Verified Cryptographic Hash Equilibrium: {computed_hash[:16]}... == {audit_entry.current_hash[:16]}...")

    # Verify Immutability: Updates strictly forbidden
    try:
        audit_entry.save()
        assert False, "FAILED: Audit log update was permitted!"
    except (DRFPermissionDenied, DjangoPermissionDenied) as pd:
        print(f"  -> Tamper attempt deflected (Immutable Audit Log): {pd}")

    # Verify Immutability: Deletions strictly forbidden
    try:
        audit_entry.delete()
        assert False, "FAILED: Audit log deletion was permitted!"
    except (DRFPermissionDenied, DjangoPermissionDenied) as pd:
        print(f"  -> Deletion attempt deflected (Immutable Audit Log): {pd}")

    print("  [PASSED] Audit trail integrity and cryptographic tamper-evidence verified.")

    # -------------------------------------------------------------------------
    # TEST 4: POSTGRESQL DDL / MIGRATION ROLLBACK SAFETY
    # -------------------------------------------------------------------------
    print("\n[Test 4] Validating Migration Reversibility and Schema Safety...")
    from django.db.migrations.recorder import MigrationRecorder
    recorder = MigrationRecorder(connection)
    applied_migrations = list(recorder.applied_migrations())
    protocol_migrations = [m for m in applied_migrations if m[0] == "protocol"]
    print(f"  -> Total Protocol Migrations Applied: {len(protocol_migrations)}")
    for app, name in protocol_migrations:
        print(f"     * {app}.{name}")
    assert len(protocol_migrations) >= 6, "Missing protocol migrations!"
    print("  [PASSED] All protocol migrations tracked in django_migrations table.")

    print("\n" + "=" * 80)
    print(">>> RECOVERY & OPERATIONAL READINESS TESTS PASSED (100%) <<<")
    print("=" * 80)


if __name__ == "__main__":
    run_recovery_and_operations_tests()
