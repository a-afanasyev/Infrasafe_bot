import type { KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export type ShiftViewMode = 'day' | 'week' | 'month'

interface ShiftViewToggleProps {
  value: ShiftViewMode
  onChange: (next: ShiftViewMode) => void
}

const MODES: ShiftViewMode[] = ['day', 'week', 'month']

export default function ShiftViewToggle({ value, onChange }: ShiftViewToggleProps) {
  const { t } = useTranslation()

  function handleKey(e: KeyboardEvent<HTMLButtonElement>, idx: number) {
    // WCAG 2.1 SC 2.1.1 — `role="tablist"` with roving tabIndex requires
    // arrow-key navigation between tabs.
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    const next = e.key === 'ArrowLeft' ? (idx + MODES.length - 1) % MODES.length : (idx + 1) % MODES.length
    onChange(MODES[next])
  }

  return (
    <div
      role="tablist"
      aria-label={t('shifts.viewMode.label')}
      className="inline-flex items-center gap-1 p-1 rounded-default bg-bg-card border border-border-default"
    >
      {MODES.map((mode, idx) => {
        const isActive = value === mode
        return (
          <button
            key={mode}
            role="tab"
            aria-selected={isActive}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(mode)}
            onKeyDown={e => handleKey(e, idx)}
            className={cn(
              'px-3 py-1.5 rounded-sm text-xs font-semibold transition-colors',
              'font-[var(--font-display)]',
              isActive
                ? 'bg-accent-dim text-accent border border-border-active'
                : 'text-text-secondary hover:text-text-primary hover:bg-bg-card-hover border border-transparent',
            )}
          >
            {t(`shifts.viewMode.${mode}`)}
          </button>
        )
      })}
    </div>
  )
}
