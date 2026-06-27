import { useAuthStore } from '@/stores/authStore'

export function useHasRole(role: string): boolean {
  const user = useAuthStore(state => state.user)
  return user?.roles?.includes(role) ?? false
}

/** True, если у пользователя есть хотя бы одна из ролей (для гейтинга действий). */
export function useHasAnyRole(roles: readonly string[]): boolean {
  const user = useAuthStore(state => state.user)
  return user?.roles?.some(r => roles.includes(r)) ?? false
}
