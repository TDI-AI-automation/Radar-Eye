import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel } from "@/components/hud/Panel";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/QueryState";
import { Crosshair, Plus, Trash2, Target } from "lucide-react";
import {
  useCalibrationCameras,
  useCalibrationResults,
  useCameraCalibration,
  useStartCalibration,
  useValidateCalibration,
} from "@/features/calibration/hooks/useCalibration";
import { buildCalibrationHistoryRowViewModel } from "@/features/calibration/view-models/calibrationHistoryRow";
import { usePermission } from "@/auth/usePermission";
import { useVideoHandle } from "@/video/VideoProviderContext";

export const Route = createFileRoute("/calibration")({
  head: () => ({
    meta: [
      { title: "Calibration Center — SENTINEL C2" },
      {
        name: "description",
        content: "Ground-plane calibration workstation for perimeter cameras.",
      },
      { property: "og:title", content: "Calibration Center — SENTINEL C2" },
      {
        property: "og:description",
        content: "Ground-plane calibration workstation for perimeter cameras.",
      },
    ],
  }),
  component: Calibration,
});

/** services/calibration/types.py::MIN_REFERENCE_POINTS -- a client-side
 * hint only; the backend is the authority and 422s below this regardless. */
const MIN_REFERENCE_POINTS = 4;

interface PointRow {
  imageX: string;
  imageY: string;
  groundX: string;
  groundY: string;
}

function emptyPointRow(): PointRow {
  return { imageX: "", imageY: "", groundX: "", groundY: "" };
}

/**
 * No endpoint exists anywhere in RM-12 to retrieve a live or reference
 * frame for a camera -- an operator cannot click points on a rendered
 * image the way a real calibration workstation normally would (tracked in
 * the Phase 3 backend-gaps list). This screen is built around what's
 * actually possible today: manual numeric reference-point entry, exactly
 * matching CalibrationStartRequestSchema's real shape, plus the real
 * Validate tool (POST /calibration/validate) for confirming a calibration
 * against a known point. useVideoHandle() is reused here (not a new
 * placeholder invented for this screen) so the "no live feed" state stays
 * centralized in one seam.
 */
