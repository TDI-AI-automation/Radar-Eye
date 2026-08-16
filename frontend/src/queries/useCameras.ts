import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { listCameras, listCamerasHealth } from "@/api/endpoints/cameras";
import { toCameraDomain } from "@/domain/mappers/cameraMapper";
import type { Camera } from "@/domain/models/Camera";
import { queryKeys } from "./queryKeys";
import { STALE_TIME } from "./staleTimes";
import { subscribeToChannel } from "@/ws/connection";
import type { components } from "@/api/generated/schema";

/**
 * Shared REST-domain query hooks for Cameras (GET /cameras, GET
 * /health/cameras) -- live in queries/, not features/cameras/hooks/,
 * because more than one feature needs "the list of cameras" (Cameras
 * Management, Analytics' per-camera incident counts). Per §9's rule,
 * anything a second feature needs is promoted out of a single feature's
 * folder; feature-specific composition (the health-join view model, the
 * update mutation) stays in features/cameras/.
 */
export function useCameras() {
  useCameraHealthChannel();

  return useQuery({
    queryKey: queryKeys.cameras.list(),
    queryFn: async (): Promise<Camera[]> => {
      const dtos = (await listCameras()) ?? [];
      return dtos.map(toCameraDomain);
    },
    staleTime: STALE_TIME.reference,
  });
}

export type CameraHealthDto = components["schemas"]["CameraHealthSchema"];

/** GET /health/cameras -- all cameras' fps/last_frame_age in one call. */
export function useCamerasHealth() {
  return useQuery({
    queryKey: queryKeys.health.cameras(),
    queryFn: async (): Promise<CameraHealthDto[]> => (await listCamerasHealth()) ?? [],
    staleTime: STALE_TIME.liveFeed,
  });
}

/**
 * /ws/camera_health carries CameraDisconnectedEvent and SystemEvent (no
 * discriminator on the wire -- docs/FRONTEND_ARCHITECTURE.md §13). Both
 * signal that a camera's connection/health facts may have changed;
 * neither carries the full new state, so this invalidates rather than
 * merges (§5's rule for messages that can't be safely merged). Safe to
 * call from every consumer of useCameras(): ChannelConnection (src/ws/
 * connection.ts) shares one underlying socket across subscribers, and
 * redundant invalidations are idempotent.
 */
function useCameraHealthChannel() {
  const queryClient = useQueryClient();

  useEffect(() => {
    return subscribeToChannel("camera_health", () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras.list() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.health.cameras() });
    });
  }, [queryClient]);
}
