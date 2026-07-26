import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { Panel } from "@/components/hud/Panel";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/QueryState";
import { Shield, Users, ArrowUpCircle, XCircle, MapPin } from "lucide-react";
import { useReviews, useResolveReview } from "@/features/reviews/hooks/useReviews";
import {
  buildReviewRowViewModel,
  type ReviewRowViewModel,
} from "@/features/reviews/view-models/reviewRow";
import { useCameras } from "@/queries/useCameras";
import { usePermission } from "@/auth/usePermission";

export const Route = createFileRoute("/reviews")({
  head: () => ({
    meta: [
      { title: "Threat Review Center — SENTINEL C2" },
      {
        name: "description",
        content: "Operator review queue for unresolved uniform classifications.",
      },
      { property: "og:title", content: "Threat Review Center — SENTINEL C2" },
      {
        property: "og:description",
        content: "Operator review queue for unresolved uniform classifications.",
      },
    ],
  }),
  component: Reviews,
});

type StatusFilter = "OPEN" | "ALL";
type Action = "confirm-military" | "confirm-civilian" | "escalate" | "dismiss";

const ACTION_LABEL: Record<Action, string> = {
  "confirm-military": "Confirm Military",
  "confirm-civilian": "Confirm Civilian",
  escalate: "Escalate",
  dismiss: "Dismiss",
};

/**
 * CLAUDE.md's Human Review Rules: unknown uniforms must never be
 * auto-resolved, operator action required. This is the highest-traffic
 * operator screen (per Phase 3 review), so keyboard efficiency is a first-
 * class requirement, not an afterthought: J/K (or arrow keys) move the
 * selection, M/C/E/X arm the four resolution actions on the selected
 * item, and a second press of the same key within 3s confirms it
 * (armed-then-confirm, not a modal -- a modal would defeat the point of
 * a keyboard-driven queue). HumanReviewSchema has no timestamp field, so
 * there is no chronological sort here -- see the Phase 3 backend-gaps
 * list.
 */
