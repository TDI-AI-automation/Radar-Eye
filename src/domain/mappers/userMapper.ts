import { User } from "../models/User";
import type { components } from "../../api/generated/schema";

type UserDto = components["schemas"]["UserSchema"];

export function toUserDomain(dto: UserDto): User {
  return new User(dto.user_id, dto.username, dto.role, new Date(dto.created_at));
}
