import Hls from "hls.js";
import { apiBaseUrl } from "@/api/instance";
import { tokenStore } from "@/auth/tokenStore";
import type { VideoHandle, VideoProvider } from "./VideoProvider";

/**
 * Real live-video delivery for Live Monitoring (ADR-031), replacing
 * WebRtcVideoProvider. One `Hls.js` instance per camera, reading the HLS
 * playlist/segments `apps.api` serves from `apps.deepstream`'s
 * `hlssink2` output (`GET /cameras/{id}/hls/playlist.m3u8`) -- no
 * signaling, no SDP/ICE, no peer connection.
 *
 * AI overlays are burned server-side into the same encoded stream -- this
 * provider has no concept of "AI on/off" at all; the playlist URL and its
 * segments never change when AI is toggled, only the pixels flowing into
 * them (identical invariant to WebRtcVideoProvider's own).
 *
 * `hls.js` is used unconditionally (never native `<video src>` HLS, even
 * on browsers with native support) because native playback has no way to
 * attach the `Authorization` header this API requires (Bearer token, not
 * a cookie) -- `hls.js`'s `xhrSetup` hook is the only mechanism that can
 * authenticate every playlist/segment request it makes.
 */
class CameraConnection {
  handle: VideoHandle = { status: "connecting", source: null };
  readonly listeners = new Set<(handle: VideoHandle) => void>();
  hls: Hls | null = null;
  retryTimer: ReturnType<typeof setTimeout> | null = null;
}

const RETRY_DELAY_MS = 2000;
/** Camera not yet added to Live Monitoring, or DeepStream hasn't written
 * a first playlist yet -- a fixed short retry rather than exponential
 * backoff, matching how quickly a freshly-registered camera typically
 * becomes watchable (no reason to make an operator wait longer for
 * something this routine). */

export class HlsVideoProvider implements VideoProvider {
  private readonly connections = new Map<string, CameraConnection>();

  connect(cameraId: string): VideoHandle {
    const existing = this.connections.get(cameraId);
    if (existing) return existing.handle;

    const connection = new CameraConnection();
    this.connections.set(cameraId, connection);

    if (!Hls.isSupported()) {
      connection.handle = {
        status: "error",
        source: null,
        errorMessage: "HLS playback is not supported in this browser",
      };
      return connection.handle;
    }

    this.startHls(cameraId, connection);
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
    connection.hls?.destroy();
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

  private startHls(cameraId: string, connection: CameraConnection): void {
    const playlistUrl = `${apiBaseUrl}/cameras/${cameraId}/hls/playlist.m3u8`;
    const hls = new Hls({
      xhrSetup: (xhr) => {
        const token = tokenStore.getAccessToken();
        if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      },
    });
    connection.hls = hls;

    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      // `source` is the live Hls instance itself, not a URL string --
      // VideoStreamElement attaches it to its own <video> element via
      // `hls.attachMedia(videoEl)`, the hls.js analogue of
      // `video.srcObject = mediaStream` for the WebRTC provider this
      // replaces. Loading (loadSource, above) does not require a media
      // element to already be attached, so this fires independent of
      // whether any component has mounted a <video> yet.
      this.setHandle(cameraId, connection, { status: "playing", source: hls });
    });

    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (!data.fatal) return;
      switch (data.type) {
        case Hls.ErrorTypes.NETWORK_ERROR:
          // The playlist 404s (camera not added to Live Monitoring yet,
          // or DeepStream hasn't written a first segment yet) or a
          // transient LAN hiccup -- retry rather than surfacing a hard
          // error, matching WebRtcVideoProvider's own "keep trying,
          // don't give up" behavior for a camera that will very likely
          // become available shortly.
          this.retryAfterDelay(cameraId, connection);
          break;
        case Hls.ErrorTypes.MEDIA_ERROR:
          hls.recoverMediaError();
          break;
        default:
          this.setHandle(cameraId, connection, {
            status: "error",
            source: null,
            errorMessage: "HLS playback failed",
          });
          hls.destroy();
          connection.hls = null;
      }
    });

    hls.loadSource(playlistUrl);
  }

  private retryAfterDelay(cameraId: string, connection: CameraConnection): void {
    connection.hls?.destroy();
    connection.hls = null;
    connection.retryTimer = setTimeout(() => {
      connection.retryTimer = null;
      if (this.connections.get(cameraId) === connection) {
        this.startHls(cameraId, connection);
      }
    }, RETRY_DELAY_MS);
  }
}
