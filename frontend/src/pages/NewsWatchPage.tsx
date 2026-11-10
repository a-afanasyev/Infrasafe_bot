import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  NEWS_PAGE_SIZE, useNewsDecision, useNewsItems, useNewsWatchConfig, useSaveNewsWatchConfig,
} from '../hooks/useNewsWatch'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import NewsWatchConfigForm from '../components/newsWatch/NewsWatchConfigForm'
import type { NewsItem, NewsItemStatus } from '../types/newsWatch'
import { cn } from '@/lib/utils'

/**
 * «Отключения» (/dashboard/news-watch, manager): очередь новостей из внешних
 * каналов (pending → опубликовать/отклонить; published → статус рассылки,
 * повтор при сбое) и настройки мониторинга. DARK за VITE_NEWS_WATCH_ENABLED.
 */
const TABS: NewsItemStatus[] = ['pending', 'published', 'rejected', 'ignored']
// = broadcast.MAX_ATTEMPTS: после стольких попыток воркер сам не повторяет.
const MAX_BROADCAST_ATTEMPTS = 5

/** «Доставлено N · заблокировали бота N · нет чата с ботом N · не доставлено N». */
function DeliveryLine({ item }: { item: NewsItem }) {
  const { t, i18n } = useTranslation()
  const d = (item.broadcast_details ?? {}) as Record<string, unknown>
  const num = (key: string) => (typeof d[key] === 'number' ? (d[key] as number) : 0)
  const len = (key: string) => (Array.isArray(d[key]) ? (d[key] as unknown[]).length : 0)
  if (!item.broadcast_details) return null
  // Записи до A11-CODE-02 списка retry не знают — показываем их errors.
  const undelivered = 'retry' in d ? len('retry') + len('groups_failed') : num('errors')
  const next = item.broadcast_next_at ? new Date(item.broadcast_next_at) : null
  const autoRetry = item.broadcast_status === 'failed' && next != null
    && item.broadcast_attempts < MAX_BROADCAST_ATTEMPTS
  return (
    <span className="text-[11px] text-text-muted">
      {t('newsWatch.delivery', {
        sent: num('sent'), blocked: num('blocked'), noChat: num('no_chat'), undelivered,
      })}
      {autoRetry && ` · ${t('newsWatch.nextAttempt', {
        time: next.toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' }),
      })}`}
    </span>
  )
}

function ItemCard({ item, onDecide, pending }: {
  item: NewsItem
  onDecide: (decision: 'publish' | 'reject' | 'retry-broadcast') => void
  pending: boolean
}) {
  const { t } = useTranslation()
  const [showRaw, setShowRaw] = useState(false)
  const kind = item.kind ?? 'other'
  return (
    <div className="bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3 text-[11px] text-text-muted">
        <span className="font-semibold text-text-primary">{t(`newsWatch.kind.${kind}`)}</span>
        <span>
          {item.chat_title ?? item.source_chat_id}
          {item.confidence != null && ` · ${t('newsWatch.confidence')} ${Math.round(item.confidence * 100)}%`}
          {item.relevant == null && item.status === 'pending' && ` · ${t('newsWatch.noVerdict')}`}
        </span>
      </div>
      <div className="text-[13px] text-text-primary">{item.summary_ru ?? item.raw_text}</div>
      {item.summary_uz && <div className="text-[12px] text-text-muted">{item.summary_uz}</div>}
      <button type="button" className="text-[11px] text-text-muted underline text-left"
        onClick={() => setShowRaw((v) => !v)}>
        {showRaw ? t('newsWatch.hideRaw') : t('newsWatch.showRaw')}
      </button>
      {showRaw && <pre className="whitespace-pre-wrap text-[11px] text-text-muted">{item.raw_text}</pre>}
      <div className="flex items-center gap-2 flex-wrap">
        {item.status === 'pending' && (
          <>
            <Button size="sm" disabled={pending} onClick={() => onDecide('publish')}>{t('newsWatch.publish')}</Button>
            <Button size="sm" variant="outline" disabled={pending} onClick={() => onDecide('reject')}>{t('newsWatch.reject')}</Button>
          </>
        )}
        {item.status === 'published' && (
          <span className="text-[11px] text-text-muted">
            {t('newsWatch.broadcast')}: {t(`newsWatch.broadcastStatus.${item.broadcast_status}`)}
            {item.broadcast_status === 'failed'
              && (item.broadcast_attempts >= MAX_BROADCAST_ATTEMPTS || !item.broadcast_next_at) && (
              <Button size="sm" variant="outline" className="ml-2" disabled={pending}
                onClick={() => onDecide('retry-broadcast')}>{t('newsWatch.retryBroadcast')}</Button>
            )}
          </span>
        )}
        {item.status === 'published' && <DeliveryLine item={item} />}
      </div>
    </div>
  )
}

