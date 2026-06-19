import { useTranslation } from 'react-i18next'
import type { YardBrief, BuildingBrief } from '../../types/api'
import { cn } from '@/lib/utils'
import { Select } from '@/components/ui/select'

type Level = 'yards' | 'buildings' | 'apartments' | 'all-buildings' | 'all-apartments'

interface AddressBreadcrumbProps {
  level: Level
  selectedYard: YardBrief | null
  selectedBuilding: BuildingBrief | null
  yards: YardBrief[]
  filterYardId: number | null
  filterBuildingId: number | null
  filterBuildings: BuildingBrief[]
  onFilterYardChange: (value: number | null) => void
  onFilterBuildingChange: (value: number | null) => void
  goToYards: () => void
  goToBuildings: () => void
}

// FE-09: хлебные крошки/заголовок справочника + фильтры плоских видов
// (вынесено из AddressesPage без изменения поведения).
export default function AddressBreadcrumb({
  level,
  selectedYard,
  selectedBuilding,
  yards,
  filterYardId,
  filterBuildingId,
  filterBuildings,
  onFilterYardChange,
  onFilterBuildingChange,
  goToYards,
  goToBuildings,
}: AddressBreadcrumbProps) {
  const { t } = useTranslation()

  if (level === 'all-buildings') {
    return (
      <div className="flex items-center gap-3 text-[13px] font-[family-name:var(--font-display)]">
        <span className="text-text-primary font-semibold">{t('addresses.allBuildings')}</span>
        <Select
          value={filterYardId ?? ''}
          onChange={e => onFilterYardChange(e.target.value ? Number(e.target.value) : null)}
          className="w-[250px] text-xs"
        >
          <option value="">{t('addresses.allYards')}</option>
          {yards.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}
        </Select>
      </div>
    )
  }

  if (level === 'all-apartments') {
    return (
      <div className="flex items-center gap-3 text-[13px] font-[family-name:var(--font-display)]">
        <span className="text-text-primary font-semibold">{t('addresses.allApartments')}</span>
        <Select
          value={filterYardId ?? ''}
          onChange={e => { onFilterYardChange(e.target.value ? Number(e.target.value) : null); onFilterBuildingChange(null) }}
          className="w-[250px] text-xs"
        >
          <option value="">{t('addresses.allYards')}</option>
          {yards.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}
        </Select>
        <Select
          value={filterBuildingId ?? ''}
          onChange={e => onFilterBuildingChange(e.target.value ? Number(e.target.value) : null)}
          className="w-[250px] text-xs"
        >
          <option value="">{t('addresses.allBuildings')}</option>
          {filterBuildings.map(b => <option key={b.id} value={b.id}>{b.address}</option>)}
        </Select>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5 text-[13px] font-[family-name:var(--font-display)]">
      <span
        onClick={goToYards}
        className={cn(
          'cursor-pointer',
          level === 'yards' ? 'text-text-primary font-semibold' : 'text-accent'
        )}
      >
        {t('addresses.stats.yards')}
      </span>
      {selectedYard && (
        <>
          <span className="text-text-muted">&rsaquo;</span>
          <span
            onClick={goToBuildings}
            className={cn(
              level === 'buildings' ? 'text-text-primary font-semibold cursor-default' : 'text-accent cursor-pointer'
            )}
          >
            {selectedYard.name}
          </span>
        </>
      )}
      {selectedBuilding && (
        <>
          <span className="text-text-muted">&rsaquo;</span>
          <span className="text-text-primary font-semibold">
            {selectedBuilding.address}
          </span>
        </>
      )}
    </div>
  )
}
