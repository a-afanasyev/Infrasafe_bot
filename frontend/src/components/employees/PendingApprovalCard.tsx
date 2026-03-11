import type { EmployeeBrief } from '../../hooks/useEmployees'

interface Props {
  employee: EmployeeBrief
  onApprove: (id: number) => void
  onReject: (id: number) => void
}

const AVATAR_GRADIENTS = [
  'linear-gradient(135deg, #3b82f6, #2563eb)',
  'linear-gradient(135deg, #8b5cf6, #7c3aed)',
  'linear-gradient(135deg, #10b981, #059669)',
  'linear-gradient(135deg, #f59e0b, #d97706)',
  'linear-gradient(135deg, #00d4aa, #0099aa)',
]

const SPEC_COLORS: Record<string, string> = {
  'Электрика': 'var(--amber)',
  'Сантехника': 'var(--blue)',
  'Отопление': 'var(--red)',
  'Уборка': 'var(--emerald)',
  'Безопасность': 'var(--violet)',
  'Лифт': 'var(--cyan)',
  'Благоустройство': 'var(--green)',
  'Вентиляция': 'var(--teal)',
}

function getInitials(firstName: string | null, lastName: string | null): string {
  const f = firstName ? firstName[0] : ''
  const l = lastName ? lastName[0] : ''
  return (f + l).toUpperCase() || '?'
}

export default function PendingApprovalCard({ employee, onApprove, onReject }: Props) {
  const gradient = AVATAR_GRADIENTS[employee.id % 5]
  const initials = getInitials(employee.first_name, employee.last_name)
  const name = [employee.first_name, employee.last_name].filter(Boolean).join(' ') || 'Без имени'

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'row',
      alignItems: 'center',
      gap: '14px',
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding: '16px',
    }}>
      {/* Avatar 48px */}
      <div style={{
        width: 48,
        height: 48,
        borderRadius: '50%',
        background: gradient,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--font-display)',
        fontWeight: 700,
        fontSize: '16px',
        color: '#fff',
        flexShrink: 0,
      }}>
        {initials}
      </div>

      {/* Info column */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 600,
          fontSize: '14px',
          color: 'var(--text-primary)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {name}
        </div>
        {employee.phone && (
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 2 }}>
            {employee.phone}
          </div>
        )}
        {employee.specialization.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '6px' }}>
            {employee.specialization.map(spec => (
              <span key={spec} style={{
                fontSize: '10px',
                fontWeight: 600,
                padding: '2px 7px',
                borderRadius: 10,
                background: (SPEC_COLORS[spec] ?? 'var(--text-muted)') + '22',
                color: SPEC_COLORS[spec] ?? 'var(--text-muted)',
              }}>
                {spec}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Time-ago label */}
      <div style={{
        fontSize: '11px',
        color: 'var(--amber)',
        fontWeight: 500,
        flexShrink: 0,
        textAlign: 'right',
        marginRight: '4px',
      }}>
        Ожидает одобрения
      </div>

      {/* Button group */}
      <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
        <button
          onClick={() => onApprove(employee.id)}
          style={{
            background: 'var(--accent)',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontSize: '12px',
            color: '#fff',
            padding: '7px 14px',
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
          }}
        >
          Одобрить
        </button>
        <button
          onClick={() => onReject(employee.id)}
          style={{
            background: 'none',
            border: '1px solid var(--red)',
            borderRadius: 8,
            cursor: 'pointer',
            fontSize: '12px',
            color: 'var(--red)',
            padding: '7px 14px',
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
          }}
        >
          Отклонить
        </button>
      </div>
    </div>
  )
}
