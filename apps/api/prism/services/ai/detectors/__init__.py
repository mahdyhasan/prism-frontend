"""Detectors compute insights from warehouse data using SQL + pandas only.

NO LLM CALLS in this layer. The math has to be deterministic and auditable.
"""
from prism.services.ai.detectors.anomaly import detect_session_anomalies

__all__ = ["detect_session_anomalies"]
