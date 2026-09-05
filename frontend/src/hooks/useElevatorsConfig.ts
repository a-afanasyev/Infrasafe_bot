import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '../utils/errorMessage'
import { ELEVATORS_BASE, elevatorKeys } from './useElevators'
import type { ElevatorsConfigIn, ElevatorsConfigOut } from '../types/elevators'

/**
 * Конфиг модуля «Лифты» (GET/PUT /config, только manager): пороги простоя,
 * уведомления жителям, стадии напоминаний персоналу. PUT частичный — бэкенд
 * мёржит секции, поэтому форма шлёт только то, что показывает.
 */

const CONFIG_KEY = ['elevators-config'] as const

export function useElevatorsConfig() {
  return useQuery<ElevatorsConfigOut>({
    queryKey: CONFIG_KEY,
    queryFn: () => apiClient.get(`${ELEVATORS_BASE}/config`).then((r) => r.data),
    staleTime: 15_000,
  })
}

export function useSaveElevatorsConfig() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ElevatorsConfigIn) =>
      apiClient.put(`${ELEVATORS_BASE}/config`, payload).then((r) => r.data as ElevatorsConfigOut),
    onSuccess: (data) => {
      queryClient.setQueryData(CONFIG_KEY, data)
      // Пороги простоя входят в сводку реестра (downtime_over_threshold).
      queryClient.invalidateQueries({ queryKey: elevatorKeys.summary })
      toast.success(t('elevators.toast.configSaved'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}
