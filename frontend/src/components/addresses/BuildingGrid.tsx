import { useTranslation } from 'react-i18next'
import type { BuildingBrief } from '../../types/api'
import { cn } from '@/lib/utils'
import EmptyState from '../shared/EmptyState'
import { ActionMenu, MenuItem } from './ActionMenu'

interface BuildingGridProps {
  buildings: BuildingBrief[]
  onBuildingClick: (building: BuildingBrief) => void
  onEdit: (building: BuildingBrief) => void
  onToggleActive: (building: BuildingBrief) => void
  onDelete: (building: BuildingBrief) => void
  onPurge: (building: BuildingBrief) => void
}

// FE-09: тайл-грид зданий (вынесен из AddressesPage без изменения поведения).
export default function BuildingGrid({
  buildings,
  onBuildingClick,
  onEdit,
  onToggleActive,
  onDelete,
  onPurge,
}: BuildingGridProps) {
  const { t } = useTranslation()

  if (buildings.length === 0) {
    return (
      <EmptyState
        icon={'\u{1F3E2}'}
        title={t('addresses.noBuildingsFound')}
        subtitle={t('addresses.noBuildingsFoundDesc')}
      />
    )
  }

  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
      {buildings.map(building => (
        <div
          key={building.id}
          onClick={() => onBuildingClick(building)}
          className="bg-bg-card border border-border-default rounded-default p-4 cursor-pointer transition-all relative hover:border-accent hover:shadow-[0_0_0_1px_var(--accent)]"
        >
          {/* Header */}
          <div className="flex items-start justify-between mb-2">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <div className={cn('w-2 h-2 rounded-full shrink-0', building.is_active ? 'bg-emerald' : 'bg-text-muted')} />
              <div className="font-[family-name:var(--font-display)] font-semibold text-[15px] text-text-primary truncate">
                {building.address}
              </div>
            </div>
            <ActionMenu>
              {(close) => (
                <>
                  <MenuItem label={t('common.edit')} onClick={() => { close(); onEdit(building) }} />
                  <MenuItem
                    label={building.is_active ? t('addresses.deactivate') : t('addresses.activate')}
                    onClick={() => { close(); onToggleActive(building) }}
                  />
                  <div className="h-px bg-border-default mx-2" />
                  {building.is_active ? (
                    <MenuItem
                      label={t('common.delete')}
                      danger
                      onClick={() => { close(); onDelete(building) }}
                    />
                  ) : (
                    <MenuItem
                      label={t('common.deletePermanently')}
                      danger
                      onClick={() => { close(); onPurge(building) }}
                    />
                  )}
                </>
              )}
            </ActionMenu>
          </div>

          {/* Details */}
          <div className="text-[13px] text-text-secondary mb-2.5 flex gap-3">
            <span>{t('addresses.entrance', { count: building.entrance_count })}</span>
            <span>{t('addresses.floor', { count: building.floor_count })}</span>
          </div>

          {/* Footer */}
          <div className="flex items-center gap-2 mt-1">
            <span className="bg-amber/[.13] text-amber rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">
              {t('addresses.apartment', { count: building.apartments_count })}
            </span>
            {!building.is_active && (
              <span className="bg-text-muted/[.13] text-text-muted rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">{t('addresses.inactive')}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