export default function NewsWatchPage() {
  const { t } = useTranslation()
  usePageTitle(t('newsWatch.title'))
  const [tab, setTab] = useState<NewsItemStatus>('pending')
  const [offset, setOffset] = useState(0)
  const items = useNewsItems(tab, offset)
  const total = items.data?.total ?? 0
  const config = useNewsWatchConfig()
  const save = useSaveNewsWatchConfig()
  const decide = useNewsDecision()

  return (
    <div className="p-6 flex flex-col gap-6">
      <h1 className="font-[var(--font-display)] font-semibold text-lg text-text-primary">{t('newsWatch.title')}</h1>

      <div className="flex gap-2">
        {TABS.map((s) => (
          <button key={s} type="button" onClick={() => { setTab(s); setOffset(0) }} aria-pressed={tab === s}
            className={cn('px-3 py-1.5 rounded-sm text-xs font-semibold border transition-colors',
              tab === s ? 'bg-accent-dim text-accent border-border-active'
                : 'bg-bg-surface text-text-muted border-border-default hover:border-border-active')}>
            {t(`newsWatch.status.${s}`)}
            {s === tab && items.data ? ` (${items.data.total})` : ''}
          </button>
        ))}
      </div>

      {items.isLoading ? <LoadingSpinner /> : items.isError ? (
        <p className="text-[13px] text-red-500">{t('common.error')}</p>
      ) : items.data && items.data.items.length === 0 ? (
        <p className="text-[13px] text-text-muted">{t('newsWatch.empty')}</p>
      ) : (
        <div className="flex flex-col gap-3">
          {items.data?.items.map((item) => (
            <ItemCard key={item.id} item={item} pending={decide.isPending}
              onDecide={(decision) => decide.mutate({ id: item.id, decision })} />
          ))}
        </div>
      )}

      {total > NEWS_PAGE_SIZE && (
        <div className="flex items-center justify-center gap-3">
          <Button variant="outline" size="sm" disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - NEWS_PAGE_SIZE))}>{t('common.back')}</Button>
          <span className="text-xs text-text-muted font-[family-name:var(--font-mono)]">
            {offset + 1}–{Math.min(offset + NEWS_PAGE_SIZE, total)} / {total}
          </span>
          <Button variant="outline" size="sm" disabled={offset + NEWS_PAGE_SIZE >= total}
            onClick={() => setOffset(offset + NEWS_PAGE_SIZE)}>{t('common.next')}</Button>
        </div>
      )}

      <section className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-3">
        <h2 className="font-[var(--font-display)] font-semibold text-sm text-text-primary">{t('newsWatch.config.title')}</h2>
        {config.isLoading ? <LoadingSpinner /> : config.data ? (
          <NewsWatchConfigForm value={config.data} pending={save.isPending} onSave={(cfg) => save.mutate(cfg)} />
        ) : (
          <p className="text-[13px] text-red-500">{t('common.error')}</p>
        )}
      </section>
    </div>
  )
}
