import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { VideoProvider, VideoHandle } from "./VideoProvider";
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

/**
 * Reactive wrapper around VideoProvider.connect()/.disconnect() -- kept
 * as a hook (not called inline in render) because the interface's own
 * contract says callers should "expect [status] to change over time"
 * even though PlaceholderVideoProvider today always returns a static
 * "unavailable" handle synchronously. Connects on mount / cameraId
 * change, disconnects on cleanup.
 */
export function useVideoHandle(cameraId: string): VideoHandle {
  const provider = useVideoProvider();
  const [handle, setHandle] = useState<VideoHandle>(() => provider.connect(cameraId));

  useEffect(() => {
    setHandle(provider.connect(cameraId));
    return () => provider.disconnect(cameraId);
  }, [provider, cameraId]);

  return handle;
}
