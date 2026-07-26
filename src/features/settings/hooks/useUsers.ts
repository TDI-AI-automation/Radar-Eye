import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listUsers, updateUserRole } from "@/api/endpoints/users";
import { toUserDomain } from "@/domain/mappers/userMapper";
import { queryKeys } from "@/queries/queryKeys";
import { STALE_TIME } from "@/queries/staleTimes";

/** Settings-exclusive (unlike cameras/threats, no other screen needs the
 * user list), so this stays in features/settings/ rather than queries/,
 * per the boundary already established for cameras (§9/§14). */
export function useUsers() {
  return useQuery({
    queryKey: queryKeys.users.list(),
    queryFn: async () => {
      const dtos = (await listUsers()) ?? [];
      return dtos.map(toUserDomain);
    },
    staleTime: STALE_TIME.reference,
  });
}

/** Admin-gated on the backend; callers must also gate the UI affordance
 * with usePermission("admin") per §12. */
export function useUpdateUserRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: { userId: string; role: string }) => {
      const dto = await updateUserRole(args.userId, { role: args.role });
      return dto ? toUserDomain(dto) : null;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.list() });
    },
  });
}
