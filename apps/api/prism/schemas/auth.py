from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator


class GoogleAuthSyncRequest(BaseModel):
    google_id_token: str
    google_refresh_token: str
    name: str
    email: EmailStr
    google_sub: str
    avatar_url: str | None = None


class AuthSyncResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    tenant_id: int
    name: str
    email: str
    role: str
    has_google_linked: bool = False  # whether user has a Google account linked
    property_id: int | None = None   # first property (for post-login redirect)


class TokenPayload(BaseModel):
    sub: str          # user_id as string
    tenant_id: int
    role: str
    exp: int


# ── Email / Password auth ─────────────────────────────────────────────────────

class EmailLoginRequest(BaseModel):
    email: EmailStr
    password: str


class EmailSignupRequest(BaseModel):
    email: EmailStr
    name: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class LinkGoogleRequest(BaseModel):
    google_id_token: str
    google_refresh_token: str


class GoogleRegisterRequest(BaseModel):
    """Single-shot Google sign-up: creates user + first property in one request."""
    google_id_token: str
    google_refresh_token: str
    google_sub: str
    email: EmailStr
    name: str
    ga4_property_id: str
    gsc_site_url: str | None = None
    display_name: str | None = None
    timezone: str = "UTC"
    currency: str = "USD"


class GoogleDiscoverRequest(BaseModel):
    """List the user's GA4 properties + GSC sites for the registration form."""
    google_id_token: str
    google_access_token: str | None = None   # preferred (hot path)
    google_refresh_token: str | None = None  # fallback


class GA4PropertyOption(BaseModel):
    property_id: str
    display_name: str
    account_name: str


class GSCSiteOption(BaseModel):
    site_url: str
    permission_level: str


class GoogleDiscoverResponse(BaseModel):
    ga4_properties: list[GA4PropertyOption]
    gsc_sites: list[GSCSiteOption]
