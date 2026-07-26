import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel } from "@/components/hud/Panel";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/QueryState";
import { Film, Image as ImageIcon, Download, Lock } from "lucide-react";
import { useEvidenceList, useDownloadEvidence } from "@/features/evidence/hooks/useEvidence";
import { useEvidencePreview } from "@/features/evidence/hooks/useEvidencePreview";
import {
  buildEvidenceRowViewModel,
  applyEvidenceFilter,
  type EvidenceRowViewModel,
  type EvidenceFilter,
} from "@/features/evidence/view-models/evidenceRow";
import { useCameras } from "@/queries/useCameras";

export const Route = createFileRoute("/evidence")({
  head: () => ({
    meta: [
      { title: "Evidence Viewer — SENTINEL C2" },
      { name: "description", content: "Recorded and captured evidence for security incidents." },
      { property: "og:title", content: "Evidence Viewer — SENTINEL C2" },
      {
        property: "og:description",
        content: "Recorded and captured evidence for security incidents.",
      },
    ],
  }),
  component: EvidenceViewer,
});

/**
 * CLAUDE.md's Evidence Preservation principle + the Phase 3 instruction:
 * treat evidence as immutable, reinforce chain-of-custody in the UI.
 * apps/api/app/routers/evidence.py exposes zero mutation routes for
 * evidence -- this screen mirrors that at the UI level: no rename, no
 * delete, no annotate, no edit affordance of any kind, ever. The only
 * actions are View (read-only inline preview) and Download (the exact
 * bytes the backend serves, unmodified). No server-side filtering exists
 * on GET /evidence (tracked in the Phase 3 backend-gaps list) -- type/
 * camera filters below are client-side over the full list.
 */
function EvidenceViewer() {
  const [filter, setFilter] = useState<EvidenceFilter>({ type: "ALL", cameraId: "ALL" });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const evidenceQuery = useEvidenceList();
  const camerasQuery = useCameras();
  const download = useDownloadEvidence();

  const cameraNameById = useMemo(
    () => new Map((camerasQuery.data ?? []).map((c) => [c.id, c.name])),
    [camerasQuery.data],
  );

  const rows = useMemo(
    () =>
      applyEvidenceFilter(
        (evidenceQuery.data ?? []).map((e) =>
          buildEvidenceRowViewModel(e, cameraNameById.get(e.cameraId)),
        ),
        filter,
      ),
    [evidenceQuery.data, cameraNameById, filter],
  );

  const selected = rows.find((r) => r.id === selectedId) ?? null;

  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-3">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <FilterTab
            label="All"
            active={filter.type === "ALL"}
            onClick={() => setFilter((f) => ({ ...f, type: "ALL" }))}
          />
          <FilterTab
            label="Snapshots"
            active={filter.type === "snapshot"}
            onClick={() => setFilter((f) => ({ ...f, type: "snapshot" }))}
          />
          <FilterTab
            label="Recordings"
            active={filter.type === "recording"}
            onClick={() => setFilter((f) => ({ ...f, type: "recording" }))}
          />
          <select
            value={filter.cameraId}
            onChange={(e) => setFilter((f) => ({ ...f, cameraId: e.target.value }))}
            className="rounded border border-border bg-black/40 px-2 py-1.5 font-mono text-[10px] text-muted-foreground"
          >
            <option value="ALL">All Cameras</option>
            {(camerasQuery.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <Panel title={`Evidence · ${rows.length}`}>
          {evidenceQuery.isLoading ? (
            <LoadingState label="Loading evidence…" />
          ) : evidenceQuery.isError ? (
            <ErrorState
              label="Failed to load evidence."
              onRetry={() => void evidenceQuery.refetch()}
            />
          ) : rows.length === 0 ? (
            <EmptyState label="No evidence recorded." />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {rows.map((row) => (
                <button
                  key={row.id}
                  onClick={() => setSelectedId(row.id)}
                  className={`text-left hud-panel rounded p-2 border transition ${
                    selectedId === row.id
                      ? "border-primary/70 hud-panel-glow"
                      : "border-border hover:border-primary/40"
                  }`}
                >
                  <div className="flex items-center gap-1.5 font-mono text-[10px] text-primary">
                    {row.evidenceType === "recording" ? (
                      <Film className="h-3 w-3" />
                    ) : (
                      <ImageIcon className="h-3 w-3" />
                    )}
                    {row.evidenceType}
                  </div>
                  <div className="mt-1 text-[11px] font-semibold">{row.cameraName}</div>
                  <div className="font-mono text-[9px] text-muted-foreground">
                    {row.capturedAt.toLocaleString()}
                  </div>
                </button>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Evidence Detail">
        {!selected ? (
          <EmptyState label="Select evidence to view." />
        ) : (
          <EvidenceDetail
            row={selected}
            onDownload={() =>
              void download.mutate({
                downloadUrl: selected.downloadUrl,
                fileName: selected.fileName,
              })
            }
            isDownloading={download.isPending}
          />
        )}
      </Panel>
    </div>
  );
}

function EvidenceDetail({
  row,
  onDownload,
  isDownloading,
}: {
  row: EvidenceRowViewModel;
  onDownload: () => void;
  isDownloading: boolean;
}) {
  const preview = useEvidencePreview(row.downloadUrl);

  return (
    <div className="space-y-3">
      <div className="hud-panel rounded aspect-video bg-black relative overflow-hidden flex items-center justify-center">
        {preview.status === "loading" ? (
          <LoadingState label="Loading preview…" />
        ) : preview.status === "error" ? (
          <span className="font-mono text-[10px] text-muted-foreground">Preview unavailable.</span>
        ) : preview.objectUrl && row.evidenceType === "snapshot" ? (
          <img
            src={preview.objectUrl}
            alt="Evidence snapshot"
            className="h-full w-full object-contain"
          />
        ) : preview.objectUrl && row.evidenceType === "recording" ? (
          // Recordings are stored as H.265 (CLAUDE.md); browser <video>
          // playback of H.265 is not reliably supported across browsers
          // -- this is a best-effort inline preview, not guaranteed to
          // render. Download always works regardless (raw bytes,
          // unmodified). Tracked in the Phase 3 backend-gaps list.
          <video src={preview.objectUrl} controls className="h-full w-full" />
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
        <Field label="Type" value={row.evidenceType} />
        <Field label="Camera" value={row.cameraName} />
        <Field label="Incident" value={row.incidentId} />
        <Field label="Captured" value={row.capturedAt.toLocaleString()} />
      </div>

      <div className="flex items-center gap-2 rounded border border-border/60 bg-black/20 px-3 py-2 font-mono text-[10px] text-muted-foreground">
        <Lock className="h-3 w-3" /> Read-only — evidence cannot be edited or deleted.
      </div>

      <button
        onClick={onDownload}
        disabled={isDownloading}
        className="w-full flex items-center justify-center gap-2 rounded border border-primary/40 bg-primary/10 py-2 font-mono text-[10px] uppercase tracking-widest text-primary hover:bg-primary/20 disabled:opacity-50"
      >
        <Download className="h-3.5 w-3.5" /> {isDownloading ? "Downloading…" : "Download Original"}
      </button>
    </div>
  );
}

function FilterTab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded border px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest ${
        active
          ? "border-primary/60 bg-primary/10 text-primary"
          : "border-border text-muted-foreground hover:text-foreground"
      }`}
    >
      {label}
    </button>
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
