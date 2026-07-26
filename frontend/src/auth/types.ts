/** Mirrors apps/api/app/models/user.py's proposed-not-ratified taxonomy
 * (docs/OPEN_QUESTIONS.md Q-009). Kept in this one place, same rationale
 * as the backend's own comment: a future taxonomy change touches one file. */
export const ROLE_RANK: Record<string, number> = { viewer: 0, operator: 1, admin: 2 };

/** apps/api/app/security/auth.py::create_token_pair's payload shape --
 * `sub` (user id), `role`, `type` ("access" | "refresh"), `exp` (unix
 * seconds). Only the fields the frontend actually reads are declared. */
export interface AccessTokenPayload {
  sub: string;
  role: string;
  type: "access" | "refresh";
  exp: number;
}

/** No GET /auth/me exists (confirmed against the generated OpenAPI schema
 * -- see docs/FRONTEND_ARCHITECTURE.md §11 finding on Auth). `username` is
 * not present in the JWT payload either, so it is carried from the login
 * form input the caller already typed correctly (login only succeeds if
 * it matched), not fetched separately. */
export interface AuthUser {
  userId: string;
  username: string;
  role: string;
}
