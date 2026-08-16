import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { VideoProvider, VideoHandle } from "./VideoProvider";
import { MpegtsVideoProvider } from "./MpegtsVideoProvider";

/**
 * The one place a concrete VideoProvider is chosen. `CameraTile` (Phase 3)
 * calls `useVideoProvider()` and never imports a concrete class directly
 * -- MpegtsVideoProvider (Live Monitoring's permanent video delivery
 * path, ADR-032: low-latency MPEG-TS over WebSocket) replaced
 * HlsVideoProvider here (rejected for ~10s measured latency); swapping
 * it again later changes only this file.
 */
const VideoProviderContext = createContext<VideoProvider | null>(null);

export function VideoProviderRoot({ children }: { children: ReactNode }) {
  const provider = useMemo<VideoProvider>(() => new MpegtsVideoProvider(), []);
  return <VideoProviderContext.Provider value={provider}>{children}</VideoProviderContext.Provider>;
}

export function useVideoProvider(): VideoProvider {
  const provider = useContext(VideoProviderContext);
  if (!provider) throw new Error("useVideoProvider() must be used within VideoProviderRoot");
  return provider;
}

/**
 * Reactive wrapper around VideoProvider.connect()/.subscribe()/
 * .disconnect(). connect() kicks off the (possibly async) connection and
 * returns its synchronous initial state; subscribe() is registered in the
 * same effect, before any awaited step inside connect() can resolve, so
 * no update is missed. Connects on mount / cameraId change, disconnects
 * on cleanup.
 */
export function useVideoHandle(cameraId: string): VideoHandle {
  const provider = useVideoProvider();
  const [handle, setHandle] = useState<VideoHandle>(() => provider.connect(cameraId));

  useEffect(() => {
    setHandle(provider.connect(cameraId));
    const unsubscribe = provider.subscribe(cameraId, setHandle);
    return () => {
      unsubscribe();
      provider.disconnect(cameraId);
    };
  }, [provider, cameraId]);

  return handle;
}
