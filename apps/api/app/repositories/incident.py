from __future__ import annotations

from apps.api.app.models.incident import Incident, IncidentEvent
from apps.api.app.repositories.base import Repository


class IncidentRepository(Repository[Incident]):
    model = Incident


class IncidentEventRepository(Repository[IncidentEvent]):
    model = IncidentEvent
