import { useTranslation } from 'react-i18next'
import type { PublicElevatorYard } from '../../hooks/usePublicElevators'
import type { PublicElevatorsFilter } from './publicElevatorsFilter'

// Поиск по адресу/двору + селект двора (только при > 1 двора). Чипы статуса
// живут в PublicElevatorsSummary (это одни и те же чипы, что и на табло).
// Сами значения — из URL (страница передаёт filter/onChange), локального
// состояния нет: ссылку с фильтрами можно переслать.

const controlStyle: React.CSSProperties = {
  font: 'inherit',
  fontSize: '0.95rem',
  padding: '10px 14px',
  borderRadius: 10,
  border: '1px solid rgba(0,0,0,0.12)',
  background: '#fff',
  color: '#1a1a1a',
  minWidth: 0,
}

export interface PublicElevatorsFiltersProps {
  filter: PublicElevatorsFilter
  yards: PublicElevatorYard[]
  onChange: (patch: Partial<PublicElevatorsFilter>) => void
}

export default function PublicElevatorsFilters({ filter, yards, onChange }: PublicElevatorsFiltersProps) {
  const { t } = useTranslation()
  return (
    <div className="pe-filters" style={{ display: 'flex', gap: 10 }}>
      <input
        type="search"
        aria-label={t('publicElevators.searchLabel')}
        placeholder={t('publicElevators.searchPlaceholder')}
        value={filter.q}
        onChange={(e) => onChange({ q: e.target.value })}
        style={{ ...controlStyle, flex: 1 }}
      />
      {yards.length > 1 && (
        <select
          aria-label={t('publicElevators.yardLabel')}
          value={filter.yard ?? ''}
          onChange={(e) => onChange({ yard: e.target.value === '' ? null : Number(e.target.value) })}
          style={{ ...controlStyle, flex: '0 1 220px' }}
        >
          <option value="">{t('publicElevators.yardAll')}</option>
          {yards.map((y) => (
            <option key={y.id} value={y.id}>{y.name}</option>
          ))}
        </select>
      )}
    </div>
  )
}
