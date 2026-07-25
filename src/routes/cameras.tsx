import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel, Bar } from "@/components/hud/Panel";
import { CAM_INVENTORY, type CamRow } from "@/lib/mock-data";
import { Search, Settings2, Power, X } from "lucide-react";

export const Route = createFileRoute("/cameras")({
  head: () => ({
    meta: [
      { title: "Camera Management — SENTINEL C2" },
      { name: "description", content: "Inventory, configuration, and health of all connected surveillance cameras." },
      { property: "og:title", content: "Camera Management — SENTINEL C2" },
      { property: "og:description", content: "Inventory and configuration of all connected surveillance cameras." },
    ],
  }),
  component: Cameras,
});

function Cameras() {
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState<CamRow | null>(null);
  const rows = CAM_INVENTORY.filter(
    (r) => !q || r.id.toLowerCase().includes(q.toLowerCase()) || r.location.toLowerCase().includes(q.toLowerCase()),
  );

  return (
    <div className="p-3 space-y-3">
      <Panel
        title="Camera Inventory"
        actions={
          <div className="relative">
            <Search className="absolute left-2 top-1.5 h-3 w-3 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search ID or location"
              className="rounded border border-border bg-black/40 pl-6 pr-2 py-1 text-[11px] font-mono placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] font-mono">
            <thead>
              <tr className="text-[9px] uppercase tracking-widest text-muted-foreground text-left border-b border-border/60">
                {["Camera", "Status", "FPS", "Health", "Latency", "AI", "REC", "Storage", "Location", ""].map((h) => (
                  <th key={h} className="px-2 py-2 font-normal">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-border/30 hover:bg-primary/5">
                  <td className="px-2 py-2 text-primary">{r.id}</td>
                  <td className="px-2 py-2">
                    <StatusPill status={r.status} />
                  </td>
                  <td className="px-2 py-2">{r.fps}</td>
                  <td className="px-2 py-2 min-w-[100px]">
                    <div className="flex items-center gap-2">
                      <Bar value={r.health} tone={r.health > 80 ? "success" : r.health > 40 ? "amber" : "red"} />
                      <span className="text-[10px] w-8 text-right">{r.health}%</span>
                    </div>
                  </td>
                  <td className="px-2 py-2">{r.latency}ms</td>
                  <td className="px-2 py-2">{r.ai ? <span className="text-glow-cyan">◉</span> : <span className="text-muted-foreground">○</span>}</td>
                  <td className="px-2 py-2">{r.recording ? <span className="text-glow-red">●</span> : <span className="text-muted-foreground">○</span>}</td>
                  <td className="px-2 py-2 text-muted-foreground">{r.storage}</td>
                  <td className="px-2 py-2 text-muted-foreground">{r.location}</td>
                  <td className="px-2 py-2 text-right">
                    <button onClick={() => setEdit(r)} className="text-primary hover:text-glow-cyan">
                      <Settings2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {edit && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setEdit(null)}>
          <div className="hud-panel hud-corner rounded max-w-lg w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
              <h3 className="font-mono text-[11px] uppercase tracking-widest text-primary">
                Configure {edit.id} · {edit.location}
              </h3>
              <button onClick={() => setEdit(null)}><X className="h-4 w-4 text-muted-foreground" /></button>
            </div>
            <div className="p-4 space-y-3 font-mono text-[11px]">
              <Row label="Resolution">
                <select className="bg-black/40 border border-border rounded px-2 py-1">
                  <option>1920 × 1080</option>
                  <option>2560 × 1440</option>
                  <option>3840 × 2160</option>
                </select>
              </Row>
              <Row label="FPS">
                <select className="bg-black/40 border border-border rounded px-2 py-1">
                  <option>30</option><option>25</option><option>60</option>
                </select>
              </Row>
              <Row label="Codec">
                <select className="bg-black/40 border border-border rounded px-2 py-1">
                  <option>H.265</option><option>H.264</option>
                </select>
              </Row>
              <Row label="Confidence Threshold">
                <input type="range" min={50} max={99} defaultValue={85} className="accent-primary" />
              </Row>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Detection Types</div>
                <div className="flex gap-3">
                  {["Crowd", "Melee", "Firearm", "Vehicle"].map((t) => (
                    <label key={t} className="flex items-center gap-1"><input type="checkbox" defaultChecked className="accent-primary" /> {t}</label>
                  ))}
                </div>
              </div>
              <Row label="Detection Distance"><span className="text-glow-cyan">120 m</span></Row>
              <Row label="Privacy Mask"><span className="text-muted-foreground">2 zones</span></Row>
              <Row label="Firmware"><span className="text-muted-foreground">v4.2.1 · up to date</span></Row>

              <div className="flex gap-2 pt-2">
                <button className="flex-1 rounded border border-primary/50 bg-primary/15 py-2 uppercase tracking-widest text-primary text-[10px]">Save</button>
                <button className="rounded border border-red-glow/40 text-red-glow py-2 px-3 uppercase tracking-widest text-[10px] flex items-center gap-1">
                  <Power className="h-3 w-3" /> Restart
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

function StatusPill({ status }: { status: CamRow["status"] }) {
  const map = {
    Online: "text-success border-success/40 bg-success/10",
    Offline: "text-red-glow border-red-glow/50 bg-red-glow/10",
    Degraded: "text-amber-glow border-amber-glow/50 bg-amber-glow/10",
  };
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-widest ${map[status]}`}>
      {status}
    </span>
  );
}
