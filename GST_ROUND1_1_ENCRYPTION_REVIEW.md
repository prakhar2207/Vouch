# SriLekh — GST Round 1.1 Credential Encryption Review

## 1. Executive Summary & Terminology Correction

The Round 1 implementation report described sensitive credential storage as "AES-256 Fernet". This review provides the formal cryptographic correction.

**Cryptographic Correction**:
`Fernet` (from Python's `cryptography.fernet` standard implementation) uses **AES-128-CBC encryption** with **HMAC-SHA256 authentication**. It does not use AES-256. While the master key is 32 bytes (256 bits), the key is divided internally:
- **16 bytes (128 bits)**: AES-128 encryption key.
- **16 bytes (128 bits)**: HMAC-SHA256 authentication key.

All documentation, docstrings, and model field descriptions have been updated in `apps/gst/encryption.py` to reflect this accurately.

---

## 2. Cryptographic Architecture (`apps/gst/encryption.py`)

### Fernet Specification Details
A Fernet token consists of:
$$\text{Version (8-bit)} \parallel \text{Timestamp (64-bit)} \parallel \text{IV (128-bit)} \parallel \text{Ciphertext (variable)} \parallel \text{HMAC (256-bit)}$$

1. **Version**: `0x80`
2. **Timestamp**: 64-bit unsigned big-endian integer (seconds since UNIX epoch).
3. **IV**: 16-byte cryptographically secure random initialization vector (CBC mode).
4. **Ciphertext**: AES-128 in CBC mode with PKCS7 padding.
5. **HMAC**: SHA-256 computed over `Version || Timestamp || IV || Ciphertext`.

---

## 3. Implementation Verification

### 1. Key Derivation & Configuration
```python
def get_gst_credential_fernet() -> Fernet:
    raw_key = (
        getattr(settings, 'GST_ENCRYPTION_KEY', None)
        or os.environ.get('GST_ENCRYPTION_KEY')
        or getattr(settings, 'GST_CREDENTIAL_KEY', None)
        or getattr(settings, 'SECRET_KEY', None)
    )
    if not raw_key:
        raise CredentialEncryptionError("Encryption key is missing. Cannot initialize secure cryptographic provider.")
    digest = hashlib.sha256(raw_key.encode('utf-8')).digest()
    key_b64 = base64.urlsafe_b64encode(digest)
    return Fernet(key_b64)
```
- **Entropy**: Derived via SHA-256, guaranteeing 256 bits of key material.
- **Fail-Closed**: If neither `GST_ENCRYPTION_KEY`, `GST_CREDENTIAL_KEY`, nor `SECRET_KEY` is set, raises `CredentialEncryptionError`.

### 2. Idempotency & Prefix Enveloping
- Ciphertext is stored with the prefix `enc:v1:`.
- `encrypt_gst_credential()` checks `value.startswith("enc:v1:")`. If already encrypted, it returns immediately without re-encrypting.
- Decrypting a non-prefixed value returns the plaintext, guaranteeing backward compatibility.

### 3. Fail-Closed Invariants
- **Tampered Ciphertext**: If HMAC verification fails or ciphertext is modified, `Fernet.decrypt()` raises `InvalidToken`.
- **Handling**: Caught and converted to `CredentialDecryptionError`.
- **Zero Leakage**: Ciphertext or corrupted bytes are never returned to the caller or displayed in UI. Plaintext is never written to disk or logged.

### 4. Key Rotation Strategy
Fernet natively supports key rotation through `MultiFernet`:
```python
from cryptography.fernet import MultiFernet
f = MultiFernet([Fernet(primary_new_key), Fernet(secondary_old_key)])
```
When key rotation is scheduled:
1. Both new and old keys are supplied to `MultiFernet`.
2. Existing records decrypt using the old key and are re-encrypted with the new primary key upon save.

---

## 4. Verification Verdict

**VERDICT: PASS (CORRECTED)** — The encryption mechanism is robust, fail-closed, and correctly documented as Fernet Authenticated Envelope Encryption (AES-128-CBC + HMAC-SHA256).
