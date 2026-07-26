/**
 * User domain model. Mirrors shared/schemas/user.py::UserSchema (GET
 * /users, admin-only). Distinct from AuthUser (src/auth/types.ts, the
 * current session's identity) -- see docs/FRONTEND_ARCHITECTURE.md §12,
 * which already resolved this: `role` is exposed as a plain fact, no
 * `hasRole()`/permission-check method. Authorization ("can the current
 * operator edit this row") is composed at the call site from
 * usePermission("admin") + this row's `role`, never fused into the entity.
 */
export class User {
  constructor(
    readonly id: string,
    readonly username: string,
    readonly role: string,
    readonly createdAt: Date,
  ) {}
}
