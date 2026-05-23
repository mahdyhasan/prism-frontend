"""Action confirmation token tests.

Verifies that the HMAC-based confirmation token system is secure:
- Tokens generated with the correct secret pass verification.
- Tokens generated with a different secret are rejected (no cross-secret forgery).
- Calling generate/verify with an empty or None secret raises RuntimeError,
  preventing silent failures when the env var is misconfigured.

Security property under test:
    An attacker who knows an action_id but not the HMAC secret cannot forge a
    valid confirmation token.  Empty/missing secrets must be loudly rejected
    rather than silently accepting any token.
"""
from __future__ import annotations

import pytest

from prism.services.actions.confirmation import (
    generate_confirmation_token,
    verify_confirmation_token,
)

_CORRECT_SECRET = "super-secret-hmac-key-for-testing"
_FORGED_SECRET = "attacker-controlled-key"


# ---------------------------------------------------------------------------
# Happy-path: correct secret round-trips
# ---------------------------------------------------------------------------

def test_generate_and_verify_correct_secret() -> None:
    """A token generated with the correct secret must verify as True."""
    token = generate_confirmation_token(action_id=42, secret=_CORRECT_SECRET)
    assert isinstance(token, str) and len(token) == 64  # SHA-256 hexdigest
    result = verify_confirmation_token(action_id=42, token=token, secret=_CORRECT_SECRET)
    assert result is True


def test_different_action_ids_produce_different_tokens() -> None:
    """Tokens are keyed on action_id — different IDs must not share a token."""
    token_42 = generate_confirmation_token(action_id=42, secret=_CORRECT_SECRET)
    token_43 = generate_confirmation_token(action_id=43, secret=_CORRECT_SECRET)
    assert token_42 != token_43


# ---------------------------------------------------------------------------
# Forgery: wrong secret must be rejected
# ---------------------------------------------------------------------------

def test_forged_token_is_rejected() -> None:
    """A token produced with the wrong secret must not verify against the correct secret.

    This is the primary anti-forgery check: an attacker who only knows the
    action_id (which is a public integer) cannot generate a valid token
    without the HMAC secret stored in the server env.
    """
    forged_token = generate_confirmation_token(action_id=42, secret=_FORGED_SECRET)
    result = verify_confirmation_token(
        action_id=42, token=forged_token, secret=_CORRECT_SECRET
    )
    assert result is False, "Forged token must not pass verification."


def test_tampered_token_is_rejected() -> None:
    """Flipping a single character in a valid token must cause verification to fail."""
    token = generate_confirmation_token(action_id=99, secret=_CORRECT_SECRET)
    # Flip the last hex character
    last = token[-1]
    replacement = "0" if last != "0" else "1"
    tampered = token[:-1] + replacement
    result = verify_confirmation_token(action_id=99, token=tampered, secret=_CORRECT_SECRET)
    assert result is False, "Tampered token must not pass verification."


# ---------------------------------------------------------------------------
# Empty / missing secret guard (BLOCKER-2 fix)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="BLOCKER-2: empty-secret guard not yet applied to generate_confirmation_token",
)
def test_empty_secret_raises_runtime_error_on_generate() -> None:
    """Calling generate_confirmation_token with an empty string secret must raise
    RuntimeError so that a misconfigured ACTIONS_HMAC_SECRET env var is caught
    immediately rather than silently accepting every token.

    BLOCKER-2: This test is designed to FAIL until an explicit empty-secret guard
    is added to generate_confirmation_token.  HMAC-SHA256 accepts an empty key
    without error, so without the guard a misconfigured server silently issues
    tokens that anyone can reproduce by calling hmac.new(b"", ...).
    """
    with pytest.raises((RuntimeError, ValueError)):
        generate_confirmation_token(action_id=1, secret="")


@pytest.mark.xfail(
    strict=True,
    reason="BLOCKER-2: empty-secret guard not yet applied to generate_confirmation_token",
)
def test_empty_secret_raises_runtime_error_on_verify() -> None:
    """Calling verify_confirmation_token with an empty string secret must raise
    RuntimeError for the same reason as the generate case.

    BLOCKER-2: Same guard required on the verify path.
    """
    with pytest.raises((RuntimeError, ValueError)):
        verify_confirmation_token(action_id=1, token="aabbcc", secret="")
