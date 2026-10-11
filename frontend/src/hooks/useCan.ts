import { useAuthStore } from '@/stores/authStore'
import { hasAction, type ActionKey } from '@/authz/actions'

/** Разрешено ли текущему пользователю действие (по списку из профиля). */
export function useCan(action: ActionKey): boolean {
  const actions = useAuthStore((state) => state.user?.actions)
  return hasAction(actions, action)
}
