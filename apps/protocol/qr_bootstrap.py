import json
import base64
import time
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .crypto import ProtocolSigner, Ed25519SignerPlaceholder
from .handshake import EdiStateMachine, EdiState

class SecurityViolation(Exception):
    pass

@dataclass
class QRBootstrapPayload:
    """Ephemeral Data strictly used to initialize an EDI session."""
    protocol_version: str
    transaction_id: str
    session_id: str
    nonce: str
    issuer_id: str
    transaction_digest: str
    expires_at: int
    signature: Optional[str] = None

    def serialize_for_signature(self) -> str:
        """Concatenates fields deterministically for signing."""
        return f"{self.protocol_version}|{self.transaction_id}|{self.session_id}|{self.nonce}|{self.issuer_id}|{self.transaction_digest}|{self.expires_at}"

    def encode_to_qr_string(self) -> str:
        """Minifies into a compact base64url string for the physical QR matrix."""
        payload = {
            "v": self.protocol_version,
            "tx": self.transaction_id,
            "sid": self.session_id,
            "n": self.nonce,
            "iss": self.issuer_id,
            "dig": self.transaction_digest,
            "exp": self.expires_at,
            "sig": self.signature
        }
        json_str = json.dumps(payload, separators=(',', ':'))
        return base64.urlsafe_b64encode(json_str.encode('utf-8')).decode('utf-8').rstrip('=')

    @classmethod
    def decode_from_qr_string(cls, qr_string: str) -> 'QRBootstrapPayload':
        """Decodes the scanned QR matrix back into the payload object."""
        padding = '=' * (4 - len(qr_string) % 4)
        json_str = base64.urlsafe_b64decode(qr_string + padding).decode('utf-8')
        data = json.loads(json_str)
        return cls(
            protocol_version=data['v'],
            transaction_id=data['tx'],
            session_id=data['sid'],
            nonce=data['n'],
            issuer_id=data['iss'],
            transaction_digest=data['dig'],
            expires_at=data['exp'],
            signature=data.get('sig')
        )

class QRSessionManager:
    """
    Validates scanned QR codes and bootstraps them directly into 
    the Phase 8 EDI Distributed State Machine.
    """
    def __init__(self, signer: ProtocolSigner):
        self.signer = signer
        # In memory nonce cache for POC. Production uses Redis/DB.
        self.used_nonces = set()

    def initiate_session_from_scan(self, qr_string: str, current_timestamp: int) -> EdiStateMachine:
        # 1. Decode
        payload = QRBootstrapPayload.decode_from_qr_string(qr_string)
        
        # 2. Expiry Check (e.g., QRs expire 5 minutes after rendering)
        if current_timestamp > payload.expires_at:
            raise SecurityViolation("QR Code has expired. Please refresh the sender's screen.")
            
        # 3. Nonce Check (Replay Attack Prevention)
        if payload.nonce in self.used_nonces:
            raise SecurityViolation("Replay Attack Detected: Nonce has already been consumed.")
            
        # 4. Signature Verification
        if not payload.signature:
            raise SecurityViolation("QR lacks cryptographic signature.")
            
        is_valid = self.signer.verify(
            payload_hash=payload.serialize_for_signature(),
            signature=payload.signature,
            public_key=f"PUB_{payload.issuer_id}"
        )
        if not is_valid:
            raise SecurityViolation("Cryptographic signature validation failed.")
            
        # Consume Nonce
        self.used_nonces.add(payload.nonce)
        
        # 5. Bootstrap the EDI State Machine
        session = EdiStateMachine(session_id=payload.session_id)
        
        # Advance through discovery since the QR *is* the discovery.
        session.advance(EdiState.CAPABILITY_EXCHANGE)
        
        return session
