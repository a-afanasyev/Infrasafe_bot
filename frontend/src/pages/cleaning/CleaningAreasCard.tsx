import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useCleaningAreas, useSaveCleaningAreas } from '../../hooks/useCleaning'
import {
  type AreasDraftRow,
  ALL_ENTRANCES,
  POINT_KINDS,
  areasFromDraft,
  draftFromAreas,
  emptyRow,
} from '../../features/cleaning/areasModel'
import type { CleaningAreasView } from '../../types/cleaning'

/**
 * Площади мест общего пользования дома (м²) — по ним считается нагрузка уборщиц в м²
 * на странице «Сотрудники». Действуют сразу, плана не меняют. Строка «Все подъезды»
 * задаёт значения дома; строка подъезда — только то, чем он отличается.
 */
const CARD = 'bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-3'
const FIELD = 'h-9 rounded-default border border-border-default bg-bg-card px-2 text-[13px] text-text-primary'
type TextField = 'typical' | 'floor1' | 'basement' | 'special'
const TEXT_FIELDS: TextField[] = ['typical', 'floor1', 'basement', 'special']

function AreasEditor({ view }: { view: CleaningAreasView }) {
  const { t } = useTranslation()
  const [rows, setRows] = useState<AreasDraftRow[]>(() => draftFromAreas(view.areas))
  const [adding, setAdding] = useState('')
  const save = useSaveCleaningAreas(view.building_id)
  const parsed = areasFromDraft(rows)
  const free = Array.from({ length: view.entrance_count }, (_, i) => String(i + 1))
    .filter((scope) => !rows.some((row) => row.scope === scope))

  const patch = (index: number, change: Partial<AreasDraftRow>) =>
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...change } : row)))
  const scopeLabel = (scope: string) =>
    scope === ALL_ENTRANCES ? t('cleaning.areas.all') : t('cleaning.areas.entrance', { n: scope })

  return (
    <section className={CARD} aria-label={t('cleaning.areas.title')}>
      <div>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.areas.title')}</h2>
        <p className="text-[12px] text-text-muted">{t('cleaning.areas.hint')}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px] text-text-primary">
          <thead>
            <tr className="text-left text-text-muted">
              <th className="p-2 font-medium">{t('cleaning.areas.col.scope')}</th>
              {TEXT_FIELDS.map((f) => <th key={f} className="p-2 font-medium">{t(`cleaning.areas.col.${f}`)}</th>)}
              {POINT_KINDS.map((k) => <th key={k} className="p-2 font-medium">{t(`cleaning.point.${k}`)}</th>)}
              <th className="p-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.scope} className="border-t border-border-default align-middle">
                <td className="p-2 whitespace-nowrap font-medium">{scopeLabel(row.scope)}</td>
                {TEXT_FIELDS.map((f) => (
                  <td key={f} className="p-2">
                    <Input
                      aria-label={`${scopeLabel(row.scope)}: ${t(`cleaning.areas.col.${f}`)}`}
                      className={f === 'special' ? 'w-40' : 'w-20'} inputMode="decimal" value={row[f]}
                      placeholder={f === 'special' ? t('cleaning.areas.specialHint') : ''}
                      onChange={(e) => patch(index, { [f]: e.target.value })}
                    />
                  </td>
                ))}
                {POINT_KINDS.map((k) => (
                  <td key={k} className="p-2">
                    <Input
                      aria-label={`${scopeLabel(row.scope)}: ${t(`cleaning.point.${k}`)}`}
                      className="w-20" inputMode="decimal" value={row.points[k]}
                      onChange={(e) => patch(index, { points: { ...row.points, [k]: e.target.value } })}
                    />
                  </td>
                ))}
                <td className="p-2 text-right">
                  {row.scope !== ALL_ENTRANCES && (
                    <Button
                      type="button" variant="ghost" size="sm" className="text-red"
                      onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
                    >
                      {t('cleaning.plan.remove')}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {free.length > 0 && (
          <>
            <select
              aria-label={t('cleaning.areas.addEntrance')} className={FIELD} value={adding}
              onChange={(e) => setAdding(e.target.value)}
            >
              <option value="">{t('cleaning.areas.addEntrance')}</option>
              {free.map((scope) => <option key={scope} value={scope}>{scopeLabel(scope)}</option>)}
            </select>
            <Button
              type="button" variant="outline" size="sm" disabled={adding === ''}
              onClick={() => { setRows((prev) => [...prev, emptyRow(adding)]); setAdding('') }}
            >
              {t('cleaning.areas.add')}
            </Button>
          </>
        )}
        <Button
          type="button" disabled={'error' in parsed || save.isPending}
          onClick={() => { if ('areas' in parsed) save.mutate(parsed.areas) }}
        >
          {t('cleaning.areas.save')}
        </Button>
        {'error' in parsed && <p role="alert" className="text-[13px] text-red">{t(`cleaning.areas.error.${parsed.error}`)}</p>}
      </div>
    </section>
  )
}

export default function CleaningAreasCard({ buildingId }: { buildingId: number }) {
  const { t } = useTranslation()
  const areas = useCleaningAreas(buildingId)
  if (areas.isError) return <p className="text-[13px] text-red">{t('common.error')}</p>
  if (!areas.data) return null
  // key: после сохранения и при смене дома черновик пересеивается из сервера
  return <AreasEditor key={`${buildingId}:${JSON.stringify(areas.data.areas)}`} view={areas.data} />
}
