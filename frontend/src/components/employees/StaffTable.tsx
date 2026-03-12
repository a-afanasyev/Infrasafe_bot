// frontend/src/components/employees/StaffTable.tsx
import type { EmployeeBrief } from '../../hooks/useEmployees'
import { AVATAR_GRADIENTS, SPEC_COLORS, SPEC_DISPLAY, getInitials } from '../../utils/employeeUtils'
import EmptyState from '../shared/EmptyState'

interface Props {
  employees: EmployeeBrief[]
  onAssign: (e: EmployeeBrief) => void
  onBlock: (e: EmployeeBrief) => void
  isBlockPending: boolean
}

const HEADERS = ['Сотрудник', 'Специализация', 'Верификация', 'Статус', 'Смена', 'Действия']
const COLS = '2.2fr 1.6fr 1fr 0.8fr 0.8fr 1fr'

function specColor(key: string): string {
  const label = (SPEC_DISPLAY[key] ?? key).replace(/^\S+\s/, '') // strip emoji prefix
  return SPEC_COLORS[label] ?? 'var(--text-muted)'
}

export default function StaffTable({ employees, onAssign, onBlock, isBlockPending }: Props) {
  if (employees.length === 0) {
    return (
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '40px',
      }}>
        <EmptyState icon="👥" title="Сотрудники не найдены" subtitle="Попробуйте другой фильтр" />
      </div>
    )
  }

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: COLS,
        background: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border)',
        padding: '10px 16px',
        gap: '8px',
      }}>
        {HEADERS.map(h => (
          <span key={h} style={{
            color: 'var(--text-muted)',
            fontSize: '10px',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
            fontFamily: 'var(--font-display)',
          }}>
            {h}
          </span>
        ))}
      </div>

      {/* Rows */}
      {employees.map((emp, idx) => {
        const gradient = AVATAR_GRADIENTS[emp.id % AVATAR_GRADIENTS.length]
        const initials = getInitials(emp.first_name, emp.last_name)
        const isOnShift = emp.active_shift_id !== null
        const isVerified = emp.verification_status === 'verified'
        const isBlocked = emp.status === 'blocked'
        const name = [emp.first_name, emp.last_name].filter(Boolean).join(' ') || 'Без имени'
        const isLast = idx === employees.length - 1

        return (
          <div
            key={emp.id}
            style={{
              display: 'grid',
              gridTemplateColumns: COLS,
              padding: '10px 16px',
              gap: '8px',
              borderBottom: isLast ? 'none' : '1px solid var(--border)',
              alignItems: 'center',
              opacity: isBlocked ? 0.6 : 1,
            }}
          >
            {/* Сотрудник */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ position: 'relative', flexShrink: 0 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: '50%', background: gradient,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#fff', fontSize: '11px', fontWeight: 700,
                  fontFamily: 'var(--font-display)',
                }}>
                  {initials}
                </div>
                <div style={{
                  position: 'absolute', bottom: 0, right: 0,
                  width: 10, height: 10, borderRadius: '50%',
                  background: isOnShift ? 'var(--emerald)' : '#5a6a7a',
                  border: '2px solid var(--bg-card)',
                }} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{
                  fontFamily: 'var(--font-display)', fontWeight: 600,
                  fontSize: '12px', color: 'var(--text-primary)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {name}
                </div>
                {emp.phone && (
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {emp.phone}
                  </div>
                )}
              </div>
            </div>

            {/* Специализация */}
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
              {emp.specialization.length > 0
                ? emp.specialization.map(spec => {
                    const label = SPEC_DISPLAY[spec] ?? spec
                    const color = specColor(spec)
                    return (
                      <span key={spec} style={{
                        fontSize: '10px', fontWeight: 600, padding: '2px 7px', borderRadius: 10,
                        background: color + '22', color,
                      }}>
                        {label}
                      </span>
                    )
                  })
                : <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>—</span>
              }
            </div>

            {/* Верификация */}
            <div>
              <span style={{
                fontSize: '10px', fontWeight: 600, padding: '2px 7px', borderRadius: 10,
                background: isVerified ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
                color: isVerified ? 'var(--emerald)' : 'var(--amber)',
              }}>
                {isVerified ? '✓ Верифицирован' : '⏳ На проверке'}
              </span>
            </div>

            {/* Статус */}
            <div>
              <span style={{
                color: isOnShift ? 'var(--emerald)' : '#5a6a7a',
                fontSize: '11px',
                fontWeight: isOnShift ? 600 : 400,
              }}>
                ● {isOnShift ? 'На смене' : 'Не на смене'}
              </span>
            </div>

            {/* Смена */}
            <div style={{ color: 'var(--text-muted)', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
              {emp.active_shift_id !== null ? `#${emp.active_shift_id}` : '—'}
            </div>

            {/* Действия */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {isBlocked ? (
                <>
                  <span style={{
                    fontSize: '10px', fontWeight: 600, padding: '2px 7px', borderRadius: 10,
                    background: 'rgba(239,68,68,0.15)', color: 'var(--red)',
                  }}>
                    Заблокирован
                  </span>
                  <button
                    onClick={() => onBlock(emp)}
                    disabled={isBlockPending}
                    style={{
                      background: 'none', border: 'none', cursor: isBlockPending ? 'not-allowed' : 'pointer',
                      fontSize: '11px', color: 'var(--amber)',
                      fontFamily: 'var(--font-display)', opacity: isBlockPending ? 0.5 : 1,
                    }}
                  >
                    Разблок
                  </button>
                </>
              ) : (
                <>
                  {isVerified && (
                    <button
                      onClick={() => onAssign(emp)}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        fontSize: '11px', color: 'var(--accent)',
                        fontFamily: 'var(--font-display)', fontWeight: 600,
                      }}
                    >
                      Назначить
                    </button>
                  )}
                  <button
                    onClick={() => onBlock(emp)}
                    disabled={isBlockPending}
                    style={{
                      background: 'none', border: 'none', cursor: isBlockPending ? 'not-allowed' : 'pointer',
                      fontSize: '11px', color: 'var(--red)',
                      fontFamily: 'var(--font-display)', opacity: isBlockPending ? 0.5 : 1,
                    }}
                  >
                    Блок
                  </button>
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
