import { ApiClient } from "./client";
import { tokenStore } from "../auth/tokenStore";

/**
 * The one place ApiClient is constructed -- the composition root that
 * glues the transport-only, auth-agnostic ApiClient (src/api/client.ts)
 * to auth/tokenStore.ts. client.ts itself has zero import-time dependency
 * on auth/; this file is what wires them together, so client.ts stays
 * independently buildable/testable.
 *
 * VITE_API_BASE_URL is not yet set anywhere in this repo -- defaults to
 * FastAPI/uvicorn's standard local port. Tracked as a Phase 1 config
 * placeholder, not an architectural decision: revisit once a real
 * deployment target/base URL is confirmed.
 */
const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const apiClient = new ApiClient({
  baseUrl,
  getAuthToken: () => tokenStore.getAccessToken(),
  onUnauthorized: () => {
    // A 401 on a request that DID carry a token means that token was
    // rejected -- proactive refresh (AuthProvider, scheduled off the
    // access token's own `exp`) is the normal path; this is the fallback
    // safety net when that hasn't happened in time. No retry-of-original-
    // request queuing is built in Phase 1 -- named seam, not implemented,
    // per the same "seam not full implementation" convention as
    // ApiClientHooks.
    tokenStore.clearTokens();
  },
});
