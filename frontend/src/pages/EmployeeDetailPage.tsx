import { useNavigate, useParams } from 'react-router-dom'
import { useEmployee } from '../hooks/useEmployees'
import { AVATAR_GRADIENTS, SPEC_COLORS, SPEC_DISPLAY, getInitials } from '../utils/employeeUtils'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { usePageTitle } from '../hooks/usePageTitle'
import { Button } from '@/components/ui/button'

export default function EmployeeDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: emp, isLoading, isError } = useEmployee(id ? Number(id) : null)
  const empName = emp ? [emp.first_name, emp.last_name].filter(Boolean).join(' ') || 'Сотрудник' : 'Сотрудник'
  usePageTitle(empName)

  if (isLoading) return <LoadingSpinner />
  if (isError || !emp) return (
    <div className="py-10 px-6 text-text-muted text-center">
      Сотрудник не найден
    </div>
  )

  const gradient = AVATAR_GRADIENTS[emp.id % AVATAR_GRADIENTS.length]
  const initials = getInitials(emp.first_name, emp.last_name)
  const name = [emp.first_name, emp.last_name].filter(Boolean).join(' ') || 'Без имени'
  const isOnShift = emp.active_shift_id !== null
  const isVerified = emp.verification_status === 'verified'
  const isBlocked = emp.status === 'blocked'

  return (
    <div className="p-5 px-6 flex flex-col gap-5 max-w-[720px]">
      {/* Back */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate(-1)}
        className="self-start px-0 text-text-muted"
      >
        ← Назад
      </Button>

      {/* Header card */}
      <div className="bg-bg-card border border-border-default rounded-default p-6 flex gap-5 items-start">
        <div className="relative shrink-0">
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center text-white text-xl font-bold font-[family-name:var(--font-display)]"
            style={{ background: gradient, opacity: isBlocked ? 0.5 : 1 }}
          >
            {initials}
          </div>
          <div
            className="absolute bottom-0.5 right-0.5 w-3.5 h-3.5 rounded-full border-2 border-bg-card"
            style={{ background: isOnShift ? 'var(--emerald)' : '#5a6a7a' }}
          />
        </div>

        <div className="flex-1 min-w-0">
          <div className="font-[family-name:var(--font-display)] font-bold text-lg text-text-primary mb-1">
            {name}
            {isBlocked && (
              <span className="ml-2.5 text-[11px] font-semibold px-2 py-0.5 rounded-[10px] bg-red/15 text-red align-middle">
                Заблокирован
              </span>
            )}
          </div>

          {emp.phone && (
            <div className="text-[13px] text-text-muted font-[family-name:var(--font-mono)] mb-3">
              {emp.phone}
            </div>
          )}

          <div className="flex gap-1.5 flex-wrap mb-3">
            {emp.specialization.length > 0
              ? emp.specialization.map(spec => {
                  const label = SPEC_DISPLAY[spec] ?? spec
                  const color = SPEC_COLORS[label.replace(/^\S+\s/, '')] ?? 'var(--text-muted)'
                  return (
                    <span
                      key={spec}
                      className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full"
                      style={{
                        background: `color-mix(in srgb, ${color} 13%, transparent)`,
                        color,
                      }}
                    >
                      {label}
                    </span>
                  )
                })
              : <span className="text-text-muted text-xs">Нет специализации</span>
            }
          </div>

          <div className="flex gap-2 flex-wrap">
            <span
              className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full"
              style={{
                background: isVerified ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
                color: isVerified ? 'var(--emerald)' : 'var(--amber)',
              }}
            >
              {isVerified ? '✓ Верифицирован' : '⏳ На проверке'}
            </span>
            <span
              className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full"
              style={{
                background: isOnShift ? 'rgba(16,185,129,0.1)' : 'rgba(90,106,122,0.1)',
                color: isOnShift ? 'var(--emerald)' : '#5a6a7a',
              }}
            >
              ● {isOnShift ? 'На смене' : 'Не на смене'}
            </span>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Смен всего', value: emp.total_shifts },
          { label: 'Выполнено', value: emp.total_completed },
          { label: 'Рейтинг', value: emp.rating != null ? emp.rating.toFixed(1) : '—' },
        ].map(s => (
          <div key={s.label} className="bg-bg-card border border-border-default rounded-default p-4 px-5">
            <div className="text-[22px] font-bold font-[family-name:var(--font-mono)] text-text-primary">
              {s.value}
            </div>
            <div className="text-[11px] text-text-muted mt-1">
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* Active shift */}
      {emp.active_shift && (
        <div className="bg-bg-card border border-border-default rounded-default p-5">
          <div className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">
            Текущая смена
          </div>
          <div className="flex gap-6 flex-wrap">
            <div>
              <div className="text-[11px] text-text-muted">ID</div>
              <div className="font-[family-name:var(--font-mono)] text-[13px] text-text-primary">#{emp.active_shift.id}</div>
            </div>
            <div>
              <div className="text-[11px] text-text-muted">Тип</div>
              <div className="text-[13px] text-text-primary">{emp.active_shift.shift_type ?? '—'}</div>
            </div>
            <div>
              <div className="text-[11px] text-text-muted">Заявок</div>
              <div className="text-[13px] text-text-primary">
                {emp.active_shift.current_request_count} / {emp.active_shift.max_requests}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-text-muted">Нагрузка</div>
              <div
                className="text-[13px]"
                style={{ color: emp.active_shift.load_percentage > 80 ? 'var(--red)' : 'var(--emerald)' }}
              >
                {emp.active_shift.load_percentage.toFixed(0)}%
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
