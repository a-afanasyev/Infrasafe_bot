import type { EmployeeBrief } from '../../hooks/useEmployees'
import { AVATAR_GRADIENTS, SPEC_COLORS, getInitials } from '../../utils/employeeUtils'

interface Props {
  employee: EmployeeBrief
  onApprove: (id: number) => void
  onReject: (id: number) => void
  isPending?: boolean
}

export default function PendingApprovalCard({ employee, onApprove, onReject, isPending }: Props) {
  const gradient = AVATAR_GRADIENTS[employee.id % AVATAR_GRADIENTS.length]
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
          disabled={isPending}
          style={{
            background: 'var(--accent)',
            border: 'none',
            borderRadius: 8,
            cursor: isPending ? 'not-allowed' : 'pointer',
            fontSize: '12px',
            color: '#fff',
            padding: '7px 14px',
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
            opacity: isPending ? 0.6 : 1,
          }}
        >
          Одобрить
        </button>
        <button
          onClick={() => onReject(employee.id)}
          disabled={isPending}
          style={{
            background: 'none',
            border: '1px solid var(--red)',
            borderRadius: 8,
            cursor: isPending ? 'not-allowed' : 'pointer',
            fontSize: '12px',
            color: 'var(--red)',
            padding: '7px 14px',
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
            opacity: isPending ? 0.6 : 1,
          }}
        >
          Отклонить
        </button>
      </div>
    </div>
  )
}
