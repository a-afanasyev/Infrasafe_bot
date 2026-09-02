import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usePersonName } from '../../hooks/usePersonName'
import { useNavigate } from 'react-router'
import { useRequestEmployeePhone } from '../../hooks/useEmployees'
import type { EmployeeBrief } from '../../hooks/useEmployees'
import { AVATAR_GRADIENTS, SPEC_COLORS, getInitials } from '../../utils/employeeUtils'
import { tSpecialization } from '../../i18n/apiMaps'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface Props {
  employee: EmployeeBrief
  onAssign?: (employee: EmployeeBrief) => void
  onBlock?: (employee: EmployeeBrief) => void
  onDelete?: (employee: EmployeeBrief) => void
  onVerify?: (employee: EmployeeBrief) => void
  isBlockPending?: boolean
}

export default function StaffCard({ employee, onAssign, onBlock, onDelete, onVerify, isBlockPending }: Props) {
  const { t } = useTranslation()
  const { full: fullName } = usePersonName()
  const [hovered, setHovered] = useState(false)
  const navigate = useNavigate()
  const requestPhone = useRequestEmployeePhone()

  const gradient = AVATAR_GRADIENTS[employee.id % AVATAR_GRADIENTS.length]
  const initials = getInitials(employee.first_name, employee.last_name)
  const isOnShift = employee.active_shift_id !== null
  const isVerified = employee.verification_status === 'verified'
  const isBlocked = employee.status === 'blocked'
  const name = fullName(employee, t('employees.noName'))
  // Бейдж роли для не-исполнителей (менеджер/обходчик) — список executor-центричен
  // по умолчанию, поэтому помечаем только тех, кто выделяется при фильтре по роли.
  const staffRole = (['manager', 'inspector'] as const).find(r => employee.roles?.includes(r))

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={cn(
        'bg-bg-card border border-border-default rounded-default overflow-hidden flex flex-col transition-all duration-200',
        hovered && 'shadow-[0_12px_40px_rgba(0,0,0,0.3)] -translate-y-0.5'
      )}
    >
      {/* Card header. Всё в потоке — до 2026-08-27 бейдж верификации был
          absolute top-right и наезжал на длинные ФИО. */}
      <div className="p-5 pb-4 flex items-start gap-3.5">
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

        {/* Name + phone + badges */}
        <div className="flex-1 min-w-0">
          {/* КАПС-ФИО из БД → Вид Имени; до двух строк вместо truncate. */}
          <div className="font-[var(--font-display)] font-semibold text-[15px] leading-snug text-text-primary break-words line-clamp-2">
            {name}
          </div>
          {employee.phone ? (
            <div className="text-xs text-text-muted mt-0.5 font-[var(--font-mono)]">
              {employee.phone}
            </div>
          ) : (
            <button
              type="button"
              onClick={() => requestPhone.mutate(employee.id)}
              disabled={requestPhone.isPending || requestPhone.isSuccess}
              className="text-xs text-accent hover:underline mt-0.5 block disabled:opacity-60 disabled:no-underline"
            >
              {requestPhone.isSuccess
                ? t('employees.phoneRequestSent')
                : `📱 ${t('employees.requestPhone')}`}
            </button>
          )}
          {/* Единый ряд бейджей: блокировка, верификация, роль, специализации */}
          <div className="flex flex-wrap gap-1 mt-2">
            {isBlocked && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-[10px] bg-red/15 text-red">
                {t('employees.blocked')}
              </span>
            )}
            {employee.bot_blocked && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-[10px] bg-red/15 text-red">
                {`🚫 ${t('residents.botBlocked')}`}
              </span>
            )}
            <span
              className={cn(
                'text-[10px] font-semibold px-2 py-0.5 rounded-[10px]',
                isVerified
                  ? 'bg-emerald/15 text-emerald'
                  : 'bg-amber/15 text-amber'
              )}
            >
              {isVerified ? `✓ ${t('employees.verified')}` : `⏳ ${t('employees.pendingVerification')}`}
            </span>
            {staffRole && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-[10px] bg-violet/15 text-violet">
                {t(`role.${staffRole}`)}
              </span>
            )}
            {employee.specialization.map(spec => (
              <span
                key={spec}
                className="text-[10px] font-semibold px-1.5 py-0.5 rounded-[10px] tracking-wide"
                style={{
                  background: `color-mix(in srgb, ${SPEC_COLORS[spec] ?? 'var(--text-muted)'} 13%, transparent)`,
                  color: SPEC_COLORS[spec] ?? 'var(--text-muted)',
                }}
              >
                {tSpecialization(spec, t)}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Shift status bar */}
      <div className="grid grid-cols-2 bg-bg-surface border-t border-b border-border-default">
        {[
          {
            value: isOnShift ? t('employees.activeShift') : t('employees.offShift'),
            label: t('employees.statusLabel'),
            accent: isOnShift,
          },
          {
            value: employee.active_shift_id !== null ? `#${employee.active_shift_id}` : '—',
            label: t('employees.shiftLabel'),
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
          {t('employees.profile')}
        </Button>
        <div className="flex-1" />
        {!isVerified ? (
          <Button
            size="sm"
            onClick={() => onVerify?.(employee)}
            className="text-xs"
          >
            {t('employees.verify')}
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={() => onAssign?.(employee)}
            className="text-xs"
          >
            {t('employees.assign')}
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
          {isBlocked ? t('employees.unblock') : t('employees.blockShort')}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDelete?.(employee)}
          className="text-xs px-2 text-text-muted hover:text-red"
        >
          {t('common.delete')}
        </Button>
      </div>
    </div>
  )
}
