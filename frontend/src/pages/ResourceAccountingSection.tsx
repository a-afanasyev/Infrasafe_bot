import { useEffect, useState } from 'react'
import { NavLink } from 'react-router'
import { useTranslation } from 'react-i18next'
import { apiClient } from '@/api/client'
import { cn } from '@/lib/utils'
import LoadingSpinner from '@/components/shared/LoadingSpinner'
import {
  ResourceAccountingProvider,
  ResourceAccountingRoutes,
  configureResourceApi,
  ensureResourceSession,
  useResourceAuth,
  canEnterReadings,
  isAdmin,
  isMeterEntry,
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

// Конфигурация api модуля — на МОНТИРОВАНИИ раздела, не на импорте модуля
// (AUD6-P2-19): оба хоста одного SPA (этот раздел и TWA-экран контролёра)
// попадают в один бандл, и module-level вызов оставлял конфиг «кто
// импортировался последним» — с разными onUnauthorized (mint по UK-JWT против
// mint по initData). Вызов ДО ensureSession обязателен: тот дергает
// /v1/auth/me ещё до монтирования Provider — без baseUrl ушёл бы не туда.
const configureApi = () =>
  configureResourceApi({
    baseUrl: RESOURCE_BASE_URL,
    onUnauthorized: () => {
      void ensureSession()
    },
  })

/**
 * Под-навигация раздела (перенесена из standalone-обёртки ресурса, которую по
 * INTEGRATION.md не копировали). Ссылки абсолютные (basePath + суффикс), чтобы
 * не зависеть от текущего вложенного пути. Роль-гейтинг: журнал — только админу,
 * контролёр (meter_entry) видит единственную страницу → навигация скрыта.
 */
function ResourceSubNav() {
  const { role } = useResourceAuth()
  const { t } = useTranslation()
  if (isMeterEntry(role)) return null

  const items = [
    { to: '', label: t('resourceAccounting.nav.summary'), end: true },
    {
      to: '/worksheet',
      label: canEnterReadings(role)
        ? t('resourceAccounting.nav.entry')
        : t('resourceAccounting.nav.worksheet'),
    },
    { to: '/meters', label: t('resourceAccounting.nav.meters') },
    { to: '/objects', label: t('resourceAccounting.nav.objects') },
    { to: '/exports', label: t('resourceAccounting.nav.exports') },
    { to: '/providers', label: t('resourceAccounting.nav.providers') },
    ...(isAdmin(role) ? [{ to: '/audit', label: t('resourceAccounting.nav.audit') }] : []),
  ]

  return (
    <nav className="mb-3 flex gap-1 overflow-x-auto border-b border-border-default px-4 pt-2">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={`${RESOURCE_BASE_PATH}${item.to}`}
          end={item.end}
          className={({ isActive }) =>
            cn(
              'whitespace-nowrap border-b-2 px-3 py-2 text-sm no-underline transition-colors',
              isActive
                ? 'border-accent font-semibold text-accent'
                : 'border-transparent text-text-secondary hover:text-text-primary',
            )
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}

export default function ResourceAccountingSection() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    configureApi()
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
      <ResourceSubNav />
      <ResourceAccountingRoutes />
    </ResourceAccountingProvider>
  )
}
