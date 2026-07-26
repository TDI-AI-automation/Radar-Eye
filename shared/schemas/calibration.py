"""Calibration Center write-route schemas -- RM-12 Phase 4.

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Calibration Center section
  (POST /calibration/start, POST /calibration/validate). Maps directly onto
  services.calibration.service.CalibrationService's existing public
  interface: "start" == calibrate() (compute + persist a new homography
  from reference points), "validate" == estimate() (project one image
  point through the camera's current calibration, for the operator to
  visually confirm accuracy against a known real-world point).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from shared.constants.distance_zones import DistanceZone


class ReferencePointSchema(BaseModel):
    """One image-pixel <-> ground-plane-metre correspondence
    (services.calibration.types.ReferencePoint)."""

    image_x: float
    image_y: float
    ground_x: float
    ground_y: float


class CalibrationStartRequestSchema(BaseModel):
    """Body of ``POST /calibration/start``."""

    camera_id: uuid.UUID
    reference_points: list[ReferencePointSchema]


class CalibrationValidateRequestSchema(BaseModel):
    """Body of ``POST /calibration/validate``."""

    camera_id: uuid.UUID
    image_x: float
    image_y: float


class CalibrationValidationResultSchema(BaseModel):
    """Returned by ``POST /calibration/validate``."""

    camera_id: uuid.UUID
    distance_meters: float
    zone: DistanceZone
