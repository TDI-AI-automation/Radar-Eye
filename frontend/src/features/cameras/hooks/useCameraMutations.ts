import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateCamera } from "@/api/endpoints/cameras";
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
