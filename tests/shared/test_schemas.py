"""Tests for shared/schemas — API response models and round-trip serialisation.

Acceptance criteria (RM-02):
  - ApiResponse wrapping works for typed payloads.
  - All schema models construct and round-trip cleanly.
  - Enum fields from shared.constants are used (no plain strings for
    constrained values).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from shared.constants import DistanceZone, IncidentStatus, IncidentType, ThreatLevel, UniformClass, WeaponType
from shared.schemas import (
    ActiveThreatSchema,
    AlarmSchema,
    ApiResponse,
    CameraHealthSchema,
    CameraSchema,
    HumanReviewSchema,
    IncidentCreatedSchema,
    IncidentSchema,
    IncidentSummarySchema,
    IncidentUpdatedSchema,
    ThreatAssessmentSchema,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CAMERA_ID = uuid.uuid4()
_INCIDENT_ID = uuid.uuid4()
_REVIEW_ID = uuid.uuid4()
_NOW = datetime.now(tz=timezone.utc)


def _round_trip(model):  # type: ignore[type-arg]
    return type(model).model_validate(json.loads(model.model_dump_json()))


# ---------------------------------------------------------------------------
# ApiResponse
# ---------------------------------------------------------------------------


class TestApiResponse:
    def test_success_with_data(self) -> None:
        resp = ApiResponse[str](success=True, data="hello")
        assert resp.success is True
        assert resp.data == "hello"

    def test_success_no_data(self) -> None:
        resp = ApiResponse[str](success=True)
        assert resp.data is None

    def test_failure_response(self) -> None:
        resp = ApiResponse[None](success=False)
        assert resp.success is False

    def test_round_trip_with_threat_schema(self) -> None:
        threat = ThreatAssessmentSchema(
            camera_id=_CAMERA_ID,
            track_id=1,
            weapon_type=WeaponType.RANGED_LETHAL,
            uniform=UniformClass.CIVILIAN,
            zone=DistanceZone.ZONE_1,
            threat_level=ThreatLevel.HIGH,
        )
        resp = ApiResponse[ThreatAssessmentSchema](success=True, data=threat)
        data = json.loads(resp.model_dump_json())
        assert data["success"] is True
        assert data["data"]["threat_level"] == "HIGH"


# ---------------------------------------------------------------------------
# ThreatAssessmentSchema / ActiveThreatSchema
# ---------------------------------------------------------------------------


class TestThreatSchemas:
    def _make(self) -> ThreatAssessmentSchema:
        return ThreatAssessmentSchema(
            camera_id=_CAMERA_ID,
            track_id=7,
            weapon_type=WeaponType.MELEE_LETHAL,
            uniform=UniformClass.CIVILIAN,
            zone=DistanceZone.ZONE_2,
            threat_level=ThreatLevel.MEDIUM,
        )

    def test_round_trip(self) -> None:
        schema = self._make()
        restored = _round_trip(schema)
        assert restored.threat_level == ThreatLevel.MEDIUM
        assert restored.zone == DistanceZone.ZONE_2

    def test_active_threat_is_subtype(self) -> None:
        active = ActiveThreatSchema(
            camera_id=_CAMERA_ID,
            track_id=7,
            weapon_type=WeaponType.NONE,
            uniform=UniformClass.MILITARY,
            zone=DistanceZone.ZONE_3,
            threat_level=ThreatLevel.ALLY,
        )
        assert isinstance(active, ThreatAssessmentSchema)

    def test_invalid_threat_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ThreatAssessmentSchema(
                camera_id=_CAMERA_ID,
                track_id=1,
                weapon_type=WeaponType.NONE,
                uniform=UniformClass.CIVILIAN,
                zone=DistanceZone.ZONE_1,
                threat_level="EXTREME",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# IncidentSchema
# ---------------------------------------------------------------------------


class TestIncidentSchemas:
    def test_full_schema_round_trip(self) -> None:
        schema = IncidentSchema(
            incident_id=_INCIDENT_ID,
            camera_id=_CAMERA_ID,
            track_id=3,
            incident_type=IncidentType.THREAT,
            threat_level=ThreatLevel.HIGH,
            status=IncidentStatus.ACTIVE,
            created_at=_NOW,
            updated_at=_NOW,
        )
        restored = _round_trip(schema)
        assert restored.status == IncidentStatus.ACTIVE
        assert restored.incident_id == _INCIDENT_ID

    def test_summary_schema(self) -> None:
        summary = IncidentSummarySchema(
            incident_id=_INCIDENT_ID,
            camera_id=_CAMERA_ID,
            threat_level=ThreatLevel.MEDIUM,
            status=IncidentStatus.NEW,
        )
        assert summary.status == IncidentStatus.NEW

    def test_ws_created_schema(self) -> None:
        ws = IncidentCreatedSchema(
            incident_id=_INCIDENT_ID,
            camera_id=_CAMERA_ID,
            track_id=5,
            status=IncidentStatus.NEW,
        )
        assert ws.track_id == 5

    def test_ws_updated_schema(self) -> None:
        ws = IncidentUpdatedSchema(
            incident_id=_INCIDENT_ID,
            old_status=IncidentStatus.ACTIVE,
            new_status=IncidentStatus.ACKNOWLEDGED,
        )
        assert ws.new_status == IncidentStatus.ACKNOWLEDGED


# ---------------------------------------------------------------------------
# HumanReviewSchema
# ---------------------------------------------------------------------------


class TestHumanReviewSchema:
    def test_round_trip(self) -> None:
        schema = HumanReviewSchema(
            review_item_id=_REVIEW_ID,
            camera_id=_CAMERA_ID,
            track_id=9,
            reason="uniform_unknown",
        )
        restored = _round_trip(schema)
        assert restored.status == "OPEN"
        assert restored.reason == "uniform_unknown"

    def test_default_status_is_open(self) -> None:
        """Per docs/DATABASE_SCHEMA.md, human_review_items' initial status is OPEN."""
        schema = HumanReviewSchema(
            review_item_id=_REVIEW_ID,
            camera_id=_CAMERA_ID,
            track_id=1,
            reason="uniform_unknown",
        )
        assert schema.status == "OPEN"


