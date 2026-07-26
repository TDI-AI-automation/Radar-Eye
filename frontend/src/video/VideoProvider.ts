/**
 * VideoProvider abstraction.
 *
 * `CameraTile` (and any future video-consuming component) depends on this
 * interface only -- never a concrete provider. This is the seam RM-13
 * deliberately defers actual live video through: no RTSP/WebRTC/HLS
 * delivery mechanism is decided yet (see docs/FRONTEND_ARCHITECTURE.md,
 * "Open Backend Dependencies"). `PlaceholderVideoProvider` is the only
 * concrete implementation today.
 *
 * Capability flags let a component ask "can this provider do X" instead of
 * assuming every provider supports every feature -- e.g. a future
 * snapshot-only provider could implement this interface honestly by
 * returning `supportsLiveVideo() === false` rather than the component
 * needing to know which concrete class it received.
 */

export type VideoStatus = "unavailable" | "connecting" | "playing" | "error";

export interface VideoHandle {
  readonly status: VideoStatus;
  /** Present only when status === "playing". Concrete providers decide what
   * this actually is (a src URL, a MediaStream, a canvas ref, ...) -- kept
   * as `unknown` at the interface level so no provider is forced into a
   * shape that doesn't fit its transport. */
  readonly source: unknown;
  readonly errorMessage?: string;
}

export interface VideoProvider {
  /** Begin streaming for a camera. Returns a handle whose `status` the
   * caller should treat as reactive (expect it to change over time) --
   * concrete providers are responsible for their own subscription model. */
  connect(cameraId: string): VideoHandle;

  /** Release any resources associated with `cameraId`. Must be safe to call
   * even if connect() was never called for that id. */
  disconnect(cameraId: string): void;

  supportsLiveVideo(): boolean;
  supportsSnapshots(): boolean;
  supportsRecordingPlayback(): boolean;
}
