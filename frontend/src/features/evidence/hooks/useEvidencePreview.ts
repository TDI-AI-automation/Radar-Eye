import { useEffect, useState } from "react";
import { downloadEvidence } from "@/api/endpoints/evidence";

interface PreviewState {
  status: "idle" | "loading" | "ready" | "error";
  objectUrl: string | null;
}

/**
 * Fetches an evidence file's bytes (auth requires a Bearer header, so a
 * plain <img src="/snapshots/{id}/download"> can't work -- the browser
 * won't attach it) and exposes a local object URL for inline preview.
 * Deliberately not a queries/ hook: an object URL is an ephemeral browser
 * resource with a manual-revoke lifecycle, not cacheable/shareable server
 * state (§7 is about the latter). Revokes the previous URL whenever
 * `downloadUrl` changes or the component unmounts -- never leaks blob
 * URLs across selections.
 */
export function useEvidencePreview(downloadUrl: string | null): PreviewState {
  const [state, setState] = useState<PreviewState>({ status: "idle", objectUrl: null });

  useEffect(() => {
    if (!downloadUrl) {
      setState({ status: "idle", objectUrl: null });
      return;
    }

    let cancelled = false;
    let createdUrl: string | null = null;
    setState({ status: "loading", objectUrl: null });

    void downloadEvidence(downloadUrl)
      .then((blob) => {
        if (cancelled) return;
        createdUrl = URL.createObjectURL(blob);
        setState({ status: "ready", objectUrl: createdUrl });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error", objectUrl: null });
      });

    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [downloadUrl]);

  return state;
}
