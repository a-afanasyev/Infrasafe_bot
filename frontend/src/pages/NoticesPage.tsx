import { lazy, Suspense, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { usePageTitle } from '../hooks/usePageTitle'
import { useNoticeAction, useNotices, useNow, type Notice, type NoticeBody, type NoticeKind, type NoticeState } from '../hooks/useNotices'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import NoticeCalendar from '../components/notices/NoticeCalendar'
import NoticeForm from '../components/notices/NoticeForm'
import OutageStatus from '../components/notices/OutageStatus'
import { draftOf, emptyDraft, ongoingOutages, type NoticeDraft } from '../components/notices/noticeModel'
import { formatDateTime } from '../utils/timezone'

// Очередь новостей из каналов и её настройки — прежняя страница «Отключения».
const NewsWatchPage = lazy(() => import('./NewsWatchPage'))
const NEWS_WATCH_ENABLED = import.meta.env.VITE_NEWS_WATCH_ENABLED === 'true'

type Tab = 'feed' | 'outages' | 'calendar' | 'channels'
type Filter = 'all' | NoticeKind | 'draft'
const FILTERS: Filter[] = ['all', 'news', 'outage', 'draft']
// = MAX_ATTEMPTS воркера: после стольких попыток он сам не повторяет.
const MAX_BROADCAST_ATTEMPTS = 5
const RESOURCE_ICON: Record<string, string> = { power: '⚡', water: '💧', gas: '🔥', heating: '🌡', internet: '🌐', other: '📢' }
const STATE_TONE: Record<NoticeState, string> = {
  draft: 'text-text-muted',
  scheduled: 'text-blue-600',
  active: 'text-accent',
  expired: 'text-text-muted',
  closed: 'text-text-muted',
}

interface Editing { notice: Notice | null; draft: NoticeDraft }

/**
 * «Новости и уведомления» (/dashboard/notices, действие notices.manage): всё,
 * что УК сообщает жителям, в одном месте — лента, календарь публикаций и
 * отключений, очередь новостей из каналов. Табло, главная и TWA показывают эти
 * записи прежними блоками «Новости» и «Ближайшие работы».
 */
export default function NoticesPage() {
  const { t } = useTranslation()
  usePageTitle(t('notices.title'))
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab')
  const tab: Tab =
    requested === 'calendar' || requested === 'outages' || (requested === 'channels' && NEWS_WATCH_ENABLED) ? requested : 'feed'
  const [filter, setFilter] = useState<Filter>('all')
  const [editing, setEditing] = useState<Editing | null>(null)
  const notices = useNotices()
  const action = useNoticeAction()
  const items = notices.data?.items ?? []
  const shown = items.filter((n) => (filter === 'all' ? true : filter === 'draft' ? n.state === 'draft' : n.kind === filter))
  const tabs: Tab[] = NEWS_WATCH_ENABLED ? ['feed', 'outages', 'calendar', 'channels'] : ['feed', 'outages', 'calendar']
  // Счётчик на вкладке: менеджер видит, что вода где-то отключена, не открывая её.
  const ongoing = ongoingOutages(items, useNow()).length

  const create = (kind: NoticeKind, day?: string) => setEditing({ notice: null, draft: emptyDraft(kind, day) })
  const open = (notice: Notice) => setEditing({ notice, draft: draftOf(notice) })

  const submit = (body: NoticeBody, publish: boolean) => {
    const done = { onSuccess: () => setEditing(null) }
    if (editing?.notice) action.mutate({ type: 'update', id: editing.notice.id, body, publish }, done)
    else action.mutate({ type: 'create', body, publish }, done)
  }

  const whenLine = (n: Notice): string => {
    if (n.starts_at) return `${formatDateTime(n.starts_at)}${n.ends_at ? ` – ${formatDateTime(n.ends_at)}` : ''}`
    const at = n.publish_at ?? n.created_at
    return at ? formatDateTime(at) : ''
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="font-[var(--font-display)] text-lg font-semibold text-text-primary">{t('notices.title')}</h1>

      <div role="tablist" className="flex gap-1 border-b border-border-default">
        {tabs.map((id) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={tab === id}
            onClick={() => setParams(id === 'feed' ? {} : { tab: id }, { replace: true })}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm font-semibold transition-colors',
              tab === id ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary',
            )}
          >
            {t(`notices.tab.${id}`)}
            {id === 'outages' && ongoing > 0 && (
              <span data-testid="outages-count" className="ml-1.5 rounded-full bg-red/15 px-1.5 py-px text-[11px] text-red">{ongoing}</span>
            )}
          </button>
        ))}
      </div>

      {tab !== 'channels' && tab !== 'outages' && (
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => create('news')}>{t('notices.addNews')}</Button>
          <Button variant="outline" onClick={() => create('outage')}>{t('notices.addOutage')}</Button>
          {tab === 'feed' && (
            <div className="ml-auto flex flex-wrap gap-1.5">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  type="button"
                  aria-pressed={filter === f}
                  onClick={() => setFilter(f)}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs font-semibold transition-colors',
                    filter === f ? 'border-border-active bg-accent-dim text-accent' : 'border-border-default bg-bg-surface text-text-muted',
                  )}
                >
                  {t(`notices.filter.${f}`)}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'channels' ? (
        <Suspense fallback={<LoadingSpinner />}><NewsWatchPage embedded /></Suspense>
      ) : tab === 'calendar' ? (
        <NoticeCalendar onOpen={open} onPickDay={(day) => create('outage', day)} />
      ) : notices.isLoading ? (
        <LoadingSpinner />
      ) : notices.isError ? (
        <p className="text-[13px] text-red-500">{t('common.error')}</p>
      ) : tab === 'outages' ? (
        <OutageStatus items={items} busy={action.isPending} onRestore={(id) => action.mutate({ type: 'close', id })} />
      ) : shown.length === 0 ? (
        <p className="text-[13px] text-text-muted">{t('notices.empty')}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {shown.map((n) => (
            <li key={n.id} data-testid="notice-row" className="flex flex-wrap items-start gap-3 rounded-default border border-border-default bg-bg-card p-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm bg-bg-surface text-lg" aria-hidden>
                {n.kind === 'outage' ? RESOURCE_ICON[n.resource ?? 'other'] : '📰'}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-text-primary">{n.title_ru}</div>
                <div className="text-xs text-text-muted">{whenLine(n)}{n.place_ru ? ` · ${n.place_ru}` : ''}</div>
                <div className="mt-1.5 flex flex-wrap gap-1.5 text-[11px] font-semibold">
                  <span className="rounded-[5px] bg-bg-surface px-1.5 py-px text-text-muted">
                    {n.kind === 'outage' ? `${t('notices.kind.outage')} · ${t(`notices.resource.${n.resource ?? 'other'}`)}` : t('notices.kind.news')}
                  </span>
                  {n.source !== 'manual' && (
                    <span className="rounded-[5px] bg-bg-surface px-1.5 py-px text-text-muted">{t(`notices.source.${n.source}`)}</span>
                  )}
                  {n.important && <span className="rounded-[5px] bg-red/15 px-1.5 py-px text-red">{t('notices.important')}</span>}
                  {n.scope !== 'all' && (
                    <span className="rounded-[5px] bg-bg-surface px-1.5 py-px text-text-muted">
                      {t(`notices.audience.short.${n.scope}`, { count: n.scope_ids.length })}
                    </span>
                  )}
                  {n.broadcast_status !== 'none' && (
                    <span data-testid="broadcast-state" className="rounded-[5px] bg-bg-surface px-1.5 py-px text-text-muted">
                      {t(`notices.broadcast.${n.broadcast_status}`, {
                        sent: n.broadcast_details?.sent ?? 0,
                        failed: (n.broadcast_details?.blocked ?? 0) + (n.broadcast_details?.no_chat ?? 0) + (n.broadcast_details?.errors ?? 0),
                      })}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <span className={cn('text-xs font-bold', STATE_TONE[n.state])}>{t(`notices.state.${n.state}`)}</span>
                <div className="flex flex-wrap justify-end gap-1.5">
                  {n.state !== 'closed' && (
                    <Button size="sm" variant="outline" onClick={() => open(n)}>{t('notices.edit')}</Button>
                  )}
                  {n.state === 'draft' && (
                    <>
                      <Button size="sm" disabled={action.isPending} onClick={() => action.mutate({ type: 'publish', id: n.id })}>{t('notices.form.publish')}</Button>
                      <Button size="sm" variant="outline" disabled={action.isPending} onClick={() => action.mutate({ type: 'delete', id: n.id })}>{t('common.delete')}</Button>
                    </>
                  )}
                  {n.broadcast_status === 'failed' && n.broadcast_attempts >= MAX_BROADCAST_ATTEMPTS && (n.state === 'active' || n.state === 'scheduled') && (
                    <Button size="sm" variant="outline" disabled={action.isPending} onClick={() => action.mutate({ type: 'retry-broadcast', id: n.id })}>
                      {t('notices.broadcast.retry')}
                    </Button>
                  )}
                  {(n.state === 'active' || n.state === 'scheduled' || n.state === 'expired') && (
                    <Button size="sm" variant="outline" disabled={action.isPending} onClick={() => action.mutate({ type: 'close', id: n.id })}>{t('notices.close')}</Button>
                  )}
                </div>
              </div>
            </li>
          ))}
          {(notices.data?.total ?? 0) > items.length && (
            <li className="text-xs text-text-muted">
              {t('notices.truncated', { shown: items.length, total: notices.data?.total })}
            </li>
          )}
        </ul>
      )}

      {editing && (
        <NoticeForm
          key={editing.notice?.id ?? `new-${editing.draft.kind}-${editing.draft.startsAt}`}
          initial={editing.draft}
          editing={editing.notice !== null}
          published={editing.notice !== null && editing.notice.status === 'published'}
          broadcastLocked={editing.notice !== null && !['none', 'pending'].includes(editing.notice.broadcast_status)}
          pending={action.isPending}
          onSubmit={submit}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
