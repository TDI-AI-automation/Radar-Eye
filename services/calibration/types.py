"""Internal Calibration Service types.

Source: docs/CAMERA_CALIBRATION_SPEC.md, ADR-016 (Distance Estimation
Strategy -- Ground Plane Projection).
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.constants.distance_zones import DistanceZone

MIN_REFERENCE_POINTS = 4
"""Mathematical minimum for a general (unconstrained) homography solution."""


@dataclass(frozen=True)
class ReferencePoint:
    """One image-pixel <-> ground-plane-metre correspondence.

    Ground coordinates are relative to the camera's own position on the
    ground plane (ground_x=0, ground_y=0), per the RM-05 design review --
    the operator measures each reference point's real-world position
    relative to the camera during calibration, so distance-from-camera
    falls straight out of the projected ground point's magnitude.
    """

    image_x: float
    image_y: float
    ground_x: float
    ground_y: float


@dataclass(frozen=True)
class DistanceEstimate:
    """Output of CalibrationService.estimate()."""

    distance_meters: float
    zone: DistanceZone


class CalibrationError(Exception):
    """Base class for Calibration Service errors."""


class InsufficientReferencePointsError(CalibrationError):
    """Fewer than MIN_REFERENCE_POINTS were supplied to calibrate()."""


class DegenerateCalibrationError(CalibrationError):
    """The supplied reference points do not admit a numerically stable
    homography (e.g. collinear points) -- the solver's system is singular
    or effectively so. Per the RM-05 design review, this is a structural
    validity check, not a reprojection-quality/acceptance gate: a
    mathematically valid homography is always persisted regardless of
    how well it reprojects its own construction points."""


class CalibrationNotFoundError(CalibrationError):
    """No calibration record exists yet for the requested camera_id."""
