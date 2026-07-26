import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel } from "@/components/hud/Panel";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/QueryState";
import { DisabledFeaturePanel } from "@/components/shared/DisabledFeaturePanel";
import { useUsers, useUpdateUserRole } from "@/features/settings/hooks/useUsers";
import { usePermission } from "@/auth/usePermission";
import { ROLE_RANK } from "@/auth/types";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Configuration — SENTINEL C2" },
      { name: "description", content: "System configuration, roles, and recording policy." },
      { property: "og:title", content: "Configuration — SENTINEL C2" },
      { property: "og:description", content: "System configuration, roles, and recording policy." },
    ],
  }),
  component: SettingsPage,
});

const TABS = [
  "Roles & Users",
  "Recording Policy",
  "AI Model",
  "Notifications",
  "Audit Log",
] as const;

/**
 * Final-phase Settings redesign, per the review's explicit grouping:
 * Roles & Users is real, administrative configuration (GET/PATCH /users,
 * admin-only). Recording Policy is real but fixed system policy (CLAUDE.md's
 * Recording Rules), not a configurable setting -- shown as read-only, not
 * as editable inputs implying a PATCH that doesn't exist. AI Model and
 * Notifications are explicitly deferred (docs/OPEN_QUESTIONS.md Q-014,
 * already tracked since Phase 0 §10) -- shown disabled, not removed.
 * Audit Log has no backend endpoint at all (§16, Tier 1 gap) -- same
 * disabled treatment as Health's Event Log Stream. The prototype's
 * "System" tab (language selector, animation toggle, backup schedule,
 * fabricated version string) had no real backend concept behind any of
 * it and no local-only feature it was worth building in isolation --
 * dropped rather than kept as an empty shell.
 */
function SettingsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Roles & Users");
  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-3">
      <Panel title="Configuration">
        <ul className="space-y-1">
          {TABS.map((t) => (
            <li key={t}>
              <button
                onClick={() => setTab(t)}
                className={`w-full text-left rounded px-2 py-1.5 font-mono text-[11px] uppercase tracking-widest ${
                  tab === t
                    ? "bg-primary/15 text-primary border-l-2 border-primary"
                    : "text-muted-foreground hover:text-primary border-l-2 border-transparent"
                }`}
              >
                {t}
              </button>
            </li>
          ))}
        </ul>
      </Panel>

      <div className="space-y-3">
        {tab === "Roles & Users" && <RolesTab />}
        {tab === "Recording Policy" && <RecordingTab />}
        {tab === "AI Model" && <AITab />}
        {tab === "Notifications" && <NotificationsTab />}
        {tab === "Audit Log" && <AuditTab />}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-3 items-center py-2 border-b border-border/30">
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}

const ROLE_OPTIONS = Object.keys(ROLE_RANK);

function RolesTab() {
  const canAdminister = usePermission("admin");
  const usersQuery = useUsers();
  const updateRole = useUpdateUserRole();

  if (!canAdminister) {
    return (
      <Panel title="Operators">
        <DisabledFeaturePanel reason="Administrator role required to view or manage users." />
      </Panel>
    );
  }

  return (
    <Panel title="Operators">
      {usersQuery.isLoading ? (
        <LoadingState label="Loading users…" />
      ) : usersQuery.isError ? (
        <ErrorState label="Failed to load users." onRetry={() => void usersQuery.refetch()} />
      ) : (usersQuery.data ?? []).length === 0 ? (
        <EmptyState label="No users registered." />
      ) : (
        <table className="w-full font-mono text-[11px]">
          <thead className="text-[9px] uppercase tracking-widest text-muted-foreground text-left">
            <tr>
              <th className="py-2">Username</th>
              <th>Role</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {(usersQuery.data ?? []).map((user) => (
              <tr key={user.id} className="border-b border-border/30">
                <td className="py-2 text-primary">{user.username}</td>
                <td className="py-2">
                  <select
                    value={user.role}
                    onChange={(e) => updateRole.mutate({ userId: user.id, role: e.target.value })}
                    disabled={updateRole.isPending}
                    className="bg-black/40 border border-border rounded px-2 py-1"
                  >
                    {ROLE_OPTIONS.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="py-2 text-muted-foreground">
                  {user.createdAt.toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {updateRole.isError && (
        <p className="mt-2 text-glow-red font-mono text-[10px]" role="alert">
          Failed to update role.
        </p>
      )}
    </Panel>
  );
}

function RecordingTab() {
  return (
    <Panel title="Recording Policy">
      <div className="mb-3 font-mono text-[10px] text-muted-foreground">
        Fixed system policy (CLAUDE.md) — not currently configurable via this interface.
      </div>
      <Row label="Continuous Recording">Enabled</Row>
      <Row label="Archive Format">H.265</Row>
      <Row label="Retention">30 days</Row>
      <Row label="Generated Artifacts">Snapshots, event clips</Row>
    </Panel>
  );
}

function AITab() {
  return (
    <Panel title="Detection & Inference">
      <DisabledFeaturePanel reason="AI model configuration is not yet exposed by the backend (docs/OPEN_QUESTIONS.md Q-014)." />
    </Panel>
  );
}

function NotificationsTab() {
  return (
    <Panel title="Notification Channels">
      <DisabledFeaturePanel reason="Notification configuration is not yet exposed by the backend (docs/OPEN_QUESTIONS.md Q-014)." />
    </Panel>
  );
}

function AuditTab() {
  return (
    <Panel title="Audit Log">
      <DisabledFeaturePanel reason="Not yet available — awaiting a GET /audit-log endpoint (docs/FRONTEND_ARCHITECTURE.md §16)." />
    </Panel>
  );
}
