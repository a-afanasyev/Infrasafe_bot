import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import i18n from '../i18n'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '@/utils/errorMessage'
import type { AutoManagerConfigData } from '../types/autoManagerConfig'

const AUTO_MANAGER_CONFIG_QUERY_KEY = ['auto-manager-config'] as const

function fetchAutoManagerConfig(): Promise<AutoManagerConfigData> {
  return apiClient.get('/api/v2/auto-manager-config').then((r) => r.data)
}

// Конфиг авто-менеджера — приватный GET (manager|admin), поэтому apiClient
// (не publicClient как у useBoardConfig). Опрос каждые 30с + рефетч на фокус
// окна (а НЕ staleTime как у клона board_config): тумблер "enabled" редактируется
// и ботом, и дашбордом — без активного polling'а состояние карточки могло бы
// разойтись с ботом на неограниченное время (acceptance: ≤30с или на фокус окна).
export function useAutoManagerConfig() {
  return useQuery<AutoManagerConfigData>({
    queryKey: AUTO_MANAGER_CONFIG_QUERY_KEY,
    queryFn: fetchAutoManagerConfig,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  })
}

// Сохранение конфига авто-менеджера — менеджерский/админский PUT. Бэкенд
// требует ПОЛНЫЙ объект (см. schemas.py), но принимает сюда только ЧАСТИЧНЫЙ
// `patch` — не полный объект из кеша вызывающего компонента. Причина: кеш
// (`useAutoManagerConfig`) может быть устаревшим до 30с (опрос) или дольше
// (вкладка без фокуса), а бот пишет тот же конфиг независимо. Если бы
// вызывающий собирал полный PUT-объект из своего возможно устаревшего `data`,
// он мог бы молча затереть более свежее изменение бота (напр. бот включил
// autoManager, дашборд в это же окно сохраняет только окно работы своим
// устаревшим enabled=false → откатывает переключатель). Здесь ПЕРЕД записью
// всегда перезапрашивается АКТУАЛЬНОЕ состояние (queryClient.fetchQuery)
// и `patch` мёржится поверх него, а не поверх кеша компонента — сужает гонку
// с «до 30с» до одного round-trip'а GET. Не устраняет гонку целиком (нет
// optimistic-locking/версии на бэкенде — TOCTOU между fetch и PUT остаётся
// теоретически возможным), но это соразмерный фикс для одного
// админ-тумблера, а не полноценный concurrency-control слой.
export function useUpdateAutoManagerConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (patch: Partial<AutoManagerConfigData>) => {
      const fresh = await queryClient.fetchQuery({
        queryKey: AUTO_MANAGER_CONFIG_QUERY_KEY,
        queryFn: fetchAutoManagerConfig,
      })
      const full: AutoManagerConfigData = { ...fresh, ...patch }
      return apiClient.put('/api/v2/auto-manager-config', full).then((r) => r.data)
    },
    onSuccess: () => {
      toast.success(i18n.t('autoManager.saved'))
      queryClient.invalidateQueries({ queryKey: AUTO_MANAGER_CONFIG_QUERY_KEY })
    },
    onError: (error: unknown) => {
      console.error('Auto-manager config save failed:', error)
      toast.error(i18n.t('autoManager.saveFailed'), {
        description: safeErrorMessage(error, 'An error occurred'),
      })
    },
  })
}
