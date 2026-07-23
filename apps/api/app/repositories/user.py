from __future__ import annotations

from apps.api.app.models.user import User
from apps.api.app.repositories.base import Repository


class UserRepository(Repository[User]):
    model = User
