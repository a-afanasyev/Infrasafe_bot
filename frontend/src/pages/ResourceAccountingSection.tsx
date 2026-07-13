import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { apiClient } from '@/api/client'
import LoadingSpinner from '@/components/shared/LoadingSpinner'
import {
  ResourceAccountingProvider,
  ResourceAccountingRoutes,
  configureResourceApi,
  ensureResourceSession,
} from '@/features/resource-accounting'

/**
 * Host-обёртка нативного раздела «Учёт ресурсов УК» (портируемый модуль
 * feature/resource-accounting). Backend ресурса не в UK — доступ same-origin
 * через edge (`/uk/api/resource/*` → resource-api). Тихий вход: наш минтинг
 * `POST /api/v2/resource-accounting/ticket` → exchange на стороне модуля.
 *
 * Раздел монтируется под build-флагом VITE_RESOURCES_ENABLED (App.tsx/меню) —
 * пока партнёрский edge не проксирует resource-api, флаг OFF (DARK).
 */

const RESOURCE_BASE_URL = '/uk/api/resource'
const RESOURCE_BASE_PATH = '/dashboard/resource-accounting'

// mint — наш существующий backend-эндпоинт (роль-маппинг УК→ресурс на бэке).
const mint = async (): Promise<string> =>
  (await apiClient.post('/api/v2/resource-accounting/ticket')).data.ticket

// Single-flight: модульный api-клиент дёргает onUnauthorized на КАЖДЫЙ 401, а
// на старте раздела их несколько (ensureSession's own /v1/auth/me + self-bootstrap
// ResourceAuthProvider + запросы страниц). Без гарда каждый 401 запускал новый
// mint→exchange — рекурсивный шторм из лишних одноразовых тикетов. Гард склеивает
// все параллельные вызовы в ОДИН mint→exchange; после сессии — сбрасывается.
let inflightSession: Promise<void> | null = null
const ensureSession = (): Promise<void> => {
  if (inflightSession) return inflightSession
  inflightSession = ensureResourceSession(mint).finally(() => {
    inflightSession = null
  })
  return inflightSession
}

// Конфигурируем api модуля ДО первого запроса (ensureSession дергает
// /v1/auth/me ещё до монтирования Provider — без baseUrl он ушёл бы не туда).
configureResourceApi({
  baseUrl: RESOURCE_BASE_URL,
  onUnauthorized: () => {
    void ensureSession()
  },
})

export default function ResourceAccountingSection() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    ensureSession()
      .then(() => !cancelled && setStatus('ready'))
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
    }
  }, [])

  if (status === 'loading') return <LoadingSpinner />
  if (status === 'error') {
    return (
      <div className="p-6 text-sm text-text-secondary">
        {t('resourceAccounting.unavailable')}
      </div>
    )
  }

  return (
    <ResourceAccountingProvider
      config={{
        baseUrl: RESOURCE_BASE_URL,
        basePath: RESOURCE_BASE_PATH,
        onUnauthorized: () => {
          void ensureSession()
        },
      }}
    >
      <ResourceAccountingRoutes />
    </ResourceAccountingProvider>
  )
}
