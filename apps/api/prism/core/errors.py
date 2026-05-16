from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse


class PRISMError(Exception):
    """Base exception for all PRISM application errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "An unexpected error occurred."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class NotFoundError(PRISMError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found."


class UnauthorizedError(PRISMError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Authentication required."


class ForbiddenError(PRISMError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "You do not have permission to perform this action."


class ConflictError(PRISMError):
    status_code = status.HTTP_409_CONFLICT
    detail = "Resource already exists."


class ValidationError(PRISMError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    detail = "Validation failed."


async def prism_exception_handler(request: Request, exc: PRISMError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )
