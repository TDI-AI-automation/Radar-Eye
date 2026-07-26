import { threatLevelLabel, type ThreatLevel } from "@/domain/threatLevel";

/**
 * Real six-value ThreatLevel badge (ALLY/OBSERVE/LOW/MEDIUM/HIGH/
 * HUMAN_REVIEW). Distinct from `components/hud/Panel.tsx`'s `LevelBadge`,
 * which is the prototype's fabricated 1|2|3 model -- kept as-is for
 * screens not yet migrated (Live Monitoring, Tactical Map), not touched
 * here. Every migrated screen that displays a threat level uses this
 * component instead.
 *
 * Tone classes mirror threatLevel.ts's threatLevelColor() mapping but as
 * the existing Tailwind-utility-class convention (LevelBadge, StatusPill
 * in routes/cameras.tsx) rather than inline CSS, for visual consistency
 * with the rest of the HUD chrome.
 */
const TONE_CLASS: Record<ThreatLevel, string> = {
  HIGH: "text-red-glow border-red-glow/70 bg-red-glow/10",
  MEDIUM: "text-amber-glow border-amber-glow/60 bg-amber-glow/10",
  HUMAN_REVIEW: "text-amber-glow border-amber-glow/60 bg-amber-glow/10",
  LOW: "text-primary border-primary/60 bg-primary/10",
  OBSERVE: "text-primary border-primary/60 bg-primary/10",
  ALLY: "text-success border-success/60 bg-success/10",
};

export function ThreatLevelBadge({ level }: { level: ThreatLevel }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-widest ${TONE_CLASS[level]}`}
    >
      {threatLevelLabel(level)}
    </span>
  );
}