# ---------------------------------------------------------------------------
# CameraSchema / CameraHealthSchema
# ---------------------------------------------------------------------------


class TestCameraSchemas:
    def test_camera_schema_round_trip(self) -> None:
        schema = CameraSchema(
            camera_id=_CAMERA_ID,
            name="North Gate",
            status="CONNECTED",
            created_at=_NOW,
            updated_at=_NOW,
        )
        restored = _round_trip(schema)
        assert restored.name == "North Gate"
        assert restored.status == "CONNECTED"

    def test_camera_health_connected(self) -> None:
        health = CameraHealthSchema(
            camera_id=_CAMERA_ID,
            status="CONNECTED",
            fps=29.8,
            last_frame_age_seconds=0.03,
        )
        assert health.fps == pytest.approx(29.8)

    def test_camera_health_disconnected_nullable_fields(self) -> None:
        health = CameraHealthSchema(
            camera_id=_CAMERA_ID,
            status="DISCONNECTED",
        )
        assert health.fps is None
        assert health.last_frame_age_seconds is None

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CameraSchema(
                camera_id=_CAMERA_ID,
                name="X",
                status="BROKEN",  # type: ignore[arg-type]
                created_at=_NOW,
                updated_at=_NOW,
            )


# ---------------------------------------------------------------------------
# AlarmSchema
# ---------------------------------------------------------------------------


class TestAlarmSchema:
    def test_round_trip(self) -> None:
        schema = AlarmSchema(
            incident_id=_INCIDENT_ID,
            camera_id=_CAMERA_ID,
            threat_level=ThreatLevel.HIGH,
        )
        restored = _round_trip(schema)
        assert restored.threat_level == ThreatLevel.HIGH

    def test_non_high_threat_allowed_by_model(self) -> None:
        """The schema itself does not enforce the HIGH-only alarm rule —
        that constraint belongs to the Threat Engine service logic (ADR-026).
        """
        schema = AlarmSchema(
            incident_id=_INCIDENT_ID,
            camera_id=_CAMERA_ID,
            threat_level=ThreatLevel.MEDIUM,
        )
        assert schema.threat_level == ThreatLevel.MEDIUM
