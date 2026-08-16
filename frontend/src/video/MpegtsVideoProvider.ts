import type Mpegts from "mpegts.js";
import { apiBaseUrl } from "@/api/instance";
import { tokenStore } from "@/auth/tokenStore";
import type { VideoHandle, VideoProvider } from "./VideoProvider";

/**
 * Real live-video delivery for Live Monitoring (ADR-032), replacing
 * HlsVideoProvider (rejected: ~10s measured glass-to-glass latency,
 * unacceptable for real-time surveillance). One `mpegts.js` MSE player
 * per camera, reading low-latency MPEG-TS over a WebSocket relay
 * (`apps.api`'s `/ws/cameras/{id}/video`, a pure byte relay onto
 * `apps.deepstream`'s permanent `tcpserversink` -- no signaling, no
 * SDP/ICE, no per-connection GStreamer branch).
 *
 * AI overlays are burned server-side into the same encoded stream --
 * this provider has no concept of "AI on/off" at all; the URL and its
 * bytes never change when AI is toggled, only the pixels flowing into
 * them (identical invariant to the providers this replaces).
 *
 * The auth token is embedded in the WebSocket URL's `?token=` query
 * parameter (mpegts.js owns the WebSocket connection internally --
 * there is no hook to attach a custom header to its handshake, same
 * constraint every other WebSocket channel in this app already works
 * around -- see apps/api/app/websockets/routes.py).
 *
 * `mpegts.js` is loaded via a dynamic `import()`, never a static
 * top-level one, and only from client-side code paths (guarded by
 * `typeof window === "undefined"` in `connect()`) -- its bundle
 * references `self` unconditionally at module-evaluation time (Worker-
 * related feature detection), which throws under this app's SSR
 * (TanStack Start renders the initial page in Node, which has no
 * `self`). The SSR-time `connect()` call is otherwise a no-op: the
 * client re-renders with its own fresh `MpegtsVideoProvider` instance
 * after hydration and calls `connect()` again for real.
 */
class CameraConnection {
  handle: VideoHandle = { status: "connecting", source: null };
  readonly listeners = new Set<(handle: VideoHandle) => void>();
  player: Mpegts.Player | null = null;
  retryTimer: ReturnType<typeof setTimeout> | null = null;
}

const RETRY_DELAY_MS = 2000;
/** Camera not yet added to Live Monitoring, or DeepStream hasn't started
 * its TCP relay yet -- a fixed short retry rather than exponential
 * backoff, matching how quickly a freshly-registered camera typically
 * becomes watchable. */

let mpegtsModulePromise: Promise<typeof Mpegts> | null = null;
function loadMpegts(): Promise<typeof Mpegts> {
  mpegtsModulePromise ??= import("mpegts.js").then((m) => m.default);
  return mpegtsModulePromise;
}

function wsUrlFor(cameraId: string): string {
  const token = tokenStore.getAccessToken() ?? "";
  const base = apiBaseUrl.replace(/^http/, "ws");
  return `${base}/ws/cameras/${cameraId}/video?token=${encodeURIComponent(token)}`;
}

export class MpegtsVideoProvider implements VideoProvider {
  private readonly connections = new Map<string, CameraConnection>();

  connect(cameraId: string): VideoHandle {
    const existing = this.connections.get(cameraId);
    if (existing) return existing.handle;

    const connection = new CameraConnection();
    this.connections.set(cameraId, connection);

    if (typeof window === "undefined") {
      // SSR -- see this class's own docstring. Never touch mpegts.js here.
      return connection.handle;
    }

    void this.startPlayer(cameraId, connection);
    return connection.handle;
  }

  subscribe(cameraId: string, callback: (handle: VideoHandle) => void): () => void {
    const connection = this.connections.get(cameraId);
    if (!connection) return () => {};
    connection.listeners.add(callback);
    return () => {
      connection.listeners.delete(callback);
    };
  }

  disconnect(cameraId: string): void {
    const connection = this.connections.get(cameraId);
    if (!connection) return;
    if (connection.retryTimer !== null) clearTimeout(connection.retryTimer);
    connection.player?.destroy();
    this.connections.delete(cameraId);
  }

  supportsLiveVideo(): boolean {
    return true;
  }

  supportsSnapshots(): boolean {
    return false;
  }

  supportsRecordingPlayback(): boolean {
    return false;
  }

  private setHandle(cameraId: string, connection: CameraConnection, handle: VideoHandle): void {
    // The camera may have been disconnected (or reconnected, replacing
    // this CameraConnection) while an async step below was in flight.
    if (this.connections.get(cameraId) !== connection) return;
    connection.handle = handle;
    for (const listener of connection.listeners) listener(handle);
  }

  private async startPlayer(cameraId: string, connection: CameraConnection): Promise<void> {
    const mpegts = await loadMpegts();
    // Disconnected (or reconnected, replacing this CameraConnection)
    // while the dynamic import above was in flight.
    if (this.connections.get(cameraId) !== connection) return;

    if (!mpegts.isSupported()) {
      this.setHandle(cameraId, connection, {
        status: "error",
        source: null,
        errorMessage: "Low-latency video playback is not supported in this browser",
      });
      return;
    }

    const player = mpegts.createPlayer(
      { type: "mpegts", isLive: true, url: wsUrlFor(cameraId) },
      {
        // Real-time playback over a LAN, not VOD -- an internal IO
        // stash buffer only adds latency here.
        enableStashBuffer: false,
        isLive: true,
        // Chase (and, if needed, mildly speed up) playback to keep the
        // HTMLMediaElement's own buffer from accumulating latency over
        // a long-running connection.
        liveBufferLatencyChasing: true,
        liveSync: true,
      },
    );
    connection.player = player;

    player.on(mpegts.Events.ERROR, (type: string) => {
      if (type === mpegts.ErrorTypes.NETWORK_ERROR) {
        // WebSocket closed (camera not streaming yet, DeepStream
        // restarting, transient LAN hiccup) -- retry rather than
        // surfacing a hard error, matching this app's other video
        // providers' "keep trying" behavior for a camera that will
        // very likely become available shortly.
        this.retryAfterDelay(cameraId, connection);
        return;
      }
      this.setHandle(cameraId, connection, {
        status: "error",
        source: null,
        errorMessage: "Live video playback failed",
      });
      player.destroy();
      connection.player = null;
    });

    // `source` becomes the live player immediately (not gated on a
    // "first data arrived" event, unlike the WebRTC/HLS providers this
    // replaces) -- mpegts.js requires `attachMediaElement()` before
    // `load()` can do anything, and that only happens once
    // VideoStreamElement (LiveCameraTile.tsx) actually mounts a real
    // <video> element, which in turn only happens once this handle
    // reports "playing". The <video> element's own black/loading state
    // covers the gap until real frames arrive, same as plain
    // `<video src>` playback.
    this.setHandle(cameraId, connection, { status: "playing", source: player });
  }

  private retryAfterDelay(cameraId: string, connection: CameraConnection): void {
    connection.player?.destroy();
    connection.player = null;
    connection.retryTimer = setTimeout(() => {
      connection.retryTimer = null;
      if (this.connections.get(cameraId) === connection) {
        void this.startPlayer(cameraId, connection);
      }
    }, RETRY_DELAY_MS);
  }
}
