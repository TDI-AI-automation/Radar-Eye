import { useEffect, useRef } from "react";
import { Camera, Maximize2, Volume2, VolumeX, Circle, Move3d, Wifi, VideoOff } from "lucide-react";

export type Detection = {
  label: string;
  confidence: number;
  distance?: string;
  level: 1 | 2 | 3;
  x: number; // 0-100 %
  y: number;
  w: number;
  h: number;
};

export type CameraFeed = {
  id: string;
  location: string;
  fps: number;
  latency: number;
  confidence: number;
  aiOn: boolean;
  health: number;
  detections: Detection[];
  ptz?: boolean;
  videoSrc?: string;
  blank?: boolean;
};

const levelColor = (l: 1 | 2 | 3) =>
  l === 3 ? "var(--red-glow)" : l === 2 ? "var(--amber-glow)" : "var(--primary)";

export function CameraTile({
  cam,
  emphasized,
  onFullscreen,
}: {
  cam: CameraFeed;
  emphasized?: boolean;
  onFullscreen?: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    // Ensure autoplay after mount even if browser hesitates
    const v = videoRef.current;
    if (v) v.play().catch(() => {});
  }, [cam.videoSrc]);

  const critical = cam.detections.some((d) => d.level === 3);
  const border = critical
    ? "border-red-glow animate-pulse-red"
    : emphasized
    ? "border-primary"
    : "border-border";

  const online = !cam.blank;

  return (
    <div className={`hud-panel rounded overflow-hidden group relative border ${border} transition-colors`}>
      {/* Video area */}
      <div className="relative aspect-video bg-black">
        {cam.videoSrc && (
          <video
            ref={videoRef}
            src={cam.videoSrc}
            autoPlay
            loop
            muted
            playsInline
            preload="auto"
            className="absolute inset-0 h-full w-full object-cover"
          />
        )}

        {cam.blank && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground/60">
            <VideoOff className="h-8 w-8 mb-2" strokeWidth={1.25} />
            <div className="font-mono text-[10px] uppercase tracking-[0.25em]">No Signal</div>
            <div className="font-mono text-[9px] tracking-widest mt-1">{cam.id}</div>
          </div>
        )}

        {/* Detections — overlay above the video */}
        {online && cam.detections.map((d, i) => (
          <div
            key={i}
            className="absolute pointer-events-none z-10"
            style={{
              left: `${d.x}%`,
              top: `${d.y}%`,
              width: `${d.w}%`,
              height: `${d.h}%`,
              border: `1px solid ${levelColor(d.level)}`,
            }}
          >
            <div
              className="absolute -top-4 left-0 whitespace-nowrap px-1 py-px text-[9px] font-mono font-semibold uppercase tracking-wider"
              style={{
                background: `${levelColor(d.level)}`,
                color: "#0f141c",
              }}
            >
              {d.label} · {Math.round(d.confidence * 100)}%
              {d.distance ? ` · ${d.distance}` : ""}
            </div>
          </div>
        ))}

        {/* Top overlay */}
        <div className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-2 py-1.5 bg-gradient-to-b from-black/75 to-transparent">
          <div className="flex items-center gap-2">
            {online ? (
              <Circle className="h-2 w-2 fill-red-glow text-red-glow animate-blink" />
            ) : (
              <Circle className="h-2 w-2 fill-muted-foreground/50 text-muted-foreground/50" />
            )}
            <span className="font-mono text-[10px] uppercase tracking-widest text-white/90">
              {online ? "REC" : "OFF"} · {cam.id}
            </span>
            <span className="hidden md:inline text-[10px] font-mono text-white/50">{cam.location}</span>
          </div>
          <div className="flex items-center gap-1.5 font-mono text-[9px] text-white/60">
            <span>AI {online && cam.aiOn ? "◉" : "○"}</span>
            <span>{cam.fps}fps</span>
            <span>{cam.latency}ms</span>
          </div>
        </div>

        {/* Bottom overlay */}
        <div className="absolute inset-x-0 bottom-0 z-20 flex items-center justify-between px-2 py-1.5 bg-gradient-to-t from-black/75 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="flex items-center gap-2">
            <IconBtn icon={Move3d} />
            <IconBtn icon={VolumeX} />
            <IconBtn icon={Wifi} />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[9px] text-white/60">CONF {Math.round(cam.confidence * 100)}%</span>
            <button onClick={onFullscreen}>
              <Maximize2 className="h-3.5 w-3.5 text-white/80" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function IconBtn({ icon: Icon }: { icon: typeof Camera }) {
  return (
    <button className="rounded border border-white/20 bg-black/40 p-1 hover:bg-white/10">
      <Icon className="h-3 w-3 text-white/80" />
    </button>
  );
}

void Volume2;
