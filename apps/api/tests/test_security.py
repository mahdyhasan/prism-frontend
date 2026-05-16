from __future__ import annotations

import pytest
from prism.core.security import decrypt_token, encrypt_token

_TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def test_encrypt_decrypt_roundtrip() -> None:
    plaintext = "ya29.my-refresh-token-value"
    ciphertext = encrypt_token(plaintext, _TEST_KEY)
    assert ciphertext != plaintext
    recovered = decrypt_token(ciphertext, _TEST_KEY)
    assert recovered == plaintext


def test_each_encrypt_is_unique() -> None:
    """Different nonces produce different ciphertexts for the same plaintext."""
    plaintext = "same-token"
    c1 = encrypt_token(plaintext, _TEST_KEY)
    c2 = encrypt_token(plaintext, _TEST_KEY)
    assert c1 != c2
    assert decrypt_token(c1, _TEST_KEY) == plaintext
    assert decrypt_token(c2, _TEST_KEY) == plaintext


def test_bad_key_raises() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        encrypt_token("token", "tooshort")


def test_tampered_ciphertext_raises() -> None:
    import base64
    ct = encrypt_token("secret", _TEST_KEY)
    raw = bytearray(base64.b64decode(ct))
    raw[-1] ^= 0xFF  # flip last byte
    tampered = base64.b64encode(bytes(raw)).decode()
    with pytest.raises(Exception):
        decrypt_token(tampered, _TEST_KEY)
