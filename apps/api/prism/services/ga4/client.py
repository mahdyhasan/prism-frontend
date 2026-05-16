from __future__ import annotations

import json
import time
from typing import Any

import httpx
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, RunReportResponse
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as SACredentials

from prism.config import get_settings
from prism.core.errors import PRISMError
from prism.core.logging import logger

_GA4_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
_MAX_RETRIES = 5
_INITIAL_BACKOFF = 1.0


class GA4QuotaError(PRISMError):
    status_code = 429
    detail = "GA4 API quota exceeded. Retry after backoff."


def _get_service_account_client() -> BetaAnalyticsDataClient:
    settings = get_settings()
    sa_json = settings.google_service_account_json
    if not sa_json:
        msg = "GOOGLE_SERVICE_ACCOUNT_JSON is not configured."
        raise RuntimeError(msg)

    info = json.loads(sa_json) if sa_json.strip().startswith("{") else json.load(open(sa_json))  # noqa: SIM115
    creds = SACredentials.from_service_account_info(info, scopes=_GA4_SCOPES)
    return BetaAnalyticsDataClient(credentials=creds)


def _get_user_client(refresh_token: str, client_id: str, client_secret: str) -> BetaAnalyticsDataClient:
    creds = UserCredentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=_GA4_SCOPES,
    )
    return BetaAnalyticsDataClient(credentials=creds)


def get_ga4_client(refresh_token: str | None = None) -> BetaAnalyticsDataClient:
    """Return a GA4 client. Uses service account by default, falls back to user token."""
    settings = get_settings()
    if settings.google_service_account_json:
        try:
            return _get_service_account_client()
        except Exception as exc:
            logger.warning("Service account client failed, falling back to user token", error=str(exc))

    if refresh_token:
        return _get_user_client(
            refresh_token,
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret,
        )

    msg = "No GA4 credentials available."
    raise RuntimeError(msg)


def run_report_with_backoff(
    client: BetaAnalyticsDataClient,
    request: RunReportRequest,
) -> RunReportResponse:
    """Execute a GA4 report request with exponential backoff on quota errors."""
    backoff = _INITIAL_BACKOFF
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            return client.run_report(request, timeout=180.0)
        except Exception as exc:
            error_str = str(exc).lower()
            is_quota = "quota" in error_str or "rate" in error_str or "429" in error_str
            is_deadline = "deadline" in error_str or "504" in error_str or "unavailable" in error_str
            if (not is_quota and not is_deadline) or attempt == _MAX_RETRIES - 1:
                raise
            reason = "quota" if is_quota else "deadline/unavailable"
            logger.warning("GA4 retryable error, backing off", reason=reason, attempt=attempt, backoff=backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            last_exc = exc

    raise last_exc or GA4QuotaError()


async def verify_property_access(ga4_property_id: str, refresh_token: str | None = None) -> bool:
    """Verify the credentials have read access to the given GA4 property."""
    from datetime import date, timedelta
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric

    client = get_ga4_client(refresh_token)
    try:
        req = RunReportRequest(
            property=ga4_property_id,
            date_ranges=[DateRange(
                start_date=(date.today() - timedelta(days=7)).isoformat(),
                end_date=date.today().isoformat(),
            )],
            dimensions=[Dimension(name="date")],
            metrics=[Metric(name="sessions")],
            limit=1,
        )
        run_report_with_backoff(client, req)
        return True
    except Exception as exc:
        logger.info("GA4 property access check failed", property=ga4_property_id, error=str(exc))
        return False
