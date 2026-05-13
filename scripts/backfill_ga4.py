"""Backfill GA4 data for a property — runs in-process, no Celery required.

Usage (from apps/api/):
    python ../../scripts/backfill_ga4.py --property-id 1
    python ../../scripts/backfill_ga4.py --property-id 1 --days 90

Looks up the property + linked user, decrypts the user's refresh token,
and runs the GA4 ingestion synchronously. Useful for dev when Redis/Celery
isn't running.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from any cwd by adding apps/api/ to path
_API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
sys.path.insert(0, str(_API_DIR))

from sqlalchemy import select  # noqa: E402

from prism.config import get_settings  # noqa: E402
from prism.core.security import decrypt_token  # noqa: E402
from prism.db.models.property import Property  # noqa: E402
from prism.db.models.user import User  # noqa: E402
from prism.db.session import get_session_factory  # noqa: E402
from prism.services.ga4.ingestion import run_backfill  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill GA4 data for a property")
    p.add_argument("--property-id", required=True, type=int, help="PRISM property.id")
    p.add_argument("--days", default=90, type=int, help="Days to backfill (default 90)")
    return p.parse_args()


async def main(property_id: int, days: int) -> None:
    settings = get_settings()
    factory = get_session_factory()

    async with factory() as db:
        prop = await db.get(Property, property_id)
        if prop is None:
            print(f"ERROR: Property {property_id} not found.")
            sys.exit(1)

        if not prop.ga4_property_id:
            print(f"ERROR: Property {property_id} has no GA4 property linked.")
            sys.exit(1)

        if not prop.linked_by_user_id:
            print(f"ERROR: Property {property_id} has no linking user — can't get refresh token.")
            sys.exit(1)

        user = await db.get(User, prop.linked_by_user_id)
        if user is None or not user.google_refresh_token_encrypted:
            print(f"ERROR: User {prop.linked_by_user_id} has no encrypted refresh token.")
            sys.exit(1)

        try:
            refresh_token = decrypt_token(
                user.google_refresh_token_encrypted,
                settings.prism_token_encryption_key,
            )
        except Exception as exc:
            print(f"ERROR: Could not decrypt refresh token: {exc}")
            sys.exit(1)

        ga4_property_id = prop.ga4_property_id
        display_name = prop.display_name

    print(f"Starting backfill for '{display_name}' (GA4 {ga4_property_id}) — {days} days...")
    try:
        rows = await run_backfill(
            property_id=property_id,
            ga4_property_id=ga4_property_id,
            days=days,
            refresh_token=refresh_token,
        )
        print(f"DONE. Ingested {rows} rows total.")
    except Exception as exc:
        print(f"FAILED: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.property_id, args.days))
