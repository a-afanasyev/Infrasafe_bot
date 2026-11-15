import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useNow, type Notice } from '../../hooks/useNotices'
import { ongoingOutages } from './noticeModel'
import { usePersonName } from '../../hooks/usePersonName'
import { formatDateTime, formatTime } from '../../utils/timezone'

const RESOURCE_ICON: Record<string, string> = { power: '⚡', water: '💧', gas: '🔥', heating: '🌡', internet: '🌐', other: '📢' }
const DAY_MS = 24 * 3_600_000

function restoredOutages(items: Notice[], now: number): Notice[] {
  return items.filter((n) => n.kind === 'outage' && n.state === 'closed' && !!n.closed_at && now - Date.parse(n.closed_at) < DAY_MS)
}

interface Props {
  items: Notice[]
  busy: boolean
  onRestore: (id: number) => void
}

/**
 * Вкладка «Отключения»: что отключено сейчас, кто объявил, с какого времени и
 * до какого срока, — и «Включили» одной кнопкой. Отключение от сантехника само
 * не закрывается: менеджер видит здесь и те, у которых срок уже вышел.
 */
export default function OutageStatus({ items, busy, onRestore }: Props) {
  const { t, i18n } = useTranslation()
  const person = usePersonName()
  const [confirming, setConfirming] = useState<number | null>(null)
  const now = useNow()
  const ongoing = ongoingOutages(items, now)
  const restored = restoredOutages(items, now)
  const title = (n: Notice) => (i18n.language.startsWith('uz') && n.title_uz) || n.title_ru
  const author = (n: Notice) =>
    n.source === 'staff'
      ? t('notices.outages.byStaff', { name: person.name(n.created_by_name, t('notices.outages.staff')) })
      : t(`notices.outages.by.${n.source}`)

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-text-primary">{t('notices.outages.now', { count: ongoing.length })}</h2>
        {ongoing.length === 0 && <p className="text-[13px] text-text-muted">{t('notices.outages.none')}</p>}
        <ul className="flex flex-col gap-2">
          {ongoing.map((n) => {
            const overdue = !!n.ends_at && Date.parse(n.ends_at) <= now
            // Отключение от сантехника менеджер закрывает с сообщением жителям; чужое — просто снимает.
            const staff = n.source === 'staff'
            return (
              <li key={n.id} data-testid="outage-row" className="flex flex-wrap items-start gap-3 rounded-default border border-border-default bg-bg-card p-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm bg-bg-surface text-lg" aria-hidden>
                  {RESOURCE_ICON[n.resource ?? 'other']}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-text-primary">{title(n)}</div>
                  <div className="text-xs text-text-muted">
                    {n.starts_at && t('notices.outages.since', { time: formatDateTime(n.starts_at) })} · {author(n)}
                  </div>
                  <div className={cn('mt-1 text-xs font-semibold', overdue ? 'text-red' : 'text-text-muted')} data-testid="outage-term">
                    {!n.ends_at
                      ? t('notices.outages.noTerm')
                      : t(overdue ? 'notices.outages.overdue' : 'notices.outages.until', { time: formatTime(n.ends_at) })}
                  </div>
                </div>
                {confirming === n.id ? (
                  <div className="flex flex-col items-end gap-1.5">
                    <p className="max-w-[240px] text-right text-xs text-text-muted">
                      {t(staff ? 'notices.outages.confirmStaff' : 'notices.outages.confirmOther')}
                    </p>
                    <div className="flex gap-1.5">
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => setConfirming(null)}>{t('common.cancel')}</Button>
                      <Button size="sm" disabled={busy} onClick={() => { onRestore(n.id); setConfirming(null) }}>{t('notices.outages.confirm')}</Button>
                    </div>
                  </div>
                ) : (
                  <Button size="sm" disabled={busy} onClick={() => setConfirming(n.id)}>
                    {t(staff ? `notices.outages.restore.${n.resource === 'heating' ? 'heating' : 'water'}` : 'notices.close')}
                  </Button>
                )}
              </li>
            )
          })}
        </ul>
      </section>

      {restored.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-text-primary">{t('notices.outages.restoredToday')}</h2>
          <ul className="flex flex-col gap-1.5">
            {restored.map((n) => (
              <li key={n.id} data-testid="restored-row" className="flex flex-wrap items-center gap-2 rounded-default border border-border-default bg-bg-surface px-3 py-2 text-xs text-text-muted">
                <span aria-hidden>{RESOURCE_ICON[n.resource ?? 'other']}</span>
                <span className="font-semibold text-text-primary">{title(n)}</span>
                <span>
                  {t('notices.outages.restoredAt', { time: formatDateTime(n.closed_at!) })}
                  {n.closed_by_name ? ` · ${person.name(n.closed_by_name)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
