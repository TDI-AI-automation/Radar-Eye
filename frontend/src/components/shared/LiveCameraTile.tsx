import { useEffect, useRef, useState } from "react";
import type Mpegts from "mpegts.js";
import { Maximize2, Circle, VideoOff } from "lucide-react";
import type { Camera } from "@/domain/models/Camera";
import type { ThreatAssessment } from "@/domain/models/ThreatAssessment";
import { useVideoHandle } from "@/video/VideoProviderContext";
import { ThreatLevelBadge } from "./ThreatLevelBadge";

/**
 * Real-data replacement for components/hud/CameraTile.tsx, kept as a
 * separate component rather than modifying the original in place --
 * CameraTile's props (fps/latency/confidence/aiOn/health as plain
 * fabricated numbers, x/y/w/h bounding-box detections) have no backend
 * source at all (docs/FRONTEND_ARCHITECTURE.md §8's "Open backend
 * dependency" already flagged this in Phase 0: "the backend's
 * ThreatAssessmentEvent carries no bounding-box coordinates for the
 * detection-overlay feature"). This preserves the visual language (video
 * area, top/bottom gradient overlays, REC indicator, fullscreen control)
 * but renders only real data: live video via the active VideoProvider
 * (falling back to a "No Signal" state for "connecting"/"error"/"unavailable"),
 * real per-camera fps (nullable), and active threats for this camera as
 * labeled chips instead of fabricated pixel-space boxes. AI overlays (when
 * enabled) are already burned into the stream server-side -- this
 * component has no separate overlay-rendering logic. PTZ/volume/wifi
 * controls from the original are dropped entirely -- no backend capability
 * backs any of them, and keeping the buttons would imply control that
 * doesn't exist.
 */
export function LiveCameraTile({
  camera,
  fps,
  threats,
  emphasized,
  onFullscreen,
}: {
  camera: Camera;
  fps: number | null;
  threats: ThreatAssessment[];
  emphasized?: boolean;
  onFullscreen?: () => void;
}) {
  const videoHandle = useVideoHandle(camera.id);
  const [videoElementErrored, setVideoElementErrored] = useState(false);
  useEffect(() => setVideoElementErrored(false), [videoHandle]);

  const player =
    videoHandle.status === "playing" && isMpegtsPlayer(videoHandle.source)
      ? videoHandle.source
      : null;
  const isPlaying = player !== null && !videoElementErrored;

  const critical = threats.some((t) => t.requiresImmediateAction());
  const border = critical
    ? "border-red-glow animate-pulse-red"
    : emphasized
      ? "border-primary"
      : "border-border";

  return (
    <div
      className={`hud-panel rounded overflow-hidden group relative border ${border} transition-colors`}
    >
      <div className="relative aspect-video bg-black">
        {isPlaying ? (
          <VideoStreamElement player={player} onError={() => setVideoElementErrored(true)} />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground/60">
            <VideoOff className="h-8 w-8 mb-2" strokeWidth={1.25} />
            <div className="font-mono text-[10px] uppercase tracking-[0.25em]">
              {videoHandle.status === "unavailable" ? "No Signal" : videoHandle.status}
            </div>
            <div className="font-mono text-[9px] tracking-widest mt-1">{camera.name}</div>
          </div>
        )}

        {threats.length > 0 && (
          <div className="absolute bottom-1 left-1 right-1 z-10 flex flex-wrap gap-1">
            {threats.map((t) => (
              <ThreatLevelBadge key={t.trackId} level={t.threatLevel} />
            ))}
          </div>
        )}

        <div className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-2 py-1.5 bg-gradient-to-b from-black/75 to-transparent">
          <div className="flex items-center gap-2">
            {camera.isOnline() ? (
              <Circle className="h-2 w-2 fill-red-glow text-red-glow animate-blink" />
            ) : (
              <Circle className="h-2 w-2 fill-muted-foreground/50 text-muted-foreground/50" />
            )}
            <span className="font-mono text-[10px] uppercase tracking-widest text-white/90">
              {camera.isOnline() ? "REC" : "OFF"} · {camera.name}
            </span>
            <span className="hidden md:inline text-[10px] font-mono text-white/50">
              {camera.location ?? "Unassigned"}
            </span>
          </div>
          <div className="flex items-center gap-1.5 font-mono text-[9px] text-white/60">
            <span>{fps !== null ? `${fps}fps` : "—"}</span>
          </div>
        </div>

        <div className="absolute inset-x-0 bottom-0 z-20 flex items-center justify-end px-2 py-1.5 bg-gradient-to-t from-black/75 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={onFullscreen}>
            <Maximize2 className="h-3.5 w-3.5 text-white/80" />
          </button>
        </div>
      </div>
    </div>
  );
}

/** Attaches an mpegts.js player to a real <video> element -- unlike
 * hls.js's `attachMedia`, mpegts.js requires `attachMediaElement()`
 * followed by an explicit `load()` (and `play()`, since `autoPlay` alone
 * doesn't reliably start a freshly-loaded MSE source across browsers) to
 * actually begin playback; MpegtsVideoProvider creates the player but
 * deliberately never calls these itself, since it has no `<video>`
 * element to attach until this component mounts. `onError` lets the
 * caller fall back to the "No Signal" state if playback itself fails
 * after MpegtsVideoProvider already reported "playing". Detaches (not
 * destroys -- MpegtsVideoProvider owns the instance's lifecycle) on
 * unmount so a remount can reattach the same instance without
 * restarting the underlying WebSocket connection. */
function VideoStreamElement({ player, onError }: { player: Mpegts.Player; onError: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    player.attachMediaElement(video);
    player.load();
    void player.play()?.catch(() => {
      // Autoplay can be rejected by browser policy even with `muted` in
      // rare cases -- the <video> element's own onError/black-frame
      // state already communicates this; no separate handling needed.
    });
    return () => {
      // MpegtsVideoProvider can call player.destroy() (a hard playback
      // error, or a network-error retry -- see its own retryAfterDelay())
      // between this effect's mount and this cleanup running. A destroyed
      // player's internal engine reference is already null, so calling
      // detachMediaElement() on it throws (reproduced: "Cannot read
      // properties of null (reading 'detachMediaElement')"), which this
      // component has no public API to check for ahead of time. Left
      // unguarded, that throw propagates out of a passive-effect cleanup
      // and trips the route's root error boundary on every subsequent
      // navigation, not just this one -- detach is best-effort here.
      try {
        player.detachMediaElement();
      } catch {
        // Already destroyed -- nothing left to detach.
      }
    };
  }, [player]);

  return (
    <video
      ref={videoRef}
      autoPlay
      playsInline
      muted
      onError={onError}
      className="absolute inset-0 h-full w-full object-cover"
    />
  );
}

function isMpegtsPlayer(source: unknown): source is Mpegts.Player {
  return (
    source !== null &&
    typeof source === "object" &&
    "attachMediaElement" in source &&
    "detachMediaElement" in source
  );
}
