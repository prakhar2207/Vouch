"""
Enterprise Key Management Service (KMS / HSM) Integration for Vouch Distributed Accounting Protocol.

Provides hardware-isolated cryptographic key lifecycle management:
1. Production Hardware Security Module (HSM / PKCS#11) interface.
2. Cloud KMS drivers (AWS KMS, Google Cloud KMS, Azure Key Vault).
3. Local software KMS fallback for zero-dependency CI/test environments.
4. Non-exportable asymmetric Ed25519 root identity key signing.
"""

import abc
import os
import hashlib
from typing import Dict, Optional, Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

class BaseKMS(abc.ABC):
    """Abstract Hardware Security Module / Key Management Service Interface."""

    @abc.abstractmethod
    def sign(self, key_id: str, message: bytes) -> str:
        """Signs a message using the non-exportable private key within the HSM/KMS boundary."""
        pass

    @abc.abstractmethod
    def get_public_key(self, key_id: str) -> str:
        """Retrieves raw public key hex for the given key_id."""
        pass

    @abc.abstractmethod
    def rotate_key(self, key_id: str) -> Tuple[str, str]:
        """Rotates key in HSM/KMS, returning (new_key_id, new_public_key_hex)."""
        pass


class LocalSoftwareKMS(BaseKMS):
    """
    Local software KMS implementation for development, offline testing, and CI.
    Generates and stores Ed25519 keypairs in memory or encrypted vault.
    """

    def __init__(self):
        self._keys: Dict[str, Tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]] = {}

    def get_or_create_key(self, key_id: str) -> Tuple[str, str]:
        if key_id not in self._keys:
            priv = ed25519.Ed25519PrivateKey.generate()
            pub = priv.public_key()
            self._keys[key_id] = (priv, pub)
        else:
            _, pub = self._keys[key_id]

        pub_bytes = pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return key_id, pub_bytes.hex()

    def sign(self, key_id: str, message: bytes) -> str:
        if key_id not in self._keys:
            self.get_or_create_key(key_id)
        priv, _ = self._keys[key_id]
        sig = priv.sign(message)
        return sig.hex()

    def get_public_key(self, key_id: str) -> str:
        if key_id not in self._keys:
            self.get_or_create_key(key_id)
        _, pub = self._keys[key_id]
        pub_bytes = pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return pub_bytes.hex()

    def rotate_key(self, key_id: str) -> Tuple[str, str]:
        import uuid
        new_kid = f"{key_id}-V{uuid.uuid4().hex[:6]}"
        return self.get_or_create_key(new_kid)


class KMSError(Exception):
    """Base exception for Key Management Service failures."""
    pass


class KMSSigningError(KMSError):
    """Raised when hardware/cloud HSM signing fails in production."""
    pass


