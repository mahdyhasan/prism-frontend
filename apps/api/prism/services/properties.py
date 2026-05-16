from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.errors import ForbiddenError, NotFoundError
from prism.core.logging import logger
from prism.core.security import decrypt_token
from prism.db.models.property import Property, PropertyMember
from prism.db.models.sync import AuditLog
from prism.db.models.user import User
from prism.schemas.properties import LLMConfigUpdate, PropertyCreate


async def list_properties(db: AsyncSession, user: User) -> list[Property]:
    result = await db.execute(
        select(Property)
        .join(PropertyMember, PropertyMember.property_id == Property.id)
        .where(
            PropertyMember.user_id == user.id,
            Property.tenant_id == user.tenant_id,
        )
        .order_by(Property.created_at)
    )
    return list(result.scalars().all())


async def get_property(db: AsyncSession, property_id: int, user: User) -> Property:
    result = await db.execute(
        select(Property)
        .join(PropertyMember, PropertyMember.property_id == Property.id)
        .where(
            Property.id == property_id,
            Property.tenant_id == user.tenant_id,
            PropertyMember.user_id == user.id,
        )
    )
    prop = result.scalar_one_or_none()
    if prop is None:
        raise NotFoundError("Property not found.")
    return prop


async def create_property(db: AsyncSession, user: User, data: PropertyCreate) -> Property:
    prop = Property(
        tenant_id=user.tenant_id,
        display_name=data.display_name,
        timezone=data.timezone,
        currency=data.currency,
        status="pending",
        linked_by_user_id=user.id,
    )
    db.add(prop)
    await db.flush()

    member = PropertyMember(property_id=prop.id, user_id=user.id, role="owner")
    db.add(member)

    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="property.create",
        target_type="property",
        target_id=prop.id,
        payload={"display_name": data.display_name},
    ))

    await db.commit()
    await db.refresh(prop)
    logger.info("Property created", property_id=prop.id, user_id=user.id)
    return prop


async def link_ga4(db: AsyncSession, property_id: int, user: User, ga4_property_id: str) -> Property:
    if not ga4_property_id.startswith("properties/"):
        ga4_property_id = f"properties/{ga4_property_id}"
    from prism.config import get_settings
    from prism.services.ga4.client import verify_property_access

    prop = await get_property(db, property_id, user)
    member_result = await db.execute(
        select(PropertyMember).where(
            PropertyMember.property_id == property_id,
            PropertyMember.user_id == user.id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
        raise ForbiddenError("Only owners and admins can link integrations.")

    # Attempt to verify access using the user's refresh token
    refresh_token: str | None = None
    if user.google_refresh_token_encrypted:
        settings = get_settings()
        try:
            refresh_token = decrypt_token(user.google_refresh_token_encrypted, settings.prism_token_encryption_key)
        except Exception:
            pass

    try:
        has_access = await verify_property_access(ga4_property_id, refresh_token)
    except Exception:
        has_access = False

    if not has_access:
        logger.warning(
            "GA4 access check failed — linking anyway; sync will surface the real error",
            property_id=property_id,
            ga4_property_id=ga4_property_id,
        )

    prop.ga4_property_id = ga4_property_id
    prop.status = "active"

    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="property.link_ga4",
        target_type="property",
        target_id=prop.id,
        payload={"ga4_property_id": ga4_property_id},
    ))

    await db.commit()
    await db.refresh(prop)
    logger.info("GA4 linked", property_id=prop.id, ga4_property_id=ga4_property_id)
    return prop


async def link_gsc(db: AsyncSession, property_id: int, user: User, site_url: str) -> Property:
    """Link a Google Search Console property. Soft-verifies access; never hard-fails the link."""
    from prism.config import get_settings
    from prism.services.gsc.client import verify_site_access

    prop = await get_property(db, property_id, user)
    member_result = await db.execute(
        select(PropertyMember).where(
            PropertyMember.property_id == property_id,
            PropertyMember.user_id == user.id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
        raise ForbiddenError("Only owners and admins can link integrations.")

    refresh_token: str | None = None
    if user.google_refresh_token_encrypted:
        settings = get_settings()
        try:
            refresh_token = decrypt_token(
                user.google_refresh_token_encrypted,
                settings.prism_token_encryption_key,
            )
        except Exception:
            pass

    try:
        has_access = await verify_site_access(site_url, refresh_token)
    except Exception:
        has_access = False

    if not has_access:
        logger.warning(
            "GSC access check failed — linking anyway; sync will surface the real error",
            property_id=property_id,
            site_url=site_url,
        )

    prop.gsc_site_url = site_url
    if prop.status == "pending":
        prop.status = "active"

    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="property.link_gsc",
        target_type="property",
        target_id=prop.id,
        payload={"gsc_site_url": site_url},
    ))

    await db.commit()
    await db.refresh(prop)
    logger.info("GSC linked", property_id=prop.id, gsc_site_url=site_url)
    return prop


