import { createFileRoute } from "@tanstack/react-router";
import { Panel, Bar } from "@/components/hud/Panel";
import { Cpu, HardDrive, Thermometer, Network, Database, Radio, Bell, Server } from "lucide-react";

export const Route = createFileRoute("/health")({
  head: () => ({
    meta: [
      { title: "System Health — SENTINEL C2" },
      { name: "description", content: "Real-time health of compute, storage, network, and detection subsystems." },
      { property: "og:title", content: "System Health — SENTINEL C2" },
      { property: "og:description", content: "Real-time health of compute, storage, network, and detection subsystems." },
    ],
  }),
  component: Health,
});

const SUBS = [
  { icon: Cpu, label: "GPU · RTX A6000", value: 73, tone: "cyan" as const, sub: "68°C · 30 FPS" },
  { icon: Cpu, label: "CPU · EPYC 7742", value: 41, tone: "cyan" as const, sub: "64 cores · 52°C" },
  { icon: Server, label: "Memory", value: 58, tone: "cyan" as const, sub: "74 / 128 GB" },
  { icon: HardDrive, label: "Storage · NVMe RAID", value: 72, tone: "amber" as const, sub: "28.8 / 40 TB" },
  { icon: Thermometer, label: "Ambient", value: 34, tone: "success" as const, sub: "24°C rack" },
  { icon: Network, label: "Network Uplink", value: 22, tone: "success" as const, sub: "220 Mbps / 1 Gbps" },
  { icon: Database, label: "Database", value: 12, tone: "success" as const, sub: "PostgreSQL 16 · nominal" },
  { icon: Radio, label: "MQTT Broker", value: 18, tone: "success" as const, sub: "312 msg/s" },
  { icon: Bell, label: "Notification Bus", value: 45, tone: "cyan" as const, sub: "SMS · Email · Radio" },
];

function Health() {
  return (
    <div className="p-3 space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {SUBS.map((s) => {
          const Icon = s.icon;
          const tone = s.value > 85 ? "red" : s.value > 65 ? "amber" : "success";
          return (
            <Panel key={s.label} title={s.label}>
              <div className="flex items-center gap-3">
                <div className="hud-panel rounded p-2 border-primary/30">
                  <Icon className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1">
                  <div className="font-mono text-2xl font-bold text-glow-cyan">{s.value}%</div>
                  <div className="text-[10px] font-mono text-muted-foreground">{s.sub}</div>
                </div>
              </div>
              <div className="mt-3">
                <Bar value={s.value} tone={tone} />
              </div>
            </Panel>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel title="Camera Health Distribution">
          <div className="grid grid-cols-12 gap-1">
            {Array.from({ length: 48 }).map((_, i) => {
              const h = i === 5 ? 0 : i === 11 ? 60 : 85 + (i % 12);
              const color = h === 0 ? "var(--red-glow)" : h < 70 ? "var(--amber-glow)" : "var(--success)";
              return (
                <div
                  key={i}
                  title={`CAM-${String(i + 1).padStart(2, "0")} · ${h}%`}
                  className="aspect-square rounded"
                  style={{ background: color, opacity: 0.85, boxShadow: `0 0 8px ${color}` }}
                />
              );
            })}
          </div>
          <div className="mt-3 flex gap-4 font-mono text-[10px] text-muted-foreground">
            <span>46 Online</span><span className="text-amber-glow">1 Degraded</span><span className="text-red-glow">1 Offline</span>
          </div>
        </Panel>

        <Panel title="Event Log Stream">
          <div className="font-mono text-[11px] space-y-1 max-h-64 overflow-auto">
            {[
              ["22:15:31", "detection", "CAM-12 · rifle detected · conf 0.99"],
              ["22:15:20", "detection", "CAM-18 · machete detected · conf 0.86"],
              ["22:14:52", "system", "Inference engine · warmup complete"],
              ["22:14:12", "detection", "CAM-04 · bamboo detected · conf 0.78"],
              ["22:12:04", "system", "MQTT reconnect · broker OK"],
              ["22:11:00", "system", "Storage GC · reclaimed 128 GB"],
              ["22:08:22", "system", "CAM-06 offline · last heartbeat 22:07:44"],
              ["22:05:11", "detection", "CAM-23 · crowd density 21 · normal"],
            ].map(([t, k, m], i) => (
              <div key={i} className="grid grid-cols-[auto_auto_1fr] gap-3 items-center py-0.5">
                <span className="text-muted-foreground">{t}</span>
                <span className={k === "detection" ? "text-glow-amber" : "text-glow-cyan"}>[{k}]</span>
                <span>{m}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
