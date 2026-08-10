import { useEffect, useRef, useState } from "react";
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
 * but renders only real data: live video via WebRtcVideoProvider (falling
 * back to a "No Signal" state for "connecting"/"error"/"unavailable"),
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

  const stream =
    videoHandle.status === "playing" && videoHandle.source instanceof MediaStream
      ? videoHandle.source
      : null;
  const isPlaying = stream !== null && !videoElementErrored;

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
          <VideoStreamElement stream={stream} onError={() => setVideoElementErrored(true)} />
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

/** Attaches a MediaStream via `srcObject` -- not settable as a plain JSX
 * attribute, so this needs a ref + effect rather than the div-based
 * placeholder's pure render. `onError` lets the caller fall back to the
 * "No Signal" state if playback itself fails after the WebRTC connection
 * already reported "playing". */
function VideoStreamElement({ stream, onError }: { stream: MediaStream; onError: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
  }, [stream]);

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
