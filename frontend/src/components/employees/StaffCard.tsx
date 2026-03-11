import { useState } from 'react'
import type { EmployeeBrief, EmployeeDetail, ShiftBrief } from '../../hooks/useEmployees'
import { formatTime } from '../../utils/timezone'

interface Props {
  employee: EmployeeBrief
  onAssign?: (employee: EmployeeBrief) => void
  onBlock?: (employee: EmployeeBrief) => void
  onVerify?: (employee: EmployeeBrief) => void
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

function getActiveShift(emp: EmployeeBrief): ShiftBrief | null {
  return (emp as Partial<EmployeeDetail>).active_shift ?? null
}

function getRating(emp: EmployeeBrief): number | null {
  return (emp as Partial<EmployeeDetail>).rating ?? null
}

function getTotalShifts(emp: EmployeeBrief): number {
  return (emp as Partial<EmployeeDetail>).total_shifts ?? 0
}

function getTotalCompleted(emp: EmployeeBrief): number {
  return (emp as Partial<EmployeeDetail>).total_completed ?? 0
}

export default function StaffCard({ employee, onAssign, onBlock, onVerify }: Props) {
  const [hovered, setHovered] = useState(false)

  const gradient = AVATAR_GRADIENTS[employee.id % 5]
  const initials = getInitials(employee.first_name, employee.last_name)
  const isOnShift = employee.active_shift_id !== null
  const isVerified = employee.verification_status === 'verified'
  const activeShift = getActiveShift(employee)
  const rating = getRating(employee)
  const totalShifts = getTotalShifts(employee)
  const totalCompleted = getTotalCompleted(employee)
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
          {/* Status dot */}
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
                  background: (SPEC_COLORS[spec] ?? 'var(--text-muted)') + '22',
                  color: SPEC_COLORS[spec] ?? 'var(--text-muted)',
                  letterSpacing: '0.3px',
                }}>
                  {spec}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Verification badge */}
        <div style={{
          position: 'absolute',
          top: 16,
          right: 16,
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

      {/* Metrics grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        background: 'var(--bg-surface)',
        borderTop: '1px solid var(--border)',
        borderBottom: '1px solid var(--border)',
      }}>
        {[
          {
            value: totalCompleted,
            label: 'Выполнено',
            accent: true,
          },
          {
            value: totalShifts,
            label: 'смен',
            accent: false,
          },
          {
            value: rating !== null ? `★ ${rating.toFixed(1)}` : '—',
            label: 'рейтинг',
            accent: false,
            amber: rating !== null,
          },
        ].map((cell, i) => (
          <div key={i} style={{
            padding: '10px',
            textAlign: 'center',
            borderRight: i < 2 ? '1px solid var(--border)' : 'none',
          }}>
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '16px',
              fontWeight: 600,
              color: cell.accent ? 'var(--accent)' : cell.amber ? 'var(--amber)' : 'var(--text-primary)',
            }}>
              {String(cell.value)}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: 2 }}>
              {cell.label}
            </div>
          </div>
        ))}
      </div>

      {/* Active shift info bar */}
      {activeShift && (
        <div style={{
          padding: '8px 20px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          borderBottom: '1px solid var(--border)',
          background: 'rgba(16,185,129,0.05)',
        }}>
          <div style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: 'var(--emerald)',
            flexShrink: 0,
          }} />
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>На смене сейчас</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-primary)', marginLeft: 'auto' }}>
            {formatTime(activeShift.start_time)}
            {activeShift.end_time ? ` – ${formatTime(activeShift.end_time)}` : ''}
          </span>
        </div>
      )}

      {/* Card actions */}
      <div style={{
        padding: '12px 20px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        borderTop: activeShift ? 'none' : '1px solid var(--border)',
        marginTop: 'auto',
      }}>
        <button
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
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '12px',
            color: 'var(--red)',
            padding: '6px 8px',
            fontFamily: 'var(--font-display)',
          }}
        >
          Блок
        </button>
      </div>
    </div>
  )
}
