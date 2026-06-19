import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

type View = 'directory' | 'moderation'

interface AddressTabBarProps {
  view: View
  onViewChange: (view: View) => void
  viewMode: 'tile' | 'table'
  onViewModeChange: (mode: 'tile' | 'table') => void
  showInactive: boolean
  onShowInactiveChange: (value: boolean) => void
  moderationCount: number
}

// FE-09: панель вкладок «справочник/модерация» + переключатель вид/неактивные
// (вынесена из AddressesPage без изменения поведения).
export default function AddressTabBar({
  view,
  onViewChange,
  viewMode,
  onViewModeChange,
  showInactive,
  onShowInactiveChange,
  moderationCount,
}: AddressTabBarProps) {
  const { t } = useTranslation()

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => onViewChange('directory')}
        className={cn(
          'rounded-full cursor-pointer text-[13px] px-4 py-1.5 font-[family-name:var(--font-display)] transition-all border',
          view === 'directory'
            ? 'bg-accent border-accent text-white font-semibold'
            : 'bg-bg-card border-border-default text-text-secondary font-normal'
        )}
      >
        {t('addresses.directory')}
      </button>
      <button
        onClick={() => onViewChange('moderation')}
        className={cn(
          'rounded-full cursor-pointer text-[13px] px-4 py-1.5 font-[family-name:var(--font-display)] transition-all border',
          view === 'moderation'
            ? 'bg-accent border-accent text-white font-semibold'
            : 'bg-bg-card border-border-default text-text-secondary font-normal'
        )}
      >
        {t('addresses.moderation')}{moderationCount > 0 ? ` (${moderationCount})` : ''}
      </button>

      <div className="flex-1" />

      {/* View toggle */}
      {view === 'directory' && (
        <div className="flex gap-1">
          <button
            onClick={() => onViewModeChange('tile')}
            className={cn(
              'border rounded-md cursor-pointer text-base px-2.5 py-1 leading-none transition-all',
              viewMode === 'tile'
                ? 'bg-accent border-accent text-white'
                : 'bg-transparent border-border-default text-text-muted'
            )}
            title={t('employees.viewTile')}
          >{'⊞'}</button>
          <button
            onClick={() => onViewModeChange('table')}
            className={cn(
              'border rounded-md cursor-pointer text-base px-2.5 py-1 leading-none transition-all',
              viewMode === 'table'
                ? 'bg-accent border-accent text-white'
                : 'bg-transparent border-border-default text-text-muted'
            )}
            title={t('employees.viewTable')}
          >{'☰'}</button>
        </div>
      )}

      {/* Show inactive toggle */}
      {view === 'directory' && (
        <label className="flex items-center gap-1.5 text-xs text-text-muted cursor-pointer font-[family-name:var(--font-display)]">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={e => onShowInactiveChange(e.target.checked)}
            className="accent-accent"
          />
          {t('addresses.showInactive')}
        </label>
      )}
    </div>
  )
}
