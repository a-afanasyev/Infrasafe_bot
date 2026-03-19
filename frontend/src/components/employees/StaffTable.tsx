// frontend/src/components/employees/StaffTable.tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { EmployeeBrief } from '../../hooks/useEmployees'
import { AVATAR_GRADIENTS, SPEC_COLORS, SPEC_DISPLAY, getInitials } from '../../utils/employeeUtils'
import EmptyState from '../shared/EmptyState'
import { cn } from '@/lib/utils'

interface Props {
  employees: EmployeeBrief[]
  onAssign: (e: EmployeeBrief) => void
  onBlock: (e: EmployeeBrief) => void
  isBlockPending: boolean
}

const HEADERS = ['Сотрудник', 'Специализация', 'Верификация', 'Статус', 'Смена', 'Действия']

function specColor(key: string): string {
  const label = (SPEC_DISPLAY[key] ?? key).replace(/^\S+\s/, '') // strip emoji prefix
  return SPEC_COLORS[label] ?? 'var(--text-muted)'
}

export default function StaffTable({ employees, onAssign, onBlock, isBlockPending }: Props) {
  const [hoveredId, setHoveredId] = useState<number | null>(null)
  const navigate = useNavigate()
  if (employees.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default p-10">
        <EmptyState icon="👥" title="Сотрудники не найдены" subtitle="Попробуйте другой фильтр" />
      </div>
    )
  }

  return (
    <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-bg-surface border-b border-border-default">
            {HEADERS.map(h => (
              <th
                key={h}
                className="px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted font-[var(--font-display)]"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {employees.map((emp, idx) => {
            const gradient = AVATAR_GRADIENTS[emp.id % AVATAR_GRADIENTS.length]
            const initials = getInitials(emp.first_name, emp.last_name)
            const isOnShift = emp.active_shift_id !== null
            const isVerified = emp.verification_status === 'verified'
            const isBlocked = emp.status === 'blocked'
            const name = [emp.first_name, emp.last_name].filter(Boolean).join(' ') || 'Без имени'
            const isLast = idx === employees.length - 1
            const isHovered = hoveredId === emp.id

            return (
              <tr
                key={emp.id}
                onClick={() => navigate(`/dashboard/employees/${emp.id}`)}
                onMouseEnter={() => setHoveredId(emp.id)}
                onMouseLeave={() => setHoveredId(null)}
                className={cn(
                  'cursor-pointer transition-colors duration-100',
                  !isLast && 'border-b border-border-default',
                  isHovered ? 'bg-bg-surface' : 'bg-transparent',
                  isBlocked && 'opacity-60'
                )}
              >
                {/* Сотрудник */}
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2.5">
                    <div className="relative shrink-0">
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center text-white text-[11px] font-bold font-[var(--font-display)]"
                        style={{ background: gradient }}
                      >
                        {initials}
                      </div>
                      <div
                        className={cn(
                          'absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2 border-bg-card',
                          isOnShift ? 'bg-emerald' : 'bg-[#5a6a7a]'
                        )}
                      />
                    </div>
                    <div className="min-w-0">
                      <div className="font-[var(--font-display)] font-semibold text-xs text-text-primary truncate">
                        {name}
                      </div>
                      {emp.phone && (
                        <div className="text-[10px] text-text-muted font-[var(--font-mono)]">
                          {emp.phone}
                        </div>
                      )}
                    </div>
                  </div>
                </td>

                {/* Специализация */}
                <td className="px-4 py-2.5">
                  <div className="flex gap-1 flex-wrap">
                    {emp.specialization.length > 0
                      ? emp.specialization.map(spec => {
                          const label = SPEC_DISPLAY[spec] ?? spec
                          const color = specColor(spec)
                          return (
                            <span
                              key={spec}
                              className="text-[10px] font-semibold px-1.5 py-0.5 rounded-[10px]"
                              style={{
                                background: `color-mix(in srgb, ${color} 13%, transparent)`,
                                color,
                              }}
                            >
                              {label}
                            </span>
                          )
                        })
                      : <span className="text-text-muted text-[11px]">—</span>
                    }
                  </div>
                </td>

                {/* Верификация */}
                <td className="px-4 py-2.5">
                  <span
                    className={cn(
                      'text-[10px] font-semibold px-1.5 py-0.5 rounded-[10px]',
                      isVerified
                        ? 'bg-emerald/15 text-emerald'
                        : 'bg-amber/15 text-amber'
                    )}
                  >
                    {isVerified ? '✓ Верифицирован' : '⏳ На проверке'}
                  </span>
                </td>

                {/* Статус */}
                <td className="px-4 py-2.5">
                  <span
                    className={cn(
                      'text-[11px]',
                      isOnShift ? 'text-emerald font-semibold' : 'text-[#5a6a7a] font-normal'
                    )}
                  >
                    ● {isOnShift ? 'На смене' : 'Не на смене'}
                  </span>
                </td>

                {/* Смена */}
                <td className="px-4 py-2.5 text-text-muted text-[11px] font-[var(--font-mono)]">
                  {emp.active_shift_id !== null ? `#${emp.active_shift_id}` : '—'}
                </td>

                {/* Действия */}
                <td className="px-4 py-2.5" onClick={e => e.stopPropagation()}>
                  <div className="flex items-center gap-2">
                    {isBlocked ? (
                      <>
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-[10px] bg-red/15 text-red">
                          Заблокирован
                        </span>
                        <button
                          onClick={() => onBlock(emp)}
                          disabled={isBlockPending}
                          className={cn(
                            'bg-transparent border-none cursor-pointer text-[11px] text-amber font-[var(--font-display)]',
                            isBlockPending && 'opacity-50 cursor-not-allowed'
                          )}
                        >
                          Разблок
                        </button>
                      </>
                    ) : (
                      <>
                        {isVerified && (
                          <button
                            onClick={() => onAssign(emp)}
                            className="bg-transparent border-none cursor-pointer text-[11px] text-accent font-[var(--font-display)] font-semibold"
                          >
                            Назначить
                          </button>
                        )}
                        <button
                          onClick={() => onBlock(emp)}
                          disabled={isBlockPending}
                          className={cn(
                            'bg-transparent border-none cursor-pointer text-[11px] text-red font-[var(--font-display)]',
                            isBlockPending && 'opacity-50 cursor-not-allowed'
                          )}
                        >
                          Блок
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
