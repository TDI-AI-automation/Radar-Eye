import type { Evidence, EvidenceType } from "@/domain/models/Evidence";

export interface EvidenceRowViewModel {
  id: string;
  evidenceType: EvidenceType;
  incidentId: string;
  cameraId: string;
  cameraName: string;
  capturedAt: Date;
  downloadUrl: string;
  fileName: string;
}

export function buildEvidenceRowViewModel(
  evidence: Evidence,
  cameraName: string | undefined,
): EvidenceRowViewModel {
  // Neither EvidenceItemSchema nor the download response exposes the
  // real file extension/content-type -- a best-effort guess for the
  // save-as filename only, never used to decide how to render a preview
  // (see useEvidencePreview, which renders by evidenceType, not this).
  const extension = evidence.isRecording() ? "mp4" : "jpg";
  return {
    id: evidence.id,
    evidenceType: evidence.evidenceType,
    incidentId: evidence.incidentId,
    cameraId: evidence.cameraId,
    cameraName: cameraName ?? evidence.cameraId,
    capturedAt: evidence.capturedAt,
    downloadUrl: evidence.downloadUrl,
    fileName: `${evidence.evidenceType}-${evidence.id}.${extension}`,
  };
}

export interface EvidenceFilter {
  type: EvidenceType | "ALL";
  cameraId: string | "ALL";
}

export function applyEvidenceFilter(
  rows: EvidenceRowViewModel[],
  filter: EvidenceFilter,
): EvidenceRowViewModel[] {
  return rows.filter(
    (r) =>
      (filter.type === "ALL" || r.evidenceType === filter.type) &&
      (filter.cameraId === "ALL" || r.cameraId === filter.cameraId),
  );
}
