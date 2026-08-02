/**
 * Evidence domain model. Mirrors shared/schemas/evidence.py::
 * EvidenceItemSchema (GET /evidence, GET /evidence/{id}) -- the unified
 * snapshot-or-recording view. No WS channel exists for evidence (by
 * design, not a gap: an on-demand, infrequent workflow, docs/
 * FRONTEND_ARCHITECTURE.md §11). No mutation of any kind exists on the
 * backend for evidence -- apps/api/app/routers/evidence.py is entirely
 * GET routes -- reinforcing CLAUDE.md's Evidence Preservation principle
 * and the Phase 3 instruction to treat evidence as immutable: this
 * domain model has no method that could imply otherwise.
 */
export type EvidenceType = "snapshot" | "recording";

export class Evidence {
  constructor(
    readonly id: string,
    readonly evidenceType: EvidenceType,
    readonly incidentId: string,
    readonly cameraId: string,
    readonly capturedAt: Date,
    readonly downloadUrl: string,
  ) {}

  isRecording(): boolean {
    return this.evidenceType === "recording";
  }

  isSnapshot(): boolean {
    return this.evidenceType === "snapshot";
  }
}
