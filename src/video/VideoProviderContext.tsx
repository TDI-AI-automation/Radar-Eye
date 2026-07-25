import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { VideoProvider } from "./VideoProvider";
import { PlaceholderVideoProvider } from "./PlaceholderVideoProvider";

/**
 * The one place a concrete VideoProvider is chosen. `CameraTile` (Phase 3)
 * calls `useVideoProvider()` and never imports a concrete class directly
 * -- swapping PlaceholderVideoProvider for a real one later (RTSP/WebRTC/
 * HLS, once docs/FRONTEND_ARCHITECTURE.md's "Open Backend Dependencies"
 * video-delivery contract exists) changes only this file.
 */
const VideoProviderContext = createContext<VideoProvider | null>(null);

export function VideoProviderRoot({ children }: { children: ReactNode }) {
  const provider = useMemo<VideoProvider>(() => new PlaceholderVideoProvider(), []);
  return <VideoProviderContext.Provider value={provider}>{children}</VideoProviderContext.Provider>;
}

export function useVideoProvider(): VideoProvider {
  const provider = useContext(VideoProviderContext);
  if (!provider) throw new Error("useVideoProvider() must be used within VideoProviderRoot");
  return provider;
}
