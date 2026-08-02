import { useQuery, useMutation } from "@tanstack/react-query";
import { listEvidence, downloadEvidence } from "@/api/endpoints/evidence";
import { toEvidenceDomain } from "@/domain/mappers/evidenceMapper";
import { queryKeys } from "@/queries/queryKeys";
import { STALE_TIME } from "@/queries/staleTimes";

/** No server-side filtering exists on GET /evidence (always the full
 * list, tracked in the Phase 3 backend-gaps list) -- filtering by
 * incident/camera/type happens client-side in the view model layer. */
export function useEvidenceList() {
  return useQuery({
    queryKey: queryKeys.evidence.list(),
    queryFn: async () => {
      const dtos = (await listEvidence()) ?? [];
      return dtos.map(toEvidenceDomain);
    },
    staleTime: STALE_TIME.reference,
  });
}

/** Triggers a browser download of the file -- read-only, no chain-of-
 * custody-relevant mutation happens client-side; the backend never
 * exposes an edit/delete path for evidence at all. */
export function useDownloadEvidence() {
  return useMutation({
    mutationFn: async (args: { downloadUrl: string; fileName: string }) => {
      const blob = await downloadEvidence(args.downloadUrl);
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = args.fileName;
      link.click();
      URL.revokeObjectURL(objectUrl);
    },
  });
}
