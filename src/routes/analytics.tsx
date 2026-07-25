import { createFileRoute } from "@tanstack/react-router";
import { Panel, Bar } from "@/components/hud/Panel";

export const Route = createFileRoute("/analytics")({
  head: () => ({
    meta: [
      { title: "AI Analytics — SENTINEL C2" },
      { name: "description", content: "Detection frequency, model performance, and operational analytics." },
      { property: "og:title", content: "AI Analytics — SENTINEL C2" },
      { property: "og:description", content: "Detection frequency, model performance, and operational analytics." },
    ],
  }),
  component: Analytics,
});

const HOURS = Array.from({ length: 24 }).map((_, h) => ({
  h,
  l1: Math.round(4 + Math.sin(h / 3) * 3 + Math.random() * 3),
  l2: Math.round(1 + Math.sin(h / 4) * 1 + Math.random() * 2),
  l3: h === 22 ? 2 : Math.random() > 0.85 ? 1 : 0,
}));

function Analytics() {
  const maxCol = Math.max(...HOURS.map((h) => h.l1 + h.l2 + h.l3));
  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-3 gap-3">
      <div className="lg:col-span-2 space-y-3">
        <Panel title="Alert Trend · 24h">
          <div className="flex items-end gap-1 h-56">
            {HOURS.map((h) => (
              <div key={h.h} className="flex-1 flex flex-col items-center gap-0.5">
                <div className="flex-1 w-full flex flex-col-reverse rounded overflow-hidden bg-black/40">
                  <div style={{ height: `${(h.l1 / maxCol) * 100}%`, background: "var(--cyan-glow)", boxShadow: "0 0 6px var(--cyan-glow)" }} />
                  <div style={{ height: `${(h.l2 / maxCol) * 100}%`, background: "var(--amber-glow)", boxShadow: "0 0 6px var(--amber-glow)" }} />
                  <div style={{ height: `${(h.l3 / maxCol) * 100}%`, background: "var(--red-glow)", boxShadow: "0 0 6px var(--red-glow)" }} />
                </div>
                <div className="font-mono text-[8px] text-muted-foreground">{String(h.h).padStart(2, "0")}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-4 font-mono text-[10px]">
            <Legend color="cyan-glow" label="L1 Crowd" />
            <Legend color="amber-glow" label="L2 Melee" />
            <Legend color="red-glow" label="L3 Firearm" />
          </div>
        </Panel>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Panel title="Detection Accuracy">
            <Metric big="96.4%" sub="Precision · last 7d" />
            <Bar value={96.4} tone="success" />
            <div className="mt-3 grid grid-cols-2 gap-3 text-[11px] font-mono">
              <MiniKV k="Recall" v="94.8%" />
              <MiniKV k="F1" v="95.6%" />
              <MiniKV k="False Pos." v="1.2%" />
              <MiniKV k="False Neg." v="0.8%" />
            </div>
          </Panel>
          <Panel title="Response Time">
            <Metric big="1.42s" sub="Detection → Alert median" />
            <div className="mt-2 space-y-2 font-mono text-[11px]">
              <Line l="p50" v="1.42s" pct={40} />
              <Line l="p90" v="2.10s" pct={60} />
              <Line l="p99" v="3.80s" pct={85} tone="amber" />
            </div>
          </Panel>
        </div>

        <Panel title="Threat Heatmap · Perimeter">
          <div className="grid grid-cols-16 gap-0.5" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>
            {Array.from({ length: 24 * 8 }).map((_, i) => {
              const v = Math.random();
              const alpha = v.toFixed(2);
              const color = v > 0.85 ? "var(--red-glow)" : v > 0.6 ? "var(--amber-glow)" : "var(--cyan-glow)";
              return (
                <div
                  key={i}
                  className="aspect-square rounded-[2px]"
                  style={{ background: color, opacity: Number(alpha) * 0.9 + 0.05 }}
                />
              );
            })}
          </div>
          <div className="mt-2 flex justify-between font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
            <span>Sector A</span><span>B</span><span>C</span><span>D</span><span>E</span><span>F</span>
          </div>
        </Panel>
      </div>

      <div className="space-y-3">
        <Panel title="Top Active Cameras">
          {[
            ["CAM-12", 128], ["CAM-07", 96], ["CAM-23", 74], ["CAM-18", 52], ["CAM-04", 41],
          ].map(([id, n]) => (
            <div key={id as string} className="flex items-center justify-between font-mono text-[11px] py-1">
              <span className="text-primary">{id}</span>
              <div className="flex-1 mx-3"><Bar value={(n as number) / 128 * 100} tone="cyan" /></div>
              <span className="text-muted-foreground w-8 text-right">{n}</span>
            </div>
          ))}
        </Panel>
        <Panel title="Inference · GPU">
          <Metric big="30 FPS" sub="RTX A6000" />
          <div className="mt-2 space-y-2">
            <Line l="GPU" v="73%" pct={73} />
            <Line l="VRAM" v="18/48 GB" pct={38} />
            <Line l="Temp" v="68°C" pct={55} tone="amber" />
          </div>
        </Panel>
        <Panel title="Weapon Frequency · 7d">
          {[
            ["Rifle", 12, "red"],
            ["Machete", 8, "amber"],
            ["Bamboo", 5, "amber"],
            ["Pistol", 2, "red"],
          ].map(([l, n, tone]) => (
            <div key={l as string} className="flex items-center justify-between font-mono text-[11px] py-1">
              <span>{l}</span>
              <div className="flex-1 mx-3"><Bar value={(n as number) * 8} tone={tone as "red" | "amber"} /></div>
              <span className="text-muted-foreground w-6 text-right">{n}</span>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}

function Metric({ big, sub }: { big: string; sub: string }) {
  return (
    <div className="mb-2">
      <div className="font-mono text-3xl font-bold text-glow-cyan">{big}</div>
      <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-widest">{sub}</div>
    </div>
  );
}
function MiniKV({ k, v }: { k: string; v: string }) {
  return (
    <div className="hud-panel rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-muted-foreground">{k}</div>
      <div className="text-glow-cyan">{v}</div>
    </div>
  );
}
function Line({ l, v, pct, tone = "cyan" }: { l: string; v: string; pct: number; tone?: "cyan" | "amber" | "red" | "success" }) {
  return (
    <div>
      <div className="flex justify-between text-[10px] font-mono"><span className="text-muted-foreground uppercase tracking-widest">{l}</span><span>{v}</span></div>
      <Bar value={pct} tone={tone} />
    </div>
  );
}
function Legend({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="h-2 w-2" style={{ background: `var(--${color})`, boxShadow: `0 0 6px var(--${color})` }} />
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}
