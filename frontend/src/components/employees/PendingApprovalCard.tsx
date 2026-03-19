import type { EmployeeBrief } from '../../hooks/useEmployees'
import { AVATAR_GRADIENTS, SPEC_COLORS, getInitials } from '../../utils/employeeUtils'
import { Button } from '@/components/ui/button'

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
    <div className="flex flex-row items-center gap-3.5 bg-bg-card border border-border-default rounded-default p-4">
      {/* Avatar 48px */}
      <div
        className="w-12 h-12 rounded-full flex items-center justify-center font-[var(--font-display)] font-bold text-base text-white shrink-0"
        style={{ background: gradient }}
      >
        {initials}
      </div>

      {/* Info column */}
      <div className="flex-1 min-w-0">
        <div className="font-[var(--font-display)] font-semibold text-sm text-text-primary truncate">
          {name}
        </div>
        {employee.phone && (
          <div className="text-xs text-text-muted mt-0.5">
            {employee.phone}
          </div>
        )}
        {employee.specialization.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {employee.specialization.map(spec => (
              <span
                key={spec}
                className="text-[10px] font-semibold px-1.5 py-0.5 rounded-[10px]"
                style={{
                  background: (SPEC_COLORS[spec] ?? 'var(--text-muted)') + '22',
                  color: SPEC_COLORS[spec] ?? 'var(--text-muted)',
                }}
              >
                {spec}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Time-ago label */}
      <div className="text-[11px] text-amber font-medium shrink-0 text-right mr-1">
        Ожидает одобрения
      </div>

      {/* Button group */}
      <div className="flex gap-2 shrink-0">
        <Button
          onClick={() => onApprove(employee.id)}
          disabled={isPending}
          size="sm"
        >
          Одобрить
        </Button>
        <Button
          onClick={() => onReject(employee.id)}
          disabled={isPending}
          variant="outline"
          size="sm"
          className="border-red text-red hover:bg-red/10"
        >
          Отклонить
        </Button>
      </div>
    </div>
  )
}
