"""Backfill GSC data for a property.

Usage:
    cd apps/api
    python ../../scripts/backfill_gsc.py --property-id <id> --days 480

Phase 2: implement after GSC service is built.
"""
from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill GSC data")
    p.add_argument("--property-id", required=True, type=int)
    p.add_argument("--days", default=480, type=int, help="Number of days to backfill (max ~16 months)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(f"GSC backfill for property {args.property_id}, {args.days} days — not yet implemented.")
