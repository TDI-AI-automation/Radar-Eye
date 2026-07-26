import type { VideoHandle, VideoProvider } from "./VideoProvider";

/**
 * The only VideoProvider implementation that exists today. Honestly
 * reports zero capability -- no live video, no live-snapshot capture, no
 * recording playback -- rather than silently returning empty/fake data.
 * `connect()` always yields an "unavailable" handle so `CameraTile` can
 * render its existing "No Signal" state unmodified.
 *
 * Note: `supportsSnapshots()`/`supportsRecordingPlayback()` here describe
 * *this live-connection* capability (e.g. "grab a still frame from the
 * current feed"), not Evidence Viewer's archived-snapshot/recording
 * retrieval -- that's already fully served by RM-12's REST endpoints
 * (GET /snapshots/{id}/download, GET /recordings/{id}/download) and has
 * nothing to do with VideoProvider.
 *
 * Future providers (RTSPProvider, WebRTCProvider, HLSProvider) implement
 * the same interface and advertise real capability flags -- CameraTile
 * never needs to change to support them.
 */
export class PlaceholderVideoProvider implements VideoProvider {
  connect(_cameraId: string): VideoHandle {
    return { status: "unavailable", source: null };
  }

  disconnect(_cameraId: string): void {
    // No resources held.
  }

  supportsLiveVideo(): boolean {
    return false;
  }

  supportsSnapshots(): boolean {
    return false;
  }

  supportsRecordingPlayback(): boolean {
    return false;
  }
}
