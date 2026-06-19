import { useTranslation } from 'react-i18next'
import type { YardBrief } from '../../types/api'
import { cn } from '@/lib/utils'
import EmptyState from '../shared/EmptyState'
import { ActionMenu, MenuItem } from './ActionMenu'

interface YardGridProps {
  yards: YardBrief[]
  onYardClick: (yard: YardBrief) => void
  onEdit: (yard: YardBrief) => void
  onToggleActive: (yard: YardBrief) => void
  onDelete: (yard: YardBrief) => void
  onPurge: (yard: YardBrief) => void
}

// FE-09: тайл-грид дворов (вынесен из AddressesPage без изменения поведения).
export default function YardGrid({
  yards,
  onYardClick,
  onEdit,
  onToggleActive,
  onDelete,
  onPurge,
}: YardGridProps) {
  const { t } = useTranslation()

  if (yards.length === 0) {
    return (
      <EmptyState
        icon={'\u{1F3D8}'}
        title={t('addresses.noAddresses')}
        subtitle={t('addresses.noAddressesDesc')}
      />
    )
  }

  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
      {yards.map(yard => (
        <div
          key={yard.id}
          onClick={() => onYardClick(yard)}
          className="bg-bg-card border border-border-default rounded-default p-4 cursor-pointer transition-all relative hover:border-accent hover:shadow-[0_0_0_1px_var(--accent)]"
        >
          {/* Header */}
          <div className="flex items-start justify-between mb-2">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <div className={cn('w-2 h-2 rounded-full shrink-0', yard.is_active ? 'bg-emerald' : 'bg-text-muted')} />
              <div className="font-[family-name:var(--font-display)] font-semibold text-[15px] text-text-primary truncate">
                {yard.name}
              </div>
            </div>
            <ActionMenu>
              {(close) => (
                <>
                  <MenuItem label={t('common.edit')} onClick={() => { close(); onEdit(yard) }} />
                  <MenuItem
                    label={yard.is_active ? t('addresses.deactivate') : t('addresses.activate')}
                    onClick={() => { close(); onToggleActive(yard) }}
                  />
                  <div className="h-px bg-border-default mx-2" />
                  {yard.is_active ? (
                    <MenuItem
                      label={t('common.delete')}
                      danger
                      onClick={() => { close(); onDelete(yard) }}
                    />
                  ) : (
                    <MenuItem
                      label={t('common.deletePermanently')}
                      danger
                      onClick={() => { close(); onPurge(yard) }}
                    />
                  )}
                </>
              )}
            </ActionMenu>
          </div>

          {/* Description */}
          {yard.description && (
            <div className="text-[13px] text-text-secondary mb-2.5 line-clamp-2 leading-snug">
              {yard.description}
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center gap-2 mt-1">
            <span className="bg-blue/[.13] text-blue rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">
              {t('addresses.building', { count: yard.buildings_count })}
            </span>
            {!yard.is_active && (
              <span className="bg-text-muted/[.13] text-text-muted rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">{t('addresses.inactive')}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
