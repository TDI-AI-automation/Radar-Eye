"""Generic thin repository base.

Source: RM-03 design review -- repositories are persistence adapters only
(create/get/list against an injected AsyncSession). Business logic (deciding
*when* to create/update a record) belongs to the service that calls a
repository, never to the repository itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    """Thin CRUD adapter for a single ORM model."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, instance: ModelT) -> ModelT:
        """Persist ``instance``. Constraint violations propagate as-is."""
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def get(self, id_: uuid.UUID) -> ModelT | None:
        return await self._session.get(self.model, id_)

    async def list(self) -> Sequence[ModelT]:
        result = await self._session.execute(select(self.model))
        return result.scalars().all()

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(self.model))
        return result.scalar_one()
