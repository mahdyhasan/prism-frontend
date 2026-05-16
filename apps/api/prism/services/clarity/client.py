"""Microsoft Clarity Data Export API client.

SPECULATIVE BUILD — the Clarity Data Export API was in beta as of mid-2025.
This client models the API shape based on public Clarity documentation and
typical REST data-export patterns.

Assumed endpoint:
    GET https://www.clarity.ms/export/projects/{project_id}/urls
    ?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&pageNum=0&pageSize=1000

Auth:
    Authorization: Bearer {api_token}

Response shape (inferred from Clarity docs):
    {
        "data": [
            {
                "url": "https://example.com/path",
                "dead_click_count": 12,
                "rage_click_count": 3,
                "error_click_count": 0,
                "quick_back_count": 7,
                "scroll_depth": 0.65,
                "session_count": 84
            },
            ...
        ],
        "total_count": 1234,
        "next_page": 1          // null when last page
    }

If the actual API differs, update _parse_row() and the field mapping below;
everything else stays the same.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from prism.core.logging import logger

_BASE_URL = "https://www.clarity.ms/export"
_PAGE_SIZE = 1000
_TIMEOUT = 30.0


class ClarityApiError(Exception):
    """Raised when Clarity returns a non-2xx response or times out."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"Clarity API {status}: {detail}")
        self.status = status
        self.detail = detail


def _parse_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalise a single Clarity API row into our internal schema.

    Returns None for rows that are missing the required `url` field or have
    zero sessions (no data to store).
    """
    url: str | None = raw.get("url") or raw.get("page_url")
    if not url:
        return None

    sessions = int(raw.get("session_count") or raw.get("sessions") or 0)
    if sessions <= 0:
        return None

    return {
        "page_url": url[:500],  # enforce DB column limit
        "session_count": sessions,
        "dead_clicks": int(raw.get("dead_click_count") or raw.get("dead_clicks") or 0),
        "rage_clicks": int(raw.get("rage_click_count") or raw.get("rage_clicks") or 0),
        "quick_backs": int(raw.get("quick_back_count") or raw.get("quick_backs") or 0),
        # scroll_depth may come as a percentage (0–100) or fraction (0–1).
        # Normalise to fraction so the DB column is consistently [0, 1].
        "scroll_depth_avg": _norm_scroll(
            raw.get("scroll_depth") or raw.get("avg_scroll_depth") or 0
        ),
    }


def _norm_scroll(raw: float | int | str) -> float:
    v = float(raw or 0)
    if v > 1.0:
        v = v / 100.0
    return round(max(0.0, min(1.0, v)), 4)


async def fetch_page_metrics(
    project_id: str,
    api_token: str,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """Fetch all URL-level metrics for a project over a date range.

    Handles pagination transparently. Returns a deduplicated list of page
    dicts (one entry per URL, keeping the row with the highest session_count
    when the same URL appears more than once across pages).
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    }
    params_base = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "pageSize": _PAGE_SIZE,
    }

    seen: dict[str, dict[str, Any]] = {}
    page_num = 0

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        while True:
            params = {**params_base, "pageNum": page_num}
            url = f"{_BASE_URL}/projects/{project_id}/urls"

            try:
                resp = await client.get(url, headers=headers, params=params)
            except httpx.TimeoutException as exc:
                raise ClarityApiError(408, f"Request timed out: {exc}") from exc
            except httpx.RequestError as exc:
                raise ClarityApiError(0, f"Network error: {exc}") from exc

            if resp.status_code == 401:
                raise ClarityApiError(401, "Invalid or expired Clarity API token.")
            if resp.status_code == 403:
                raise ClarityApiError(403, "Clarity API token lacks access to this project.")
            if resp.status_code == 429:
                raise ClarityApiError(429, "Clarity API rate-limit exceeded.")
            if not resp.is_success:
                raise ClarityApiError(
                    resp.status_code,
                    resp.text[:200],
                )

            body = resp.json()
            rows: list[dict] = body.get("data") or body.get("items") or []

            for raw in rows:
                parsed = _parse_row(raw)
                if parsed is None:
                    continue
                key = parsed["page_url"]
                # Keep the row with more sessions (more reliable averages).
                if key not in seen or parsed["session_count"] > seen[key]["session_count"]:
                    seen[key] = parsed

            logger.debug(
                "Clarity page fetched",
                project_id=project_id,
                page=page_num,
                rows_returned=len(rows),
                rows_kept=len(seen),
            )

            # Detect end of pagination
            next_page = body.get("next_page")
            total = int(body.get("total_count") or body.get("total") or 0)
            fetched_so_far = (page_num + 1) * _PAGE_SIZE

            if (
                not rows
                or next_page is None
                or fetched_so_far >= total
            ):
                break

            page_num += 1

    logger.info(
        "Clarity fetch complete",
        project_id=project_id,
        start=start.isoformat(),
        end=end.isoformat(),
        unique_pages=len(seen),
    )
    return list(seen.values())
