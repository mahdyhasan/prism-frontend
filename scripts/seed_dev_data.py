"""Seed the development database with a default tenant and user.

Usage:
    cd apps/api
    python ../../scripts/seed_dev_data.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from prism.db.session import get_engine


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        # Phase 1: insert seed tenant and user once models are defined
        result = await conn.execute(text("SELECT 1"))
        print(f"DB connection OK: {result.scalar()}")
    print("Seed complete (Phase 0: no data to seed yet).")


if __name__ == "__main__":
    asyncio.run(main())
