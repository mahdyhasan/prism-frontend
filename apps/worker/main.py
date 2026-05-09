"""Celery worker entrypoint.

Start with:
  celery -A apps.worker.main:celery_app worker --loglevel=info
  celery -A apps.worker.main:celery_app beat --loglevel=info
"""
from __future__ import annotations

from prism.core.logging import configure_logging
from prism.config import get_settings
from prism.workers.celery_app import celery_app  # noqa: F401 — imported for side effects

settings = get_settings()
configure_logging(debug=settings.debug)
