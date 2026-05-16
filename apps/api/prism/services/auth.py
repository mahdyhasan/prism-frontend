from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt
import httpx
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.config import get_settings
from prism.core.errors import ConflictError, NotFoundError, UnauthorizedError
from prism.core.logging import logger
from prism.core.security import encrypt_token
from prism.db.models.tenant import Tenant
from prism.db.models.user import User
from prism.schemas.auth import (
    EmailLoginRequest,
    EmailSignupRequest,
    GoogleAuthSyncRequest,
    GoogleRegisterRequest,
    LinkGoogleRequest,
    TokenPayload,
)


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(rounds=12)).decode()


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


_GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_ALGORITHM = "HS256"
_TOKEN_EXPIRY_DAYS = 30


async def verify_google_id_token(id_token: str) -> dict:
    """Verify a Google ID token by calling Google's tokeninfo endpoint."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(_GOOGLE_TOKENINFO_URL, params={"id_token": id_token})
    if response.status_code != 200:
        raise UnauthorizedError("Invalid Google ID token.")
    data = response.json()
    if "error" in data:
        raise UnauthorizedError(f"Google token error: {data['error']}")
    return data


def _slug_from_email(email: str) -> str:
    domain = email.split("@")[-1]
    slug = re.sub(r"[^a-z0-9]", "-", domain.lower()).strip("-")
    return slug[:100]


async def sync_google_user(db: AsyncSession, payload: GoogleAuthSyncRequest) -> User:
    """Sign in an existing Google user. Does NOT auto-create — registration is a separate flow.

    Lookup order: google_sub → email. If found by email but not by google_sub,
    auto-link the Google account (covers admin/email-password user signing in with Google).
    """
    settings = get_settings()

    # Verify ID token
    token_data = await verify_google_id_token(payload.google_id_token)
    if token_data.get("sub") != payload.google_sub:
        raise UnauthorizedError("Google sub mismatch.")

    # Lookup by google_sub first, then by email
    result = await db.execute(select(User).where(User.google_sub == payload.google_sub))
    user = result.scalar_one_or_none()

    if user is None:
        result = await db.execute(select(User).where(User.email == payload.email))
        user = result.scalar_one_or_none()
        if user is not None:
            # Auto-link this Google account to the existing email/password user
            user.google_sub = payload.google_sub
            logger.info("Auto-linked Google to existing user", user_id=user.id, email=user.email)

    if user is None:
        raise NotFoundError("Account not registered. Please complete registration first.")

    # Update refresh token + last login
    if payload.google_refresh_token:
        user.google_refresh_token_encrypted = encrypt_token(
            payload.google_refresh_token, settings.prism_token_encryption_key
        )
    user.last_login_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(user)
    return user


async def register_google_user(
    db: AsyncSession, payload: GoogleRegisterRequest,
):
    """Register a new Google user AND create their first property in one transaction.

    Raises ConflictError if either:
    - The Google account is already registered (sign in instead)
    - The GA4 property ID or GSC site URL is already tracked by another account
    """
    from prism.db.models.property import Property, PropertyMember

    settings = get_settings()

    # Verify ID token
    token_data = await verify_google_id_token(payload.google_id_token)
    if token_data.get("sub") != payload.google_sub:
        raise UnauthorizedError("Google sub mismatch.")

    # User must not already exist (by sub OR email)
    existing_by_sub = await db.execute(
        select(User).where(User.google_sub == payload.google_sub),
    )
    if existing_by_sub.scalar_one_or_none() is not None:
        raise ConflictError("This Google account is already registered. Please sign in instead.")

    existing_by_email = await db.execute(select(User).where(User.email == payload.email))
    if existing_by_email.scalar_one_or_none() is not None:
        raise ConflictError("An account with this email already exists. Please sign in instead.")

    # Normalize and check property uniqueness
    ga4_id = payload.ga4_property_id.strip()
    if not ga4_id.startswith("properties/"):
        ga4_id = f"properties/{ga4_id}"

    existing_ga4 = await db.execute(
        select(Property).where(Property.ga4_property_id == ga4_id),
    )
    if existing_ga4.scalar_one_or_none() is not None:
        raise ConflictError(
            "This GA4 property is already being tracked by another account.",
        )

    if payload.gsc_site_url:
        existing_gsc = await db.execute(
            select(Property).where(Property.gsc_site_url == payload.gsc_site_url),
        )
        if existing_gsc.scalar_one_or_none() is not None:
            raise ConflictError(
                "This Search Console site is already being tracked by another account.",
            )

    # Tenant (per email domain, shared if it already exists)
    slug = _slug_from_email(payload.email)
    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name=payload.email.split("@")[-1], slug=slug, plan="free")
        db.add(tenant)
        await db.flush()
        logger.info("Tenant created (registration)", slug=slug, tenant_id=tenant.id)

    # User
    encrypted_token = None
    if payload.google_refresh_token:
        encrypted_token = encrypt_token(
            payload.google_refresh_token, settings.prism_token_encryption_key,
        )

    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        name=payload.name,
        role="owner",
        google_sub=payload.google_sub,
        google_refresh_token_encrypted=encrypted_token,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    await db.flush()

    # Property + membership
    display_name = (payload.display_name or "").strip() or payload.email.split("@")[-1]
    prop = Property(
        tenant_id=tenant.id,
        display_name=display_name,
        ga4_property_id=ga4_id,
        gsc_site_url=payload.gsc_site_url or None,
        timezone=payload.timezone,
        currency=payload.currency,
        status="active",
        linked_by_user_id=user.id,
    )
    db.add(prop)
    await db.flush()

    db.add(PropertyMember(property_id=prop.id, user_id=user.id, role="owner"))

    await db.commit()
    await db.refresh(user)
    await db.refresh(prop)

    logger.info(
        "Google registration complete",
        user_id=user.id,
        email=user.email,
        property_id=prop.id,
        ga4=ga4_id,
        gsc=payload.gsc_site_url,
    )
    return user, prop


async def login_with_password(db: AsyncSession, payload: EmailLoginRequest) -> User:
    """Authenticate with email + password. Raises UnauthorizedError on failure."""
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not user.password_hash:
        raise UnauthorizedError("Invalid email or password.")
    if not _verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password.")
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)
    logger.info("Email/password login", user_id=user.id, email=user.email)
    return user


async def create_user_with_password(db: AsyncSession, payload: EmailSignupRequest) -> User:
    """Create a new user with email + password. Raises ConflictError if email taken."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("An account with this email already exists.")

    slug = _slug_from_email(payload.email)
    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name=payload.email.split("@")[-1], slug=slug, plan="free")
        db.add(tenant)
        await db.flush()
        logger.info("Created tenant (signup)", slug=slug)

    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        name=payload.name,
        role="owner",
        password_hash=_hash_password(payload.password),
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("User created via signup", user_id=user.id, email=user.email)
    return user


async def link_google_account(db: AsyncSession, user: User, payload: LinkGoogleRequest) -> User:
    """Attach a Google account to an existing PRISM user (e.g. email/password user)."""
    token_data = await verify_google_id_token(payload.google_id_token)
    google_sub = token_data.get("sub", "")

    # Make sure this Google account isn't already bound to a different user
    existing = await db.execute(select(User).where(User.google_sub == google_sub))
    other = existing.scalar_one_or_none()
    if other is not None and other.id != user.id:
        raise ConflictError("This Google account is already linked to another user.")

    settings = get_settings()
    user.google_sub = google_sub
    if payload.google_refresh_token:
        user.google_refresh_token_encrypted = encrypt_token(
            payload.google_refresh_token, settings.prism_token_encryption_key
        )
    await db.commit()
    await db.refresh(user)
    logger.info("Google account linked", user_id=user.id)
    return user


def create_access_token(user: User) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(days=_TOKEN_EXPIRY_DAYS)
    payload = {
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "role": user.role,
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.prism_jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        raw = jwt.decode(token, settings.prism_jwt_secret, algorithms=[_ALGORITHM])
        return TokenPayload(**raw)
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired token.") from exc