function Calibration() {
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);
  const canOperate = usePermission("operator");

  const camerasQuery = useCalibrationCameras();
  const resultsQuery = useCalibrationResults();
  const currentCalibrationQuery = useCameraCalibration(selectedCameraId);
  const startCalibration = useStartCalibration();
  const validateCalibration = useValidateCalibration();

  const cameraNameById = useMemo(
    () => new Map((camerasQuery.data ?? []).map((c) => [c.id, c.name])),
    [camerasQuery.data],
  );

  const historyRows = useMemo(
    () =>
      (resultsQuery.data ?? []).map((r) =>
        buildCalibrationHistoryRowViewModel(r, cameraNameById.get(r.cameraId)),
      ),
    [resultsQuery.data, cameraNameById],
  );

  const videoHandle = useVideoHandle(selectedCameraId ?? "");

  const [points, setPoints] = useState<PointRow[]>([
    emptyPointRow(),
    emptyPointRow(),
    emptyPointRow(),
    emptyPointRow(),
  ]);
  const [validateX, setValidateX] = useState("");
  const [validateY, setValidateY] = useState("");

  const validPointCount = points.filter(
    (p) => p.imageX !== "" && p.imageY !== "" && p.groundX !== "" && p.groundY !== "",
  ).length;
  const canSubmitCalibration =
    canOperate && selectedCameraId !== null && validPointCount >= MIN_REFERENCE_POINTS;

  async function handleStartCalibration() {
    if (!selectedCameraId) return;
    await startCalibration.mutateAsync({
      camera_id: selectedCameraId,
      reference_points: points
        .filter((p) => p.imageX !== "" && p.imageY !== "" && p.groundX !== "" && p.groundY !== "")
        .map((p) => ({
          image_x: Number(p.imageX),
          image_y: Number(p.imageY),
          ground_x: Number(p.groundX),
          ground_y: Number(p.groundY),
        })),
    });
    setPoints([emptyPointRow(), emptyPointRow(), emptyPointRow(), emptyPointRow()]);
  }

  async function handleValidate() {
    if (!selectedCameraId || validateX === "" || validateY === "") return;
    await validateCalibration.mutateAsync({
      camera_id: selectedCameraId,
      image_x: Number(validateX),
      image_y: Number(validateY),
    });
  }

  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-3">
      <Panel title="Cameras">
        {camerasQuery.isLoading ? (
          <LoadingState />
        ) : camerasQuery.isError ? (
          <ErrorState onRetry={() => void camerasQuery.refetch()} />
        ) : (camerasQuery.data ?? []).length === 0 ? (
          <EmptyState label="No cameras registered." />
        ) : (
          <ul className="space-y-1">
            {(camerasQuery.data ?? []).map((camera) => (
              <li key={camera.id}>
                <button
                  onClick={() => setSelectedCameraId(camera.id)}
                  className={`w-full text-left rounded px-2 py-1.5 font-mono text-[11px] ${
                    selectedCameraId === camera.id
                      ? "bg-primary/10 text-primary border-l-2 border-primary"
                      : "text-muted-foreground border-l-2 border-transparent hover:text-foreground hover:bg-accent/40"
                  }`}
                >
                  {camera.name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="space-y-3">
        {!selectedCameraId ? (
          <Panel title="Calibration Workstation">
            <EmptyState label="Select a camera to begin." />
          </Panel>
        ) : (
          <>
            <Panel title="Current State">
              <div className="hud-panel rounded aspect-video bg-black relative overflow-hidden flex items-center justify-center mb-3">
                <div className="flex flex-col items-center gap-2 text-muted-foreground">
                  <Crosshair className="h-8 w-8" />
                  <span className="font-mono text-[10px] uppercase tracking-widest">
                    {videoHandle.status === "unavailable"
                      ? "No Signal — manual point entry required"
                      : videoHandle.status}
                  </span>
                </div>
              </div>

              {currentCalibrationQuery.isLoading ? (
                <LoadingState />
              ) : !currentCalibrationQuery.data ? (
                <EmptyState label="Not yet calibrated." />
              ) : (
                <div className="grid grid-cols-3 gap-2 font-mono text-[11px]">
                  <Field
                    label="Reference Points"
                    value={String(currentCalibrationQuery.data.referencePointCount() ?? "—")}
                  />
                  <Field
                    label="Calibrated By"
                    value={currentCalibrationQuery.data.calibratedBy ?? "Unknown"}
                  />
                  <Field
                    label="Calibrated At"
                    value={currentCalibrationQuery.data.createdAt.toLocaleString()}
                  />
                </div>
              )}
            </Panel>

            <Panel title="New Calibration">
              <div className="space-y-2">
                {points.map((p, i) => (
                  <div
                    key={i}
                    className="grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-2 items-center font-mono text-[11px]"
                  >
                    <input
                      placeholder="image_x"
                      value={p.imageX}
                      onChange={(e) =>
                        setPoints((rows) =>
                          rows.map((r, ri) => (ri === i ? { ...r, imageX: e.target.value } : r)),
                        )
                      }
                      className="bg-black/40 border border-border rounded px-2 py-1"
                    />
                    <input
                      placeholder="image_y"
                      value={p.imageY}
                      onChange={(e) =>
                        setPoints((rows) =>
                          rows.map((r, ri) => (ri === i ? { ...r, imageY: e.target.value } : r)),
                        )
                      }
                      className="bg-black/40 border border-border rounded px-2 py-1"
                    />
                    <input
                      placeholder="ground_x (m)"
                      value={p.groundX}
                      onChange={(e) =>
                        setPoints((rows) =>
                          rows.map((r, ri) => (ri === i ? { ...r, groundX: e.target.value } : r)),
                        )
                      }
                      className="bg-black/40 border border-border rounded px-2 py-1"
                    />
                    <input
                      placeholder="ground_y (m)"
                      value={p.groundY}
                      onChange={(e) =>
                        setPoints((rows) =>
                          rows.map((r, ri) => (ri === i ? { ...r, groundY: e.target.value } : r)),
                        )
                      }
                      className="bg-black/40 border border-border rounded px-2 py-1"
                    />
                    <button
                      onClick={() => setPoints((rows) => rows.filter((_, ri) => ri !== i))}
                      disabled={points.length <= 1}
                      className="text-muted-foreground hover:text-red-glow disabled:opacity-30"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
                <button
                  onClick={() => setPoints((rows) => [...rows, emptyPointRow()])}
                  className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-primary hover:text-glow-cyan"
                >
                  <Plus className="h-3 w-3" /> Add Point
                </button>

                <div className="pt-2 flex items-center justify-between">
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {validPointCount} / {MIN_REFERENCE_POINTS} minimum points
                  </span>
                  <button
                    onClick={() => void handleStartCalibration()}
                    disabled={!canSubmitCalibration || startCalibration.isPending}
                    title={!canOperate ? "Operator role required" : undefined}
                    className="rounded border border-primary/50 bg-primary/15 px-4 py-2 uppercase tracking-widest text-primary text-[10px] disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {startCalibration.isPending ? "Calibrating…" : "Start Calibration"}
                  </button>
                </div>
                {startCalibration.isError && (
                  <p className="text-glow-red font-mono text-[10px]" role="alert">
                    Calibration failed — check reference points are non-degenerate.
                  </p>
                )}
              </div>
            </Panel>

            <Panel title="Validate">
              <div className="flex items-end gap-2 font-mono text-[11px]">
                <div className="flex-1">
                  <div className="text-[9px] uppercase tracking-widest text-muted-foreground mb-1">
                    Image X
                  </div>
                  <input
                    value={validateX}
                    onChange={(e) => setValidateX(e.target.value)}
                    className="w-full bg-black/40 border border-border rounded px-2 py-1"
                  />
                </div>
                <div className="flex-1">
                  <div className="text-[9px] uppercase tracking-widest text-muted-foreground mb-1">
                    Image Y
                  </div>
                  <input
                    value={validateY}
                    onChange={(e) => setValidateY(e.target.value)}
                    className="w-full bg-black/40 border border-border rounded px-2 py-1"
                  />
                </div>
                <button
                  onClick={() => void handleValidate()}
                  disabled={
                    !canOperate || !currentCalibrationQuery.data || validateCalibration.isPending
                  }
                  className="flex items-center gap-1 rounded border border-primary/40 bg-primary/10 px-3 py-1.5 uppercase tracking-widest text-primary text-[10px] disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Target className="h-3 w-3" /> Validate
                </button>
              </div>
              {validateCalibration.data && (
                <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[11px]">
                  <Field
                    label="Distance"
                    value={`${validateCalibration.data.distance_meters.toFixed(2)} m`}
                  />
                  <Field label="Zone" value={validateCalibration.data.zone} />
                </div>
              )}
              {validateCalibration.isError && (
                <p className="mt-2 text-glow-red font-mono text-[10px]" role="alert">
                  Validation failed.
                </p>
              )}
            </Panel>
          </>
        )}

        <Panel title={`Calibration History · ${historyRows.length}`}>
          {resultsQuery.isLoading ? (
            <LoadingState />
          ) : resultsQuery.isError ? (
            <ErrorState onRetry={() => void resultsQuery.refetch()} />
          ) : historyRows.length === 0 ? (
            <EmptyState label="No calibrations recorded." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px] font-mono">
                <thead>
                  <tr className="text-[9px] uppercase tracking-widest text-muted-foreground text-left border-b border-border/60">
                    {["Camera", "Points", "Calibrated By", "Calibrated At"].map((h) => (
                      <th key={h} className="px-2 py-2 font-normal">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {historyRows.map((row) => (
                    <tr key={row.id} className="border-b border-border/30">
                      <td className="px-2 py-2 text-primary">{row.cameraName}</td>
                      <td className="px-2 py-2">{row.pointCount ?? "—"}</td>
                      <td className="px-2 py-2 text-muted-foreground">{row.calibratedBy}</td>
                      <td className="px-2 py-2 text-muted-foreground">
                        {row.createdAt.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
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
