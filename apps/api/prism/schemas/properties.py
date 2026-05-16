from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PropertyCreate(BaseModel):
    display_name: str
    timezone: str = "UTC"
    currency: str = "USD"


class LinkGA4Request(BaseModel):
    ga4_property_id: str  # e.g. "properties/123456789"


class PropertyResponse(BaseModel):
    id: int
    tenant_id: int
    display_name: str
    ga4_property_id: str | None
    gsc_site_url: str | None
    timezone: str
    currency: str
    status: str
    created_at: datetime
    primary_conversion_events: list[str] | None = None
    clarity_project_id: str | None = None
    # Never expose the raw token — just whether one is configured.
    has_clarity_api_token: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):  # type: ignore[override]
        instance = super().model_validate(obj, *args, **kwargs)
        # Derive has_clarity_api_token from the ORM attribute if present
        if hasattr(obj, "clarity_api_token_encrypted"):
            instance.has_clarity_api_token = bool(obj.clarity_api_token_encrypted)
        return instance


class SyncJobResponse(BaseModel):
    id: int
    property_id: int
    source: str
    kind: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    rows_pulled: int
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TriggerSyncRequest(BaseModel):
    source: str = "ga4"       # ga4 | gsc
    start_date: str | None = None   # ISO date, default = last 3 days
    end_date: str | None = None     # ISO date, default = today


# ── Sync status per integration ───────────────────────────────────────────────

class IntegrationSyncStatus(BaseModel):
    source: str
    status: str | None = None          # None = never synced
    last_finished_at: datetime | None = None
    error: str | None = None
    job_id: int | None = None
    rows_pulled: int | None = None


class PropertySyncStatusResponse(BaseModel):
    ga4: IntegrationSyncStatus
    gsc: IntegrationSyncStatus


# ── LLM configuration ─────────────────────────────────────────────────────────

class LLMConfigResponse(BaseModel):
    property_id: int
    llm_provider: str
    llm_model: str
    has_api_key_override: bool  # true if a custom API key is stored


class LLMConfigUpdate(BaseModel):
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key: str | None = None  # None = leave unchanged; "" = clear override


# ── Primary conversion events ────────────────────────────────────────────────

class AvailableEvent(BaseModel):
    event_name: str
    total_count: int
    is_ga4_conversion: bool  # whether GA4 has marked any occurrence as a conversion


class PrimaryConversionEventsUpdate(BaseModel):
    event_names: list[str]  # full replacement of the property's list


# ── Microsoft Clarity ────────────────────────────────────────────────────────

class ClarityProjectIdUpdate(BaseModel):
    clarity_project_id: str | None  # 10-char alphanumeric, or null to unlink


class ClarityApiTokenUpdate(BaseModel):
    api_token: str | None  # plain-text; empty/None = clear the stored token
