import { useTranslation } from 'react-i18next'
import type { ElevatorStatus } from '../../types/elevators'
import type { PublicElevatorsSummary as Summary } from '../../hooks/usePublicElevators'
import ElevatorStatusChips from './ElevatorStatusChips'
import { monoStyle, statusStyle } from './publicElevatorStyles'

// «84 из 100 работают» + чипы по одной и той же сводке. На табло — общая сводка
// ответа, статичные чипы (нулевые скрыты); на странице /elevators — сводка в
// пределах двора/поиска, чипы = фильтр по статусу.

export interface PublicElevatorsSummaryProps {
  summary: Summary
  hideZero?: boolean
  value?: ElevatorStatus | null
  onChange?: (status: ElevatorStatus | null) => void
}

export default function PublicElevatorsSummary({ summary, hideZero, value, onChange }: PublicElevatorsSummaryProps) {
  const { t } = useTranslation()
  const allWorking = summary.total > 0 && summary.working === summary.total
  const headlineColor = allWorking ? statusStyle('working').color : '#1a1a1a'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ ...monoStyle, fontWeight: 800, fontSize: 'clamp(1.4rem, 5vw, 2rem)', letterSpacing: '-0.03em', lineHeight: 1.1, color: headlineColor }}>
        {t('board.elevators.workingOf', { count: summary.working, total: summary.total })}
      </div>
      <ElevatorStatusChips counts={summary} hideZero={hideZero} value={value} onChange={onChange} />
    </div>
  )
}
