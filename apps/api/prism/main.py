from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import sentry_sdk

from prism.api.v1.router import api_router
from prism.config import get_settings
from prism.core.errors import PRISMError, prism_exception_handler
from prism.core.logging import configure_logging, logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(debug=settings.debug)
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.prism_env,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.0,
        )
        logger.info("Sentry initialised", env=settings.prism_env)
    logger.info("PRISM API starting", env=settings.prism_env)
    yield
    logger.info("PRISM API shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PRISM API",
        description="Performance, Reporting, Intelligence, Search & Marketing",
        version="0.1.0",
        docs_url="/api/docs" if not settings.is_prod else None,
        redoc_url="/api/redoc" if not settings.is_prod else None,
        openapi_url="/api/openapi.json" if not settings.is_prod else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.prism_web_base_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(PRISMError, prism_exception_handler)  # type: ignore[arg-type]

    # Catch-all: ensures CORS headers survive unhandled 500s
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        origin = request.headers.get("origin", "")
        allowed = settings.prism_web_base_url
        headers = {"Access-Control-Allow-Origin": origin if origin == allowed else ""} if origin else {}
        logger.exception("Unhandled exception", path=request.url.path, exc=str(exc))
        return JSONResponse({"error": "Internal server error"}, status_code=500, headers=headers)

    app.include_router(api_router)

    return app


app = create_app()
