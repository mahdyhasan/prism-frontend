"""
Flush all data tables and seed the PRISM superadmin user.

Usage (from the apps/api directory with venv active):
    python ../../scripts/seed_admin.py

Or from the repo root:
    cd apps/api && python ../../scripts/seed_admin.py

Requires passlib[bcrypt] installed in the active venv.
"""
from __future__ import annotations

import asyncio
import sys
import os

# Allow running from anywhere in the repo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

import bcrypt as _bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from prism.config import get_settings


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(rounds=12)).decode()

ADMIN_EMAIL = "mahdyhasan@gmail.com"
ADMIN_NAME = "Mahdy Hasan"
ADMIN_PASSWORD = "Prism@2026!"

# Tables in safe truncation order (FK children before parents)
TRUNCATE_ORDER = [
    "pinned_question_runs",
    "pinned_questions",
    "chat_messages",
    "chat_sessions",
    "chat_memories",
    "daily_briefs",
    "xs_page_daily",
    "audit_log",
    "sync_jobs",
    "gsc_query_page_daily",
    "gsc_queries_daily",
    "gsc_pages_daily",
    "gsc_appearance_daily",
    "gsc_search_type_daily",
    "ga4_events_daily",
    "ga4_geo_daily",
    "ga4_devices_daily",
    "ga4_channels_daily",
    "ga4_traffic_sources_daily",
    "ga4_landing_pages_daily",
    "ga4_daily_metrics",
    "ai_insights",
    "property_llm_configs",
    "property_members",
    "properties",
    "users",
    "tenants",
]


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.prism_database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        print("Flushing all data tables…")
        await db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in TRUNCATE_ORDER:
            try:
                await db.execute(text(f"TRUNCATE TABLE `{table}`"))
                print(f"  OK {table}")
            except Exception as e:
                print(f"  SKIP {table}: {e}")
        await db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        await db.commit()
        print("Flush complete.\n")

        print("Seeding admin user…")
        # Create tenant
        result = await db.execute(
            text(
                "INSERT INTO tenants (name, slug, plan, created_at, updated_at) "
                "VALUES (:name, :slug, 'free', NOW(), NOW())"
            ),
            {"name": "Augmex", "slug": "augmex-io"},
        )
        tenant_id = result.lastrowid
        print(f"  OK Tenant created (id={tenant_id})")

        # Create admin user
        password_hash = _hash_password(ADMIN_PASSWORD)
        result = await db.execute(
            text(
                "INSERT INTO users "
                "(tenant_id, email, name, role, password_hash, created_at, updated_at) "
                "VALUES (:tid, :email, :name, 'owner', :phash, NOW(), NOW())"
            ),
            {
                "tid": tenant_id,
                "email": ADMIN_EMAIL,
                "name": ADMIN_NAME,
                "phash": password_hash,
            },
        )
        user_id = result.lastrowid
        print(f"  OK User created (id={user_id}, email={ADMIN_EMAIL})")

        await db.commit()

    await engine.dispose()
    print(f"\nDone! Login with: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
