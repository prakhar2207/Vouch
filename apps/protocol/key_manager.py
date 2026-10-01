import time
import uuid
import hashlib
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

class SecurityViolationError(Exception):
    """Raised when cryptographic key validity or replay boundaries are violated."""
    pass

@dataclass
class KeyEnvelope:
    key_id: str
    replica_id: str
    public_key_hex: str
    private_key_hex: Optional[str]
    created_at: float
    valid_until: Optional[float] = None
    is_revoked: bool = False

_default_key_manager = None

class ProtocolKeyManager:
    """
    Manages asymmetric Ed25519 cryptographic keys, key rotation, and revocation lists.
    """
    @classmethod
    def get_default(cls) -> 'ProtocolKeyManager':
        global _default_key_manager
        if _default_key_manager is None:
            _default_key_manager = cls()
        return _default_key_manager

    @classmethod
    def get_active_public_key(cls, replica_id: str) -> Optional[str]:
        try:
            return cls.get_default().get_public_key(replica_id)
        except Exception:
            return None

    def __init__(self):
        self._keys: Dict[str, KeyEnvelope] = {} # key_id -> KeyEnvelope
        self._active_keys_by_replica: Dict[str, str] = {} # replica_id -> current key_id

    def generate_keypair(self, replica_id: str, validity_duration_seconds: Optional[int] = 86400 * 365) -> KeyEnvelope:
        """Generates a new Ed25519 keypair and assigns a unique key_id (KID)."""
        priv_key = ed25519.Ed25519PrivateKey.generate()
        pub_key = priv_key.public_key()

        priv_bytes = priv_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        pub_bytes = pub_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

        now = time.time()
        kid = f"KID-{uuid.uuid4().hex[:12].upper()}"
        valid_until = (now + validity_duration_seconds) if validity_duration_seconds else None

        envelope = KeyEnvelope(
            key_id=kid,
            replica_id=replica_id,
            public_key_hex=pub_bytes.hex(),
            private_key_hex=priv_bytes.hex(),
            created_at=now,
            valid_until=valid_until,
            is_revoked=False
        )

        self._keys[kid] = envelope
        self._active_keys_by_replica[replica_id] = kid
        return envelope

    def register_public_key(self, key_id: str, replica_id: str, public_key_hex: str, valid_until: Optional[float] = None) -> KeyEnvelope:
        """Registers a known counterparty public key."""
        envelope = KeyEnvelope(
            key_id=key_id,
            replica_id=replica_id,
            public_key_hex=public_key_hex,
            private_key_hex=None,
            created_at=time.time(),
            valid_until=valid_until,
            is_revoked=False
        )
        self._keys[key_id] = envelope
        self._active_keys_by_replica[replica_id] = key_id
        return envelope

    def rotate_key(self, replica_id: str) -> KeyEnvelope:
        """Rotates the active key for a replica, creating a new one and keeping old one valid for verification."""
        return self.generate_keypair(replica_id)

    def revoke_key(self, key_id: str):
        """Immediately revokes a compromised or decommissioned key."""
        if key_id in self._keys:
            self._keys[key_id].is_revoked = True

    def get_public_key(self, key_id_or_replica: str) -> str:
        """Retrieves verified public key hex, failing closed on revocation or expiry."""
        envelope = self._keys.get(key_id_or_replica)
        if not envelope and key_id_or_replica in self._active_keys_by_replica:
            active_kid = self._active_keys_by_replica[key_id_or_replica]
            envelope = self._keys.get(active_kid)

        if not envelope:
            raise SecurityViolationError(f"No key found for '{key_id_or_replica}'.")

        if envelope.is_revoked:
            raise SecurityViolationError(f"Key '{envelope.key_id}' has been REVOKED.")

        if envelope.valid_until and time.time() > envelope.valid_until:
            raise SecurityViolationError(f"Key '{envelope.key_id}' has EXPIRED.")

        return envelope.public_key_hex


class ReplayProtectionEngine:
    """
    Guarantees deterministic replay prevention using a sliding timestamp window
    and cryptographic nonce caching.
    """
    def __init__(self, window_seconds: int = 300):
        self.window_seconds = window_seconds
        self._consumed_nonces: Dict[str, float] = {} # nonce_key -> timestamp

    def _purge_expired(self, current_time: float):
        cutoff = current_time - self.window_seconds
        expired_keys = [k for k, ts in self._consumed_nonces.items() if ts < cutoff]
        for k in expired_keys:
            del self._consumed_nonces[k]

    def validate_and_consume(self, replica_id: str, nonce: str, issued_at: float):
        """
        Validates that issued_at is within the accepted sliding window,
        and that the nonce has not been consumed previously by this replica.
        """
        now = time.time()
        self._purge_expired(now)

        # 1. Timestamp freshness check
        if abs(now - issued_at) > self.window_seconds:
            raise SecurityViolationError(
                f"Replay Protection: Timestamp {issued_at} exceeds sliding window of {self.window_seconds}s (server time: {now:.1f})"
            )

        # 2. Nonce uniqueness check
        nonce_key = f"{replica_id}:{nonce}"
        if nonce_key in self._consumed_nonces:
            raise SecurityViolationError(
                f"Replay Protection: Replayed nonce detected from {replica_id} ('{nonce}')"
            )

        self._consumed_nonces[nonce_key] = issued_at
