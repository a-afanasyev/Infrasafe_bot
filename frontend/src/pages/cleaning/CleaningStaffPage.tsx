import { useState } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { usePageTitle } from '../../hooks/usePageTitle'
import { usePersonName } from '../../hooks/usePersonName'
import {
  useAssignCleaner,
  useCleaningBuildings,
  useCleaningStaff,
  useSaveCleaningRules,
} from '../../hooks/useCleaning'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import { toast } from 'sonner'
import { WEEKDAYS, parseEntrances } from '../../features/cleaning/planModel'
import type { CleaningBuilding, CleaningStaffMember } from '../../types/cleaning'

/**
 * Уборщицы, дома и нагрузка (/dashboard/cleaning/staff, manager). У подъезда
 * один ответственный; привязка дома назначает все его подъезды и действует с
 * завтра. Нагрузка — этажи и м² мест общего пользования по плану на каждый день
 * недели; перегрузка по м², если задана норма м², иначе по этажам.
 */
const CARD = 'bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-3'
const FIELD = 'h-9 rounded-default border border-border-default bg-bg-card px-2 text-[13px] text-text-primary'

/** Подъезды уборщицы, сгруппированные по домам. */
function byBuilding(member: CleaningStaffMember): Map<number, number[]> {
  const groups = new Map<number, number[]>()
  for (const { building_id, entrance } of member.entrances) {
    groups.set(building_id, [...(groups.get(building_id) ?? []), entrance])
  }
  return groups
}

interface NormFormProps {
  norm: number
  ruleKey: 'floors_norm_per_day' | 'area_norm_m2_per_day'
  max: number
  label: string
}

function NormForm({ norm, ruleKey, max, label }: NormFormProps) {
  const { t } = useTranslation()
  const [value, setValue] = useState(String(norm))
  const save = useSaveCleaningRules()
  const parsed = Number(value)
  const valid = Number.isInteger(parsed) && parsed >= 0 && parsed <= max
  const id = `cleaning-norm-${ruleKey}`
  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(e) => { e.preventDefault(); if (valid) save.mutate({ [ruleKey]: parsed }) }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={id}>{label}</Label>
        <Input id={id} type="number" min={0} max={max} className="w-32" value={value} onChange={(e) => setValue(e.target.value)} />
      </div>
      <Button type="submit" variant="outline" disabled={!valid || parsed === norm || save.isPending}>{t('cleaning.staff.saveNorm')}</Button>
    </form>
  )
}

