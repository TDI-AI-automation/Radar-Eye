import { login as loginRequest, refresh as refreshRequest } from "../api/endpoints/auth";
import { tokenStore } from "./tokenStore";
import { decodeJwtPayload } from "./jwt";
import type { AccessTokenPayload, AuthUser } from "./types";

export class InvalidCredentialsError extends Error {
  constructor() {
    super("Invalid username or password");
    this.name = "InvalidCredentialsError";
  }
}

function toAuthUser(accessToken: string, username: string): AuthUser | null {
  const payload = decodeJwtPayload<AccessTokenPayload>(accessToken);
  if (!payload) return null;
  return { userId: payload.sub, username, role: payload.role };
}

export async function loginWithCredentials(username: string, password: string): Promise<AuthUser> {
  let tokenResponse: Awaited<ReturnType<typeof loginRequest>>;
  try {
    tokenResponse = await loginRequest({ username, password });
  } catch {
    throw new InvalidCredentialsError();
  }
  if (!tokenResponse) throw new InvalidCredentialsError();

  tokenStore.setTokens({
    accessToken: tokenResponse.access_token,
    refreshToken: tokenResponse.refresh_token,
    username,
  });

  const user = toAuthUser(tokenResponse.access_token, username);
  if (!user) throw new InvalidCredentialsError();
  return user;
}

export function logout(): void {
  tokenStore.clearTokens();
}

/** Proactive refresh -- AuthProvider schedules this off the access
 * token's own `exp`. Falls back to force-logout (clearing tokens) on any
 * failure; the caller's route guard picks that up via tokenStore's
 * subscribe() and redirects to /login. */
export async function refreshSession(): Promise<AuthUser | null> {
  const refreshToken = tokenStore.getRefreshToken();
  const username = tokenStore.getUsername();
  if (!refreshToken || !username) return null;

  let tokenResponse: Awaited<ReturnType<typeof refreshRequest>>;
  try {
    tokenResponse = await refreshRequest(refreshToken);
  } catch {
    tokenStore.clearTokens();
    return null;
  }
  if (!tokenResponse) {
    tokenStore.clearTokens();
    return null;
  }

  tokenStore.setTokens({
    accessToken: tokenResponse.access_token,
    refreshToken: tokenResponse.refresh_token,
    username,
  });
  return toAuthUser(tokenResponse.access_token, username);
}

/** Reconstructs the current user from whatever tokenStore already has
 * (e.g. on page load, after localStorage hydration) without a network
 * call. Returns null if there's no token or it has expired. */
export function currentUserFromStore(): AuthUser | null {
  const accessToken = tokenStore.getAccessToken();
  const username = tokenStore.getUsername();
  if (!accessToken || !username) return null;
  const payload = decodeJwtPayload<AccessTokenPayload>(accessToken);
  if (!payload) return null;
  if (payload.exp * 1000 <= Date.now()) return null;
  return { userId: payload.sub, username, role: payload.role };
}

/** Milliseconds until the current access token expires, or null if there
 * is none. AuthProvider uses this to schedule proactive refresh. */
export function msUntilAccessTokenExpiry(): number | null {
  const accessToken = tokenStore.getAccessToken();
  if (!accessToken) return null;
  const payload = decodeJwtPayload<AccessTokenPayload>(accessToken);
  if (!payload) return null;
  return payload.exp * 1000 - Date.now();
}
