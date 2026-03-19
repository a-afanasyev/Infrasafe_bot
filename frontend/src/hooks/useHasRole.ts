import { useAuthStore } from '@/stores/authStore'

export function useHasRole(role: string): boolean {
  const user = useAuthStore(state => state.user)
  return user?.roles?.includes(role) ?? false
}
