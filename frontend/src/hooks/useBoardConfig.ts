import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import i18n from '../i18n'
import { apiClient } from '../api/client'
import { publicClient } from '../api/publicClient'
import { safeErrorMessage } from '@/utils/errorMessage'
import { toEditableBoardConfig } from '../types/boardConfig'
import type { BoardConfigData, BoardConfigResponse } from '../types/boardConfig'

// Конфиг витрины — публичный GET, без аутентификации.
export function useBoardConfig() {
  return useQuery<BoardConfigResponse>({
    queryKey: ['board-config'],
    queryFn: () => publicClient.get('/api/v2/public/board-config').then((r) => r.data),
    staleTime: 60_000,
  })
}

// Сохранение конфига витрины — менеджерский PUT.
export function useUpdateBoardConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    // Страховка на wire: PUT-схема бэка строгая (extra="forbid"), а draft
    // мог быть посеян из ответа с display_tz — снимаем поле перед отправкой.
    mutationFn: (config: BoardConfigData) =>
      apiClient.put('/api/v2/board-config', toEditableBoardConfig(config)).then((r) => r.data),
    onSuccess: () => {
      toast.success(i18n.t('boardEditor.saved'))
      queryClient.invalidateQueries({ queryKey: ['board-config'] })
    },
    onError: (error: unknown) => {
      console.error('Board config save failed:', error)
      toast.error(i18n.t('boardEditor.saveFailed'), {
        description: safeErrorMessage(error, 'An error occurred'),
      })
    },
  })
}
