from __future__ import annotations

from fastapi import APIRouter

from prism.api.v1.routes.actions import router as actions_router
from prism.api.v1.routes.auth import router as auth_router
from prism.api.v1.routes.brief import router as brief_router
from prism.api.v1.routes.chat import router as chat_router
from prism.api.v1.routes.cwv import router as cwv_router
from prism.api.v1.routes.exports import router as exports_router
from prism.api.v1.routes.health import router as health_router
from prism.api.v1.routes.insights import router as insights_router
from prism.api.v1.routes.overview import router as overview_router
from prism.api.v1.routes.pages import router as pages_router
from prism.api.v1.routes.pinned import router as pinned_router
from prism.api.v1.routes.properties import router as properties_router
from prism.api.v1.routes.search import router as search_router
from prism.api.v1.routes.sync import router as sync_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(properties_router)
api_router.include_router(overview_router)
api_router.include_router(pages_router)
api_router.include_router(cwv_router)
api_router.include_router(search_router)
api_router.include_router(sync_router)
api_router.include_router(insights_router)
api_router.include_router(exports_router)
api_router.include_router(chat_router)
api_router.include_router(brief_router)
api_router.include_router(pinned_router)
api_router.include_router(actions_router)
