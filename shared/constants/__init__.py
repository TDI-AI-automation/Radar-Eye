"""Shared constants — canonical enums for the Radar Eye platform.

Import from here rather than from the individual sub-modules so that
internal reorganisation never breaks service-level imports.

    from shared.constants import ThreatLevel, DistanceZone, WeaponType
    from shared.constants import UniformClass, IncidentType, IncidentStatus
"""

from shared.constants.distance_zones import DistanceZone
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType

__all__ = [
    "DistanceZone",
    "IncidentStatus",
    "IncidentType",
    "ThreatLevel",
    "UniformClass",
    "WeaponType",
]
