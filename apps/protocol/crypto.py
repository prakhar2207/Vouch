import hashlib
import json
import os
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

class CryptographicSecurityError(Exception):
    """Raised when cryptographic key or signature validation fails closed."""
    pass

class ProtocolCrypto:
    """
    Production-grade asymmetric cryptography engine using Ed25519.
    Implements key generation, signing, and non-repudiation verification.
    STRICTLY FAILS CLOSED on invalid, malformed, or missing keys.
    """

    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        """Generates an Ed25519 keypair, returning (private_key_hex, public_key_hex)."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        priv_hex = private_key.private_bytes_raw().hex()
        pub_hex = public_key.public_bytes_raw().hex()
        return priv_hex, pub_hex

    @staticmethod
    def sign(data: str | bytes, private_key_hex: str) -> str:
        """
        Signs raw data using an Ed25519 private key.
        Strictly fails closed if key is invalid or malformed.
        """
        if not private_key_hex or len(private_key_hex) != 64:
            raise CryptographicSecurityError("Invalid Ed25519 private key: must be a 64-character hex string (32 bytes).")

        try:
            if isinstance(data, str):
                data = data.encode('utf-8')
            priv_bytes = bytes.fromhex(private_key_hex)
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
            signature = private_key.sign(data)
            return signature.hex()
        except Exception as e:
            raise CryptographicSecurityError(f"Ed25519 signing failed: {str(e)}") from e

    @staticmethod
    def verify(data: str | bytes, signature_hex: str, public_key_hex: str) -> bool:
        """
        Verifies an Ed25519 signature against data and public key.
        Strictly fails closed: returns False on any signature or key mismatch.
        """
        if not public_key_hex or len(public_key_hex) != 64 or not signature_hex or len(signature_hex) != 128:
            return False

        try:
            if isinstance(data, str):
                data = data.encode('utf-8')
            pub_bytes = bytes.fromhex(public_key_hex)
            sig_bytes = bytes.fromhex(signature_hex)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            public_key.verify(sig_bytes, data)
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False


class MerkleTree:
    """
    Deterministic Binary Merkle Tree for state-root commitments and audit proofs.
    Computes cryptographic roots for operations, ledgers, inventory, and transactions.
    """

    def __init__(self, elements: List[str | Dict[str, Any]]):
        self.leaves: List[str] = [self._hash_element(elem) for elem in elements]
        if not self.leaves:
            self.leaves = [hashlib.sha256(b"EMPTY_MERKLE_LEAF").hexdigest()]
        self.tree_levels: List[List[str]] = self._build_tree(self.leaves)

    @staticmethod
    def _hash_element(elem: str | Dict[str, Any]) -> str:
        if isinstance(elem, dict):
            canonical = json.dumps(elem, sort_keys=True, separators=(',', ':'))
            return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        if isinstance(elem, str):
            if len(elem) == 64 and all(c in '0123456789abcdefABCDEF' for c in elem):
                return elem.lower()
            return hashlib.sha256(elem.encode('utf-8')).hexdigest()
        return hashlib.sha256(str(elem).encode('utf-8')).hexdigest()

    def _build_tree(self, leaves: List[str]) -> List[List[str]]:
        levels = [leaves]
        current_level = leaves
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = left + right
                parent_hash = hashlib.sha256(combined.encode('utf-8')).hexdigest()
                next_level.append(parent_hash)
            levels.append(next_level)
            current_level = next_level
        return levels

    @property
    def root(self) -> str:
        """Returns the Merkle root hash (top of tree)."""
        return self.tree_levels[-1][0]

    def get_proof(self, leaf_index: int) -> List[Tuple[str, str]]:
        """Generates an audit proof for a leaf at leaf_index."""
        if leaf_index < 0 or leaf_index >= len(self.leaves):
            raise IndexError("Leaf index out of range")
        
        proof: List[Tuple[str, str]] = []
        idx = leaf_index
        for level in self.tree_levels[:-1]:
            is_right_child = (idx % 2 == 1)
            sibling_idx = idx - 1 if is_right_child else idx + 1
            sibling_hash = level[sibling_idx] if sibling_idx < len(level) else level[idx]
            direction = 'L' if is_right_child else 'R'
            proof.append((sibling_hash, direction))
            idx = idx // 2
        return proof

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Tuple[str, str]], expected_root: str) -> bool:
        """Verifies that leaf_hash belongs to the tree represented by expected_root."""
        current = leaf_hash
        for sibling_hash, direction in proof:
            combined = (sibling_hash + current) if direction == 'L' else (current + sibling_hash)
            current = hashlib.sha256(combined.encode('utf-8')).hexdigest()
        return current.lower() == expected_root.lower()


@dataclass(frozen=True)
class CrossLedgerCommitment:
    """
    Cryptographic Cross-Ledger State Commitment ($C_n$).
    MAIN CONSTITUTION: Maintains INDEPENDENT Seller & Buyer State Roots.
    Binds:
    - Transaction baseline root ($T_n$)
    - Operation causal state root ($O_n$)
    - Seller accounting ledger root ($L_{seller}$)
    - Seller inventory stock root ($I_{seller}$)
    - Buyer accounting ledger root ($L_{buyer}$)
    - Buyer inventory stock root ($I_{buyer}$)
    - Previous commitment hash ($C_{n-1}$)
    - Protocol version ($V_n$)
    """
    transaction_id: str
    transaction_state_root: str   # T_n: Merkle root of canonical invoice
    operation_state_root: str     # O_n: Merkle root of causal operations
    seller_ledger_root: str = ""       # L_seller: Merkle root of seller's double-entry ledgers
    seller_inventory_root: str = ""    # I_seller: Merkle root of seller's stock positions
    buyer_ledger_root: str = ""        # L_buyer: Merkle root of buyer's double-entry ledgers
    buyer_inventory_root: str = ""     # I_buyer: Merkle root of buyer's stock positions
    seller_identity: str = "SELLER"    # S_n: Seller GSTIN / Company UUID
    buyer_identity: str = "BUYER"      # B_n: Buyer GSTIN / Company UUID
    protocol_version: str = "1.0"      # V_n
    previous_commitment_hash: Optional[str] = None # C_{n-1}
    seller_signature: Optional[str] = None
    buyer_signature: Optional[str] = None
    ledger_state_root: Optional[str] = None
    inventory_state_root: Optional[str] = None

    def __post_init__(self):
        if not self.seller_ledger_root and self.ledger_state_root:
            object.__setattr__(self, 'seller_ledger_root', self.ledger_state_root)
        if not self.buyer_ledger_root and self.ledger_state_root:
            object.__setattr__(self, 'buyer_ledger_root', self.ledger_state_root)
        if not self.seller_inventory_root and self.inventory_state_root:
            object.__setattr__(self, 'seller_inventory_root', self.inventory_state_root)
        if not self.buyer_inventory_root and self.inventory_state_root:
            object.__setattr__(self, 'buyer_inventory_root', self.inventory_state_root)

    def calculate_hash(self) -> str:
        """
        Calculates C_n = H( TxID || Tn || On || L_seller || I_seller || L_buyer || I_buyer || Sn || Bn || Cn-1 || Vn )
        This strictly verifies both parties' independent accounting states.
        """
        components = [
            self.transaction_id,
            self.transaction_state_root,
            self.operation_state_root,
            self.seller_ledger_root,
            self.seller_inventory_root,
            self.buyer_ledger_root,
            self.buyer_inventory_root,
            self.seller_identity,
            self.buyer_identity,
            self.previous_commitment_hash or "GENESIS",
            self.protocol_version
        ]
        concat_str = "||".join(components)
        return hashlib.sha256(concat_str.encode('utf-8')).hexdigest()

    def sign_seller(self, seller_private_key_hex: str) -> 'CrossLedgerCommitment':
        """Signs commitment hash with Seller's Ed25519 private key."""
        h = self.calculate_hash()
        sig = ProtocolCrypto.sign(h, seller_private_key_hex)
        return CrossLedgerCommitment(
            transaction_id=self.transaction_id,
            transaction_state_root=self.transaction_state_root,
            operation_state_root=self.operation_state_root,
            seller_ledger_root=self.seller_ledger_root,
            seller_inventory_root=self.seller_inventory_root,
            buyer_ledger_root=self.buyer_ledger_root,
            buyer_inventory_root=self.buyer_inventory_root,
            seller_identity=self.seller_identity,
            buyer_identity=self.buyer_identity,
            protocol_version=self.protocol_version,
            previous_commitment_hash=self.previous_commitment_hash,
            seller_signature=sig,
            buyer_signature=self.buyer_signature
        )

    def sign_buyer(self, buyer_private_key_hex: str) -> 'CrossLedgerCommitment':
        """Signs commitment hash with Buyer's Ed25519 private key."""
        h = self.calculate_hash()
        sig = ProtocolCrypto.sign(h, buyer_private_key_hex)
        return CrossLedgerCommitment(
            transaction_id=self.transaction_id,
            transaction_state_root=self.transaction_state_root,
            operation_state_root=self.operation_state_root,
            seller_ledger_root=self.seller_ledger_root,
            seller_inventory_root=self.seller_inventory_root,
            buyer_ledger_root=self.buyer_ledger_root,
            buyer_inventory_root=self.buyer_inventory_root,
            seller_identity=self.seller_identity,
            buyer_identity=self.buyer_identity,
            protocol_version=self.protocol_version,
            previous_commitment_hash=self.previous_commitment_hash,
            seller_signature=self.seller_signature,
            buyer_signature=sig
        )

    def verify_signatures(self, seller_public_key_hex: Optional[str] = None, buyer_public_key_hex: Optional[str] = None) -> Dict[str, bool]:
        """Validates asymmetric digital signatures against counterparties."""
        h = self.calculate_hash()
        results = {"seller_valid": False, "buyer_valid": False}
        if seller_public_key_hex and self.seller_signature:
            results["seller_valid"] = ProtocolCrypto.verify(h, self.seller_signature, seller_public_key_hex)
        if buyer_public_key_hex and self.buyer_signature:
            results["buyer_valid"] = ProtocolCrypto.verify(h, self.buyer_signature, buyer_public_key_hex)
        return results


class ProtocolSigner:
    """Abstract interface for protocol digital signatures."""
    def sign(self, payload: str, private_key_hex: str) -> str:
        raise NotImplementedError

    def verify(
        self, 
        payload: str = "", 
        signature_hex: str = "", 
        public_key_hex: str = "", 
        payload_hash: Optional[str] = None,
        signature: Optional[str] = None,
        public_key: Optional[str] = None
    ) -> bool:
        raise NotImplementedError


class Ed25519Signer(ProtocolSigner):
    """
    Production Ed25519 signer. Real elliptic-curve signatures only.
    Fails closed on any invalid key or tampered signature.
    """
    def sign(self, payload: str, private_key_hex: str) -> str:
        return ProtocolCrypto.sign(payload, private_key_hex)

    def verify(
        self, 
        payload: str = "", 
        signature_hex: str = "", 
        public_key_hex: str = "", 
        payload_hash: Optional[str] = None,
        signature: Optional[str] = None,
        public_key: Optional[str] = None
    ) -> bool:
        data = payload_hash if payload_hash is not None else payload
        sig = signature if signature is not None else signature_hex
        pub = public_key if public_key is not None else public_key_hex
        return ProtocolCrypto.verify(data, sig, pub)
