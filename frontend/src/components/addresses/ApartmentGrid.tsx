import { useTranslation } from 'react-i18next'
import type { ApartmentBrief } from '../../types/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import EmptyState from '../shared/EmptyState'
import { ActionMenu, MenuItem } from './ActionMenu'

interface ApartmentGridProps {
  apartments: ApartmentBrief[]
  onProfileClick: (apt: ApartmentBrief) => void
  onEdit: (apt: ApartmentBrief) => void
  onToggleActive: (apt: ApartmentBrief) => void
  onDelete: (apt: ApartmentBrief) => void
  onPurge: (apt: ApartmentBrief) => void
  onBulkCreate: () => void
}

// FE-09: тайл-грид квартир + кнопка массового создания (вынесено из
// AddressesPage без изменения поведения).
export default function ApartmentGrid({
  apartments,
  onProfileClick,
  onEdit,
  onToggleActive,
  onDelete,
  onPurge,
  onBulkCreate,
}: ApartmentGridProps) {
  const { t } = useTranslation()

  return (
    <>
      {/* Bulk create button */}
      <div className="flex justify-end">
        <Button variant="outline" onClick={onBulkCreate}>
          {t('addresses.bulkCreate')}
        </Button>
      </div>

      {apartments.length === 0 ? (
        <EmptyState
          icon={'\u{1F3E0}'}
          title={t('addresses.noApartmentsFound')}
          subtitle={t('addresses.noApartmentsFoundDesc')}
        />
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
          {apartments.map(apt => (
            <div
              key={apt.id}
              className="bg-bg-card border border-border-default rounded-default p-4 cursor-pointer transition-all relative hover:border-accent hover:shadow-[0_0_0_1px_var(--accent)]"
              onClick={() => onProfileClick(apt)}
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className={cn('w-2 h-2 rounded-full shrink-0', apt.is_active ? 'bg-emerald' : 'bg-text-muted')} />
                  <div className="font-[family-name:var(--font-mono)] font-bold text-xl text-text-primary">
                    {apt.apartment_number}
                  </div>
                </div>
                <ActionMenu>
                  {(close) => (
                    <>
                      <MenuItem label={t('common.edit')} onClick={() => { close(); onEdit(apt) }} />
                      <MenuItem
                        label={apt.is_active ? t('addresses.deactivate') : t('addresses.activate')}
                        onClick={() => { close(); onToggleActive(apt) }}
                      />
                      <div className="h-px bg-border-default mx-2" />
                      {apt.is_active ? (
                        <MenuItem
                          label={t('common.delete')}
                          danger
                          onClick={() => { close(); onDelete(apt) }}
                        />
                      ) : (
                        <MenuItem
                          label={t('common.deletePermanently')}
                          danger
                          onClick={() => { close(); onPurge(apt) }}
                        />
                      )}
                    </>
                  )}
                </ActionMenu>
              </div>

              {/* Details */}
              <div className="text-xs text-text-secondary flex flex-col gap-0.5">
                {apt.building_address && (
                  <div className="text-text-muted">{apt.building_address}</div>
                )}
                <div className="flex gap-3">
                  {apt.floor != null && <span>{t('addresses.floor')}: {apt.floor}</span>}
                  {apt.entrance != null && <span>{t('addresses.entrance')}: {apt.entrance}</span>}
                  {apt.area != null && <span>{apt.area} м&sup2;</span>}
                </div>
              </div>

              {/* Footer */}
              <div className="flex items-center gap-2 mt-2.5">
                <span className="bg-violet/[.13] text-violet rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">
                  {t('addresses.resident', { count: apt.residents_count })}
                </span>
                {!apt.is_active && (
                  <span className="bg-text-muted/[.13] text-text-muted rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">{t('addresses.inactive')}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
