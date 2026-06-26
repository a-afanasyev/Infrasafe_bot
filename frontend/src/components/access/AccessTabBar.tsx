import { cn } from '@/lib/utils'

/**
 * Панель вкладок в стиле AddressTabBar (pill-кнопки) — общая для экранов
 * контроля доступа (пост охраны, база данных).
 */
export interface AccessTab {
  key: string
  label: string
  badge?: number
}

interface Props {
  tabs: AccessTab[]
  active: string
  onChange: (key: string) => void
}

export default function AccessTabBar({ tabs, active, onChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={cn(
            'rounded-full cursor-pointer text-[13px] px-4 py-1.5 font-[family-name:var(--font-display)] transition-all border',
            active === tab.key
              ? 'bg-accent border-accent text-white font-semibold'
              : 'bg-bg-card border-border-default text-text-secondary font-normal',
          )}
        >
          {tab.label}
          {tab.badge ? ` (${tab.badge})` : ''}
        </button>
      ))}
    </div>
  )
}
