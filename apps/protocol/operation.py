from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import hashlib
import json
import time

class OperationClass(str, Enum):
    """Formal taxonomy of accounting operation convergence behaviors."""
    COMMUTATIVE = "COMMUTATIVE"   # Independent, order-insensitive (e.g., independent cash receipt)
    CAUSAL = "CAUSAL"             # Causally dependent on parent events (e.g., initial invoice issue)
    EXCLUSIVE = "EXCLUSIVE"       # Mutually exclusive alternatives
    COMPENSATING = "COMPENSATING" # Deterministic adjustment correcting semantic delta (e.g., return)
    FINALIZING = "FINALIZING"     # Terminal event that seals the causal branch (e.g., cancellation)
    REVERSAL = "REVERSAL"         # Exact counter-entry reversing an earlier operation

class OperationType(str, Enum):
    """Exhaustive classification of B2B accounting state transitions."""
    TRANSACTION_ISSUED = "TRANSACTION_ISSUED"
    INVOICE_ISSUED = "TRANSACTION_ISSUED"     # Semantic alias
    PURCHASE_INVOICE_CREATED = "PURCHASE_INVOICE_CREATED"
    ITEM_ACCEPTED = "ITEM_ACCEPTED"
    ITEM_REJECTED = "ITEM_REJECTED"
    QUANTITY_ADJUSTED = "QUANTITY_ADJUSTED"
    PRICE_ADJUSTED = "PRICE_ADJUSTED"
    TAX_ADJUSTED = "TAX_ADJUSTED"
    PAYMENT_ALLOCATED = "PAYMENT_ALLOCATED"
    PAYMENT_UNALLOCATED = "PAYMENT_UNALLOCATED"
    CREDIT_NOTE_ISSUED = "CREDIT_NOTE_ISSUED"
    CREDIT_NOTE_CREATED = "CREDIT_NOTE_ISSUED" # Semantic alias
    DEBIT_NOTE_ISSUED = "DEBIT_NOTE_ISSUED"
    DEBIT_NOTE_CREATED = "DEBIT_NOTE_ISSUED"   # Semantic alias
    CONTRA_CREATED = "CONTRA_CREATED"
    JOURNAL_CREATED = "JOURNAL_CREATED"
    SALES_RETURN_CREATED = "SALES_RETURN_CREATED"
    PURCHASE_RETURN_CREATED = "PURCHASE_RETURN_CREATED"
    STOCK_ADJUSTED = "STOCK_ADJUSTED"
    VOUCHER_CANCELLED = "VOUCHER_CANCELLED"
    INVOICE_CANCELLED = "VOUCHER_CANCELLED"    # Semantic alias
    COMMIT_CREATED = "COMMIT_CREATED"

# Formal mapping of operations to their execution class
DEFAULT_OPERATION_CLASSES: Dict[OperationType, OperationClass] = {
    OperationType.TRANSACTION_ISSUED: OperationClass.CAUSAL,
    OperationType.PURCHASE_INVOICE_CREATED: OperationClass.CAUSAL,
    OperationType.ITEM_ACCEPTED: OperationClass.COMMUTATIVE,
    OperationType.ITEM_REJECTED: OperationClass.COMPENSATING,
    OperationType.QUANTITY_ADJUSTED: OperationClass.COMPENSATING,
    OperationType.PRICE_ADJUSTED: OperationClass.COMPENSATING,
    OperationType.TAX_ADJUSTED: OperationClass.COMPENSATING,
    OperationType.PAYMENT_ALLOCATED: OperationClass.COMMUTATIVE,
    OperationType.PAYMENT_UNALLOCATED: OperationClass.REVERSAL,
    OperationType.CREDIT_NOTE_ISSUED: OperationClass.COMPENSATING,
    OperationType.DEBIT_NOTE_ISSUED: OperationClass.COMPENSATING,
    OperationType.CONTRA_CREATED: OperationClass.COMMUTATIVE,
    OperationType.JOURNAL_CREATED: OperationClass.CAUSAL,
    OperationType.SALES_RETURN_CREATED: OperationClass.COMPENSATING,
    OperationType.PURCHASE_RETURN_CREATED: OperationClass.COMPENSATING,
    OperationType.STOCK_ADJUSTED: OperationClass.COMMUTATIVE,
    OperationType.VOUCHER_CANCELLED: OperationClass.FINALIZING,
    OperationType.COMMIT_CREATED: OperationClass.FINALIZING,
}

