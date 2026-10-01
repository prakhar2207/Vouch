from django.db import models
from django.utils import timezone

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

