import { useState } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { usePageTitle } from '../../hooks/usePageTitle'
import {
  useCleaningBuildings,
  useCleaningPlan,
  useSaveCleaningPlan,
  useSaveCleaningSettings,
} from '../../hooks/useCleaning'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import CleaningAreasCard from './CleaningAreasCard'
import {
  type DraftItem,
  BASEMENT_FLOOR,
  type FloorsMode,
  FLOOR_WORKS,
  WEEKDAYS,
  WORK_KINDS,
  coverage,
  draftFrom,
  emptyItem,
  splitInHalf,
  toPayload,
  toggleDay,
  validate,
  weekPreview,
} from '../../features/cleaning/planModel'
import type { CleaningBuilding, CleaningPlanView, CleaningWorkKind } from '../../types/cleaning'

/**
 * План уборки дома (/dashboard/cleaning, manager): работы по дням недели,
 * подъездам и отрезкам этажей. Сохранение создаёт новую версию плана, она
 * действует с завтра (сегодняшние задания уже выданы). Покрытие этажей и
 * предпросмотр недели считаются по несохранённому черновику.
 */
const CARD = 'bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-3'
const FIELD = 'h-9 rounded-default border border-border-default bg-bg-card px-2 text-[13px] text-text-primary'

interface EditorProps {
  building: CleaningBuilding
  view: CleaningPlanView
}

