import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { AccessEvent } from '../src/hooks/useAccessSecurityFeed'
import { formatDateTime } from '../src/utils/accessFormat'

/**
 * Тонкая копия верстки AccessLiveFeed для СТАТИЧЕСКОГО превью: оригинальный
 * компонент жёстко завязан на WS-хук useAccessSecurityFeed (данные приходят
 * только из сокета). Здесь та же разметка/классы, но события — мок-пропсы,
 * а индикатор соединения зафиксирован «На связи». Никакой сети.
 */

const DECISION_CLASS: Record<string, string> = {
  allow: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  deny: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  manual_review: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
}
const DECISION_FALLBACK_CLASS = 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'

function ConnectionIndicator() {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-2 text-[13px] text-text-secondary">
      <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
      {t('accessControl.connection.open')}
    </div>
  )
}

function EventRow({ event }: { event: AccessEvent }) {
  const { t } = useTranslation()
  const decisionLabel = t(`accessControl.decision.${event.decision}`, {
    defaultValue: event.decision || '—',
  })
  const reasonLabel = event.reason
    ? t(`accessControl.reason.${event.reason}`, { defaultValue: event.reason })
    : '—'
  const directionLabel = event.direction
    ? t(`accessControl.direction.${event.direction}`, { defaultValue: event.direction })
    : '—'
  const location =
    [
      event.zone_id != null ? `${t('accessControl.zone')} ${event.zone_id}` : null,
      event.gate_id != null ? `${t('accessControl.gate')} ${event.gate_id}` : null,
    ]
      .filter(Boolean)
      .join(' · ') || '—'

  return (
    <tr className="border-b border-border-default last:border-0">
      <td className="px-3 py-2 text-[13px] text-text-secondary whitespace-nowrap">
        {formatDateTime(event.occurred_at)}
      </td>
      <td className="px-3 py-2">
        <span
          className={cn(
            'inline-block rounded-full px-2.5 py-0.5 text-[12px] font-medium',
            DECISION_CLASS[event.decision] ?? DECISION_FALLBACK_CLASS,
          )}
        >
          {decisionLabel}
        </span>
      </td>
      <td className="px-3 py-2 text-[13px] text-text-primary">{reasonLabel}</td>
      <td className="px-3 py-2 text-[13px] text-text-secondary whitespace-nowrap">{location}</td>
      <td className="px-3 py-2 text-[13px] text-text-secondary whitespace-nowrap">{directionLabel}</td>
      <td className="px-3 py-2 text-[13px] font-mono text-text-primary whitespace-nowrap">
        {event.plate_masked ?? '—'}
      </td>
    </tr>
  )
}

export default function LiveFeedPreview({ events }: { events: AccessEvent[] }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <ConnectionIndicator />
      </div>
      <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-border-default">
              {['time', 'decision', 'reason', 'location', 'direction', 'plate'].map((col) => (
                <th
                  key={col}
                  className="px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted"
                >
                  {t(`accessControl.columns.${col}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.map((event, i) => (
              <EventRow key={`${event.occurred_at ?? ''}-${i}`} event={event} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
