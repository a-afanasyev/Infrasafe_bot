import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { EmployeeBrief } from '../../hooks/useEmployees'
import { AVATAR_GRADIENTS, SPEC_COLORS, getInitials } from '../../utils/employeeUtils'

interface Props {
  employee: EmployeeBrief
  onAssign?: (employee: EmployeeBrief) => void
  onBlock?: (employee: EmployeeBrief) => void
  onVerify?: (employee: EmployeeBrief) => void
  isBlockPending?: boolean
}

export default function StaffCard({ employee, onAssign, onBlock, onVerify, isBlockPending }: Props) {
  const [hovered, setHovered] = useState(false)
  const navigate = useNavigate()

  const gradient = AVATAR_GRADIENTS[employee.id % AVATAR_GRADIENTS.length]
  const initials = getInitials(employee.first_name, employee.last_name)
  const isOnShift = employee.active_shift_id !== null
  const isVerified = employee.verification_status === 'verified'
  const isBlocked = employee.status === 'blocked'
  const name = [employee.first_name, employee.last_name].filter(Boolean).join(' ') || 'Без имени'

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        transition: 'transform 0.2s, box-shadow 0.2s',
        transform: hovered ? 'translateY(-2px)' : 'translateY(0)',
        boxShadow: hovered ? '0 12px 40px rgba(0,0,0,0.3)' : 'none',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Card header */}
      <div style={{ padding: '20px 20px 16px', display: 'flex', alignItems: 'flex-start', gap: '14px', position: 'relative' }}>
        {/* Avatar */}
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <div style={{
            width: 56,
            height: 56,
            borderRadius: '50%',
            background: gradient,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: '20px',
            color: '#fff',
            letterSpacing: '0.5px',
          }}>
            {initials}
          </div>
          {/* Status dot: green = on shift, gray = off shift */}
          <div style={{
            position: 'absolute',
            bottom: 1,
            right: 1,
            width: 14,
            height: 14,
            borderRadius: '50%',
            background: isOnShift ? 'var(--emerald)' : '#5a6a7a',
            border: '2px solid var(--bg-card)',
          }} />
        </div>

        {/* Name + phone */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
            fontSize: '15px',
            color: 'var(--text-primary)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}>
            {name}
          </div>
          {employee.phone && (
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 3, fontFamily: 'var(--font-mono)' }}>
              {employee.phone}
            </div>
          )}
          {/* Spec tags */}
          {employee.specialization.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '8px' }}>
              {employee.specialization.map(spec => (
                <span key={spec} style={{
                  fontSize: '10px',
                  fontWeight: 600,
                  padding: '2px 7px',
                  borderRadius: 10,
                  background: `color-mix(in srgb, ${SPEC_COLORS[spec] ?? 'var(--text-muted)'} 13%, transparent)`,
                  color: SPEC_COLORS[spec] ?? 'var(--text-muted)',
                  letterSpacing: '0.3px',
                }}>
                  {spec}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Verification / blocked badge */}
        <div style={{
          position: 'absolute',
          top: 16,
          right: 16,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: '4px',
        }}>
          {isBlocked && (
            <div style={{
              fontSize: '10px',
              fontWeight: 600,
              padding: '3px 8px',
              borderRadius: 10,
              background: 'rgba(239,68,68,0.15)',
              color: 'var(--red)',
            }}>
              Заблокирован
            </div>
          )}
          <div style={{
            fontSize: '10px',
            fontWeight: 600,
            padding: '3px 8px',
            borderRadius: 10,
            background: isVerified ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
            color: isVerified ? 'var(--emerald)' : 'var(--amber)',
          }}>
            {isVerified ? '✓ Верифицирован' : '⏳ На проверке'}
          </div>
        </div>
      </div>

      {/* Shift status bar */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, 1fr)',
        background: 'var(--bg-surface)',
        borderTop: '1px solid var(--border)',
        borderBottom: '1px solid var(--border)',
      }}>
        {[
          {
            value: isOnShift ? 'На смене' : 'Не на смене',
            label: 'статус',
            accent: isOnShift,
          },
          {
            value: employee.active_shift_id !== null ? `#${employee.active_shift_id}` : '—',
            label: 'смена',
            accent: false,
          },
        ].map((cell, i) => (
          <div key={i} style={{
            padding: '10px',
            textAlign: 'center',
            borderRight: i < 1 ? '1px solid var(--border)' : 'none',
          }}>
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
              fontWeight: 600,
              color: cell.accent ? 'var(--emerald)' : 'var(--text-primary)',
            }}>
              {cell.value}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: 2 }}>
              {cell.label}
            </div>
          </div>
        ))}
      </div>

      {/* Card actions */}
      <div style={{
        padding: '12px 20px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginTop: 'auto',
      }}>
        <button
          onClick={() => navigate(`/dashboard/employees/${employee.id}`)}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '12px',
            color: 'var(--text-secondary)',
            padding: '6px 0',
            fontFamily: 'var(--font-display)',
          }}
        >
          Профиль
        </button>
        <div style={{ flex: 1 }} />
        {!isVerified ? (
          <button
            onClick={() => onVerify?.(employee)}
            style={{
              background: 'var(--accent)',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontSize: '12px',
              color: '#fff',
              padding: '6px 12px',
              fontFamily: 'var(--font-display)',
              fontWeight: 600,
            }}
          >
            Верифицировать
          </button>
        ) : (
          <button
            onClick={() => onAssign?.(employee)}
            style={{
              background: 'var(--accent)',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontSize: '12px',
              color: '#fff',
              padding: '6px 12px',
              fontFamily: 'var(--font-display)',
              fontWeight: 600,
            }}
          >
            Назначить
          </button>
        )}
        <button
          onClick={() => onBlock?.(employee)}
          disabled={isBlockPending}
          style={{
            background: 'none',
            border: 'none',
            cursor: isBlockPending ? 'not-allowed' : 'pointer',
            fontSize: '12px',
            color: isBlocked ? 'var(--amber)' : 'var(--red)',
            padding: '6px 8px',
            fontFamily: 'var(--font-display)',
            opacity: isBlockPending ? 0.5 : 1,
          }}
        >
          {isBlocked ? 'Разблокировать' : 'Блок'}
        </button>
      </div>
    </div>
  )
}
