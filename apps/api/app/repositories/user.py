from __future__ import annotations

from sqlalchemy import select

from apps.api.app.models.user import User
from apps.api.app.repositories.base import Repository


class UserRepository(Repository[User]):
    model = User

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
