from django.db import models
from django.utils import timezone
from apps.companies.models import Company
from apps.accounts.models import User

class ProtocolTransaction(models.Model):
    """Phase 13: Django ORM persistence for the Canonical Transaction Envelope."""
    transaction_id = models.CharField(max_length=100, unique=True, db_index=True)
    transaction_type = models.CharField(max_length=50) # e.g. SALE, PURCHASE
    protocol_version = models.CharField(max_length=10, default="1.0")
    state_version = models.IntegerField(default=1)
    
    source_company_id = models.CharField(max_length=100)
    destination_company_id = models.CharField(max_length=100)
    
    canonical_payload = models.JSONField(help_text="The immutable Canonical Transaction payload")
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = "protocol_transactions"

class ProtocolOperation(models.Model):
    """Phase 13: Django ORM persistence for the Operational DAG."""
    operation_id = models.CharField(max_length=100, unique=True, db_index=True)
    transaction = models.ForeignKey(ProtocolTransaction, on_delete=models.CASCADE, related_name="operations")
    replica_id = models.CharField(max_length=100)
    operation_type = models.CharField(max_length=50)
    
    payload = models.JSONField()
    logical_timestamp = models.BigIntegerField()
    parents = models.JSONField(default=list)
    
    payload_hash = models.CharField(max_length=128)
    signature = models.CharField(max_length=512, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "protocol_operations"
        unique_together = ('operation_id', 'replica_id')
        ordering = ['logical_timestamp']

class CryptographicCommitment(models.Model):
    """Phase 13: Django ORM persistence for Cross-Ledger State Commitments."""
    transaction = models.ForeignKey(ProtocolTransaction, on_delete=models.CASCADE, related_name="commitments")
    commitment_hash = models.CharField(max_length=128, unique=True)
    operation_state_root = models.CharField(max_length=128)
    previous_commitment_hash = models.CharField(max_length=128, null=True, blank=True)
    signature = models.CharField(max_length=512, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "protocol_commitments"
        
class EntityMapping(models.Model):
    """Phase 13: Django ORM persistence for Cross-Enterprise Mappings."""
    mapping_id = models.CharField(max_length=100, unique=True)
    source_company_id = models.CharField(max_length=100)
    destination_company_id = models.CharField(max_length=100)
    foreign_sku = models.CharField(max_length=100)
    local_sku = models.CharField(max_length=100)
    
    mapping_version = models.IntegerField(default=1)
    confidence_level = models.CharField(max_length=50) # MANUAL, HEURISTIC, ML_PREDICTED
    approval_state = models.CharField(max_length=50)   # PENDING, APPROVED, REJECTED
    
    conversion_multiplier = models.FloatField(default=1.0)
    hsn_override = models.CharField(max_length=20, null=True, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = "protocol_entity_mappings"
        unique_together = ('source_company_id', 'destination_company_id', 'foreign_sku', 'mapping_version')

class EdiSession(models.Model):
    """Crash-safe persistence for EDI handshake and consensus state machine."""
    session_id = models.CharField(max_length=100, unique=True, db_index=True)
    current_state = models.CharField(max_length=50, default="DISCOVER", db_index=True)
    transaction_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    initiator_replica_id = models.CharField(max_length=100, null=True, blank=True)
    responder_replica_id = models.CharField(max_length=100, null=True, blank=True)
    timeout_seconds = models.IntegerField(default=300)
    context_data = models.JSONField(default=dict, blank=True)
    transition_history = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "protocol_edi_sessions"
        ordering = ['-created_at']

class ProtocolBridgeExecution(models.Model):
    """Phase 13: Audit trail and idempotency ledger for Protocol -> LedgerBridge executions."""
    execution_id = models.CharField(max_length=100, unique=True, db_index=True)
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    company_id = models.CharField(max_length=100, db_index=True)
    transaction_id = models.CharField(max_length=100, db_index=True)
    role = models.CharField(max_length=20)  # SELLER or BUYER
    base_voucher_number = models.CharField(max_length=100, null=True, blank=True)
    posted_vouchers = models.JSONField(default=list)
    status = models.CharField(max_length=50, default="SUCCESS")  # SUCCESS, FAILED
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "protocol_bridge_executions"
        ordering = ['-created_at']


class AuthorizedDevice(models.Model):
    """
    Cryptographic identity binding a physical client/replica device to an enterprise Company.
    Enforces device authorization, replica ID validation, and asymmetric Ed25519 public key pinning.
    """
    device_id = models.CharField(max_length=100, unique=True, db_index=True)
    replica_id = models.CharField(max_length=100, unique=True, db_index=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="authorized_devices")
    registered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    device_name = models.CharField(max_length=255, default="Browser Client")
    
    public_key_hex = models.CharField(max_length=128, db_index=True)
    key_id = models.CharField(max_length=100, db_index=True)
    
    STATUS_CHOICES = (
        ("ACTIVE", "Active"),
        ("REVOKED", "Revoked"),
        ("ROTATED", "Rotated"),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE", db_index=True)
    
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "protocol_authorized_devices"
        unique_together = ('company', 'replica_id')
        ordering = ['-created_at']


class ProtocolConsumedNonce(models.Model):
    """
    Durable, cross-instance replay prevention for ephemeral nonces (QR codes, handshake nonces).
    Guarantees strict once-only execution across horizontally scaled backend servers.
    """
    nonce_key = models.CharField(max_length=255, unique=True, db_index=True)
    issuer_id = models.CharField(max_length=100, db_index=True)
    nonce = models.CharField(max_length=128)
    expires_at = models.BigIntegerField(db_index=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "protocol_consumed_nonces"
        ordering = ['-created_at']


class DeviceKeyRotationAudit(models.Model):
    """
    Immutable audit ledger for cryptographic key rotation events.
    Records previous public key, new public key, authorizer, rotation proof, and timestamp.
    """
    device = models.ForeignKey(AuthorizedDevice, on_delete=models.CASCADE, related_name="rotation_history")
    old_public_key_hex = models.CharField(max_length=128)
    old_key_id = models.CharField(max_length=100)
    new_public_key_hex = models.CharField(max_length=128)
    new_key_id = models.CharField(max_length=100)
    rotated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    authorization_method = models.CharField(max_length=50) # 'CRYPTOGRAPHIC_PROOF' or 'COMPANY_ADMIN'
    rotation_signature = models.CharField(max_length=512, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "protocol_device_key_rotations"
        ordering = ['-created_at']




