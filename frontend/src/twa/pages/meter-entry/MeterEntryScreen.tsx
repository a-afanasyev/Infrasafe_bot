import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ResourceAccountingProvider,
  ResourceAccountingRoutes,
  configureResourceApi,
  ensureResourceSession,
} from '@/features/resource-accounting'
import { getTWAInitData } from '@/utils/isTWA'
import { twaClient } from '../../twaClient'
import LoadingSpinner from '@/components/shared/LoadingSpinner'

/**
 * TWA-экран «Ввод показаний» для полевого контролёра (роль-капабилити
 * resource_meter_entry). Авторизация — напрямую в ресурс-сервис: initData →
 * наш `POST /api/v2/resource-accounting/twa-ticket` (mint по initData, без
 * UK-JWT) → exchange на стороне модуля в httpOnly-сессию. Backend ресурса не в
 * UK — доступ same-origin через edge `/uk/api/resource/*`.
 *
 * Модуль сам рендерит slim-режим контролёра (роль сессии = resource_meter_entry
 * → единственная страница ввода; под-навигация скрыта) — доп. гейтинга не нужно.
 */

const RESOURCE_BASE_URL = '/uk/api/resource'
const RESOURCE_BASE_PATH = '/twa/meter-entry'

// mint по initData через twaClient (same-origin, /uk/api/...). Ticket/nonce в
// теле, не в URL — как того требует контракт (наш сервис без bot-token).
const mint = async (): Promise<string> =>
  (await twaClient.post('/api/v2/resource-accounting/twa-ticket', {
    init_data: getTWAInitData(),
  })).data.ticket

// Single-flight: модульный api-клиент дёргает onUnauthorized на КАЖДЫЙ 401, а на
// старте их несколько (ensureSession's /v1/auth/me + self-bootstrap + запросы
// страницы). Гард склеивает параллельные вызовы в ОДИН mint→exchange (фикс #242).
let inflightSession: Promise<void> | null = null
const ensureSession = (): Promise<void> => {
  if (inflightSession) return inflightSession
  inflightSession = ensureResourceSession(mint).finally(() => {
    inflightSession = null
  })
  return inflightSession
}

// Конфигурируем api модуля ДО первого запроса.
configureResourceApi({
  baseUrl: RESOURCE_BASE_URL,
  onUnauthorized: () => {
    void ensureSession()
  },
})

export default function MeterEntryScreen() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  const hasInitData = !!getTWAInitData()

  useEffect(() => {
    if (!hasInitData) return
    let cancelled = false
    ensureSession()
      .then(() => !cancelled && setStatus('ready'))
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
    }
  }, [hasInitData])

  if (!hasInitData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-6 text-center">
        <p className="text-gray-500 text-[14px]">{t('resourceAccounting.openViaBot')}</p>
      </div>
    )
  }

  if (status === 'loading') return <LoadingSpinner />
  if (status === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-6 text-center">
        <p className="text-gray-500 text-[14px]">{t('resourceAccounting.unavailable')}</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
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
    </div>
  )
}
