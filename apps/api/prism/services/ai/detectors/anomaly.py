"""Anomaly detection — pure stats, no LLM.

Pulls daily session counts from the GA4 warehouse, computes a rolling 7-day
mean and stddev, and flags days where |z| exceeds the threshold.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.ga4 import GA4DailyMetrics


def _severity_from_z(z: float) -> str:
    abs_z = abs(z)
    if abs_z > 4.0:
        return "critical"
    if abs_z > 3.0:
        return "high"
    return "medium"


async def detect_session_anomalies(
    db: AsyncSession,
    property_id: int,
    lookback_days: int = 30,
    z_threshold: float = 2.5,
) -> list[dict]:
    """Detect sessions anomalies over the last `lookback_days`.

    Returns a list of dicts: {date, metric, actual, baseline, stddev, z_score, severity}.
    Math is deterministic — pandas only, no LLM.
    """
    end = date.today() - timedelta(days=1)
    # Add a 7-day warm-up so the rolling window has data for the first flagged day.
    start = end - timedelta(days=lookback_days + 7)

    result = await db.execute(
        select(GA4DailyMetrics.date, GA4DailyMetrics.sessions)
        .where(
            GA4DailyMetrics.property_id == property_id,
            GA4DailyMetrics.date >= start,
            GA4DailyMetrics.date <= end,
            GA4DailyMetrics.dimension_hash == "base",
        )
        .order_by(GA4DailyMetrics.date)
    )
    rows = result.all()
    if not rows:
        logger.info("No GA4 daily metrics found for anomaly detection", property_id=property_id)
        return []

    df = pd.DataFrame(rows, columns=["date", "sessions"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Rolling 7-day mean/std on the prior 7 days (shifted so today isn't in its own baseline).
    df["baseline"] = df["sessions"].shift(1).rolling(window=7, min_periods=7).mean()
    df["stddev"] = df["sessions"].shift(1).rolling(window=7, min_periods=7).std()

    # Restrict to the actual lookback window.
    cutoff = pd.Timestamp(end - timedelta(days=lookback_days))
    df = df[df["date"] >= cutoff].copy()

    anomalies: list[dict] = []
    for _, row in df.iterrows():
        baseline = row["baseline"]
        stddev = row["stddev"]
        actual = row["sessions"]
        if pd.isna(baseline) or pd.isna(stddev) or stddev == 0:
            continue
        z = (actual - baseline) / stddev
        if abs(z) <= z_threshold:
            continue
        anomalies.append({
            "date": row["date"].date(),
            "metric": "sessions",
            "actual": float(actual),
            "baseline": round(float(baseline), 2),
            "stddev": round(float(stddev), 2),
            "z_score": round(float(z), 2),
            "severity": _severity_from_z(z),
        })

    logger.info(
        "Anomaly detection complete",
        property_id=property_id,
        anomalies_found=len(anomalies),
        lookback_days=lookback_days,
        z_threshold=z_threshold,
    )
    return anomalies
