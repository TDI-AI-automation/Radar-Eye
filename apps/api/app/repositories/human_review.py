from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from apps.api.app.models.human_review import HumanReviewItem
from apps.api.app.repositories.base import Repository


class HumanReviewRepository(Repository[HumanReviewItem]):
    model = HumanReviewItem

    async def list_by_camera(self, camera_id: uuid.UUID) -> Sequence[HumanReviewItem]:
        """Every review item for a camera, any status -- backs camera
        deletion's evidence cascade (``CameraRegistryService.delete()``)."""
        result = await self._session.execute(
            select(HumanReviewItem).where(HumanReviewItem.camera_id == camera_id)
        )
        return result.scalars().all()

    async def get_open_for_track(
        self, camera_id: uuid.UUID, track_id: int
    ) -> HumanReviewItem | None:
        """The current OPEN review item for (camera_id, track_id), if any --
        mirrors ``IncidentRepository.get_active_for_track()``. Backs the
        pre-insert check (and, on a lost create race, the fallback lookup
        after ``ux_human_review_items_open_camera_track`` rejects a
        duplicate) in ``services/incident_service/main.py``."""
        result = await self._session.execute(
            select(HumanReviewItem).where(
                HumanReviewItem.camera_id == camera_id,
                HumanReviewItem.track_id == track_id,
                HumanReviewItem.status == "OPEN",
            )
        )
        return result.scalar_one_or_none()
