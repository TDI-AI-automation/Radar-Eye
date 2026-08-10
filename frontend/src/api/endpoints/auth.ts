import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type LoginRequest = components["schemas"]["LoginRequestSchema"];
type RefreshRequest = components["schemas"]["RefreshRequestSchema"];
type TokenResponse = components["schemas"]["TokenResponseSchema"];

/** POST /auth/login -- no GET /auth/me exists (verified against the
 * generated schema), so this is the only source of a token pair. */
export function login(credentials: LoginRequest): Promise<TokenResponse | null> {
  return apiClient.request<TokenResponse>("/auth/login", {
    method: "POST",
    body: credentials,
  });
}

/** POST /auth/refresh -- exchanges a refresh token for a new pair
 * (rotation: the old refresh token is not reusable once exchanged). */
export function refresh(refreshToken: string): Promise<TokenResponse | null> {
  const body: RefreshRequest = { refresh_token: refreshToken };
  return apiClient.request<TokenResponse>("/auth/refresh", {
    method: "POST",
    body,
  });
}
