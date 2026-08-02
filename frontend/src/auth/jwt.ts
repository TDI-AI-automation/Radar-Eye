/**
 * Client-side JWT payload decode only -- never signature verification.
 * The backend (apps/api/app/security/auth.py::decode_token) is the sole
 * authority on whether a token is valid; this just reads claims already
 * proven valid by a prior successful request (login/refresh response) so
 * the UI can render role/expiry without a round trip.
 */
export function decodeJwtPayload<T>(token: string): T | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "="));
    return JSON.parse(json) as T;
  } catch {
    return null;
  }
}