async def unlink_ga4(db: AsyncSession, property_id: int, user: User) -> Property:
    prop = await get_property(db, property_id, user)
    member_result = await db.execute(
        select(PropertyMember).where(
            PropertyMember.property_id == property_id,
            PropertyMember.user_id == user.id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
        raise ForbiddenError("Only owners and admins can unlink integrations.")

    prop.ga4_property_id = None
    if not prop.gsc_site_url:
        prop.status = "pending"
    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="property.unlink_ga4",
        target_type="property",
        target_id=prop.id,
        payload={},
    ))
    await db.commit()
    await db.refresh(prop)
    logger.info("GA4 unlinked", property_id=prop.id)
    return prop


async def unlink_gsc(db: AsyncSession, property_id: int, user: User) -> Property:
    prop = await get_property(db, property_id, user)
    member_result = await db.execute(
        select(PropertyMember).where(
            PropertyMember.property_id == property_id,
            PropertyMember.user_id == user.id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
        raise ForbiddenError("Only owners and admins can unlink integrations.")

    prop.gsc_site_url = None
    if not prop.ga4_property_id:
        prop.status = "pending"
    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="property.unlink_gsc",
        target_type="property",
        target_id=prop.id,
        payload={},
    ))
    await db.commit()
    await db.refresh(prop)
    logger.info("GSC unlinked", property_id=prop.id)
    return prop


async def get_llm_config(db: AsyncSession, property_id: int, user: User):
    from prism.db.models.llm_config import PropertyLLMConfig
    await get_property(db, property_id, user)  # access check
    result = await db.execute(
        select(PropertyLLMConfig).where(PropertyLLMConfig.property_id == property_id)
    )
    return result.scalar_one_or_none()


