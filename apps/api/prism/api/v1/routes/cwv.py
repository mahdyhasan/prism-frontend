"""Core Web Vitals API routes.

Exposes CWV audit data stored by the nightly PSI / CrUX ingestion tasks.

Endpoints:
  GET /properties/{id}/cwv/origin           — site-wide CrUX origin data
  GET /properties/{id}/cwv/problems         — pages with poor/needs-improvement CWV
  GET /properties/{id}/cwv/mobile-desktop   — pages where mobile diverges from desktop
  GET /properties/{id}/cwv/page             — latest audit for a single URL
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.ai.tools.cwv_tools import (
    CWVMobileDesktopInput,
    GetOriginCWVInput,
    GetPageCWVInput,
    ScanCWVProblemsInput,
    cwv_mobile_desktop_compare,
    get_origin_cwv,
    get_page_cwv,
    scan_cwv_problem_pages,
)
from prism.core.middleware import CurrentUser
from prism.db.models.cwv import PropertySettings
from prism.db.session import get_db_session

router = APIRouter(prefix="/properties/{property_id}/cwv", tags=["cwv"])


class OriginCWVResponse(BaseModel):
    strategy: str
    lcp_ms: float | None
    inp_ms: float | None
    cls: float | None
    cwv_status: str
    audited_at: str | None
    found: bool


class CWVProblemPage(BaseModel):
    url: str
    strategy: str = "mobile"
    cwv_status: str
    lcp_ms: float | None
    inp_ms: float | None
    cls: float | None
    lighthouse_performance_score: float | None
    audited_at: str | None


class CWVScanResponse(BaseModel):
    pages: list[CWVProblemPage]
    total: int
    strategy: str


class CWVMobileDesktopRow(BaseModel):
    url: str
    mobile_status: str
    desktop_status: str
    mobile_lcp_ms: float | None
    desktop_lcp_ms: float | None
    lcp_gap_ms: float | None


class CWVMobileDesktopResponse(BaseModel):
    rows: list[CWVMobileDesktopRow]


@router.get("/origin", response_model=OriginCWVResponse)
async def get_origin(
    property_id: int,
    current_user: CurrentUser,
    strategy: str = Query("mobile", pattern="^(mobile|desktop)$"),
    db: AsyncSession = Depends(get_db_session),
) -> OriginCWVResponse:
    result = await get_origin_cwv(
        GetOriginCWVInput(property_id=property_id, strategy=strategy),  # type: ignore[arg-type]
        db,
    )
    return OriginCWVResponse(
        strategy=result.get("strategy", strategy),
        lcp_ms=result.get("lcp_p75_ms") or result.get("lcp_ms"),
        inp_ms=result.get("inp_p75_ms") or result.get("inp_ms"),
        cls=result.get("cls_p75") or result.get("cls"),
        cwv_status=result.get("cwv_status", "unknown"),
        audited_at=result.get("audited_at"),
        found=result.get("found", False),
    )


@router.get("/problems", response_model=CWVScanResponse)
async def scan_problems(
    property_id: int,
    current_user: CurrentUser,
    strategy: str = Query("mobile", pattern="^(mobile|desktop)$"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> CWVScanResponse:
    result = await scan_cwv_problem_pages(
        ScanCWVProblemsInput(property_id=property_id, strategy=strategy, limit=limit),  # type: ignore[arg-type]
        db,
    )
    pages_raw: list[dict[str, Any]] = result.get("pages", [])
    pages = [
        CWVProblemPage(
            url=p["url"],
            strategy=strategy,
            cwv_status=p.get("cwv_status", "unknown"),
            lcp_ms=p.get("lcp_ms"),
            inp_ms=p.get("inp_ms"),
            cls=p.get("cls"),
            lighthouse_performance_score=p.get("lighthouse_performance_score"),
            audited_at=p.get("audited_at"),
        )
        for p in pages_raw
    ]
    return CWVScanResponse(pages=pages, total=result.get("total_problem_pages", len(pages)), strategy=strategy)


@router.get("/mobile-desktop", response_model=CWVMobileDesktopResponse)
async def mobile_desktop(
    property_id: int,
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db_session),
) -> CWVMobileDesktopResponse:
    result = await cwv_mobile_desktop_compare(
        CWVMobileDesktopInput(property_id=property_id, limit=limit),
        db,
    )
    pages_raw: list[dict[str, Any]] = result.get("pages", [])
    rows = [
        CWVMobileDesktopRow(
            url=p["url"],
            mobile_status=p.get("mobile_status", "unknown"),
            desktop_status=p.get("desktop_status", "unknown"),
            mobile_lcp_ms=p.get("mobile_lcp_ms"),
            desktop_lcp_ms=p.get("desktop_lcp_ms"),
            lcp_gap_ms=(
                (p["mobile_lcp_ms"] or 0) - (p["desktop_lcp_ms"] or 0)
                if p.get("mobile_lcp_ms") is not None and p.get("desktop_lcp_ms") is not None
                else None
            ),
        )
        for p in pages_raw
    ]
    return CWVMobileDesktopResponse(rows=rows)


@router.get("/page", response_model=dict)
async def get_page(
    property_id: int,
    current_user: CurrentUser,
    url: str = Query(...),
    strategy: str = Query("mobile", pattern="^(mobile|desktop)$"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    return await get_page_cwv(
        GetPageCWVInput(property_id=property_id, url=url, strategy=strategy),  # type: ignore[arg-type]
        db,
    )


# ── Property settings ─────────────────────────────────────────────────────────


class PropertySettingsResponse(BaseModel):
    property_id: int
    cwv_audit_enabled: bool
    cwv_top_pages_count: int
    cwv_mobile_enabled: bool
    cwv_desktop_enabled: bool
    allow_destructive_actions: bool


class PropertySettingsUpdate(BaseModel):
    cwv_audit_enabled: bool | None = None
    cwv_top_pages_count: int | None = None
    cwv_mobile_enabled: bool | None = None
    cwv_desktop_enabled: bool | None = None
    allow_destructive_actions: bool | None = None


@router.get("/settings", response_model=PropertySettingsResponse)
async def get_settings(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertySettingsResponse:
    row = (await db.execute(
        select(PropertySettings).where(PropertySettings.property_id == property_id)
    )).scalar_one_or_none()
    if row is None:
        # Return defaults if no row exists yet
        return PropertySettingsResponse(
            property_id=property_id,
            cwv_audit_enabled=True,
            cwv_top_pages_count=25,
            cwv_mobile_enabled=True,
            cwv_desktop_enabled=True,
            allow_destructive_actions=False,
        )
    return PropertySettingsResponse(
        property_id=row.property_id,
        cwv_audit_enabled=row.cwv_audit_enabled,
        cwv_top_pages_count=row.cwv_top_pages_count,
        cwv_mobile_enabled=row.cwv_mobile_enabled,
        cwv_desktop_enabled=row.cwv_desktop_enabled,
        allow_destructive_actions=row.allow_destructive_actions,
    )


@router.put("/settings", response_model=PropertySettingsResponse)
async def update_settings(
    property_id: int,
    body: PropertySettingsUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PropertySettingsResponse:
    row = (await db.execute(
        select(PropertySettings).where(PropertySettings.property_id == property_id)
    )).scalar_one_or_none()
    if row is None:
        row = PropertySettings(property_id=property_id)
        db.add(row)

    if body.cwv_audit_enabled is not None:
        row.cwv_audit_enabled = body.cwv_audit_enabled
    if body.cwv_top_pages_count is not None:
        row.cwv_top_pages_count = max(1, min(100, body.cwv_top_pages_count))
    if body.cwv_mobile_enabled is not None:
        row.cwv_mobile_enabled = body.cwv_mobile_enabled
    if body.cwv_desktop_enabled is not None:
        row.cwv_desktop_enabled = body.cwv_desktop_enabled
    if body.allow_destructive_actions is not None:
        row.allow_destructive_actions = body.allow_destructive_actions

    await db.commit()
    await db.refresh(row)
    return PropertySettingsResponse(
        property_id=row.property_id,
        cwv_audit_enabled=row.cwv_audit_enabled,
        cwv_top_pages_count=row.cwv_top_pages_count,
        cwv_mobile_enabled=row.cwv_mobile_enabled,
        cwv_desktop_enabled=row.cwv_desktop_enabled,
        allow_destructive_actions=row.allow_destructive_actions,
    )
