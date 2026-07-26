import { useAuth } from "./AuthProvider";
import { ROLE_RANK } from "./types";

/**
 * Mirrors apps/api/app/security/dependencies.py::require_role's fail-
 * closed semantics exactly: an unrecognized role ranks below every known
 * role, never above. This is a UI-only gate (hide/disable controls); the
 * backend's own require_role is the actual enforcement -- this hook must
 * never be the only thing standing between an operator and a mutation.
 *
 * Whether role-check logic belongs here or on a `User` domain model
 * (`hasRole()`) is an open design question (docs/FRONTEND_ARCHITECTURE.md
 * §11, Finding 4) deferred to Phase 2 -- not a Phase 1 blocker.
 */
export function usePermission(minimumRole: string): boolean {
  const { user } = useAuth();
  if (!user) return false;
  const userRank = ROLE_RANK[user.role] ?? -1;
  const requiredRank = ROLE_RANK[minimumRole] ?? 99;
  return userRank >= requiredRank;
}
