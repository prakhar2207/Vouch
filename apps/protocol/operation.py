from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import hashlib
import json

class OperationType(str, Enum):
    TRANSACTION_ISSUED = "TRANSACTION_ISSUED"
    ITEM_ACCEPTED = "ITEM_ACCEPTED"
    ITEM_REJECTED = "ITEM_REJECTED"
    QUANTITY_ADJUSTED = "QUANTITY_ADJUSTED"
    PRICE_ADJUSTED = "PRICE_ADJUSTED"
    TAX_ADJUSTED = "TAX_ADJUSTED"
    PAYMENT_ALLOCATED = "PAYMENT_ALLOCATED"
    CREDIT_NOTE_ISSUED = "CREDIT_NOTE_ISSUED"
    DEBIT_NOTE_ISSUED = "DEBIT_NOTE_ISSUED"
    VOUCHER_CANCELLED = "VOUCHER_CANCELLED"

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
    Immutable representation of a state transition in the accounting protocol.
    Designed for append-only logs and CRDT synchronization.
    """
    operation_id: str
    transaction_id: str
    replica_id: str
    operation_type: OperationType
    payload: Dict[str, Any]
    logical_timestamp: int
    parents: List[str] = field(default_factory=list)
    version: int = 1
    signature: Optional[str] = None

    def __post_init__(self):
        object.__setattr__(self, 'payload', _freeze(self.payload))
        if isinstance(self.parents, list):
            object.__setattr__(self, 'parents', tuple(self.parents))

    @property
    def payload_hash(self) -> str:
        """
        Generates a strictly deterministic SHA-256 hash of the operation.
        This forms the basis for cryptographic integrity and DAG linkage.
        """
        canonical_dict = {
            "operation_id": self.operation_id,
            "transaction_id": self.transaction_id,
            "replica_id": self.replica_id,
            "type": self.operation_type.value if isinstance(self.operation_type, Enum) else self.operation_type,
            "payload": self.payload,
            "timestamp": self.logical_timestamp,
            "parents": sorted(self.parents),
            "version": self.version
        }
        # Serialize with strict ordering and no extra whitespace
        canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
        
    def to_dict(self) -> Dict[str, Any]:
        """Exports the operation for EDI transmission."""
        return {
            "operation_id": self.operation_id,
            "transaction_id": self.transaction_id,
            "replica_id": self.replica_id,
            "operation_type": self.operation_type.value if isinstance(self.operation_type, Enum) else self.operation_type,
            "payload": self.payload,
            "logical_timestamp": self.logical_timestamp,
            "parents": self.parents,
            "version": self.version,
            "payload_hash": self.payload_hash,
            "signature": self.signature
        }
