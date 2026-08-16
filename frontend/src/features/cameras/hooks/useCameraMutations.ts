import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createCamera, deleteCamera, updateCamera } from "@/api/endpoints/cameras";
import { toCameraDomain } from "@/domain/mappers/cameraMapper";
import { queryKeys } from "@/queries/queryKeys";

/** PATCH /cameras/{id} -- admin-gated on the backend; callers must also
 * gate the UI affordance with usePermission("admin") (src/auth/
 * usePermission.ts), per docs/FRONTEND_ARCHITECTURE.md §12. Feature-
 * specific (only the Cameras screen performs this action), unlike
 * useCameras()/useCamerasHealth() in queries/useCameras.ts. */
export function useUpdateCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: { cameraId: string; body: Parameters<typeof updateCamera>[1] }) => {
      const dto = await updateCamera(args.cameraId, args.body);
      return dto ? toCameraDomain(dto) : null;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras.list() });
    },
  });
}

/** POST /cameras -- admin-only. Registers a new camera; the operator
 * supplies brand + IP + credentials, never a raw RTSP URL. */
export function useCreateCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Parameters<typeof createCamera>[0]) => {
      const dto = await createCamera(body);
      return dto ? toCameraDomain(dto) : null;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras.list() });
    },
  });
}

/** DELETE /cameras/{id} -- admin-only. 409s (AppError) if the camera has
 * existing incidents/review items/recordings -- that history is never
 * cascade-deleted; callers should surface that as "resolve or export that
 * history first" rather than retrying. */
export function useDeleteCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (cameraId: string) => {
      await deleteCamera(cameraId);
      return cameraId;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras.list() });
    },
  });
}