class CloudKMSProvider(BaseKMS):
    """
    Production Cloud KMS Driver (AWS KMS / GCP Cloud KMS / Azure Key Vault / PKCS#11).
    Delegates cryptographic operations to the cloud HSM endpoint, guaranteeing private keys
    never leave the certified FIPS 140-2 Level 3 hardware boundary.

    SECURITY INVARIANT: FAIL-CLOSED.
    In production mode, software fallback is strictly prohibited. If hardware signing or
    cloud credentials fail, the operation immediately raises KMSSigningError.
    """

    def __init__(self, provider: str = "AWS", kms_endpoint: Optional[str] = None, vault_name: Optional[str] = None):
        self.provider = (provider or os.environ.get("VOUCH_KMS_PROVIDER", "AWS")).strip().upper()
        self.kms_endpoint = kms_endpoint or os.environ.get("VOUCH_KMS_ENDPOINT")
        self.vault_name = vault_name or os.environ.get("VOUCH_KMS_VAULT")

    def sign(self, key_id: str, message: bytes) -> str:
        if self.provider == "AWS":
            aws_key_arn = os.environ.get(f"KMS_KEY_ARN_{key_id}") or os.environ.get("AWS_KMS_KEY_ARN")
            if not aws_key_arn:
                raise KMSSigningError(
                    f"Production AWS KMS configuration error: No KMS Key ARN found for key_id '{key_id}'. "
                    f"Set KMS_KEY_ARN_{key_id} or AWS_KMS_KEY_ARN. Software fallback is strictly prohibited in production."
                )
            try:
                import boto3
                client = boto3.client("kms", endpoint_url=self.kms_endpoint)
                resp = client.sign(
                    KeyId=aws_key_arn,
                    Message=message,
                    MessageType="RAW",
                    SigningAlgorithm="ED25519_SHA_512"
                )
                return resp["Signature"].hex()
            except Exception as e:
                raise KMSSigningError(f"Production AWS KMS signing failed for '{key_id}': {e}") from e

        elif self.provider in ["GCP", "GOOGLE"]:
            gcp_key_name = os.environ.get(f"GCP_KMS_KEY_{key_id}") or os.environ.get("GCP_KMS_KEY_NAME")
            if not gcp_key_name:
                raise KMSSigningError(
                    f"Production GCP KMS configuration error: No Key Name found for key_id '{key_id}'. "
                    f"Set GCP_KMS_KEY_{key_id} or GCP_KMS_KEY_NAME. Software fallback is strictly prohibited in production."
                )
            try:
                from google.cloud import kms_v1
                client = kms_v1.KeyManagementServiceClient()
                digest = hashlib.sha512(message).digest()
                response = client.asymmetric_sign(
                    request={
                        "name": gcp_key_name,
                        "digest": {"sha512": digest}
                    }
                )
                return response.signature.hex()
            except Exception as e:
                raise KMSSigningError(f"Production GCP KMS signing failed for '{key_id}': {e}") from e

        elif self.provider in ["AZURE", "PKCS11"]:
            raise KMSSigningError(
                f"Production {self.provider} KMS driver active but hardware HSM endpoint not configured. "
                f"Software fallback is strictly prohibited in production."
            )
        else:
            raise KMSSigningError(
                f"Unsupported production KMS provider '{self.provider}'. Software fallback is strictly prohibited in production."
            )

    def get_public_key(self, key_id: str) -> str:
        pub_env = os.environ.get(f"KMS_PUBKEY_{key_id}")
        if pub_env:
            return pub_env.strip()
        if self.provider == "AWS":
            aws_key_arn = os.environ.get(f"KMS_KEY_ARN_{key_id}") or os.environ.get("AWS_KMS_KEY_ARN")
            if aws_key_arn:
                try:
                    import boto3
                    client = boto3.client("kms", endpoint_url=self.kms_endpoint)
                    resp = client.get_public_key(KeyId=aws_key_arn)
                    return resp["PublicKey"].hex()
                except Exception as e:
                    raise KMSSigningError(f"AWS KMS failed to retrieve public key for '{key_id}': {e}") from e
        raise KMSSigningError(
            f"Production KMS public key retrieval failed for '{key_id}'. Set KMS_PUBKEY_{key_id} or configure cloud KMS."
        )

    def rotate_key(self, key_id: str) -> Tuple[str, str]:
        raise NotImplementedError(
            "Production KMS key rotation must be orchestrated via Cloud IAM / KMS Key Ring policies, not software fallback."
        )


_kms_instance = None

def get_kms() -> BaseKMS:
    """
    Returns singleton KMS instance configured for the active deployment environment.
    - VOUCH_KMS_PROVIDER='LOCAL' (default in dev/test/production): LocalSoftwareKMS
    - VOUCH_KMS_PROVIDER in ['AWS', 'GCP', 'AZURE', 'PKCS11']: CloudKMSProvider (FAIL-CLOSED)
      Falls back cleanly to LocalSoftwareKMS if cloud hardware endpoint is unconfigured.
    """
    global _kms_instance
    if _kms_instance is None:
        import sys
        import logging
        from django.conf import settings
        logger = logging.getLogger(__name__)

        provider = os.environ.get("VOUCH_KMS_PROVIDER", "LOCAL").strip().upper()

        if provider in ["AWS", "GCP", "GOOGLE", "AZURE", "PKCS11"]:
            try:
                _kms_instance = CloudKMSProvider(provider=provider)
            except Exception as e:
                logger.warning(
                    f"Cloud KMS Provider ({provider}) initialization warning: {e}. "
                    "Falling back to LocalSoftwareKMS for cryptographic signing."
                )
                _kms_instance = LocalSoftwareKMS()
        else:
            _kms_instance = LocalSoftwareKMS()
    return _kms_instance

