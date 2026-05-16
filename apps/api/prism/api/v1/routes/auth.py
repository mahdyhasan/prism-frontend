from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.middleware import CurrentUser
from prism.db.session import get_db_session
from prism.schemas.auth import (
    AuthSyncResponse,
    EmailLoginRequest,
    EmailSignupRequest,
    GoogleAuthSyncRequest,
    GoogleDiscoverRequest,
    GoogleDiscoverResponse,
    GoogleRegisterRequest,
    LinkGoogleRequest,
)
from prism.services.auth import (
    create_access_token,
    create_user_with_password,
    link_google_account,
    login_with_password,
    register_google_user,
    sync_google_user,
    verify_google_id_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _resolve_first_property_id(db: AsyncSession, user) -> int | None:
    """Return the id of the first property this user is a member of, or None."""
    from sqlalchemy import select as _select
    from prism.db.models.property import Property, PropertyMember
    result = await db.execute(
        _select(Property.id)
        .join(PropertyMember, PropertyMember.property_id == Property.id)
        .where(PropertyMember.user_id == user.id)
        .order_by(Property.created_at)
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return int(row) if row is not None else None


def _build_response(user, token: str, property_id: int | None = None) -> AuthSyncResponse:
    return AuthSyncResponse(
        access_token=token,
        user_id=user.id,
        tenant_id=user.tenant_id,
        name=user.name,
        email=user.email,
        role=user.role,
        has_google_linked=bool(user.google_sub),
        property_id=property_id,
    )


@router.post("/sync", response_model=AuthSyncResponse)
async def auth_sync(
    payload: GoogleAuthSyncRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthSyncResponse:
    """Sign in an existing Google user. Returns 404 if the user isn't registered."""
    user = await sync_google_user(db, payload)
    prop_id = await _resolve_first_property_id(db, user)
    return _build_response(user, create_access_token(user), prop_id)


@router.post("/register-google", response_model=AuthSyncResponse, status_code=201)
async def auth_register_google(
    payload: GoogleRegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthSyncResponse:
    """Create a new account + first property in one shot, via Google OAuth."""
    user, prop = await register_google_user(db, payload)
    return _build_response(user, create_access_token(user), prop.id)


@router.post("/google/discover", response_model=GoogleDiscoverResponse)
async def auth_google_discover(
    payload: GoogleDiscoverRequest,
) -> GoogleDiscoverResponse:
    """List the user's accessible GA4 properties and GSC sites.

    Called right after Google OAuth when the user is new — the frontend
    uses the result to populate dropdowns instead of asking for typed IDs.
    """
    from prism.services.ga4.discovery import list_ga4_properties
    from prism.services.gsc.discovery import list_gsc_sites

    # Verify the id_token to confirm the request is legit
    await verify_google_id_token(payload.google_id_token)

    ga4 = await list_ga4_properties(
        access_token=payload.google_access_token,
        refresh_token=payload.google_refresh_token,
    )
    sites = await list_gsc_sites(
        access_token=payload.google_access_token,
        refresh_token=payload.google_refresh_token,
    )
    return GoogleDiscoverResponse(ga4_properties=ga4, gsc_sites=sites)


@router.get("/google/discover-mine", response_model=GoogleDiscoverResponse)
async def auth_google_discover_mine(
    current_user: CurrentUser,
) -> GoogleDiscoverResponse:
    """Same as /google/discover but uses the logged-in user's stored refresh
    token. Used by the Settings page to populate the GA4/GSC pickers without
    requiring a fresh Google OAuth round-trip.
    """
    from prism.config import get_settings
    from prism.core.errors import UnauthorizedError
    from prism.core.security import decrypt_token
    from prism.services.ga4.discovery import list_ga4_properties
    from prism.services.gsc.discovery import list_gsc_sites

    if not current_user.google_refresh_token_encrypted:
        raise UnauthorizedError(
            "No Google refresh token stored. Connect your Google account first.",
        )

    settings = get_settings()
    try:
        refresh_token = decrypt_token(
            current_user.google_refresh_token_encrypted,
            settings.prism_token_encryption_key,
        )
    except Exception as exc:
        raise UnauthorizedError(
            "Stored Google credentials are unreadable. Reconnect your Google account.",
        ) from exc

    ga4 = await list_ga4_properties(refresh_token=refresh_token)
    sites = await list_gsc_sites(refresh_token=refresh_token)
    return GoogleDiscoverResponse(ga4_properties=ga4, gsc_sites=sites)


@router.post("/login", response_model=AuthSyncResponse)
async def email_login(
    payload: EmailLoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthSyncResponse:
    """Authenticate with email + password (admin fallback)."""
    user = await login_with_password(db, payload)
    prop_id = await _resolve_first_property_id(db, user)
    return _build_response(user, create_access_token(user), prop_id)


@router.post("/signup", response_model=AuthSyncResponse, status_code=201)
async def email_signup(
    payload: EmailSignupRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthSyncResponse:
    """Create a new account with email + password (admin only path)."""
    user = await create_user_with_password(db, payload)
    return _build_response(user, create_access_token(user), None)


@router.post("/link-google", response_model=AuthSyncResponse)
async def link_google(
    payload: LinkGoogleRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> AuthSyncResponse:
    """Attach a Google OAuth account to the currently logged-in user.

    Used by email/password users (admin) who want to enable GA4 / GSC sync.
    """
    user = await link_google_account(db, current_user, payload)
    prop_id = await _resolve_first_property_id(db, user)
    return _build_response(user, create_access_token(user), prop_id)


@router.get("/me")
async def get_me(current_user: CurrentUser) -> dict:
    return {
        "id": current_user.id,
        "tenant_id": current_user.tenant_id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role,
        "has_google_linked": bool(current_user.google_sub),
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
    }