export default function CleaningStaffPage() {
  const { t } = useTranslation()
  usePageTitle(t('cleaning.staff.title'))
  const person = usePersonName()
  const staff = useCleaningStaff()
  const buildings = useCleaningBuildings()
  const assign = useAssignCleaner()
  // Подъезды для следующей привязки, по уборщице: пусто — весь дом.
  const [picked, setPicked] = useState<Record<number, string>>({})

  if (staff.isLoading || buildings.isLoading) return <LoadingSpinner />
  if (staff.isError || buildings.isError || !staff.data || !buildings.data) {
    return <div className="p-6"><p className="text-[13px] text-red">{t('common.error')}</p></div>
  }

  const { cleaners, norm, area_norm: areaNorm, unassigned } = staff.data
  const byArea = areaNorm > 0
  const address = new Map<number, CleaningBuilding>(buildings.data.map((b) => [b.id, b]))
  const nameOf = (member: CleaningStaffMember) => person.full(member, `#${member.user_id}`)
  /** Привязать дом (или подъезды из поля) уборщице; чужие подъезды — только после подтверждения. */
  const addBuilding = (member: CleaningStaffMember, buildingId: number) => {
    const max = address.get(buildingId)?.entrance_count ?? 0
    const entrances = parseEntrances(picked[member.user_id] ?? '')
    if (entrances === 'invalid' || (entrances && entrances.some((e) => e > max))) {
      toast.error(t('cleaning.staff.badEntrances', { max }))
      return
    }
    const taken = cleaners.some((other) => other.user_id !== member.user_id && other.entrances.some(
      (e) => e.building_id === buildingId && (entrances === null || entrances.includes(e.entrance))))
    if (taken && !window.confirm(t('cleaning.staff.takeOver', { name: nameOf(member) }))) return
    assign.mutate({ building_id: buildingId, entrances, user_id: member.user_id })
    setPicked({ ...picked, [member.user_id]: '' })
  }
  const entranceLabel = (buildingId: number, entrance: number) =>
    `${address.get(buildingId)?.address ?? `#${buildingId}`}, ${t('cleaning.staff.entrance', { n: entrance })}`

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to="/dashboard/cleaning" className="text-[13px] font-medium text-accent">← {t('cleaning.staff.planLink')}</Link>
          <h1 className="text-[18px] font-semibold text-text-primary">{t('cleaning.staff.title')}</h1>
          <p className="text-[13px] text-text-muted">{t('cleaning.staff.subtitle')}</p>
        </div>
        <div className="flex flex-wrap items-end gap-4">
          <NormForm key={`f${norm}`} norm={norm} ruleKey="floors_norm_per_day" max={1000} label={t('cleaning.staff.norm')} />
          <NormForm
            key={`m${areaNorm}`} norm={areaNorm} ruleKey="area_norm_m2_per_day" max={100000} label={t('cleaning.staff.normM2')}
          />
        </div>
      </div>

      {cleaners.filter((c) => c.overloaded).map((c) => (
        <p key={c.user_id} role="alert" className="rounded-default border border-red p-3 text-[13px] font-semibold text-red">
          {byArea
            ? t('cleaning.staff.overloadM2', { name: nameOf(c), peak: c.m2_peak, norm: areaNorm })
            : t('cleaning.staff.overload', { name: nameOf(c), peak: c.peak, norm })}
        </p>
      ))}
      {unassigned.length > 0 && (
        <p role="alert" className="rounded-default border border-amber p-3 text-[13px] text-text-primary">
          {t('cleaning.staff.unassigned', { list: unassigned.map((u) => entranceLabel(u.building_id, u.entrance)).join('; ') })}
        </p>
      )}

      <section className={CARD} aria-label={t('cleaning.staff.assignments')}>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.staff.assignments')}</h2>
        {cleaners.length === 0 && <p className="text-[13px] text-text-muted">{t('cleaning.staff.empty')}</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-[13px] text-text-primary">
            <thead>
              <tr className="text-left text-text-muted">
                <th className="p-2 font-medium">{t('cleaning.staff.col.cleaner')}</th>
                <th className="p-2 font-medium">{t('cleaning.staff.col.buildings')}</th>
                <th className="p-2 font-medium">{t('cleaning.staff.col.week')}</th>
                <th className="p-2 font-medium">{t('cleaning.staff.col.peak')}</th>
                <th className="p-2 font-medium">{t('cleaning.staff.col.peakM2')}</th>
                <th className="p-2 font-medium">{t(byArea ? 'cleaning.staff.col.percentM2' : 'cleaning.staff.col.percent')}</th>
              </tr>
            </thead>
            <tbody>
              {cleaners.map((member) => (
                <tr key={member.user_id} className="border-t border-border-default align-middle">
                  <td className="p-2 font-semibold whitespace-nowrap">{nameOf(member)}</td>
                  <td className="p-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {[...byBuilding(member)].map(([buildingId, entrances]) => {
                        const building = address.get(buildingId)
                        const label = `${building?.address ?? `#${buildingId}`} (${t('cleaning.staff.entrancesList', { list: entrances.join(', ') })})`
                        return (
                          <span key={buildingId} className="inline-flex items-center gap-1 rounded-default border border-border-default px-2 py-1">
                            {label}
                            <button
                              type="button" className="px-1 font-bold text-text-muted" disabled={assign.isPending}
                              aria-label={t('cleaning.staff.unassign', { address: label })}
                              onClick={() => assign.mutate({ building_id: buildingId, entrances, user_id: null })}
                            >
                              ×
                            </button>
                          </span>
                        )
                      })}
                      {member.entrances.length === 0 && <span className="text-text-muted">{t('cleaning.staff.none')}</span>}
                      <select
                        aria-label={t('cleaning.staff.addBuildingFor', { name: nameOf(member) })} className={FIELD} value=""
                        disabled={assign.isPending}
                        onChange={(e) => addBuilding(member, Number(e.target.value))}
                      >
                        <option value="">{t('cleaning.staff.addBuilding')}</option>
                        {buildings.data.map((b) => <option key={b.id} value={b.id}>{b.address}</option>)}
                      </select>
                      <input
                        className={cn(FIELD, 'w-36')} placeholder={t('cleaning.staff.entrancesPlaceholder')}
                        aria-label={t('cleaning.staff.pickEntrances', { address: '…', name: nameOf(member) })}
                        value={picked[member.user_id] ?? ''}
                        onChange={(e) => setPicked({ ...picked, [member.user_id]: e.target.value })}
                      />
                    </div>
                  </td>
                  <td className="p-2">{member.week}</td>
                  <td className={cn('p-2', !byArea && member.overloaded && 'font-semibold text-red')}>{member.peak}</td>
                  <td className="p-2">
                    <span className={cn(byArea && member.overloaded && 'font-semibold text-red')}>{member.m2_peak || '—'}</span>
                    {member.missing_areas.length > 0 && (
                      <p className="text-[12px] text-amber">
                        {t('cleaning.staff.missingAreas', {
                          list: member.missing_areas.map((id) => address.get(id)?.address ?? `#${id}`).join(', '),
                        })}
                      </p>
                    )}
                  </td>
                  <td className={cn('p-2 font-semibold whitespace-nowrap', member.overloaded ? 'text-red' : 'text-green')}>
                    {byArea ? member.m2_percent : member.percent}% — {t(member.overloaded ? 'cleaning.staff.over' : 'cleaning.staff.ok')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[12px] text-text-muted">{t('cleaning.staff.effective')}</p>
      </section>

      <section className={CARD} aria-label={t('cleaning.staff.byDay')}>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.staff.byDay')}</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px] text-text-primary">
            <thead>
              <tr className="text-left text-text-muted">
                <th className="p-2 font-medium">{t('cleaning.staff.col.cleaner')}</th>
                {WEEKDAYS.map((day) => <th key={day} className="p-2 font-medium">{t(`cleaning.day.${day}`)}</th>)}
              </tr>
            </thead>
            <tbody>
              {cleaners.filter((c) => c.week > 0).flatMap((member) => [
                <tr key={member.user_id} className="border-t border-border-default font-semibold">
                  <td className="p-2">{nameOf(member)}</td>
                  {member.by_weekday.map((n, i) => {
                    const m2 = member.m2_by_weekday[i]
                    const over = byArea ? m2 > areaNorm : norm > 0 && n > norm
                    return (
                      <td key={i} className={cn('p-2', over && 'text-red')}>
                        {n || '—'}
                        {m2 > 0 && <span className="block text-[12px] font-normal">{t('cleaning.staff.m2', { n: m2 })}</span>}
                      </td>
                    )
                  })}
                </tr>,
                ...Object.entries(member.buildings).map(([buildingId, days]) => (
                  <tr key={`${member.user_id}:${buildingId}`} className="text-text-muted">
                    <td className="p-2 pl-6">{address.get(Number(buildingId))?.address ?? `#${buildingId}`}</td>
                    {days.map((n, i) => <td key={i} className="p-2">{n || '—'}</td>)}
                  </tr>
                )),
              ])}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
