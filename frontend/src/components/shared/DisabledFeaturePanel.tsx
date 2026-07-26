import { Lock } from "lucide-react";

/**
 * Explicit "not yet available" state for a feature with no backend
 * support -- used instead of removing the entry, per CLAUDE.md's Settings
 * instruction ("Continue disabling unsupported functionality explicitly
 * rather than removing it silently"). First used for Health's Event Log
 * Stream panel; promoted here once Settings needed the same pattern three
 * more times (AI Model, Notifications, Audit Log), per §9's "if a second
 * feature needs it, promote it" rule.
 */
export function DisabledFeaturePanel({ reason }: { reason: string }) {
  return (
    <div className="flex items-center gap-2 rounded border border-border/60 bg-black/20 px-3 py-3 font-mono text-[11px] text-muted-foreground">
      <Lock className="h-3.5 w-3.5 shrink-0" />
      {reason}
    </div>
  );
}
