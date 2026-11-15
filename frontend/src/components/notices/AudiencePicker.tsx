import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { useAllBuildings, useYards } from '../../hooks/useAddresses'
import { useAudience, type NoticeScope } from '../../hooks/useNotices'

interface Props {
  scope: NoticeScope
  ids: number[]
  onChange: (scope: NoticeScope, ids: number[]) => void
}

const SCOPES: NoticeScope[] = ['all', 'yards', 'buildings']
const CHIP = 'rounded-sm border px-2.5 py-1 text-xs font-semibold transition-colors'
const tone = (on: boolean): string =>
  on ? 'border-border-active bg-accent-dim text-accent' : 'border-border-default bg-bg-surface text-text-muted'

/**
 * Кому адресована запись: все жители, дворы или дома (из справочника адресов).
 * Житель относится к дому, если у него одобрена привязка к квартире в нём —
 * число получателей считает сервер.
 */
export default function AudiencePicker({ scope, ids, onChange }: Props) {
  const { t } = useTranslation()
  const yards = useYards()
  const buildings = useAllBuildings()
  const ready = scope === 'all' || ids.length > 0
  const audience = useAudience(scope, ids, ready)
  const toggle = (id: number) => onChange(scope, ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id])

  // Дома — группами по дворам: адрес без двора не однозначен.
  const byYard = new Map<string, { id: number; address: string }[]>()
  for (const b of buildings.data ?? []) {
    const key = b.yard_name ?? ''
    byYard.set(key, [...(byYard.get(key) ?? []), { id: b.id, address: b.address }])
  }

  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold text-text-muted">{t('notices.audience.label')}</div>
      <div role="radiogroup" aria-label={t('notices.audience.label')} className="flex gap-1.5">
        {SCOPES.map((s) => (
          <button key={s} type="button" role="radio" aria-checked={scope === s} className={cn(CHIP, tone(scope === s))} onClick={() => onChange(s, [])}>
            {t(`notices.audience.scope.${s}`)}
          </button>
        ))}
      </div>

      {scope === 'yards' && (
        <div className="flex flex-wrap gap-1.5">
          {(yards.data ?? []).map((y) => (
            <button key={y.id} type="button" aria-pressed={ids.includes(y.id)} className={cn(CHIP, tone(ids.includes(y.id)))} onClick={() => toggle(y.id)}>
              {y.name}
            </button>
          ))}
        </div>
      )}

      {scope === 'buildings' && (
        <div className="max-h-44 space-y-2 overflow-y-auto rounded-sm border border-border-default p-2">
          {[...byYard.entries()].map(([yard, list]) => (
            <div key={yard}>
              {yard && <div className="mb-1 text-[11px] font-bold uppercase text-text-muted">{yard}</div>}
              <div className="flex flex-wrap gap-1.5">
                {list.map((b) => (
                  <button key={b.id} type="button" aria-pressed={ids.includes(b.id)} className={cn(CHIP, tone(ids.includes(b.id)))} onClick={() => toggle(b.id)}>
                    {b.address}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-text-muted">
        {!ready
          ? t('notices.audience.pick')
          : audience.data
            ? t('notices.audience.count', { count: audience.data.count })
            : ''}
      </p>
    </div>
  )
}