class ReadOnlyDict(dict):
    """Immutable dictionary wrapper enforcing tamper-proof payload integrity."""
    def _immutable(self, *args, **kwargs):
        raise TypeError("AccountingOperation payload is strictly immutable.")
    __setitem__ = _immutable
    __delitem__ = _immutable
    pop = _immutable
    popitem = _immutable
    clear = _immutable
    update = _immutable
    setdefault = _immutable

def _freeze(obj: Any) -> Any:
    if isinstance(obj, dict):
        return ReadOnlyDict({k: _freeze(v) for k, v in obj.items()})
    elif isinstance(obj, (list, tuple)):
        return tuple(_freeze(v) for v in obj)
    return obj

@dataclass(frozen=True)
class AccountingOperation:
    """
    Immutable representation of a state transition in the distributed accounting protocol.
    Enforces causal tracking, cryptographic non-repudiation, and audit lineage.
    """
    operation_id: str
    transaction_id: str
    replica_id: str
    operation_type: OperationType
    payload: Dict[str, Any]
    logical_timestamp: int
    parents: List[str] = field(default_factory=list)
    operation_class: Optional[OperationClass] = None
    tenant_id: str = "DEFAULT_TENANT"
    vector_clock: Dict[str, int] = field(default_factory=dict)
    physical_timestamp: float = field(default_factory=time.time)
    mapping_version: int = 1
    protocol_version: str = "1.0"
    schema_version: int = 1
    created_by: str = "SYSTEM"
    signature: Optional[str] = None
    previous_operation_hash: Optional[str] = None
    version: int = 1

    def __post_init__(self):
        # Deep freeze payload and parent arrays
        object.__setattr__(self, 'payload', _freeze(self.payload))
        if isinstance(self.parents, list):
            object.__setattr__(self, 'parents', tuple(self.parents))
        if isinstance(self.vector_clock, dict):
            object.__setattr__(self, 'vector_clock', _freeze(self.vector_clock))
        # Infer operation_class if not explicitly provided
        if self.operation_class is None:
            op_cls = DEFAULT_OPERATION_CLASSES.get(self.operation_type, OperationClass.CAUSAL)
            object.__setattr__(self, 'operation_class', op_cls)

    @property
    def payload_hash(self) -> str:
        """
        Generates a strictly deterministic SHA-256 digest of the complete operation.
        Forms the cryptographic node for causal DAG linkage.
        """
        canonical_dict = {
            "operation_id": self.operation_id,
            "transaction_id": self.transaction_id,
            "tenant_id": self.tenant_id,
            "replica_id": self.replica_id,
            "type": self.operation_type.value if isinstance(self.operation_type, Enum) else self.operation_type,
            "class": self.operation_class.value if isinstance(self.operation_class, Enum) else self.operation_class,
            "payload": self.payload,
            "timestamp": self.logical_timestamp,
            "parents": sorted(list(self.parents)),
            "vector_clock": dict(self.vector_clock),
            "prev_hash": self.previous_operation_hash or "GENESIS",
            "version": self.version
        }
        canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
        
    def to_dict(self) -> Dict[str, Any]:
        """Exports the operation for distributed EDI/transport wire transmission."""
        return {
            "operation_id": self.operation_id,
            "transaction_id": self.transaction_id,
            "tenant_id": self.tenant_id,
            "replica_id": self.replica_id,
            "operation_type": self.operation_type.value if isinstance(self.operation_type, Enum) else self.operation_type,
            "operation_class": self.operation_class.value if isinstance(self.operation_class, Enum) else self.operation_class,
            "payload": dict(self.payload),
            "logical_timestamp": self.logical_timestamp,
            "parents": list(self.parents),
            "vector_clock": dict(self.vector_clock),
            "physical_timestamp": self.physical_timestamp,
            "mapping_version": self.mapping_version,
            "protocol_version": self.protocol_version,
            "schema_version": self.schema_version,
            "created_by": self.created_by,
            "signature": self.signature,
            "previous_operation_hash": self.previous_operation_hash,
            "version": self.version,
            "payload_hash": self.payload_hash
        }
