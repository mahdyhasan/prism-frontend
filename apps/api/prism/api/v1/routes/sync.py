from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.errors import NotFoundError
from prism.core.middleware import CurrentUser
from prism.db.models.sync import SyncJob
from prism.db.session import get_db_session
from prism.schemas.properties import SyncJobResponse

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/jobs", response_model=list[SyncJobResponse])
async def list_sync_jobs(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    property_id: int | None = Query(None),
    limit: int = Query(50, le=200),
) -> list[SyncJobResponse]:
    from prism.db.models.property import Property, PropertyMember

    query = (
        select(SyncJob)
        .join(Property, Property.id == SyncJob.property_id)
        .join(PropertyMember, PropertyMember.property_id == SyncJob.property_id)
        .where(
            Property.tenant_id == current_user.tenant_id,
            PropertyMember.user_id == current_user.id,
        )
        .order_by(SyncJob.created_at.desc())
        .limit(limit)
    )
    if property_id is not None:
        query = query.where(SyncJob.property_id == property_id)

    result = await db.execute(query)
    return [SyncJobResponse.model_validate(j) for j in result.scalars().all()]


@router.get("/jobs/{job_id}", response_model=SyncJobResponse)
async def get_sync_job(
    job_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> SyncJobResponse:
    """Fetch a single sync job — used by the frontend to poll running job status."""
    from prism.db.models.property import Property, PropertyMember

    result = await db.execute(
        select(SyncJob)
        .join(Property, Property.id == SyncJob.property_id)
        .join(PropertyMember, PropertyMember.property_id == SyncJob.property_id)
        .where(
            SyncJob.id == job_id,
            Property.tenant_id == current_user.tenant_id,
            PropertyMember.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise NotFoundError("Sync job not found.")
    return SyncJobResponse.model_validate(job)
