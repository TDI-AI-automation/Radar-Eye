import type { ReactNode } from "react";

export function Panel({
  title,
  children,
  actions,
  glow,
  className = "",
  padding = true,
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
  glow?: boolean;
  className?: string;
  padding?: boolean;
}) {
  return (
    <div className={`hud-panel rounded ${glow ? "hud-panel-glow" : ""} ${className}`}>
      {title && (
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
            <h3 className="font-mono text-[10px] uppercase tracking-[0.22em] text-foreground/80">
              {title}
            </h3>
          </div>
          {actions}
        </div>
      )}
      <div className={padding ? "p-3" : ""}>{children}</div>
    </div>
  );
}

export function StatTile({
  label,
  value,
  sub,
  tone = "cyan",
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  tone?: "cyan" | "amber" | "red" | "success" | "muted";
}) {
  const toneMap = {
    cyan: "text-foreground",
    amber: "text-amber-glow",
    red: "text-red-glow",
    success: "text-success",
    muted: "text-muted-foreground",
  } as const;
  return (
    <div className="hud-panel rounded px-3 py-2">
      <div className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
      <div className={`font-mono text-2xl font-semibold leading-tight ${toneMap[tone]}`}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-[10px] text-muted-foreground font-mono">{sub}</div>}
    </div>
  );
}

export function Bar({
  value,
  tone = "cyan",
}: {
  value: number;
  tone?: "cyan" | "amber" | "red" | "success";
}) {
  const colorVar = {
    cyan: "var(--primary)",
    amber: "var(--amber-glow)",
    red: "var(--red-glow)",
    success: "var(--success)",
  }[tone];
  return (
    <div className="h-1.5 w-full rounded-full bg-black/40 overflow-hidden">
      <div
        className="h-full rounded-full transition-all"
        style={{
          width: `${Math.max(0, Math.min(100, value))}%`,
          background: colorVar,
        }}
      />
    </div>
  );
}
