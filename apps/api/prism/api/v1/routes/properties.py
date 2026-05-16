from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.middleware import CurrentUser
from prism.db.session import get_db_session
from prism.schemas.properties import (
    AvailableEvent,
    ClarityApiTokenUpdate,
    ClarityProjectIdUpdate,
    IntegrationSyncStatus,
    LinkGA4Request,
    LLMConfigResponse,
    LLMConfigUpdate,
    PrimaryConversionEventsUpdate,
    PropertyCreate,
    PropertyResponse,
    PropertySyncStatusResponse,
    SyncJobResponse,
    TriggerSyncRequest,
)
from prism.schemas.search import LinkGSCRequest
from prism.services import properties as svc

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("", response_model=list[PropertyResponse])
async def list_properties(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> list[PropertyResponse]:
    props = await svc.list_properties(db, current_user)
    return [PropertyResponse.model_validate(p) for p in props]


@router.post("", response_model=PropertyResponse, status_code=201)
async def create_property(
    body: PropertyCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    prop = await svc.create_property(db, current_user, body)
    return PropertyResponse.model_validate(prop)


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    prop = await svc.get_property(db, property_id, current_user)
    return PropertyResponse.model_validate(prop)


@router.post("/{property_id}/link-ga4", response_model=PropertyResponse)
async def link_ga4(
    property_id: int,
    body: LinkGA4Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    prop = await svc.link_ga4(db, property_id, current_user, body.ga4_property_id)
    return PropertyResponse.model_validate(prop)


@router.delete("/{property_id}/ga4", response_model=PropertyResponse)
async def unlink_ga4(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    prop = await svc.unlink_ga4(db, property_id, current_user)
    return PropertyResponse.model_validate(prop)


@router.post("/{property_id}/link-gsc", response_model=PropertyResponse)
async def link_gsc(
    property_id: int,
    body: LinkGSCRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    prop = await svc.link_gsc(db, property_id, current_user, body.site_url)
    return PropertyResponse.model_validate(prop)


@router.delete("/{property_id}/gsc", response_model=PropertyResponse)
async def unlink_gsc(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    prop = await svc.unlink_gsc(db, property_id, current_user)
    return PropertyResponse.model_validate(prop)


@router.post("/{property_id}/sync", response_model=SyncJobResponse, status_code=202)
async def trigger_sync(
    property_id: int,
    body: TriggerSyncRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> SyncJobResponse:
    from prism.services.sync import trigger_manual_sync
    job = await trigger_manual_sync(db, property_id, current_user, body, background_tasks)
    return SyncJobResponse.model_validate(job)


@router.get("/{property_id}/sync-status", response_model=PropertySyncStatusResponse)
async def get_sync_status(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertySyncStatusResponse:
    """Return the most recent sync job for each source (ga4, gsc)."""
    from prism.db.models.sync import SyncJob

    await svc.get_property(db, property_id, current_user)  # access check

    def _build(source: str, job) -> IntegrationSyncStatus:
        if job is None:
            return IntegrationSyncStatus(source=source)
        return IntegrationSyncStatus(
            source=source,
            status=job.status,
            last_finished_at=job.finished_at,
            error=job.error,
            job_id=job.id,
            rows_pulled=job.rows_pulled,
        )

    ga4_result = await db.execute(
        select(SyncJob)
        .where(SyncJob.property_id == property_id, SyncJob.source == "ga4")
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    )
    gsc_result = await db.execute(
        select(SyncJob)
        .where(SyncJob.property_id == property_id, SyncJob.source == "gsc")
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    )

    return PropertySyncStatusResponse(
        ga4=_build("ga4", ga4_result.scalar_one_or_none()),
        gsc=_build("gsc", gsc_result.scalar_one_or_none()),
    )


@router.get("/{property_id}/llm-config", response_model=LLMConfigResponse)
async def get_llm_config(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> LLMConfigResponse:
    cfg = await svc.get_llm_config(db, property_id, current_user)
    if cfg is None:
        return LLMConfigResponse(
            property_id=property_id,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            has_api_key_override=False,
        )
    return LLMConfigResponse(
        property_id=property_id,
        llm_provider=cfg.llm_provider,
        llm_model=cfg.llm_model,
        has_api_key_override=bool(cfg.llm_api_key_encrypted),
    )


@router.put("/{property_id}/llm-config", response_model=LLMConfigResponse)
async def update_llm_config(
    property_id: int,
    body: LLMConfigUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> LLMConfigResponse:
    cfg = await svc.upsert_llm_config(db, property_id, current_user, body)
    return LLMConfigResponse(
        property_id=property_id,
        llm_provider=cfg.llm_provider,
        llm_model=cfg.llm_model,
        has_api_key_override=bool(cfg.llm_api_key_encrypted),
    )


# ── Primary conversion events ────────────────────────────────────────────────

@router.get("/{property_id}/available-events", response_model=list[AvailableEvent])
async def get_available_events(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> list[AvailableEvent]:
    """List GA4 event names this property has recorded in the last 90 days,
    sorted with GA4-flagged conversions first. Powers the Settings picker."""
    rows = await svc.list_available_events(db, property_id, current_user)
    return [AvailableEvent(**r) for r in rows]


@router.put("/{property_id}/primary-conversion-events", response_model=PropertyResponse)
async def update_primary_conversion_events(
    property_id: int,
    body: PrimaryConversionEventsUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    """Replace the list of GA4 events this property considers primary conversions.

    Used by the overview KPIs to compute conversion-rate per primary event.
    """
    prop = await svc.set_primary_conversion_events(
        db, property_id, current_user, body.event_names,
    )
    return PropertyResponse.model_validate(prop)


@router.put("/{property_id}/clarity-project-id", response_model=PropertyResponse)
async def update_clarity_project_id(
    property_id: int,
    body: ClarityProjectIdUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    """Save (or clear) the Microsoft Clarity project ID for this property.

    User installs Clarity on their site separately; PRISM just stores the ID
    so the dashboard can deep-link into Clarity for heatmaps and recordings.
    """
    prop = await svc.set_clarity_project_id(
        db, property_id, current_user, body.clarity_project_id,
    )
    return PropertyResponse.model_validate(prop)


@router.put("/{property_id}/clarity-api-token", response_model=PropertyResponse)
async def update_clarity_api_token(
    property_id: int,
    body: ClarityApiTokenUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    """Store (or clear) the Clarity Data Export API token for nightly pulls.

    The token is AES-256-GCM encrypted at rest.  The response never includes
    the raw token — only `has_clarity_api_token: true/false`.
    """
    prop = await svc.set_clarity_api_token(
        db, property_id, current_user, body.api_token,
    )
    return PropertyResponse.model_validate(prop)
