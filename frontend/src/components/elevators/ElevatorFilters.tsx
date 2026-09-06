import { useTranslation } from 'react-i18next'
import { Select } from '@/components/ui/select'
import { useBuildings, useYards } from '../../hooks/useAddresses'
import {
  ELEVATOR_STATUSES,
  REGISTRY_FLAGS,
  type ElevatorListFilters,
  type ElevatorStatus,
  type RegistryFlag,
} from '../../types/elevators'

/**
 * Фильтры реестра: двор → дом (каскад из хуков адресов), статус, флаги-чекбоксы,
 * «показать архивные». Любое изменение сбрасывает offset (делает вызывающий).
 */
interface Props {
  filters: ElevatorListFilters
  onChange: (patch: Partial<ElevatorListFilters>) => void
}

export default function ElevatorFilters({ filters, onChange }: Props) {
  const { t } = useTranslation()
  const yards = useYards()
  const buildings = useBuildings(filters.yard_id ?? null)
  const flags = filters.flag ?? []

  const toggleFlag = (flag: RegistryFlag, checked: boolean) => {
    const next = checked ? [...flags, flag] : flags.filter((f) => f !== flag)
    onChange({ flag: next.length ? next : undefined })
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select
        className="max-w-48"
        aria-label={t('elevators.filters.yard')}
        value={filters.yard_id ?? ''}
        onChange={(e) =>
          onChange({ yard_id: e.target.value ? Number(e.target.value) : undefined, building_id: undefined })
        }
      >
        <option value="">{t('elevators.filters.allYards')}</option>
        {(yards.data ?? []).map((y) => (
          <option key={y.id} value={y.id}>{y.name}</option>
        ))}
      </Select>
      <Select
        className="max-w-56"
        aria-label={t('elevators.filters.building')}
        value={filters.building_id ?? ''}
        disabled={!filters.yard_id}
        onChange={(e) => onChange({ building_id: e.target.value ? Number(e.target.value) : undefined })}
      >
        <option value="">{t('elevators.filters.allBuildings')}</option>
        {(buildings.data ?? []).map((b) => (
          <option key={b.id} value={b.id}>{b.address}</option>
        ))}
      </Select>
      <Select
        className="max-w-44"
        aria-label={t('elevators.filters.status')}
        value={filters.status ?? ''}
        onChange={(e) => onChange({ status: (e.target.value || undefined) as ElevatorStatus | undefined })}
      >
        <option value="">{t('elevators.filters.allStatuses')}</option>
        {ELEVATOR_STATUSES.map((s) => (
          <option key={s} value={s}>{t(`elevators.status.${s}`)}</option>
        ))}
      </Select>
      {REGISTRY_FLAGS.map((flag) => (
        <label key={flag} className="flex items-center gap-2 text-[13px] text-text-secondary">
          <input
            type="checkbox"
            checked={flags.includes(flag)}
            onChange={(e) => toggleFlag(flag, e.target.checked)}
          />
          {t(`elevators.flags.${flag}`)}
        </label>
      ))}
      <label className="flex items-center gap-2 text-[13px] text-text-secondary">
        <input
          type="checkbox"
          checked={filters.include_archived ?? false}
          onChange={(e) => onChange({ include_archived: e.target.checked || undefined })}
        />
        {t('elevators.filters.includeArchived')}
      </label>
    </div>
  )
}
