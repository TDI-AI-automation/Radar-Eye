"""Ground-plane homography estimation and projection (ADR-016).

Pure linear algebra, no I/O. Uses the classic Direct Linear Transform (DLT):
each image<->ground correspondence contributes two rows to a homogeneous
linear system A h = 0; h is the (unit-norm) right singular vector of A
associated with its smallest singular value, reshaped to a 3x3 matrix.

No OpenCV dependency: DeepStream owns OpenCV/CUDA on-device (RM-11); this
module only needs a small, independently testable routine, via numpy.
"""

from __future__ import annotations

import numpy as np

from services.calibration.types import (
    MIN_REFERENCE_POINTS,
    DegenerateCalibrationError,
    InsufficientReferencePointsError,
    ReferencePoint,
)


def compute_homography(reference_points: list[ReferencePoint]) -> np.ndarray:
    """Fit a 3x3 homography mapping image pixels to ground-plane metres.

    Raises InsufficientReferencePointsError if fewer than
    MIN_REFERENCE_POINTS were supplied, or DegenerateCalibrationError if the
    supplied points do not admit a numerically stable solution (e.g. all
    collinear).
    """
    if len(reference_points) < MIN_REFERENCE_POINTS:
        raise InsufficientReferencePointsError(
            f"calibrate() requires at least {MIN_REFERENCE_POINTS} reference points, "
            f"got {len(reference_points)}"
        )

    rows = []
    for point in reference_points:
        x, y = point.image_x, point.image_y
        gx, gy = point.ground_x, point.ground_y
        rows.append([-x, -y, -1, 0, 0, 0, x * gx, y * gx, gx])
        rows.append([0, 0, 0, -x, -y, -1, x * gy, y * gy, gy])
    a_matrix = np.array(rows, dtype=np.float64)

    _, singular_values, vh = np.linalg.svd(a_matrix)
    if singular_values[-2] < 1e-9 or (singular_values[-2] / singular_values[0]) < 1e-9:
        # The two smallest singular values are (near-)equal -- the null
        # space is not one-dimensional, so the fit is not well-determined
        # (e.g. collinear reference points).
        raise DegenerateCalibrationError(
            "reference points do not determine a unique homography "
            "(likely collinear or otherwise degenerate)"
        )

    homography = vh[-1].reshape(3, 3)
    if abs(homography[2, 2]) > 1e-12:
        homography = homography / homography[2, 2]
    return homography


def project(homography: np.ndarray, image_x: float, image_y: float) -> tuple[float, float]:
    """Project an image pixel to a ground-plane point (metres, camera-relative)."""
    vec = homography @ np.array([image_x, image_y, 1.0])
    w = vec[2]
    if abs(w) < 1e-12:
        raise DegenerateCalibrationError("projected point is at infinity (homogeneous w ~= 0)")
    return float(vec[0] / w), float(vec[1] / w)


def to_json(homography: np.ndarray) -> dict:
    """Serialize a homography matrix for JSONB storage."""
    return {"matrix": homography.tolist()}


def from_json(data: dict) -> np.ndarray:
    """Deserialize a homography matrix stored via to_json()."""
    return np.array(data["matrix"], dtype=np.float64)
