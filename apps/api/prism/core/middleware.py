from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.errors import UnauthorizedError
from prism.db.models.user import User
from prism.db.session import get_db_session
from prism.services.auth import decode_access_token


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db_session),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header.")

    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)

    result = await db.execute(select(User).where(User.id == int(payload.sub)))
    user = result.scalar_one_or_none()
    if user is None:
        raise UnauthorizedError("User not found.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
