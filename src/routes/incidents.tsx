import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel, LevelBadge } from "@/components/hud/Panel";
import { INCIDENTS, type Incident } from "@/lib/mock-data";
import { Play, MapPin, User, Download, X, ChevronRight } from "lucide-react";

export const Route = createFileRoute("/incidents")({
  head: () => ({
    meta: [
      { title: "Incident Center — SENTINEL C2" },
      { name: "description", content: "Active and historical security incidents with full response timeline." },
      { property: "og:title", content: "Incident Center — SENTINEL C2" },
      { property: "og:description", content: "Active and historical security incidents with response timeline." },
    ],
  }),
  component: Incidents,
});

function Incidents() {
  const [sel, setSel] = useState<Incident>(INCIDENTS[0]);
  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-3">
      <div className="space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <MiniStat label="Open" value="3" tone="red" />
          <MiniStat label="Investigating" value="1" tone="amber" />
          <MiniStat label="Resolved 24h" value="27" tone="success" />
          <MiniStat label="Avg. Response" value="42s" tone="cyan" />
        </div>

        <Panel title={`Incidents · ${INCIDENTS.length}`}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {INCIDENTS.map((i) => (
              <button
                key={i.id}
                onClick={() => setSel(i)}
                className={`text-left hud-panel rounded p-3 border transition ${
                  sel.id === i.id ? "border-primary/70 hud-panel-glow" : "border-border hover:border-primary/40"
                }`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-mono text-[10px] tracking-widest text-muted-foreground">{i.id}</div>
                    <div className="mt-1 text-sm font-semibold">{i.object}</div>
                  </div>
                  <LevelBadge level={i.level} />
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-[10px] text-muted-foreground">
                  <span className="flex items-center gap-1"><MapPin className="h-3 w-3" /> {i.location}</span>
                  <span>{i.camera} · {i.time}</span>
                  <span className="flex items-center gap-1"><User className="h-3 w-3" /> {i.operator}</span>
                  <span className="text-glow-cyan justify-self-end">{i.status}</span>
                </div>
              </button>
            ))}
          </div>
        </Panel>
      </div>

      {/* Detail */}
      <Panel
        title={`${sel.id} · Detail`}
        actions={
          <button className="rounded border border-border p-1 text-muted-foreground hover:text-primary">
            <X className="h-3 w-3" />
          </button>
        }
      >
        <div className="space-y-4">
          <div className="hud-panel rounded aspect-video bg-black relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-red-glow/10 via-transparent to-primary/10" />
            <div className="absolute inset-0 flex items-center justify-center">
              <button className="flex items-center gap-2 rounded-full border border-primary/60 bg-black/50 px-4 py-2 backdrop-blur">
                <Play className="h-4 w-4 text-primary" />
                <span className="font-mono text-[11px] uppercase tracking-widest text-primary">Play Footage</span>
              </button>
            </div>
            <div className="absolute top-2 left-2 font-mono text-[10px] text-glow-cyan">{sel.camera} · {sel.time}</div>
            <div className="absolute bottom-2 right-2"><LevelBadge level={sel.level} /></div>
          </div>

          <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
            <Field label="Object" value={sel.object} />
            <Field label="Confidence" value="98%" />
            <Field label="Location" value={sel.location} />
            <Field label="Operator" value={sel.operator} />
            <Field label="Status" value={sel.status} />
            <Field label="Escalation" value={sel.level === 3 ? "QRF" : "Standard"} />
          </div>

          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-primary mb-2">Response Timeline</div>
            <ol className="space-y-2">
              {[
                { t: "22:18:02", label: "Detection", tone: "cyan" as const },
                { t: "22:18:03", label: "Tracking initiated", tone: "cyan" as const },
                { t: "22:18:04", label: `Alert dispatched · L${sel.level}`, tone: sel.level === 3 ? ("red" as const) : ("amber" as const) },
                { t: "22:18:12", label: "Operator acknowledged", tone: "success" as const },
                { t: "22:18:44", label: sel.status, tone: sel.status === "Resolved" ? ("success" as const) : ("amber" as const) },
              ].map((s, i) => (
                <li key={i} className="flex items-center gap-3 font-mono text-[11px]">
                  <span className="text-muted-foreground w-16">{s.t}</span>
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{
                      background: `var(--${s.tone === "success" ? "success" : s.tone === "red" ? "red-glow" : s.tone === "amber" ? "amber-glow" : "cyan-glow"})`,
                      boxShadow: `0 0 8px var(--${s.tone === "success" ? "success" : s.tone === "red" ? "red-glow" : s.tone === "amber" ? "amber-glow" : "cyan-glow"})`,
                    }}
                  />
                  <span className="flex-1">{s.label}</span>
                  <ChevronRight className="h-3 w-3 text-muted-foreground" />
                </li>
              ))}
            </ol>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button className="rounded border border-primary/40 bg-primary/10 py-2 font-mono text-[10px] uppercase tracking-widest text-primary hover:bg-primary/20">
              Assign
            </button>
            <button className="rounded border border-border py-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-primary flex items-center justify-center gap-1">
              <Download className="h-3 w-3" /> Export
            </button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function MiniStat({ label, value, tone }: { label: string; value: string; tone: "cyan" | "amber" | "red" | "success" }) {
  const cls = { cyan: "text-glow-cyan", amber: "text-glow-amber", red: "text-glow-red", success: "text-success" }[tone];
  return (
    <div className="hud-panel rounded p-3">
      <div className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className={`font-mono text-2xl font-bold ${cls}`}>{value}</div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="hud-panel rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className="text-foreground">{value}</div>
    </div>
  );
}
