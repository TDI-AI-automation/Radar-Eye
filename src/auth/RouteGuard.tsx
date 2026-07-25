import { useEffect, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuth } from "./AuthProvider";

/**
 * Client-side-only auth enforcement. TanStack Start server-renders this
 * app; the server has no access to localStorage, so it cannot know
 * whether a request is authenticated -- there is no reliable server-side
 * redirect available while the token lives in localStorage (the tradeoff
 * accepted when localStorage was approved, see docs/FRONTEND_ARCHITECTURE.md
 * §3). AuthProvider's status starts at "loading" on both server and
 * client (identical markup, no hydration mismatch) and resolves to
 * "authenticated"/"unauthenticated" once the client mounts and reads
 * tokenStore. Until that resolves, this renders a neutral loading shell
 * rather than protected content, so there is no flash of real data before
 * a redirect.
 *
 * Applied once, around the whole authenticated shell in __root.tsx --
 * not per-screen. /login itself is rendered outside this guard entirely
 * (see RootComponent), so there's no redirect loop to guard against here.
 */
export function RouteGuard({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (status === "unauthenticated") {
      void navigate({ to: "/login" });
    }
  }, [status, navigate]);

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground animate-pulse">
          Establishing secure link…
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
