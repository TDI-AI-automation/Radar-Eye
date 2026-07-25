import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel } from "@/components/hud/Panel";
import { Camera, Wifi, HardDrive, Activity, Signal } from "lucide-react";

export const Route = createFileRoute("/map")({
  head: () => ({
    meta: [
      { title: "Tactical Map — SENTINEL C2" },
      { name: "description", content: "Tactical perimeter map with camera coverage cones, blind spots, and patrol routes." },
      { property: "og:title", content: "Tactical Map — SENTINEL C2" },
      { property: "og:description", content: "Tactical perimeter map with camera coverage cones and blind spots." },
    ],
  }),
  component: TacticalMap,
});

type MapCam = {
  id: string;
  name: string;
  x: number;
  y: number;
  rot: number;
  fov: number;
  range: number;
  status: "ok" | "warn" | "down";
};

const CAMS: MapCam[] = [
  { id: "CAM-01", name: "North Gate", x: 50, y: 12, rot: 180, fov: 60, range: 22, status: "ok" },
  { id: "CAM-04", name: "NE Corner", x: 78, y: 18, rot: 220, fov: 70, range: 24, status: "ok" },
  { id: "CAM-07", name: "East Fence", x: 88, y: 45, rot: 260, fov: 55, range: 20, status: "warn" },
  { id: "CAM-12", name: "SE Watch", x: 82, y: 72, rot: 300, fov: 65, range: 22, status: "ok" },
  { id: "CAM-15", name: "South Gate", x: 50, y: 88, rot: 0, fov: 65, range: 25, status: "ok" },
  { id: "CAM-18", name: "SW Corner", x: 20, y: 76, rot: 60, fov: 60, range: 22, status: "ok" },
  { id: "CAM-21", name: "West Fence", x: 12, y: 48, rot: 90, fov: 55, range: 20, status: "down" },
  { id: "CAM-23", name: "NW Watch", x: 22, y: 22, rot: 130, fov: 60, range: 22, status: "ok" },
  { id: "CAM-31", name: "HQ Overlook", x: 50, y: 48, rot: 45, fov: 90, range: 18, status: "ok" },
];

const LAYERS = [
  "Cameras",
  "Detection Cones",
  "Blind Spots",
  "Perimeter Fence",
  "Patrol Routes",
  "Restricted Zones",
  "Intrusion Events",
  "Crowd Density",
];

function statusColor(s: MapCam["status"]) {
  return s === "ok" ? "var(--success)" : s === "warn" ? "var(--amber-glow)" : "var(--red-glow)";
}

