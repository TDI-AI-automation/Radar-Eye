import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type UserDto = components["schemas"]["UserSchema"];
type UserRoleUpdateRequest = components["schemas"]["UserRoleUpdateRequestSchema"];

/** Admin-gated on the backend (require_role(ROLE_ADMIN)) -- both routes. */
export function listUsers(): Promise<UserDto[] | null> {
  return apiClient.request<UserDto[]>("/users");
}

/** Role changes only -- username/password are not updatable through this
 * route (shared/schemas/user.py::UserRoleUpdateRequestSchema). */
export function updateUserRole(
  userId: string,
  body: UserRoleUpdateRequest,
): Promise<UserDto | null> {
  return apiClient.request<UserDto>(`/users/${userId}`, { method: "PATCH", body });
}