function PlanEditor({ building, view }: EditorProps) {
  const { t } = useTranslation()
  const shown = view.upcoming ?? view.current
  const [items, setItems] = useState<DraftItem[]>(() => (shown ? draftFrom(shown.items) : [emptyItem()]))
  const [points, setPoints] = useState(() => (shown?.extra_points ?? []).join(', '))
  const [showResidents, setShowResidents] = useState(building.show_to_residents)
  const [showPhotos, setShowPhotos] = useState(building.show_photos)
  const savePlan = useSaveCleaningPlan(building.id)
  const saveSettings = useSaveCleaningSettings(building.id)

  const { floor_count: floors, entrance_count: entrances } = view
  const problem = validate(items, floors, entrances)
  const preview = weekPreview(items, floors)
  const patch = (index: number, change: Partial<DraftItem>) =>
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, ...change } : item)))

  const submit = () => {
    if (problem) return
    const extra_points = points.split(',').map((p) => p.trim()).filter(Boolean)
    savePlan.mutate({ items: toPayload(items), extra_points })
    if (showResidents !== building.show_to_residents || showPhotos !== building.show_photos) {
      saveSettings.mutate({ show_to_residents: showResidents, show_photos: showPhotos })
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {view.snapshot_mismatch && <p role="alert" className="text-[13px] text-amber">{t('cleaning.plan.mismatch')}</p>}
      {view.upcoming && (
        <p className="text-[13px] text-text-muted">{t('cleaning.plan.upcoming', { date: view.upcoming.valid_from })}</p>
      )}

      <section className={CARD} aria-label={t('cleaning.plan.works')}>
        <h2 className="text-[14px] font-semibold text-text-primary">
          {building.address} · {t('cleaning.plan.meta', { entrances, floors })}
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px] text-text-primary">
            <thead>
              <tr className="text-left text-text-muted">
                <th className="p-2 font-medium">{t('cleaning.plan.col.work')}</th>
                <th className="p-2 font-medium">{t('cleaning.plan.col.days')}</th>
                <th className="p-2 font-medium">{t('cleaning.plan.col.entrances')}</th>
                <th className="p-2 font-medium">{t('cleaning.plan.col.floors')}</th>
                <th className="p-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => {
                const byFloors = FLOOR_WORKS.includes(item.work_kind)
                const row = index + 1
                return (
                  <tr key={index} className="border-t border-border-default align-middle">
                    <td className="p-2">
                      <select
                        aria-label={t('cleaning.plan.aria.work', { row })} className={FIELD} value={item.work_kind}
                        onChange={(e) => patch(index, { work_kind: e.target.value as CleaningWorkKind })}
                      >
                        {WORK_KINDS.map((kind) => <option key={kind} value={kind}>{t(`cleaning.work.${kind}`)}</option>)}
                      </select>
                    </td>
                    <td className="p-2 whitespace-nowrap">
                      {WEEKDAYS.map((day) => {
                        const on = item.weekdays.includes(day)
                        return (
                          <button
                            key={day} type="button" aria-pressed={on}
                            aria-label={t('cleaning.plan.aria.day', { row, day: t(`cleaning.day.${day}`) })}
                            onClick={() => patch(index, { weekdays: toggleDay(item.weekdays, day) })}
                            className={cn(
                              'mr-1 h-9 w-9 rounded-default border text-[12px]',
                              on ? 'border-accent bg-accent font-semibold text-white' : 'border-border-default text-text-muted',
                            )}
                          >
                            {t(`cleaning.day.${day}`)}
                          </button>
                        )
                      })}
                    </td>
                    <td className="p-2">
                      <Input
                        aria-label={t('cleaning.plan.aria.entrances', { row })} className="w-24" value={item.entrances}
                        placeholder={t('cleaning.plan.entrancesAll')}
                        onChange={(e) => patch(index, { entrances: e.target.value })}
                      />
                    </td>
                    <td className="p-2 whitespace-nowrap">
                      {byFloors ? (
                        <>
                          <select
                            aria-label={t('cleaning.plan.aria.floors', { row })} className={FIELD} value={item.floors}
                            onChange={(e) => patch(index, { floors: e.target.value as FloorsMode })}
                          >
                            <option value="all">{t('cleaning.floors.all')}</option>
                            <option value="first">{t('cleaning.floors.first')}</option>
                            <option value="basement">{t('cleaning.floors.basement')}</option>
                            <option value="range">{t('cleaning.floors.range')}</option>
                          </select>
                          {item.floors === 'range' && (
                            <>
                              <Input
                                aria-label={t('cleaning.plan.aria.from', { row })} type="number" min={BASEMENT_FLOOR} max={floors}
                                className="ml-2 inline-block w-16" value={item.floor_from}
                                onChange={(e) => patch(index, { floor_from: e.target.value })}
                              />
                              <span className="mx-1">–</span>
                              <Input
                                aria-label={t('cleaning.plan.aria.to', { row })} type="number" min={1} max={floors}
                                className="inline-block w-16" value={item.floor_to}
                                onChange={(e) => patch(index, { floor_to: e.target.value })}
                              />
                            </>
                          )}
                          {item.floors === 'all' && item.weekdays.length > 1 && floors > 1 && (
                            <Button
                              type="button" variant="ghost" size="sm" className="ml-2"
                              onClick={() => setItems((prev) => prev.flatMap((it, i) => (i === index ? splitInHalf(it, floors) : [it])))}
                            >
                              {t('cleaning.plan.split')}
                            </Button>
                          )}
                        </>
                      ) : (
                        <span className="text-text-muted">{t('cleaning.floors.na')}</span>
                      )}
                    </td>
                    <td className="p-2 text-right">
                      <Button
                        type="button" variant="ghost" size="sm" className="text-red"
                        onClick={() => setItems((prev) => prev.filter((_, i) => i !== index))}
                      >
                        {t('cleaning.plan.remove')}
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div>
          <Button type="button" variant="outline" size="sm" onClick={() => setItems((prev) => [...prev, emptyItem()])}>
            {t('cleaning.plan.addWork')}
          </Button>
        </div>
      </section>

      <section className={CARD} aria-label={t('cleaning.plan.coverage')}>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.plan.coverage')}</h2>
        {FLOOR_WORKS.filter((kind) => items.some((item) => item.work_kind === kind)).map((kind) => {
          const counts = coverage(items, kind, floors, entrances)
          const gaps = counts.flatMap((n, i) => (n === 0 ? [i + 1] : []))
          return (
            <div key={kind} className="flex flex-col gap-1.5">
              <p className="text-[13px] text-text-primary">
                {t(`cleaning.work.${kind}`)} —{' '}
                {gaps.length === 0
                  ? <span className="text-green">{t('cleaning.plan.coverageOk')}</span>
                  : <span className="font-semibold text-red">{t('cleaning.plan.coverageGap', { floors: gaps.join(', ') })}</span>}
              </p>
              <div className="flex flex-wrap gap-1">
                {counts.map((n, i) => (
                  <span
                    key={i}
                    className={cn('min-w-10 rounded-default border px-1.5 py-1 text-center text-[12px]',
                      n === 0 ? 'border-red font-semibold text-red' : 'border-border-default text-text-primary')}
                  >
                    {i + 1}: {n}×
                  </span>
                ))}
              </div>
            </div>
          )
        })}
      </section>

      <section className={CARD} aria-label={t('cleaning.plan.week')}>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.plan.week')}</h2>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
          {preview.map((day, i) => (
            <div key={i} className="rounded-default border border-border-default p-2 text-[12px] text-text-primary">
              <p className="font-semibold">{t(`cleaning.day.${i}`)}</p>
              {day.works.length === 0 && <p className="text-text-muted">{t('cleaning.plan.dayOff')}</p>}
              {day.works.map((work, j) => (
                <p key={j}>
                  {t(`cleaning.work.${work.kind}`)}
                  {work.from != null && `, ${work.from === work.to ? work.from : `${work.from}–${work.to}`}`}
                </p>
              ))}
              {day.floors > 0 && <p className="text-text-muted">{t('cleaning.plan.floorsPerEntrance', { n: day.floors })}</p>}
            </div>
          ))}
        </div>
      </section>

      <section className={CARD} aria-label={t('cleaning.plan.extraPoints')}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cleaning-points">{t('cleaning.plan.extraPoints')}</Label>
          <Input id="cleaning-points" value={points} placeholder={t('cleaning.plan.extraPointsHint')} onChange={(e) => setPoints(e.target.value)} />
          <p className="text-[12px] text-text-muted">{t('cleaning.plan.photoRule')}</p>
        </div>
        <label className="flex items-center gap-2 text-[13px] text-text-primary">
          <input type="checkbox" checked={showResidents} onChange={(e) => setShowResidents(e.target.checked)} />
          {t('cleaning.plan.showResidents')}
        </label>
        <label className="flex items-center gap-2 text-[13px] text-text-primary">
          <input type="checkbox" checked={showPhotos} onChange={(e) => setShowPhotos(e.target.checked)} />
          {t('cleaning.plan.showPhotos')}
        </label>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" disabled={problem !== null || savePlan.isPending} onClick={submit}>{t('cleaning.plan.save')}</Button>
        {problem
          ? <p role="alert" className="text-[13px] text-red">{t(`cleaning.plan.problem.${problem}`)}</p>
          : <p className="text-[13px] text-text-muted">{t('cleaning.plan.effective')}</p>}
      </div>
    </div>
  )
}