function Reviews() {
  const [filter, setFilter] = useState<StatusFilter>("OPEN");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [armedAction, setArmedAction] = useState<Action | null>(null);
  const armTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const reviewsQuery = useReviews();
  const camerasQuery = useCameras();
  const resolve = useResolveReview();
  const canOperate = usePermission("operator");

  const cameraNameById = useMemo(
    () => new Map((camerasQuery.data ?? []).map((c) => [c.id, c.name])),
    [camerasQuery.data],
  );

  const rows = useMemo<ReviewRowViewModel[]>(() => {
    const items = reviewsQuery.data ?? [];
    return items
      .filter((i) => filter === "ALL" || i.status === "OPEN")
      .map((i) => buildReviewRowViewModel(i, cameraNameById.get(i.cameraId)));
  }, [reviewsQuery.data, cameraNameById, filter]);

  const openCount = (reviewsQuery.data ?? []).filter((i) => i.status === "OPEN").length;

  const clearArm = useCallback(() => {
    setArmedAction(null);
    if (armTimerRef.current) {
      clearTimeout(armTimerRef.current);
      armTimerRef.current = null;
    }
  }, []);

  const runAction = useCallback(
    (reviewId: string, action: Action) => {
      resolve.mutate({ reviewId, action });
      clearArm();
    },
    [resolve, clearArm],
  );

  const handleAction = useCallback(
    (row: ReviewRowViewModel, action: Action) => {
      if (!canOperate || !row.canResolve) return;
      if (armedAction === action) {
        runAction(row.id, action);
      } else {
        setArmedAction(action);
        clearArm();
        armTimerRef.current = setTimeout(() => setArmedAction(null), 3000);
      }
    },
    [armedAction, canOperate, runAction, clearArm],
  );

  useEffect(() => {
    if (selectedIndex >= rows.length) setSelectedIndex(Math.max(0, rows.length - 1));
  }, [rows.length, selectedIndex]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (rows.length === 0) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;

      const row = rows[selectedIndex];
      switch (e.key.toLowerCase()) {
        case "j":
        case "arrowdown":
          e.preventDefault();
          clearArm();
          setSelectedIndex((i) => Math.min(i + 1, rows.length - 1));
          break;
        case "k":
        case "arrowup":
          e.preventDefault();
          clearArm();
          setSelectedIndex((i) => Math.max(i - 1, 0));
          break;
        case "m":
          if (row) handleAction(row, "confirm-military");
          break;
        case "c":
          if (row) handleAction(row, "confirm-civilian");
          break;
        case "e":
          if (row) handleAction(row, "escalate");
          break;
        case "x":
          if (row) handleAction(row, "dismiss");
          break;
        case "escape":
          clearArm();
          break;
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [rows, selectedIndex, handleAction, clearArm]);

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <FilterTab
            label={`Open (${openCount})`}
            active={filter === "OPEN"}
            onClick={() => setFilter("OPEN")}
          />
          <FilterTab label="All" active={filter === "ALL"} onClick={() => setFilter("ALL")} />
        </div>
        <div className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
          J/K navigate · M military · C civilian · E escalate · X dismiss · press twice to confirm
        </div>
      </div>

      <Panel title={`Review Queue · ${rows.length}`}>
        {reviewsQuery.isLoading ? (
          <LoadingState label="Loading review queue…" />
        ) : reviewsQuery.isError ? (
          <ErrorState
            label="Failed to load review queue."
            onRetry={() => void reviewsQuery.refetch()}
          />
        ) : rows.length === 0 ? (
          <EmptyState label={filter === "OPEN" ? "No open reviews." : "No reviews recorded."} />
        ) : (
          <div className="space-y-2">
            {rows.map((row, index) => (
              <ReviewCard
                key={row.id}
                row={row}
                selected={index === selectedIndex}
                armedAction={index === selectedIndex ? armedAction : null}
                canOperate={canOperate}
                onSelect={() => {
                  setSelectedIndex(index);
                  clearArm();
                }}
                onAction={(action) => handleAction(row, action)}
                isPending={resolve.isPending}
              />
            ))}
          </div>
        )}
        {resolve.isError && (
          <p className="mt-2 text-glow-red font-mono text-[10px]" role="alert">
            Failed to resolve review item.
          </p>
        )}
      </Panel>
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

function ReviewCard({
  row,
  selected,
  armedAction,
  canOperate,
  onSelect,
  onAction,
  isPending,
}: {
  row: ReviewRowViewModel;
  selected: boolean;
  armedAction: Action | null;
  canOperate: boolean;
  onSelect: () => void;
  onAction: (action: Action) => void;
  isPending: boolean;
}) {
  return (
    <div
      onClick={onSelect}
      className={`hud-panel rounded p-3 border cursor-pointer transition ${
        selected ? "border-primary/70 hud-panel-glow" : "border-border hover:border-primary/40"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-1 text-sm font-semibold">
            <MapPin className="h-3 w-3 text-muted-foreground" /> {row.cameraName}
            <span className="text-muted-foreground font-mono text-[10px]">
              · track {row.trackId}
            </span>
          </div>
          <div className="mt-1 font-mono text-[10px] text-muted-foreground">{row.reason}</div>
        </div>
        <span
          className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest ${
            row.status === "OPEN"
              ? "text-amber-glow border-amber-glow/50 bg-amber-glow/10"
              : "text-muted-foreground border-border bg-black/20"
          }`}
        >
          {row.status}
        </span>
      </div>

      {row.canResolve && (
        <div className="mt-3 grid grid-cols-4 gap-1.5">
          <ActionButton
            icon={Shield}
            label={ACTION_LABEL["confirm-military"]}
            armed={armedAction === "confirm-military"}
            disabled={!canOperate || isPending}
            onClick={(e) => {
              e.stopPropagation();
              onAction("confirm-military");
            }}
          />
          <ActionButton
            icon={Users}
            label={ACTION_LABEL["confirm-civilian"]}
            armed={armedAction === "confirm-civilian"}
            disabled={!canOperate || isPending}
            onClick={(e) => {
              e.stopPropagation();
              onAction("confirm-civilian");
            }}
          />
          <ActionButton
            icon={ArrowUpCircle}
            label={ACTION_LABEL.escalate}
            armed={armedAction === "escalate"}
            disabled={!canOperate || isPending}
            onClick={(e) => {
              e.stopPropagation();
              onAction("escalate");
            }}
          />
          <ActionButton
            icon={XCircle}
            label={ACTION_LABEL.dismiss}
            armed={armedAction === "dismiss"}
            disabled={!canOperate || isPending}
            onClick={(e) => {
              e.stopPropagation();
              onAction("dismiss");
            }}
          />
        </div>
      )}
    </div>
  );
}

function ActionButton({
  icon: Icon,
  label,
  armed,
  disabled,
  onClick,
}: {
  icon: typeof Shield;
  label: string;
  armed: boolean;
  disabled: boolean;
  onClick: (e: React.MouseEvent) => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={disabled ? "Operator role required" : label}
      className={`flex flex-col items-center gap-1 rounded border py-1.5 font-mono text-[9px] uppercase tracking-widest transition disabled:opacity-40 disabled:cursor-not-allowed ${
        armed
          ? "border-red-glow/70 bg-red-glow/15 text-red-glow"
          : "border-border text-muted-foreground hover:border-primary/40 hover:text-primary"
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
      {armed ? "Confirm?" : label}
    </button>
  );
}
