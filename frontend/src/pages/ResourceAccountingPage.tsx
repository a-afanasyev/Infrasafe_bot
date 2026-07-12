import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ExternalLink } from 'lucide-react'
import { apiClient } from '@/api/client'

// postMessage-протокол обмена с встраиваемым сервисом ресурсов.
const MSG = {
  ready: 'resource-accounting:ready',
  ticket: 'resource-accounting:ticket',
  authOk: 'resource-accounting:auth-ok',
  height: 'resource-accounting:height',
} as const

const DEFAULT_HEIGHT = 800
const MIN_HEIGHT = 200
const MAX_HEIGHT = 20000

interface IncomingMessage {
  type?: string
  nonce?: string
  height?: number
}

/**
 * Встраиваемый раздел «Учёт ресурсов УК» (внешний сервис).
 *
 * SSO без повторного логина: сервис (в iframe ИЛИ в отдельной вкладке через
 * window.opener) шлёт `ready` → наш backend выпускает одноразовый ticket → мы
 * отвечаем `event.source` тем же ticket'ом с уникальным nonce. Ticket/nonce
 * НИКОГДА не кладём в URL/сторедж. Отвечаем строго на origin ресурсов.
 *
 * URL сервиса — из `VITE_RESOURCES_URL`; пусто → раздел «не настроен» (бренд-гейт:
 * infrasafe включён, profk тёмный, пока партнёр не поддержит его origin).
 */
export default function ResourceAccountingPage() {
  const { t } = useTranslation()
  const resourcesUrl = (import.meta.env.VITE_RESOURCES_URL as string | undefined) ?? ''
  const origin = resourcesUrl ? new URL(resourcesUrl).origin : ''
  const [height, setHeight] = useState(DEFAULT_HEIGHT)
  // Выпущенные, но ещё не подтверждённые nonce — для валидации auth-ok.
  const pendingNonces = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!origin) return

    async function handleMessage(event: MessageEvent) {
      // Строгая проверка источника: реагируем только на сообщения от ресурсов.
      if (event.origin !== origin) return
      const data = event.data as IncomingMessage | null
      if (!data || typeof data.type !== 'string') return

      if (data.type === MSG.ready) {
        const source = event.source as Window | null
        if (!source) return
        const nonce = crypto.randomUUID()
        pendingNonces.current.add(nonce)
        try {
          const { data: res } = await apiClient.post('/api/v2/resource-accounting/ticket')
          // Отвечаем ИСТОЧНИКУ (iframe.contentWindow или окно новой вкладки),
          // targetOrigin строго = origin ресурсов, никогда '*'.
          source.postMessage({ type: MSG.ticket, ticket: res.ticket, nonce }, origin)
        } catch {
          // Тихо: iframe покажет свою ошибку/повторит ready. Ticket не выпущен.
          pendingNonces.current.delete(nonce)
        }
        return
      }

      if (data.type === MSG.authOk) {
        if (data.nonce) pendingNonces.current.delete(data.nonce)
        return
      }

      if (data.type === MSG.height) {
        const h = Number(data.height)
        if (Number.isFinite(h) && h > 0) {
          setHeight(Math.min(Math.max(h, MIN_HEIGHT), MAX_HEIGHT))
        }
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [origin])

  if (!resourcesUrl) {
    return (
      <div className="p-6">
        <p className="text-sm text-text-secondary">{t('resourceAccounting.notConfigured')}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text-primary">{t('resourceAccounting.title')}</h1>
        <button
          type="button"
          // Открываем БЕЗ noopener: сервису нужен window.opener для SSO новой
          // вкладки; безопасность держим строгим origin-чеком в обработчике.
          onClick={() => window.open(resourcesUrl, '_blank')}
          className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
        >
          <ExternalLink size={15} />
          {t('resourceAccounting.openInNewTab')}
        </button>
      </div>
      <iframe
        src={resourcesUrl}
        title={t('resourceAccounting.title')}
        className="w-full rounded-xl border border-border bg-white"
        style={{ height }}
      />
    </div>
  )
}
