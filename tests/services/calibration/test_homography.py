"""Tests for services.calibration.homography.

Source: docs/CAMERA_CALIBRATION_SPEC.md ("Validation" -- measure known
distances, calculate error) and docs/BENCHMARK_ACCEPTANCE_CRITERIA.md
(distance error <=2m @20m, <=5m @50m). No physical cameras exist yet, so
per the RM-05 design review these tests validate the math against a known
synthetic homography rather than real-world measurements (deferred to
RM-11 / physical mounting).
"""

from __future__ import annotations

import numpy as np
import pytest

from services.calibration.homography import compute_homography, from_json, project, to_json
from services.calibration.types import (
    DegenerateCalibrationError,
    InsufficientReferencePointsError,
    ReferencePoint,
)

# A hand-chosen, invertible homography with a mild perspective term (not a
# pure affine transform), used as ground truth to synthesize test data.
_H_TRUE = np.array(
    [
        [0.05, 0.0, 0.0],
        [0.0, 0.05, 0.0],
        [0.0002, 0.0003, 1.0],
    ]
)


def _apply(matrix: np.ndarray, x: float, y: float) -> tuple[float, float]:
    """Reference-oracle homogeneous transform, independent of project()."""
    vec = matrix @ np.array([x, y, 1.0])
    return float(vec[0] / vec[2]), float(vec[1] / vec[2])


def _reference_points(image_points: list[tuple[float, float]]) -> list[ReferencePoint]:
    points = []
    for ix, iy in image_points:
        gx, gy = _apply(_H_TRUE, ix, iy)
        points.append(ReferencePoint(image_x=ix, image_y=iy, ground_x=gx, ground_y=gy))
    return points


class TestComputeHomography:
    def test_recovers_known_homography_up_to_scale(self) -> None:
        points = _reference_points([(0, 0), (100, 0), (0, 100), (100, 100)])
        recovered = compute_homography(points)

        normalized_true = _H_TRUE / _H_TRUE[2, 2]
        normalized_recovered = recovered / recovered[2, 2]
        assert np.allclose(normalized_recovered, normalized_true, atol=1e-6)

    def test_overdetermined_system_still_recovers_homography(self) -> None:
        points = _reference_points([(0, 0), (100, 0), (0, 100), (100, 100), (50, 50), (25, 75)])
        recovered = compute_homography(points)

        normalized_true = _H_TRUE / _H_TRUE[2, 2]
        normalized_recovered = recovered / recovered[2, 2]
        assert np.allclose(normalized_recovered, normalized_true, atol=1e-6)

    def test_raises_when_fewer_than_minimum_reference_points(self) -> None:
        points = _reference_points([(0, 0), (100, 0), (0, 100)])
        with pytest.raises(InsufficientReferencePointsError):
            compute_homography(points)

    def test_raises_on_collinear_reference_points(self) -> None:
        points = _reference_points([(0, 0), (10, 0), (20, 0), (30, 0)])
        with pytest.raises(DegenerateCalibrationError):
            compute_homography(points)


class TestProject:
    def test_projects_held_out_point_within_benchmark_tolerance(self) -> None:
        calibration_points = _reference_points([(0, 0), (100, 0), (0, 100), (100, 100)])
        recovered = compute_homography(calibration_points)

        held_out_image_point = (37.0, 62.0)
        expected_gx, expected_gy = _apply(_H_TRUE, *held_out_image_point)

        gx, gy = project(recovered, *held_out_image_point)
        assert gx == pytest.approx(expected_gx, abs=1e-6)
        assert gy == pytest.approx(expected_gy, abs=1e-6)

    def test_raises_when_projected_point_is_at_infinity(self) -> None:
        # Last row [1, 0, 0] makes w = image_x -- zero exactly at image_x=0.
        matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
        with pytest.raises(DegenerateCalibrationError):
            project(matrix, 0.0, 5.0)

    @pytest.mark.parametrize(
        "target_distance_meters,max_error_meters",
        [(20.0, 2.0), (50.0, 5.0)],
    )
    def test_distance_estimate_within_acceptance_criteria(
        self, target_distance_meters: float, max_error_meters: float
    ) -> None:
        calibration_points = _reference_points([(0, 0), (100, 0), (0, 100), (100, 100)])
        recovered = compute_homography(calibration_points)

        h_inv = np.linalg.inv(_H_TRUE)
        image_x, image_y = _apply(h_inv, target_distance_meters, 0.0)

        gx, gy = project(recovered, image_x, image_y)
        distance = (gx**2 + gy**2) ** 0.5
        assert distance == pytest.approx(target_distance_meters, abs=max_error_meters)


class TestJsonRoundTrip:
    def test_to_json_from_json_round_trip(self) -> None:
        points = _reference_points([(0, 0), (100, 0), (0, 100), (100, 100)])
        matrix = compute_homography(points)

        restored = from_json(to_json(matrix))
        assert np.allclose(restored, matrix)
