import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel } from "@/components/hud/Panel";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Configuration — SENTINEL C2" },
      { name: "description", content: "AI thresholds, notification rules, roles, and system configuration." },
      { property: "og:title", content: "Configuration — SENTINEL C2" },
      { property: "og:description", content: "AI thresholds, notification rules, roles, and system configuration." },
    ],
  }),
  component: SettingsPage,
});

const TABS = ["AI Model", "Notifications", "Roles & Users", "Recording", "Audit Log", "System"] as const;

function SettingsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("AI Model");
  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-3">
      <Panel title="Configuration">
        <ul className="space-y-1">
          {TABS.map((t) => (
            <li key={t}>
              <button
                onClick={() => setTab(t)}
                className={`w-full text-left rounded px-2 py-1.5 font-mono text-[11px] uppercase tracking-widest ${
                  tab === t ? "bg-primary/15 text-primary border-l-2 border-primary" : "text-muted-foreground hover:text-primary border-l-2 border-transparent"
                }`}
              >
                {t}
              </button>
            </li>
          ))}
        </ul>
      </Panel>

      <div className="space-y-3">
        {tab === "AI Model" && <AITab />}
        {tab === "Notifications" && <NotificationsTab />}
        {tab === "Roles & Users" && <RolesTab />}
        {tab === "Recording" && <RecordingTab />}
        {tab === "Audit Log" && <AuditTab />}
        {tab === "System" && <SystemTab />}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-3 items-center py-2 border-b border-border/30">
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{label}</div>
      <div>{children}</div>
    </div>
  );
}

function AITab() {
  return (
    <Panel title="Detection & Inference">
      <Row label="Global Confidence Threshold">
        <input type="range" min={50} max={99} defaultValue={82} className="w-full accent-primary" />
      </Row>
      <Row label="Detection Classes">
        <div className="flex flex-wrap gap-2">
          {["Person", "Crowd", "Vehicle", "Bamboo", "Machete", "Rifle", "Pistol", "UAV"].map((c) => (
            <label key={c} className="inline-flex items-center gap-1 rounded border border-border bg-black/30 px-2 py-1 font-mono text-[10px]">
              <input type="checkbox" defaultChecked className="accent-primary" /> {c}
            </label>
          ))}
        </div>
      </Row>
      <Row label="Tracking Model">
        <select className="bg-black/40 border border-border rounded px-2 py-1 font-mono text-[11px]">
          <option>ByteTrack v2 (default)</option>
          <option>OC-SORT</option>
          <option>DeepSORT</option>
        </select>
      </Row>
      <Row label="Escalation Rules">
        <div className="font-mono text-[11px] space-y-1">
          <div>L1 · Crowd ≥ 15 for 30s → auto-notify watch</div>
          <div>L2 · Melee within 20m of perimeter → dispatch patrol</div>
          <div className="text-red-glow">L3 · Firearm → QRF alert + auto-record + siren</div>
        </div>
      </Row>
    </Panel>
  );
}

function NotificationsTab() {
  return (
    <Panel title="Notification Channels">
      {[
        ["Sound (Ops Room)", true],
        ["SMS", true],
        ["Email", true],
        ["Military Radio (VHF)", true],
        ["Push · Command App", false],
      ].map(([l, on]) => (
        <Row key={l as string} label={l as string}>
          <label className="inline-flex items-center gap-2">
            <input type="checkbox" defaultChecked={on as boolean} className="accent-primary" />
            <span className="font-mono text-[11px] text-muted-foreground">Enabled for L2 and L3</span>
          </label>
        </Row>
      ))}
    </Panel>
  );
}

function RolesTab() {
  return (
    <Panel title="Operators">
      <table className="w-full font-mono text-[11px]">
        <thead className="text-[9px] uppercase tracking-widest text-muted-foreground text-left">
          <tr><th className="py-2">Callsign</th><th>Rank</th><th>Role</th><th>Last Seen</th><th>Status</th></tr>
        </thead>
        <tbody>
          {[
            ["Rahman-S", "LT", "Watch Commander", "now", "Active"],
            ["Karim-A", "SGT", "Sector B Lead", "2m", "Active"],
            ["Islam-M", "CPL", "Sensor Op", "12m", "Standby"],
            ["Hasan-R", "PVT", "Trainee", "1h", "Idle"],
          ].map((r) => (
            <tr key={r[0]} className="border-b border-border/30">
              <td className="py-2 text-primary">{r[0]}</td>
              <td>{r[1]}</td>
              <td>{r[2]}</td>
              <td className="text-muted-foreground">{r[3]}</td>
              <td className={r[4] === "Active" ? "text-success" : r[4] === "Standby" ? "text-glow-cyan" : "text-muted-foreground"}>{r[4]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function RecordingTab() {
  return (
    <Panel title="Recording Policy">
      <Row label="Continuous Recording">30 days rolling · H.265 · 1080p</Row>
      <Row label="Event Snapshot">Keep for 180 days · full resolution</Row>
      <Row label="Alert Video Clip">±30s buffer · L2+ archived to cold storage</Row>
      <Row label="Encryption">AES-256 at rest · TLS 1.3 in transit</Row>
    </Panel>
  );
}

function AuditTab() {
  return (
    <Panel title="Audit Log">
      <div className="font-mono text-[11px] space-y-1 max-h-96 overflow-auto">
        {[
          "22:18:44 · LT Rahman · acknowledged INC-000124",
          "22:15:31 · SYSTEM · L3 alert generated · CAM-12",
          "22:10:02 · SGT Karim · updated ROI on CAM-18",
          "21:52:14 · LT Rahman · resolved INC-000121",
          "21:34:00 · CPL Islam · closed INC-000120",
          "20:12:00 · SYSTEM · nightly backup complete · 128 GB",
        ].map((l, i) => (
          <div key={i} className="border-b border-border/30 py-1">{l}</div>
        ))}
      </div>
    </Panel>
  );
}

function SystemTab() {
  return (
    <Panel title="System">
      <Row label="Language">
        <select className="bg-black/40 border border-border rounded px-2 py-1 font-mono text-[11px]">
          <option>English</option><option>বাংলা</option>
        </select>
      </Row>
      <Row label="Animations"><label className="inline-flex items-center gap-2"><input type="checkbox" defaultChecked className="accent-primary" /> Enabled</label></Row>
      <Row label="Backup Schedule">Nightly · 02:00 · Remote vault</Row>
      <Row label="Version">SENTINEL C2 · v4.2.1 · edge build 2026.07.13</Row>
    </Panel>
  );
}
