/**
 * Camera domain model.
 *
 * Mirrors Radar-Eye backend's shared/schemas/camera.py::CameraSchema.
 * Note: the backend's `location` field is free text (no lat/lng or map
 * coordinates) -- Tactical Map placement is a known open gap, not
 * something this model can resolve (see docs/FRONTEND_ARCHITECTURE.md).
 */

export type CameraConnectionStatus = "CONNECTED" | "DISCONNECTED" | "RECONNECTING";

export class Camera {
  constructor(
    readonly id: string,
    readonly name: string,
    readonly location: string | null,
    readonly status: CameraConnectionStatus,
    readonly createdAt: Date,
    readonly updatedAt: Date,
  ) {}

  isOnline(): boolean {
    return this.status === "CONNECTED";
  }

  healthStatus(): "healthy" | "degraded" | "offline" {
    switch (this.status) {
      case "CONNECTED":
        return "healthy";
      case "RECONNECTING":
        return "degraded";
      case "DISCONNECTED":
        return "offline";
    }
  }

  /** Recording requires an actual flowing stream -- RECONNECTING has no
   * frames arriving either, same as DISCONNECTED, for this purpose. */
  canRecord(): boolean {
    return this.status === "CONNECTED";
  }
}
