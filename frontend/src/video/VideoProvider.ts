/**
 * VideoProvider abstraction.
 *
 * `CameraTile` (and any future video-consuming component) depends on this
 * interface only -- never a concrete provider. `MpegtsVideoProvider` is
 * the concrete implementation today (Live Monitoring's low-latency
 * MPEG-TS-over-WebSocket video delivery, ADR-032, see its own docstring);
 * this is the seam that keeps components ignorant of the underlying
 * transport.
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
  /** Begin streaming for a camera. Returns the handle's current state
   * synchronously; concrete providers whose connection is asynchronous
   * (e.g. waiting for a WebSocket handshake) return a "connecting" handle
   * here and deliver later updates through subscribe(). Idempotent --
   * calling this again for a camera that's already connecting/connected
   * must not restart the connection. */
  connect(cameraId: string): VideoHandle;

  /** Reactive updates for `cameraId`'s handle -- mirrors ws/connection.ts's
   * `subscribeToChannel` convention. `callback` fires on every status
   * change after connect() (never for the synchronous value connect()
   * itself returned). Returns an unsubscribe function; safe to call
   * multiple times / after disconnect(). Providers with no asynchronous
   * state (e.g. a placeholder) may implement this as a no-op subscription
   * that's never called. */
  subscribe(cameraId: string, callback: (handle: VideoHandle) => void): () => void;

  /** Release any resources associated with `cameraId`. Must be safe to call
   * even if connect() was never called for that id. */
  disconnect(cameraId: string): void;

  supportsLiveVideo(): boolean;
  supportsSnapshots(): boolean;
  supportsRecordingPlayback(): boolean;
}