async def upsert_llm_config(
    db: AsyncSession, property_id: int, user: User, data: LLMConfigUpdate
):
    from prism.config import get_settings
    from prism.core.security import encrypt_token
    from prism.db.models.llm_config import PropertyLLMConfig

    await get_property(db, property_id, user)  # access check

    result = await db.execute(
        select(PropertyLLMConfig).where(PropertyLLMConfig.property_id == property_id)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = PropertyLLMConfig(property_id=property_id)
        db.add(cfg)

    cfg.llm_provider = data.llm_provider
    cfg.llm_model = data.llm_model

    if data.llm_api_key is not None:
        if data.llm_api_key == "":
            cfg.llm_api_key_encrypted = None  # clear override
        else:
            settings = get_settings()
            cfg.llm_api_key_encrypted = encrypt_token(
                data.llm_api_key, settings.prism_token_encryption_key
            )

    await db.commit()
    await db.refresh(cfg)
    return cfg


# ── Primary conversion events ────────────────────────────────────────────────

async def list_available_events(
    db: AsyncSession, property_id: int, user: User, limit: int = 200,
) -> list[dict]:
    """Return distinct event names from ga4_events_daily that this property
    has actually recorded, with total counts. Use for the Settings picker.

    Ordered: events flagged as conversions first (highest count), then
    everything else by count. Limited to `limit` rows.
    """
    from datetime import date, timedelta
    from prism.db.models.ga4 import GA4EventsDaily
    from sqlalchemy import func

    await get_property(db, property_id, user)  # access check

    # Last 90 days is a sensible default — most properties' event taxonomy
    # is stable, and 90d is enough for new events to surface.
    end = date.today()
    start = end - timedelta(days=90)

    result = await db.execute(
        select(
            GA4EventsDaily.event_name,
            func.coalesce(func.sum(GA4EventsDaily.event_count), 0).label("count"),
            func.coalesce(func.sum(GA4EventsDaily.conversions), 0).label("conv_count"),
        )
        .where(
            GA4EventsDaily.property_id == property_id,
            GA4EventsDaily.date >= start,
            GA4EventsDaily.date <= end,
        )
        .group_by(GA4EventsDaily.event_name)
        .order_by(text("conv_count DESC, count DESC"))
        .limit(limit)
    )
    return [
        {
            "event_name": row.event_name,
            "total_count": int(row.count or 0),
            "is_ga4_conversion": int(row.conv_count or 0) > 0,
        }
        for row in result.all()
    ]


async def set_primary_conversion_events(
    db: AsyncSession,
    property_id: int,
    user: User,
    event_names: list[str],
) -> Property:
    prop = await get_property(db, property_id, user)
    member_result = await db.execute(
        select(PropertyMember).where(
            PropertyMember.property_id == property_id,
            PropertyMember.user_id == user.id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
        raise ForbiddenError("Only owners and admins can change conversion settings.")

    # Deduplicate, strip, and limit to 10 events (UI sanity)
    clean = []
    seen = set()
    for raw in event_names:
        name = (raw or "").strip()
        if name and name not in seen:
            seen.add(name)
            clean.append(name)
        if len(clean) >= 10:
            break

    prop.primary_conversion_events = clean or None

    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="property.set_primary_conversion_events",
        target_type="property",
        target_id=prop.id,
        payload={"events": clean},
    ))
    await db.commit()
    await db.refresh(prop)
    logger.info("Primary conversion events set", property_id=prop.id, events=clean)
    return prop


# ── Microsoft Clarity ────────────────────────────────────────────────────────

import re as _re

_CLARITY_ID_RE = _re.compile(r"^[a-z0-9]{6,32}$")


async def set_clarity_project_id(
    db: AsyncSession,
    property_id: int,
    user: User,
    project_id: str | None,
) -> Property:
    """Store the user's Microsoft Clarity project ID on the property (or clear it).

    Accepts the 10-char-ish alphanumeric ID Clarity surfaces in its dashboard
    URL. Empty/whitespace input unlinks. Validates format defensively so junk
    pastes (full URLs, etc.) get rejected with a clear error.
    """
    from prism.core.errors import ValidationError

    prop = await get_property(db, property_id, user)
    member_result = await db.execute(
        select(PropertyMember).where(
            PropertyMember.property_id == property_id,
            PropertyMember.user_id == user.id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
        raise ForbiddenError("Only owners and admins can change Clarity settings.")

    cleaned: str | None = (project_id or "").strip().lower() or None

    if cleaned is not None:
        # If user pasted a full Clarity URL, try to extract the project ID from it
        if "clarity.microsoft.com" in cleaned and "/view/" in cleaned:
            try:
                cleaned = cleaned.split("/view/", 1)[1].split("/")[0]
            except Exception:
                pass
        if not _CLARITY_ID_RE.match(cleaned):
            raise ValidationError(
                "Clarity project ID must be 6–32 lowercase alphanumeric characters "
                "(e.g. 'abcd1234ef'). Find it in your Clarity dashboard URL.",
            )

    prop.clarity_project_id = cleaned
    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="property.set_clarity_project_id",
        target_type="property",
        target_id=prop.id,
        payload={"clarity_project_id": cleaned},
    ))
    await db.commit()
    await db.refresh(prop)
    logger.info("Clarity project ID set", property_id=prop.id, project_id=cleaned)
    return prop


async def set_clarity_api_token(
    db: AsyncSession,
    property_id: int,
    user: User,
    api_token: str | None,
) -> Property:
    """Encrypt and store the Clarity Data Export API token (or clear it).

    Pass an empty string / None to unlink the token. The property must
    already have a clarity_project_id or an api_token alone is rejected.
    """
    from prism.config import get_settings
    from prism.core.errors import ValidationError
    from prism.core.security import encrypt_token

    prop = await get_property(db, property_id, user)
    member_result = await db.execute(
        select(PropertyMember).where(
            PropertyMember.property_id == property_id,
            PropertyMember.user_id == user.id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
        raise ForbiddenError("Only owners and admins can change Clarity settings.")

    cleaned: str | None = (api_token or "").strip() or None

    if cleaned is not None and not prop.clarity_project_id:
        raise ValidationError(
            "Set a Clarity Project ID before adding an API token."
        )

    settings = get_settings()
    encrypted: str | None = None
    if cleaned:
        try:
            encrypted = encrypt_token(cleaned, settings.prism_token_encryption_key)
        except Exception as exc:
            raise ValidationError(f"Failed to encrypt token: {exc}") from exc

    prop.clarity_api_token_encrypted = encrypted

    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="property.set_clarity_api_token",
        target_type="property",
        target_id=prop.id,
        payload={"has_token": bool(encrypted)},
    ))
    await db.commit()
    await db.refresh(prop)
    logger.info(
        "Clarity API token updated",
        property_id=prop.id,
        has_token=bool(encrypted),
    )
    return prop
