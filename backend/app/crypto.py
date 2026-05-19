"""AES-256-GCM encryption for landlord signatures.

Stored format: base64(nonce || ciphertext_with_tag).
The 32-byte key comes from the SIGNATURE_ENCRYPTION_KEY env var (hex-encoded).
Plaintext bytes are NEVER persisted to disk — only encrypted form is stored
in user_profiles.signature_encrypted, and decryption happens in-memory at
signature-display or PDF-render time.
"""

import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings


_NONCE_BYTES = 12  # standard for AES-GCM


def _load_key() -> bytes:
    hex_key = settings.signature_encryption_key or os.environ.get("SIGNATURE_ENCRYPTION_KEY", "")
    if not hex_key:
        raise RuntimeError(
            "SIGNATURE_ENCRYPTION_KEY is required. Generate one with: openssl rand -hex 32"
        )
    try:
        key = bytes.fromhex(hex_key)
    except ValueError as exc:
        raise RuntimeError("SIGNATURE_ENCRYPTION_KEY must be hex-encoded") from exc
    if len(key) != 32:
        raise RuntimeError("SIGNATURE_ENCRYPTION_KEY must decode to 32 bytes (256 bits)")
    return key


_KEY = _load_key()
_AEAD = AESGCM(_KEY)


def encrypt_signature(plaintext: bytes) -> str:
    """Encrypt bytes and return a base64 ASCII string safe for TEXT storage."""
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ciphertext = _AEAD.encrypt(nonce, plaintext, associated_data=None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_signature(token: str) -> bytes:
    """Inverse of encrypt_signature. Raises if the token is corrupt or the key
    doesn't match. Caller is responsible for keeping the returned bytes in
    memory only."""
    raw = base64.b64decode(token.encode("ascii"))
    nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    return _AEAD.decrypt(nonce, ciphertext, associated_data=None)
