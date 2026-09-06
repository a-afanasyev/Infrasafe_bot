import { useTranslation } from 'react-i18next'
import { ELEVATOR_STATUSES, type ElevatorStatus } from '../../types/elevators'
import type { PublicElevatorsSummary } from '../../hooks/usePublicElevators'
import { NEUTRAL_STYLE, monoStyle, statusStyle, type StatusPalette } from './publicElevatorStyles'

// Чипы «Работают N · Не работают N · В ремонте N · На ТО N» с цветной точкой в
// палитре ElevatorStatusBadge. Два режима:
//  • табло (без onChange): статичные, нулевые скрыты (hideZero), «Работают» — всегда;
//  • страница /elevators (с onChange): кнопки-фильтры + чип «Все», aria-pressed.

type ChipKey = ElevatorStatus | 'all'

export interface ElevatorStatusChipsProps {
  counts: PublicElevatorsSummary
  hideZero?: boolean
  value?: ElevatorStatus | null
  onChange?: (status: ElevatorStatus | null) => void
}

function chipKeys(counts: PublicElevatorsSummary, interactive: boolean, hideZero: boolean): ChipKey[] {
  const statuses = ELEVATOR_STATUSES.filter((s) => !hideZero || s === 'working' || counts[s] > 0)
  return interactive ? ['all', ...statuses] : statuses
}

function chipStyle(palette: StatusPalette, selected: boolean, interactive: boolean): React.CSSProperties {
  // `font: inherit` — ПЕРВЫМ: шорткат сбрасывает размер/вес, заданные после него
  // (нужен, чтобы <button> не брал UA-шрифт).
  return {
    font: 'inherit',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 12px',
    borderRadius: 20,
    border: `1px solid ${selected ? palette.color : 'transparent'}`,
    background: selected ? palette.color : palette.bg,
    color: selected ? '#fff' : palette.color,
    fontSize: '0.82rem',
    fontWeight: 700,
    lineHeight: 1.2,
    whiteSpace: 'nowrap',
    cursor: interactive ? 'pointer' : 'default',
  }
}

export default function ElevatorStatusChips({ counts, hideZero = false, value = null, onChange }: ElevatorStatusChipsProps) {
  const { t } = useTranslation()
  const interactive = onChange != null

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      {chipKeys(counts, interactive, hideZero).map((key) => {
        const isAll = key === 'all'
        const palette = isAll ? { color: '#1a1a1a', bg: NEUTRAL_STYLE.bg } : statusStyle(key)
        const selected = interactive && (isAll ? value == null : value === key)
        const content = (
          <>
            {!isAll && <span aria-hidden style={{ width: 8, height: 8, borderRadius: '50%', background: selected ? '#fff' : palette.color, flexShrink: 0 }} />}
            <span>{t(`board.elevators.chips.${key}`)}</span>{' '}
            <span style={{ ...monoStyle, fontWeight: 700 }}>{isAll ? counts.total : counts[key]}</span>
          </>
        )
        const shared = { 'data-testid': 'elevator-status-chip', 'data-status': key, style: chipStyle(palette, selected, interactive) }
        return interactive ? (
          <button key={key} type="button" aria-pressed={selected} onClick={() => onChange(isAll ? null : key)} {...shared}>
            {content}
          </button>
        ) : (
          <span key={key} {...shared}>{content}</span>
        )
      })}
    </div>
  )
}
