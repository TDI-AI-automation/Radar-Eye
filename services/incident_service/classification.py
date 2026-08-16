"""Detector-label -> WeaponType/UniformClass mapping and person-weapon
spatial association -- the piece ADR-029's ObservationEvent contract
deliberately excludes from AI Runtime (observations only, never a
classification/decision) and that ``_handle_observation`` previously
stubbed out entirely (every detection reported as
``WeaponType.NONE``/``UniformClass.UNKNOWN``, honestly, since no real
classifier was wired in yet).

The trained models (see ``configs/models.yaml``) detect "person" and
each weapon class as *separate* detections, not one combined
person-carrying-a-weapon detection -- confirmed via
``configs/models.yaml``'s SGIE section (``operate_on_class_ids: "3"``,
"person" is class index 3 in the PGIE's own labels.txt): the uniform
classifier runs only on "person" detections, never on a weapon
detection directly. The Threat Engine's ``ingest()`` needs exactly one
``weapon_type``/``uniform`` pair per tracked person, so a weapon has to
be attributed to a specific nearby person before that call can be made.

Association method: nearest bounding-box-center distance, one weapon
per person, greedy nearest-pair-first assignment (a weapon already
claimed by a closer person is not reassigned to a farther one). A
weapon detection with no person within its own bounding-box diagonal is
left unassociated (not reported against any track) -- the Threat Engine
is a per-tracked-*subject* decision maker (THREAT_ENGINE_SPEC.md), and
an unattributed weapon has no subject to report it against yet.
"""

from __future__ import annotations

import math

from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.payloads import BoundingBoxPayload, ObservationDetection

PERSON_LABEL = "person"

WEAPON_LABEL_TO_TYPE: dict[str, WeaponType] = {
    "fire": WeaponType.FIRE,
    "ranged_lethal": WeaponType.RANGED_LETHAL,
    "melee_lethal": WeaponType.MELEE_LETHAL,
    "non_lethal": WeaponType.NON_LETHAL,
}
"""Maps ``configs/models.yaml``'s PGIE ``labels.txt`` classes to
THREAT_ENGINE_SPEC.md's ``WeaponType`` categories -- confirmed directly
against the real ``yolo26m_weapon.onnx`` label file (``models/labels.txt``:
``fire, melee_lethal, non_lethal, person, ranged_lethal``), which already
uses THREAT_ENGINE_SPEC.md's own lethality taxonomy rather than a
material-based one -- correcting MODEL_REGISTRY.md's earlier, unconfirmed
``metal``/``non_metal``/``ranged_metal`` guess (see that document's
Model-001 entry). "person" is intentionally absent -- it is never a
weapon label, see ``PERSON_LABEL``."""

UNIFORM_LABEL_TO_CLASS: dict[str, UniformClass] = {
    "Civilian": UniformClass.CIVILIAN,
    "Military": UniformClass.MILITARY,
}
"""Maps the SGIE's own labels_vit.txt values to UniformClass. Any other
(or missing) secondary_label -- including the placeholder SGIE's
unrelated vehicle-type output -- falls back to UniformClass.UNKNOWN,
never a fabricated guess (THREAT_ENGINE_SPEC.md: unknown uniforms are
always routed to HUMAN_REVIEW, never auto-resolved)."""


def _bbox_center(bbox: BoundingBoxPayload) -> tuple[float, float]:
    return (bbox.left + bbox.width / 2, bbox.top + bbox.height / 2)


def _bbox_diagonal(bbox: BoundingBoxPayload) -> float:
    return math.hypot(bbox.width, bbox.height)


def associate_weapons_with_persons(
    detections: list[ObservationDetection],
) -> dict[int, tuple[UniformClass, WeaponType]]:
    """Returns ``{person_track_id: (uniform, weapon_type)}`` for every
    tracked person detection in this one frame's ``detections``.

    A person with no associated weapon gets ``WeaponType.NONE``
    (honestly "no weapon observed near this person", not "unknown").
    A person with no secondary_label (SGIE didn't run, or ran below its
    own confidence threshold and produced no classification) gets
    ``UniformClass.UNKNOWN``.
    """
    persons = [
        detection
        for detection in detections
        if detection.label == PERSON_LABEL and detection.track_id is not None
    ]
    weapons = [detection for detection in detections if detection.label in WEAPON_LABEL_TO_TYPE]

    candidate_pairs: list[tuple[float, ObservationDetection, ObservationDetection]] = []
    for person in persons:
        person_center = _bbox_center(person.bbox)
        max_distance = _bbox_diagonal(person.bbox)
        for weapon in weapons:
            weapon_center = _bbox_center(weapon.bbox)
            distance = math.hypot(
                person_center[0] - weapon_center[0], person_center[1] - weapon_center[1]
            )
            if distance <= max_distance:
                candidate_pairs.append((distance, person, weapon))
    candidate_pairs.sort(key=lambda pair: pair[0])

    weapon_type_by_person_track: dict[int, WeaponType] = {}
    assigned_person_tracks: set[int] = set()
    assigned_weapon_ids = set()
    for _distance, person, weapon in candidate_pairs:
        assert person.track_id is not None  # filtered above
        if person.track_id in assigned_person_tracks or weapon.detection_id in assigned_weapon_ids:
            continue
        weapon_type_by_person_track[person.track_id] = WEAPON_LABEL_TO_TYPE[weapon.label]
        assigned_person_tracks.add(person.track_id)
        assigned_weapon_ids.add(weapon.detection_id)

    result: dict[int, tuple[UniformClass, WeaponType]] = {}
    for person in persons:
        assert person.track_id is not None  # filtered above
        uniform = UNIFORM_LABEL_TO_CLASS.get(person.secondary_label or "", UniformClass.UNKNOWN)
        weapon_type = weapon_type_by_person_track.get(person.track_id, WeaponType.NONE)
        result[person.track_id] = (uniform, weapon_type)
    return result