export default function CleaningPlanPage() {
  const { t } = useTranslation()
  usePageTitle(t('cleaning.plan.title'))
  const buildings = useCleaningBuildings()
  const [selected, setSelected] = useState<number | null>(null)
  const buildingId = selected ?? buildings.data?.[0]?.id ?? null
  const building = buildings.data?.find((b) => b.id === buildingId) ?? null
  const plan = useCleaningPlan(buildingId)

  if (buildings.isLoading) return <LoadingSpinner />
  if (buildings.isError) return <div className="p-6"><p className="text-[13px] text-red">{t('common.error')}</p></div>

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[18px] font-semibold text-text-primary">{t('cleaning.plan.title')}</h1>
          <p className="text-[13px] text-text-muted">{t('cleaning.plan.subtitle')}</p>
        </div>
        <div className="flex gap-3">
          <Link to="/dashboard/cleaning/control" className="text-[13px] font-medium text-accent">{t('cleaning.control.title')}</Link>
          <Link to="/dashboard/cleaning/staff" className="text-[13px] font-medium text-accent">{t('cleaning.plan.staffLink')}</Link>
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="cleaning-building">{t('cleaning.plan.building')}</Label>
        <select
          id="cleaning-building" className={cn(FIELD, 'max-w-md')} value={buildingId ?? ''}
          onChange={(e) => setSelected(Number(e.target.value))}
        >
          {(buildings.data ?? []).map((b) => (
            <option key={b.id} value={b.id}>{b.address}{b.has_plan ? '' : ` — ${t('cleaning.plan.noPlan')}`}</option>
          ))}
        </select>
      </div>
      {plan.isLoading && <LoadingSpinner />}
      {plan.isError && <p className="text-[13px] text-red">{t('common.error')}</p>}
      {/* key: при смене дома и после сохранения (новая версия) черновик пересеивается */}
      {building && plan.data && (
        <PlanEditor key={`${building.id}:${plan.data.upcoming?.id ?? plan.data.current?.id ?? 0}`} building={building} view={plan.data} />
      )}
      {building && <CleaningAreasCard buildingId={building.id} />}
    </div>
  )
}
