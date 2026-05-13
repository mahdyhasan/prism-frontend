"""Backfill GSC data for a property — runs in-process, no Celery required.

Usage (from apps/api/):
    python ../../scripts/backfill_gsc.py --property-id 4
    python ../../scripts/backfill_gsc.py --property-id 4 --days 90

Looks up the property + linked user, decrypts the user's refresh token,
and runs the GSC ingestion synchronously. GSC has a 16-month max history,
so default is 480 days (~16 months).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
sys.path.insert(0, str(_API_DIR))

from prism.config import get_settings  # noqa: E402
from prism.core.security import decrypt_token  # noqa: E402
from prism.db.models.property import Property  # noqa: E402
from prism.db.models.user import User  # noqa: E402
from prism.db.session import get_session_factory  # noqa: E402
from prism.services.gsc.ingestion import run_backfill  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill GSC data for a property")
    p.add_argument("--property-id", required=True, type=int, help="PRISM property.id")
    p.add_argument("--days", default=480, type=int, help="Days to backfill (default 480, max ~16 months)")
    return p.parse_args()


async def main(property_id: int, days: int) -> None:
    settings = get_settings()
    factory = get_session_factory()

    async with factory() as db:
        prop = await db.get(Property, property_id)
        if prop is None:
            print(f"ERROR: Property {property_id} not found.")
            sys.exit(1)

        if not prop.gsc_site_url:
            print(f"ERROR: Property {property_id} has no GSC site URL linked.")
            sys.exit(1)

        if not prop.linked_by_user_id:
            print(f"ERROR: Property {property_id} has no linking user.")
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

        site_url = prop.gsc_site_url
        display_name = prop.display_name

    print(f"Starting GSC backfill for '{display_name}' (site {site_url}) — {days} days...")
    try:
        rows = await run_backfill(
            property_id=property_id,
            gsc_site_url=site_url,
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