function TacticalMap() {
  const [selected, setSelected] = useState<MapCam | null>(CAMS[0]);
  const [layers, setLayers] = useState<Record<string, boolean>>(
    Object.fromEntries(LAYERS.map((l) => [l, true])),
  );

  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-[200px_1fr_320px] gap-3 h-[calc(100vh-3.5rem)]">
      {/* Layers */}
      <Panel title="Layers">
        <div className="space-y-2">
          {LAYERS.map((l) => (
            <label key={l} className="flex items-center gap-2 text-[11px] font-mono cursor-pointer">
              <input
                type="checkbox"
                checked={layers[l]}
                onChange={(e) => setLayers((s) => ({ ...s, [l]: e.target.checked }))}
                className="accent-primary"
              />
              <span className={layers[l] ? "text-foreground" : "text-muted-foreground"}>{l}</span>
            </label>
          ))}
        </div>
        <div className="hud-divider my-4" />
        <div className="space-y-1 font-mono text-[10px]">
          <LegendRow color="var(--success)" label="Covered" />
          <LegendRow color="var(--amber-glow)" label="Weak" />
          <LegendRow color="var(--red-glow)" label="Blind / Down" />
        </div>
      </Panel>

      {/* Map */}
      <Panel title="Camp Alpha — Perimeter" padding={false}>
        <div className="relative w-full h-[calc(100vh-8rem)] overflow-hidden bg-black/60">
          {/* Grid */}
          <svg className="absolute inset-0 w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 100">
            <defs>
              <pattern id="g" width="5" height="5" patternUnits="userSpaceOnUse">
                <path d="M 5 0 L 0 0 0 5" fill="none" stroke="oklch(0.82 0.16 210 / 0.08)" strokeWidth="0.1" />
              </pattern>
              <radialGradient id="glow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="oklch(0.82 0.19 205)" stopOpacity="0.15" />
                <stop offset="100%" stopColor="oklch(0.82 0.19 205)" stopOpacity="0" />
              </radialGradient>
            </defs>
            <rect width="100" height="100" fill="url(#g)" />

            {/* Perimeter fence */}
            {layers["Perimeter Fence"] && (
              <polygon
                points="8,10 92,10 95,90 5,90"
                fill="oklch(0.22 0.05 210 / 0.3)"
                stroke="oklch(0.82 0.19 205 / 0.6)"
                strokeWidth="0.3"
                strokeDasharray="1 0.5"
              />
            )}

            {/* Restricted zone (armory) */}
            {layers["Restricted Zones"] && (
              <rect x="42" y="40" width="16" height="12" fill="oklch(0.68 0.24 25 / 0.15)" stroke="oklch(0.68 0.24 25 / 0.7)" strokeWidth="0.2" strokeDasharray="0.8 0.4" />
            )}

            {/* Blind spot polygon */}
            {layers["Blind Spots"] && (
              <polygon points="4,45 12,50 12,60 4,58" fill="oklch(0.68 0.24 25 / 0.25)" stroke="oklch(0.68 0.24 25 / 0.5)" strokeWidth="0.2" />
            )}

            {/* Patrol route */}
            {layers["Patrol Routes"] && (
              <path
                d="M 15,20 Q 40,10 70,15 T 90,50 T 60,85 T 20,80 Z"
                fill="none"
                stroke="oklch(0.82 0.17 75 / 0.6)"
                strokeWidth="0.4"
                strokeDasharray="1.5 1"
              />
            )}

            {/* Coverage cones */}
            {layers["Detection Cones"] &&
              CAMS.map((c) => {
                if (c.status === "down") return null;
                const rad = (Math.PI / 180) * c.rot;
                const half = (Math.PI / 180) * (c.fov / 2);
                const r = c.range;
                const x1 = c.x + Math.cos(rad - half) * r;
                const y1 = c.y + Math.sin(rad - half) * r;
                const x2 = c.x + Math.cos(rad + half) * r;
                const y2 = c.y + Math.sin(rad + half) * r;
                return (
                  <g key={c.id}>
                    <path
                      d={`M ${c.x} ${c.y} L ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2} Z`}
                      fill={statusColor(c.status)}
                      fillOpacity="0.12"
                      stroke={statusColor(c.status)}
                      strokeOpacity="0.5"
                      strokeWidth="0.15"
                    />
                  </g>
                );
              })}

            {/* Cameras */}
            {layers["Cameras"] &&
              CAMS.map((c) => (
                <g
                  key={c.id}
                  className="cursor-pointer"
                  onClick={() => setSelected(c)}
                  style={{ transformOrigin: `${c.x}px ${c.y}px` }}
                >
                  <circle cx={c.x} cy={c.y} r="1.4" fill="url(#glow)" />
                  <circle
                    cx={c.x}
                    cy={c.y}
                    r="0.9"
                    fill="oklch(0.16 0.02 250)"
                    stroke={statusColor(c.status)}
                    strokeWidth="0.25"
                  />
                  {selected?.id === c.id && (
                    <circle cx={c.x} cy={c.y} r="2" fill="none" stroke="var(--cyan-glow)" strokeWidth="0.2" className="animate-blink" />
                  )}
                </g>
              ))}

            {/* Recent intrusion events */}
            {layers["Intrusion Events"] &&
              [{ x: 82, y: 72 }, { x: 20, y: 76 }, { x: 78, y: 18 }].map((p, i) => (
                <g key={i}>
                  <circle cx={p.x} cy={p.y} r="1.8" fill="none" stroke="var(--red-glow)" strokeWidth="0.2" className="animate-blink" />
                  <circle cx={p.x} cy={p.y} r="0.5" fill="var(--red-glow)" />
                </g>
              ))}
          </svg>

          {/* Corner readouts */}
          <div className="absolute top-2 left-2 font-mono text-[10px] text-primary/70 tracking-widest">
            LAT 23.7808 · LON 90.2792
          </div>
          <div className="absolute top-2 right-2 font-mono text-[10px] text-primary/70 tracking-widest">
            SCALE 1:2500 · GRID MGRS 42R
          </div>
          <div className="absolute bottom-2 left-2 font-mono text-[10px] text-muted-foreground">
            {CAMS.length} cameras · {CAMS.filter((c) => c.status === "ok").length} operational
          </div>
        </div>
      </Panel>

      {/* Detail */}
      <Panel title={selected ? `${selected.id} — Details` : "Select Camera"}>
        {selected ? (
          <div className="space-y-3 font-mono text-[11px]">
            <div className="flex items-center gap-2">
              <div
                className="h-2 w-2 rounded-full"
                style={{ background: statusColor(selected.status), boxShadow: `0 0 10px ${statusColor(selected.status)}` }}
              />
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                {selected.status === "ok" ? "Online" : selected.status === "warn" ? "Degraded" : "Offline"}
              </span>
            </div>
            <DetailRow icon={Camera} label="Location" value={selected.name} />
            <DetailRow icon={Activity} label="Resolution" value="1920 × 1080" />
            <DetailRow icon={Signal} label="FPS" value="30" />
            <DetailRow icon={Wifi} label="Latency" value="31 ms" />
            <DetailRow icon={HardDrive} label="Storage" value="4.2 TB" />
            <DetailRow icon={Activity} label="AI" value="Running · 98% health" />

            <div className="hud-divider my-2" />
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground">Coverage</div>
            <div className="flex items-center gap-3">
              <div className="text-glow-cyan text-lg">{selected.fov}°</div>
              <div className="text-muted-foreground">FoV</div>
              <div className="text-glow-cyan text-lg">{selected.range * 5}m</div>
              <div className="text-muted-foreground">range</div>
            </div>

            <div className="flex gap-2 pt-2">
              <button className="flex-1 rounded border border-primary/40 bg-primary/10 py-1.5 text-[10px] uppercase tracking-widest text-primary hover:bg-primary/20">
                Live Feed
              </button>
              <button className="flex-1 rounded border border-border py-1.5 text-[10px] uppercase tracking-widest text-muted-foreground hover:text-primary">
                PTZ
              </button>
            </div>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground font-mono">Click a camera on the map.</div>
        )}
      </Panel>
    </div>
  );
}

function LegendRow({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2 w-2 rounded-full" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}

function DetailRow({ icon: Icon, label, value }: { icon: typeof Camera; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="flex items-center gap-2 text-muted-foreground uppercase tracking-widest text-[10px]">
        <Icon className="h-3 w-3" /> {label}
      </span>
      <span className="text-foreground">{value}</span>
    </div>
  );
}
