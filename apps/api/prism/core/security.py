from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_key(encoded_key: str) -> bytes:
    key = base64.b64decode(encoded_key)
    if len(key) != 32:  # noqa: PLR2004
        msg = "PRISM_TOKEN_ENCRYPTION_KEY must decode to exactly 32 bytes."
        raise ValueError(msg)
    return key


def encrypt_token(plaintext: str, encoded_key: str) -> str:
    """AES-256-GCM encrypt. Returns base64(nonce + ciphertext)."""
    key = _get_key(encoded_key)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_token(encoded: str, encoded_key: str) -> str:
    """AES-256-GCM decrypt. Accepts base64(nonce + ciphertext)."""
    key = _get_key(encoded_key)
    raw = base64.b64decode(encoded)
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
