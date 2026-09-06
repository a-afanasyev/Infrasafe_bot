import { useTranslation } from 'react-i18next'
import type { PublicElevator, PublicElevatorBuilding, PublicElevatorYard } from '../../hooks/usePublicElevators'
import PublicElevatorRow from './PublicElevatorRow'
import type { BuildingCount } from './publicElevatorsFilter'
import { cardStyle, monoStyle, statusStyle } from './publicElevatorStyles'

// Список страницы /elevators: двор (заголовок только при > 1 двора) → карточка
// дома с адресом и мини-счётчиком «N из M работают» → подъезды → строки лифтов.
// Сетка подъездов auto-fill 260px — на телефоне (≤ 600px) сама сжимается в колонку.

interface EntranceGroup {
  entrance: number
  elevators: PublicElevator[]
}

// Лифты дома уже отсортированы бэкендом подъезд → номер; группировка линейная.
function groupByEntrance(elevators: PublicElevator[]): EntranceGroup[] {
  return elevators.reduce<EntranceGroup[]>((groups, e) => {
    const last = groups[groups.length - 1]
    if (last && last.entrance === e.entrance_number) {
      return [...groups.slice(0, -1), { ...last, elevators: [...last.elevators, e] }]
    }
    return [...groups, { entrance: e.entrance_number, elevators: [e] }]
  }, [])
}

function BuildingCard({ building, count }: { building: PublicElevatorBuilding; count: BuildingCount | undefined }) {
  const { t } = useTranslation()
  const allWorking = count != null && count.total > 0 && count.working === count.total
  const counterPalette = allWorking ? statusStyle('working') : { color: '#6b7280', bg: '#f0ede6' }
  return (
    <div style={{ ...cardStyle, padding: '16px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1rem' }}>{building.address}</div>
        {count && (
          <span style={{ ...monoStyle, fontSize: '0.75rem', fontWeight: 700, padding: '4px 10px', borderRadius: 20, background: counterPalette.bg, color: counterPalette.color, whiteSpace: 'nowrap' }}>
            {t('board.elevators.workingOf', { count: count.working, total: count.total })}
          </span>
        )}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
        {groupByEntrance(building.elevators).map((group) => (
          <div key={group.entrance}>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#6b7280', marginBottom: 6 }}>
              {t('board.elevators.entrance', { entrance: group.entrance })}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {group.elevators.map((e) => (
                <PublicElevatorRow key={`${e.entrance_number}-${e.elevator_number}`} e={e} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export interface PublicElevatorsListProps {
  yards: PublicElevatorYard[]
  counts: Record<number, BuildingCount>
  showYardNames: boolean
}

export default function PublicElevatorsList({ yards, counts, showYardNames }: PublicElevatorsListProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {yards.map((yard) => (
        <div key={yard.id} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {showYardNames && (
            <div style={{ ...monoStyle, fontSize: '0.75rem', fontWeight: 700, color: '#2563eb', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              {yard.name}
            </div>
          )}
          {yard.buildings.map((b) => (
            <BuildingCard key={b.id} building={b} count={counts[b.id]} />
          ))}
        </div>
      ))}
    </div>
  )
}
