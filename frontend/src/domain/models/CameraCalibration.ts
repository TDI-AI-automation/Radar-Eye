/**
 * CameraCalibration domain model. Mirrors shared/schemas/camera.py::
 * CameraCalibrationSchema (GET /calibration/{camera_id}, GET
 * /calibration/results, and the response of POST /calibration/start).
 *
 * homography_matrix/reference_points are typed as opaque dicts in the
 * generated schema (Pydantic stores them as raw JSON columns, not nested
 * models, per docs/DATABASE_SCHEMA.md's append-only camera_calibrations
 * table) -- referencePointCount() below is sourced from
 * services/calibration/service.py::calibrate()'s actual persisted shape
 * (`{"points": [{image_x, image_y, ground_x, ground_y}, ...]}`), not from
 * the OpenAPI schema, since the schema itself doesn't expose that
 * structure. Verified against the source, not assumed.
 */
export class CameraCalibration {
  constructor(
    readonly id: string,
    readonly cameraId: string,
    readonly referencePoints: unknown,
    readonly calibratedBy: string | null,
    readonly createdAt: Date,
  ) {}

  /** Returns null if the persisted shape doesn't match what
   * CalibrationService.calibrate() is known to write -- treated as
   * "unknown," never fabricated as 0. */
  referencePointCount(): number | null {
    if (
      typeof this.referencePoints === "object" &&
      this.referencePoints !== null &&
      "points" in this.referencePoints &&
      Array.isArray((this.referencePoints as { points: unknown }).points)
    ) {
      return (this.referencePoints as { points: unknown[] }).points.length;
    }
    return null;
  }
}
