import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { EmployeeBrief } from '../../hooks/useEmployees'
import { AVATAR_GRADIENTS, SPEC_COLORS, getInitials } from '../../utils/employeeUtils'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

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
      className={cn(
        'bg-bg-card border border-border-default rounded-default overflow-hidden flex flex-col transition-all duration-200',
        hovered && 'shadow-[0_12px_40px_rgba(0,0,0,0.3)] -translate-y-0.5'
      )}
    >
      {/* Card header */}
      <div className="p-5 pb-4 flex items-start gap-3.5 relative">
        {/* Avatar */}
        <div className="relative shrink-0">
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center font-[var(--font-display)] font-bold text-xl text-white tracking-wide"
            style={{ background: gradient }}
          >
            {initials}
          </div>
          {/* Status dot */}
          <div
            className={cn(
              'absolute bottom-0.5 right-0.5 w-3.5 h-3.5 rounded-full border-2 border-bg-card',
              isOnShift ? 'bg-emerald' : 'bg-[#5a6a7a]'
            )}
          />
        </div>

        {/* Name + phone */}
        <div className="flex-1 min-w-0">
          <div className="font-[var(--font-display)] font-semibold text-[15px] text-text-primary truncate">
            {name}
          </div>
          {employee.phone && (
            <div className="text-xs text-text-muted mt-0.5 font-[var(--font-mono)]">
              {employee.phone}
            </div>
          )}
          {/* Spec tags */}
          {employee.specialization.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {employee.specialization.map(spec => (
                <span
                  key={spec}
                  className="text-[10px] font-semibold px-1.5 py-0.5 rounded-[10px] tracking-wide"
                  style={{
                    background: `color-mix(in srgb, ${SPEC_COLORS[spec] ?? 'var(--text-muted)'} 13%, transparent)`,
                    color: SPEC_COLORS[spec] ?? 'var(--text-muted)',
                  }}
                >
                  {spec}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Verification / blocked badge */}
        <div className="absolute top-4 right-4 flex flex-col items-end gap-1">
          {isBlocked && (
            <div className="text-[10px] font-semibold px-2 py-0.5 rounded-[10px] bg-red/15 text-red">
              Заблокирован
            </div>
          )}
          <div
            className={cn(
              'text-[10px] font-semibold px-2 py-0.5 rounded-[10px]',
              isVerified
                ? 'bg-emerald/15 text-emerald'
                : 'bg-amber/15 text-amber'
            )}
          >
            {isVerified ? '✓ Верифицирован' : '⏳ На проверке'}
          </div>
        </div>
      </div>

      {/* Shift status bar */}
      <div className="grid grid-cols-2 bg-bg-surface border-t border-b border-border-default">
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
          <div
            key={i}
            className={cn(
              'p-2.5 text-center',
              i < 1 && 'border-r border-border-default'
            )}
          >
            <div
              className={cn(
                'font-[var(--font-mono)] text-[13px] font-semibold',
                cell.accent ? 'text-emerald' : 'text-text-primary'
              )}
            >
              {cell.value}
            </div>
            <div className="text-[10px] text-text-muted mt-0.5">
              {cell.label}
            </div>
          </div>
        ))}
      </div>

      {/* Card actions */}
      <div className="px-5 py-3 flex items-center gap-2 mt-auto">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate(`/dashboard/employees/${employee.id}`)}
          className="px-0 text-xs text-text-secondary"
        >
          Профиль
        </Button>
        <div className="flex-1" />
        {!isVerified ? (
          <Button
            size="sm"
            onClick={() => onVerify?.(employee)}
            className="text-xs"
          >
            Верифицировать
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={() => onAssign?.(employee)}
            className="text-xs"
          >
            Назначить
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onBlock?.(employee)}
          disabled={isBlockPending}
          className={cn(
            'text-xs px-2',
            isBlocked ? 'text-amber' : 'text-red'
          )}
        >
          {isBlocked ? 'Разблокировать' : 'Блок'}
        </Button>
      </div>
    </div>
  )
}
