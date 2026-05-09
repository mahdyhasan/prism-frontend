"""Backfill GA4 data for a property.

Usage:
    cd apps/api
    python ../../scripts/backfill_ga4.py --property-id <id> --days 420

Phase 1: implement after GA4 service is built.
"""
from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill GA4 data")
    p.add_argument("--property-id", required=True, type=int)
    p.add_argument("--days", default=420, type=int, help="Number of days to backfill")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(f"GA4 backfill for property {args.property_id}, {args.days} days — not yet implemented.")
