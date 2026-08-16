import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { useAuthStore } from '@/stores/authStore'
import {
  invalidateSeenCache,
  isUnread as isUnreadPure,
  markSeen as markSeenPure,
  readSeen,
  storageKeyFor,
  subscribeSeen,
  type SeenMap,
} from '../components/kanban/seenRequests'

const EMPTY: SeenMap = {}

/** Отметки «прочитано» текущего менеджера, реактивно.
 *
 * Хранилище — localStorage (решение владельца), поэтому подписка идёт двумя
 * путями: локальные подписчики модуля для своей вкладки (событие `storage` в
 * ней не срабатывает) и слушатель `storage` для соседних.
 */
export function useSeenRequests() {
  const userId = useAuthStore(state => state.user?.id ?? null)

  const seen = useSyncExternalStore(
    subscribeSeen,
    // Ссылка стабильна, пока не было записи — иначе useSyncExternalStore
    // уходит в бесконечный ре-рендер.
    () => (userId === null ? EMPTY : readSeen(userId)),
    () => EMPTY,
  )

  useEffect(() => {
    if (userId === null) return
    const key = storageKeyFor(userId)
    const onStorage = (e: StorageEvent) => {
      // key === null — localStorage.clear() в соседней вкладке.
      if (e.key === null || e.key === key) invalidateSeenCache()
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [userId])

  const markSeen = useCallback(
    (requestNumber: string, version: string | null) => {
      if (userId === null) return
      markSeenPure(userId, requestNumber, version)
    },
    [userId],
  )

  const isUnread = useCallback(
    (requestNumber: string, updatedAt: string | null, createdAt: string | null) =>
      isUnreadPure(seen, requestNumber, updatedAt, createdAt),
    [seen],
  )

  return { seen, isUnread, markSeen }
}
