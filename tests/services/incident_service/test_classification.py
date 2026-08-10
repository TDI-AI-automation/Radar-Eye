"""Unit tests for services/incident_service/classification.py's detector
label mapping and person-weapon spatial association.

Source: services/incident_service/classification.py's own docstring
for the confirmed label->WeaponType/UniformClass mapping and the
nearest-pair-first association algorithm.
"""

from __future__ import annotations

import uuid

import pytest

from services.incident_service.classification import associate_weapons_with_persons
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.payloads import BoundingBoxPayload, ObservationDetection


def _detection(
    *,
    label: str,
    track_id: int | None,
    left: float,
    top: float,
    width: float = 50.0,
    height: float = 100.0,
    secondary_label: str | None = None,
) -> ObservationDetection:
    return ObservationDetection(
        detection_id=uuid.uuid4(),
        track_id=track_id,
        class_id=0,
        label=label,
        confidence=0.9,
        bbox=BoundingBoxPayload(left=left, top=top, width=width, height=height),
        secondary_label=secondary_label,
    )


class TestNoDetections:
    def test_empty_list_returns_empty_dict(self) -> None:
        assert associate_weapons_with_persons([]) == {}

    def test_no_person_detections_returns_empty_dict(self) -> None:
        detections = [_detection(label="ranged_lethal", track_id=None, left=0, top=0)]
        assert associate_weapons_with_persons(detections) == {}


class TestUniformMapping:
    def test_civilian_secondary_label_maps_to_civilian(self) -> None:
        detections = [
            _detection(label="person", track_id=1, left=0, top=0, secondary_label="Civilian")
        ]
        result = associate_weapons_with_persons(detections)
        assert result[1] == (UniformClass.CIVILIAN, WeaponType.NONE)

    def test_military_secondary_label_maps_to_military(self) -> None:
        detections = [
            _detection(label="person", track_id=1, left=0, top=0, secondary_label="Military")
        ]
        result = associate_weapons_with_persons(detections)
        assert result[1] == (UniformClass.MILITARY, WeaponType.NONE)

    def test_missing_secondary_label_maps_to_unknown(self) -> None:
        detections = [_detection(label="person", track_id=1, left=0, top=0)]
        result = associate_weapons_with_persons(detections)
        assert result[1] == (UniformClass.UNKNOWN, WeaponType.NONE)

    def test_unrecognized_secondary_label_maps_to_unknown(self) -> None:
        """Placeholder SGIE outputs (e.g. vehicle types) must never be
        silently treated as a real uniform classification."""
        detections = [
            _detection(label="person", track_id=1, left=0, top=0, secondary_label="sedan")
        ]
        result = associate_weapons_with_persons(detections)
        assert result[1] == (UniformClass.UNKNOWN, WeaponType.NONE)


class TestWeaponLabelMapping:
    @pytest.mark.parametrize(
        "label,expected",
        [
            ("fire", WeaponType.FIRE),
            ("ranged_lethal", WeaponType.RANGED_LETHAL),
            ("melee_lethal", WeaponType.MELEE_LETHAL),
            ("non_lethal", WeaponType.NON_LETHAL),
        ],
    )
    def test_weapon_near_person_maps_to_expected_type(
        self, label: str, expected: WeaponType
    ) -> None:
        detections = [
            _detection(label="person", track_id=1, left=100, top=100, width=50, height=100),
            _detection(label=label, track_id=None, left=110, top=110, width=20, height=20),
        ]
        result = associate_weapons_with_persons(detections)
        assert result[1][1] is expected


class TestSpatialAssociation:
    def test_weapon_far_from_any_person_is_not_associated(self) -> None:
        detections = [
            _detection(label="person", track_id=1, left=0, top=0, width=50, height=100),
            _detection(
                label="ranged_lethal", track_id=None, left=10_000, top=10_000, width=20, height=20
            ),
        ]
        result = associate_weapons_with_persons(detections)
        assert result[1] == (UniformClass.UNKNOWN, WeaponType.NONE)

    def test_weapon_assigned_to_nearest_of_two_persons(self) -> None:
        near_person = _detection(
            label="person", track_id=1, left=100, top=100, width=50, height=100
        )
        far_person = _detection(
            label="person", track_id=2, left=1000, top=1000, width=50, height=100
        )
        weapon = _detection(
            label="melee_lethal", track_id=None, left=110, top=110, width=20, height=20
        )
        result = associate_weapons_with_persons([near_person, far_person, weapon])
        assert result[1][1] is WeaponType.MELEE_LETHAL
        assert result[2][1] is WeaponType.NONE

    def test_each_weapon_assigned_to_at_most_one_person(self) -> None:
        """Two people standing close together, one real weapon between
        them -- only the nearer person gets it; the other must not also
        report a weapon it isn't actually carrying."""
        person_a = _detection(label="person", track_id=1, left=100, top=100, width=50, height=100)
        person_b = _detection(label="person", track_id=2, left=160, top=100, width=50, height=100)
        weapon = _detection(
            label="ranged_lethal", track_id=None, left=115, top=115, width=20, height=20
        )
        result = associate_weapons_with_persons([person_a, person_b, weapon])
        armed_tracks = [track_id for track_id, (_, w) in result.items() if w is not WeaponType.NONE]
        assert armed_tracks == [1]

    def test_persons_without_track_id_are_ignored(self) -> None:
        detections = [_detection(label="person", track_id=None, left=0, top=0)]
        assert associate_weapons_with_persons(detections) == {}
