import { postWebRtcOffer } from "@/api/endpoints/cameras";
import type { VideoHandle, VideoProvider } from "./VideoProvider";

/**
 * Real live-video delivery for Live Monitoring, replacing
 * PlaceholderVideoProvider. One RTCPeerConnection per camera, non-trickle
 * signaling (this deployment is single-node/LAN-only -- host ICE
 * candidates only, no STUN/TURN -- so gathering fully completes before the
 * one-shot POST /cameras/{id}/webrtc/offer exchange; see
 * apps.deepstream.app.live_stream's module docstring on the backend).
 *
 * AI overlays are burned server-side into the same encoded stream
 * (apps.deepstream's input-selector) -- this provider has no concept of
 * "AI on/off" at all; the connection and its remote track never change
 * when AI is toggled, only the pixels flowing into it.
 */
class CameraConnection {
  handle: VideoHandle = { status: "connecting", source: null };
  readonly listeners = new Set<(handle: VideoHandle) => void>();
  pc: RTCPeerConnection | null = null;
}

export class WebRtcVideoProvider implements VideoProvider {
  private readonly connections = new Map<string, CameraConnection>();

  connect(cameraId: string): VideoHandle {
    const existing = this.connections.get(cameraId);
    if (existing) return existing.handle;

    const connection = new CameraConnection();
    this.connections.set(cameraId, connection);

    if (typeof RTCPeerConnection === "undefined") {
      connection.handle = {
        status: "error",
        source: null,
        errorMessage: "WebRTC is not available in this browser",
      };
      return connection.handle;
    }

    void this.negotiate(cameraId, connection);
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
    connection.pc?.close();
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

  private async negotiate(cameraId: string, connection: CameraConnection): Promise<void> {
    try {
      const pc = new RTCPeerConnection();
      connection.pc = pc;
      pc.addTransceiver("video", { direction: "recvonly" });

      pc.ontrack = (event) => {
        const stream = event.streams[0] ?? new MediaStream([event.track]);
        this.setHandle(cameraId, connection, { status: "playing", source: stream });

        // "unmute" fires the first time this track actually carries real
        // media data -- the browser-side half of Stage B's transport
        // evidence (backend: "Bitstream received"/"AppSrc push"/"RTP
        // packet transmitted"; this is "first browser frame rendered").
        event.track.addEventListener(
          "unmute",
          () => {
            console.info(`[Live Monitoring] First frame rendered for camera ${cameraId}`);
          },
          { once: true },
        );
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "failed" || pc.connectionState === "closed") {
          this.setHandle(cameraId, connection, {
            status: "error",
            source: null,
            errorMessage: `WebRTC connection ${pc.connectionState}`,
          });
        }
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await waitForIceGatheringComplete(pc);

      const localDescription = pc.localDescription;
      if (!localDescription) throw new Error("No local SDP after ICE gathering");

      const answer = await postWebRtcOffer(cameraId, {
        sdp: localDescription.sdp,
        type: "offer",
      });
      if (!answer) throw new Error("Live Monitoring returned no answer");

      await pc.setRemoteDescription({ type: "answer", sdp: answer.sdp });
    } catch (err) {
      this.setHandle(cameraId, connection, {
        status: "error",
        source: null,
        errorMessage: err instanceof Error ? err.message : "WebRTC negotiation failed",
      });
    }
  }
}

function waitForIceGatheringComplete(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const check = () => {
      if (pc.iceGatheringState === "complete") {
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    };
    pc.addEventListener("icegatheringstatechange", check);
  });
}
