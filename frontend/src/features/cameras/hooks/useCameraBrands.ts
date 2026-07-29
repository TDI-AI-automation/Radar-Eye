import { useQuery } from "@tanstack/react-query";
import { listCameraBrands } from "@/api/endpoints/cameras";
import type { CameraBrandInfoDto } from "@/api/endpoints/cameras";
import { queryKeys } from "@/queries/queryKeys";
import { STALE_TIME } from "@/queries/staleTimes";

/** GET /cameras/brands -- feature-specific (only the Add/Edit Camera form
 * needs brand-driven port/stream defaults), unlike useCameras() in
 * queries/useCameras.ts which more than one feature consumes. */
export function useCameraBrands() {
  return useQuery({
    queryKey: queryKeys.cameras.brands(),
    queryFn: async (): Promise<CameraBrandInfoDto[]> => (await listCameraBrands()) ?? [],
    staleTime: STALE_TIME.reference,
  });
}
