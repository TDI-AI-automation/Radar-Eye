import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  useRouterState,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  Radar,
  AlertTriangle,
  Camera,
  BrainCircuit,
  HeartPulse,
  Settings,
  Shield,
  Signal,
  Wifi,
  ShieldAlert,
  Crosshair,
  FolderLock,
} from "lucide-react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { AuthProvider, useAuth } from "@/auth/AuthProvider";
import { RouteGuard } from "@/auth/RouteGuard";
import { VideoProviderRoot } from "@/video/VideoProviderContext";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="hud-panel hud-corner max-w-md text-center p-10">
        <h1 className="text-glow-cyan text-6xl font-mono font-bold">404</h1>
        <h2 className="mt-4 text-lg font-semibold uppercase tracking-widest">Signal Lost</h2>
        <p className="mt-2 text-sm text-muted-foreground">The requested sector is out of range.</p>
        <Link
          to="/"
          className="mt-6 inline-flex items-center justify-center rounded border border-primary/40 bg-primary/10 px-4 py-2 text-xs font-mono uppercase tracking-widest text-primary hover:bg-primary/20"
        >
          Return to Command
        </Link>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="hud-panel hud-corner max-w-md p-8 text-center">
        <h1 className="text-glow-red text-lg font-mono uppercase tracking-widest">System Fault</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          A subsystem failed to load. Retry to re-establish link.
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="rounded border border-primary/40 bg-primary/10 px-4 py-2 text-xs font-mono uppercase tracking-widest text-primary hover:bg-primary/20"
          >
            Retry
          </button>
          <a
            href="/"
            className="rounded border border-border px-4 py-2 text-xs font-mono uppercase tracking-widest text-muted-foreground hover:text-foreground"
          >
            Command
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Live Monitoring — SENTINEL C2" },
      {
        name: "description",
        content: "Real-time AI-driven perimeter monitoring across all camera feeds.",
      },
      { name: "author", content: "SENTINEL" },
      { property: "og:title", content: "Live Monitoring — SENTINEL C2" },
      {
        property: "og:description",
        content: "Real-time AI-driven perimeter monitoring across all camera feeds.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { name: "twitter:title", content: "Live Monitoring — SENTINEL C2" },
      {
        name: "twitter:description",
        content: "Real-time AI-driven perimeter monitoring across all camera feeds.",
      },
      {
        property: "og:image",
        content:
          "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/4425d33b-709e-441f-947a-f8c4456cba67/id-preview-f686e65d--d74d4cbd-a321-41f8-a680-15330c53a948.lovable.app-1783995403366.png",
      },
      {
        name: "twitter:image",
        content:
          "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/4425d33b-709e-441f-947a-f8c4456cba67/id-preview-f686e65d--d74d4cbd-a321-41f8-a680-15330c53a948.lovable.app-1783995403366.png",
      },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap",
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

const NAV = [
  { to: "/", label: "Live Monitoring", icon: Activity },
  { to: "/map", label: "Tactical Map", icon: Radar },
  { to: "/cameras", label: "Cameras", icon: Camera },
  { to: "/incidents", label: "Incidents", icon: AlertTriangle },
  { to: "/reviews", label: "Threat Review", icon: ShieldAlert },
  { to: "/calibration", label: "Calibration", icon: Crosshair },
  { to: "/evidence", label: "Evidence", icon: FolderLock },
  { to: "/analytics", label: "AI Analytics", icon: BrainCircuit },
  { to: "/health", label: "System Health", icon: HeartPulse },
  { to: "/settings", label: "Configuration", icon: Settings },
] as const;

function TopBar() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const time = now.toISOString().substring(11, 19);
  const date = now.toISOString().substring(0, 10);
  return (
    <header className="hud-panel flex items-center justify-between px-4 py-2 h-14 rounded-none border-x-0 border-t-0">
      <div className="flex items-center gap-3">
        <div className="relative flex h-9 w-9 items-center justify-center rounded border border-primary/50 bg-primary/10">
          <Shield className="h-4 w-4 text-primary" />
          <span className="absolute inset-0 rounded animate-pulse-cyan" />
        </div>
        <div className="leading-tight">
          <div className="font-mono text-xs uppercase tracking-[0.3em] text-primary">
            SENTINEL C2
          </div>
          <div className="text-[10px] text-muted-foreground">Army Camp Alpha • Sector 7</div>
        </div>
      </div>
      <div className="hidden md:flex items-center gap-6 font-mono text-[11px] uppercase tracking-wider">
        <StatChip label="MISSION" value="ACTIVE" tone="success" />
        <StatChip label="THREAT" value="MEDIUM" tone="amber" />
        <StatChip label="CAMS" value="46/48" tone="cyan" />
        <StatChip label="AI FPS" value="30" tone="cyan" />
        <StatChip label="GPU" value="73%" tone="cyan" />
      </div>
      <div className="flex items-center gap-3 font-mono">
        <Signal className="h-3.5 w-3.5 text-success" />
        <Wifi className="h-3.5 w-3.5 text-success" />
        <div className="text-right leading-tight">
          <div className="text-sm text-glow-cyan">{time}</div>
          <div className="text-[10px] text-muted-foreground">{date} UTC</div>
        </div>
      </div>
    </header>
  );
}

function StatChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "cyan" | "amber" | "red" | "success";
}) {
  const toneClass = {
    cyan: "text-primary border-primary/40",
    amber: "text-amber-glow border-amber-glow/40",
    red: "text-red-glow border-red-glow/40",
    success: "text-success border-success/40",
  }[tone];
  return (
    <div className={`flex items-center gap-2 rounded border px-2 py-1 bg-black/30 ${toneClass}`}>
      <span className="text-muted-foreground text-[9px]">{label}</span>
      <span className="text-[11px] font-semibold">{value}</span>
    </div>
  );
}

function SideNav() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const { user } = useAuth();
  return (
    <nav className="hud-panel rounded-none border-y-0 border-l-0 w-16 lg:w-56 flex flex-col py-4">
      <div className="px-3 pb-2 hidden lg:block">
        <div className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
          Command Modules
        </div>
      </div>
      <ul className="flex-1 space-y-1 px-2">
        {NAV.map((item) => {
          const active = path === item.to;
          const Icon = item.icon;
          return (
            <li key={item.to}>
              <Link
                to={item.to}
                className={`group flex items-center gap-3 rounded px-2.5 py-2 text-xs font-mono uppercase tracking-wider transition-all ${
                  active
                    ? "bg-primary/10 text-primary border-l-2 border-primary"
                    : "text-muted-foreground border-l-2 border-transparent hover:text-foreground hover:bg-accent/40"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="hidden lg:inline">{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="px-3 pt-4 hidden lg:block">
        <div className="hud-divider mb-3" />
        <div className="text-[10px] font-mono text-muted-foreground">
          OPERATOR
          <br />
          <span className="text-primary">{user?.username ?? "—"}</span>
        </div>
      </div>
    </nav>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </QueryClientProvider>
  );
}

/**
 * /login is rendered outside RouteGuard and without the operator chrome
 * (TopBar/SideNav) entirely -- it's the one route unauthenticated users
 * can reach, so it can neither require auth nor show authenticated-only
 * content (stat chips, operator name). Every other route is wrapped in
 * RouteGuard, which redirects to /login when unauthenticated.
 */
function AppShell() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  if (pathname === "/login") {
    return <Outlet />;
  }
  return (
    <RouteGuard>
      <VideoProviderRoot>
        <div className="flex min-h-screen flex-col">
          <TopBar />
          <div className="flex flex-1 overflow-hidden">
            <SideNav />
            <main className="flex-1 overflow-auto">
              <Outlet />
            </main>
          </div>
        </div>
      </VideoProviderRoot>
    </RouteGuard>
  );
}
