from __future__ import annotations

from apps.api.app.models.human_review import HumanReviewItem
from apps.api.app.repositories.base import Repository


class HumanReviewRepository(Repository[HumanReviewItem]):
    model = HumanReviewItem
