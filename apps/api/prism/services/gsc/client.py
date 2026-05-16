from __future__ import annotations

import time
from typing import Any

from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from prism.config import get_settings
from prism.core.errors import PRISMError
from prism.core.logging import logger

_GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
_MAX_RETRIES = 5
_INITIAL_BACKOFF = 1.0


class GSCQuotaError(PRISMError):
    status_code = 429
    detail = "GSC API quota exceeded. Retry after backoff."


def _get_user_credentials(refresh_token: str, client_id: str, client_secret: str) -> UserCredentials:
    return UserCredentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=_GSC_SCOPES,
    )


def get_gsc_service(refresh_token: str | None = None) -> Resource:
    """Return a Google Search Console v1 discovery service.

    GSC has no service-account flow that works for arbitrary properties without
    domain-wide delegation, so we always use the user's refresh token.
    """
    if not refresh_token:
        msg = "GSC requires a user refresh token — none provided."
        raise RuntimeError(msg)

    settings = get_settings()
    creds = _get_user_credentials(
        refresh_token,
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
    )
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def run_query_with_backoff(request_callable: Any) -> Any:
    """Execute a GSC API request callable with exponential backoff on quota errors.

    `request_callable` should be a zero-arg callable returning the API response,
    typically a lambda wrapping `service.searchanalytics().query(...).execute()`.
    """
    backoff = _INITIAL_BACKOFF
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            return request_callable()
        except HttpError as exc:
            status = getattr(exc.resp, "status", None) if exc.resp is not None else None
            is_quota = status in (429, 503) or "quota" in str(exc).lower() or "rate" in str(exc).lower()
            if not is_quota or attempt == _MAX_RETRIES - 1:
                raise
            logger.warning("GSC quota hit, backing off", attempt=attempt, backoff=backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            last_exc = exc
        except Exception as exc:
            error_str = str(exc).lower()
            is_quota = "quota" in error_str or "rate" in error_str or "429" in error_str
            if not is_quota or attempt == _MAX_RETRIES - 1:
                raise
            logger.warning("GSC quota hit, backing off", attempt=attempt, backoff=backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            last_exc = exc

    raise last_exc or GSCQuotaError()


async def verify_site_access(site_url: str, refresh_token: str | None = None) -> bool:
    """Verify the credentials have read access to the given GSC site."""
    if not refresh_token:
        return False
    try:
        service = get_gsc_service(refresh_token)
        run_query_with_backoff(lambda: service.sites().get(siteUrl=site_url).execute())
        return True
    except Exception as exc:
        logger.info("GSC site access check failed", site=site_url, error=str(exc))
        return False
