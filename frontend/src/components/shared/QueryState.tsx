/**
 * Shared loading/empty/error presentational states for migrated screens.
 * Every Phase 2+ screen needs these three (Phase 2 review checklist) --
 * built once here rather than reinvented per screen, promoted per §9's
 * "if two features need the same thing, promote it" rule.
 */
export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center py-12">
      <span className="font-mono text-xs uppercase tracking-widest text-muted-foreground animate-pulse">
        {label}
      </span>
    </div>
  );
}

export function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center py-12">
      <span className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
        {label}
      </span>
    </div>
  );
}

export function ErrorState({
  label = "Failed to load data.",
  onRetry,
}: {
  label?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12">
      <span className="font-mono text-xs uppercase tracking-widest text-red-glow">{label}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded border border-primary/40 bg-primary/10 px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest text-primary hover:bg-primary/20"
        >
          Retry
        </button>
      )}
    </div>
  );
}
