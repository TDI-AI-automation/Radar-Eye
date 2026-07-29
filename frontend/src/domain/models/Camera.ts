/**
 * Camera domain model.
 *
 * Mirrors Radar-Eye backend's shared/schemas/camera.py::CameraSchema.
 * Note: the backend's `location` field is free text (no lat/lng or map
 * coordinates) -- Tactical Map placement is a known open gap, not
 * something this model can resolve (see docs/FRONTEND_ARCHITECTURE.md).
 */

export type CameraConnectionStatus = "CONNECTED" | "DISCONNECTED" | "RECONNECTING";

export type CameraLifecycleState =
  | "DRAFT"
  | "TESTING"
  | "VERIFIED"
  | "OPERATIONAL"
  | "MAINTENANCE"
  | "DISABLED";

export type CameraBrand = "HIKVISION" | "DAHUA" | "UNIVIEW" | "AXIS" | "HANWHA";

export class Camera {
  constructor(
    readonly id: string,
    readonly name: string,
    readonly location: string | null,
    readonly status: CameraConnectionStatus,
    readonly lifecycleState: CameraLifecycleState,
    readonly aiEnabled: boolean,
    readonly recordingEnabled: boolean,
    readonly brand: CameraBrand | null,
    readonly model: string | null,
    readonly ipAddress: string | null,
    readonly port: number | null,
    readonly streamPath: string | null,
    readonly username: string | null,
    readonly transport: string | null,
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
