import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel, StatTile, Bar, LevelBadge } from "@/components/hud/Panel";
import { CameraTile } from "@/components/hud/CameraTile";
import { CAMERAS, ALERTS } from "@/lib/mock-data";
import { useAnimatedNumber, useTick } from "@/lib/hud-hooks";
import { Filter, Check, Radio } from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Live Monitoring — SENTINEL C2" },
      { name: "description", content: "Real-time AI-driven perimeter monitoring across all camera feeds." },
      { property: "og:title", content: "Live Monitoring — SENTINEL C2" },
      { property: "og:description", content: "Real-time AI-driven perimeter monitoring across all camera feeds." },
    ],
  }),
  component: LiveMonitoring,
});

function LiveMonitoring() {
  useTick(2000);
  const [filter, setFilter] = useState<"all" | 1 | 2 | 3>("all");
  const [emphasized, setEmphasized] = useState<string | null>(null);

  const gpu = useAnimatedNumber(70 + Math.random() * 8);
  const fps = useAnimatedNumber(29 + Math.random() * 2);
  const online = 46;
  const total = 48;

  const filteredAlerts = useMemo(
    () => (filter === "all" ? ALERTS : ALERTS.filter((a) => a.level === filter)),
    [filter],
  );

  const criticalCam = CAMERAS.find((c) => c.detections.some((d) => d.level === 3));

  return (
    <div className="p-3 space-y-3 min-h-full">
      {/* Status strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <StatTile label="Mission" value="ACTIVE" sub="Op. IRON-VEIL" tone="success" />
        <StatTile label="Threat Level" value="MEDIUM" sub="↑ 12% last hour" tone="amber" />
        <StatTile label="Cameras" value={`${online}/${total}`} sub="2 offline" tone="cyan" />
        <StatTile label="Inference FPS" value={fps.toFixed(0)} sub="target ≥ 25" tone="cyan" />
        <StatTile label="GPU" value={`${gpu.toFixed(0)}%`} sub="RTX A6000 · 68°C" tone="cyan" />
        <StatTile label="Uptime" value="14d 06h" sub="last restart 30/06" tone="muted" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-3">
        {/* Camera grid */}
        <div className="space-y-3">
          {criticalCam && (
            <div className="hud-panel hud-corner rounded flex items-center justify-between px-3 py-2 border-red-glow/60 animate-pulse-red">
              <div className="flex items-center gap-3">
                <LevelBadge level={3} />
                <div>
                  <div className="font-mono text-xs text-glow-red uppercase tracking-widest">
                    CRITICAL — FIREARM DETECTED
                  </div>
                  <div className="text-[11px] text-muted-foreground font-mono">
                    {criticalCam.id} · {criticalCam.location} · Auto-emphasized
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button className="rounded border border-red-glow/60 bg-red-glow/10 px-3 py-1 font-mono text-[10px] uppercase tracking-widest text-red-glow hover:bg-red-glow/20">
                  Dispatch QRF
                </button>
                <button
                  onClick={() => setEmphasized(criticalCam.id)}
                  className="rounded border border-primary/40 bg-primary/10 px-3 py-1 font-mono text-[10px] uppercase tracking-widest text-primary hover:bg-primary/20"
                >
                  Focus
                </button>
              </div>
            </div>
          )}

          <div className={`grid gap-3 ${emphasized ? "grid-cols-1 lg:grid-cols-[2fr_1fr]" : "grid-cols-1 md:grid-cols-2"}`}>
            {emphasized ? (
              <>
                <CameraTile
                  cam={CAMERAS.find((c) => c.id === emphasized) ?? CAMERAS[0]}
                  emphasized
                  onFullscreen={() => setEmphasized(null)}
                />
                <div className="grid grid-cols-1 gap-3">
                  {CAMERAS.filter((c) => c.id !== emphasized).map((c) => (
                    <CameraTile key={c.id} cam={c} onFullscreen={() => setEmphasized(c.id)} />
                  ))}
                </div>
              </>
            ) : (
              CAMERAS.map((c) => (
                <CameraTile key={c.id} cam={c} onFullscreen={() => setEmphasized(c.id)} />
              ))
            )}
          </div>

          {/* Alert timeline */}
          <Panel
            title="Active Alert Timeline"
            actions={
              <div className="flex items-center gap-1">
                <Filter className="h-3 w-3 text-muted-foreground" />
                {(["all", 1, 2, 3] as const).map((f) => (
                  <button
                    key={String(f)}
                    onClick={() => setFilter(f)}
                    className={`rounded px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest border ${
                      filter === f
                        ? "border-primary/60 bg-primary/15 text-primary"
                        : "border-border text-muted-foreground hover:text-primary"
                    }`}
                  >
                    {f === "all" ? "All" : `L${f}`}
                  </button>
                ))}
              </div>
            }
          >
            <div className="max-h-72 overflow-auto divide-y divide-border/40">
              {filteredAlerts.map((a) => (
                <div key={a.id} className="animate-ticker grid grid-cols-[auto_auto_auto_1fr_auto] items-center gap-3 py-2 text-[11px] font-mono">
                  <span className="text-muted-foreground">{a.time}</span>
                  <LevelBadge level={a.level} />
                  <span className="text-primary">{a.camera}</span>
                  <span className="text-foreground/90 truncate">{a.message}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-muted-foreground">{a.sector}</span>
                    {a.ack ? (
                      <span className="inline-flex items-center gap-1 text-success">
                        <Check className="h-3 w-3" /> ACK
                      </span>
                    ) : (
                      <button className="inline-flex items-center gap-1 rounded border border-primary/40 px-1.5 py-0.5 text-primary hover:bg-primary/10">
                        <Radio className="h-3 w-3" /> ACK
                      </button>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        {/* Right rail */}
        <div className="space-y-3">
          <Panel title="Threat Overview">
            <div className="space-y-3">
              <ThreatRow label="Firearm" value={1} tone="red" />
              <ThreatRow label="Melee" value={2} tone="amber" />
              <ThreatRow label="Crowd" value={21} tone="cyan" />
              <ThreatRow label="Vehicle" value={3} tone="cyan" />
            </div>
          </Panel>

          <Panel title="System Load">
            <div className="space-y-3 font-mono text-[11px]">
              <LoadRow label="GPU" pct={gpu} tone="cyan" />
              <LoadRow label="CPU" pct={41} tone="cyan" />
              <LoadRow label="Memory" pct={58} tone="cyan" />
              <LoadRow label="Storage" pct={72} tone="amber" />
              <LoadRow label="Network" pct={22} tone="success" />
            </div>
          </Panel>

          <Panel title="Radar Sweep">
            <div className="relative aspect-square rounded-full border border-primary/40 bg-black/60 overflow-hidden">
              {[20, 40, 60, 80].map((r) => (
                <div
                  key={r}
                  className="absolute inset-0 m-auto rounded-full border border-primary/15"
                  style={{ width: `${r}%`, height: `${r}%` }}
                />
              ))}
              <div className="absolute left-1/2 top-0 bottom-0 w-px bg-primary/15" />
              <div className="absolute top-1/2 left-0 right-0 h-px bg-primary/15" />
              <div
                className="absolute inset-0 animate-radar"
                style={{
                  background:
                    "conic-gradient(from 0deg, transparent 0deg, oklch(0.82 0.19 205 / 0.35) 30deg, transparent 60deg)",
                }}
              />
              {[
                { t: 20, l: 60, tone: "red-glow" },
                { t: 55, l: 30, tone: "amber-glow" },
                { t: 70, l: 72, tone: "cyan-glow" },
                { t: 40, l: 80, tone: "cyan-glow" },
              ].map((p, i) => (
                <span
                  key={i}
                  className="absolute h-1.5 w-1.5 rounded-full animate-blink"
                  style={{
                    top: `${p.t}%`,
                    left: `${p.l}%`,
                    background: `var(--${p.tone})`,
                    boxShadow: `0 0 10px var(--${p.tone})`,
                  }}
                />
              ))}
            </div>
            <div className="mt-2 flex justify-between font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
              <span>Range 500m</span>
              <span className="text-glow-cyan">SWEEP 0.25 Hz</span>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function ThreatRow({ label, value, tone }: { label: string; value: number; tone: "cyan" | "amber" | "red" }) {
  const toneCls = {
    cyan: "text-glow-cyan",
    amber: "text-glow-amber",
    red: "text-glow-red",
  }[tone];
  return (
    <div className="flex items-center justify-between font-mono">
      <span className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</span>
      <span className={`text-lg font-bold ${toneCls}`}>{String(value).padStart(2, "0")}</span>
    </div>
  );
}

function LoadRow({ label, pct, tone }: { label: string; pct: number; tone: "cyan" | "amber" | "red" | "success" }) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <span className="uppercase tracking-widest text-muted-foreground text-[10px]">{label}</span>
        <span className="text-foreground">{pct.toFixed(0)}%</span>
      </div>
      <Bar value={pct} tone={tone} />
    </div>
  );
}
