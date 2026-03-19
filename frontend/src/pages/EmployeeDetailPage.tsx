import { useNavigate, useParams } from 'react-router-dom'
import { useEmployee } from '../hooks/useEmployees'
import { AVATAR_GRADIENTS, SPEC_COLORS, SPEC_DISPLAY, getInitials } from '../utils/employeeUtils'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { usePageTitle } from '../hooks/usePageTitle'

export default function EmployeeDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: emp, isLoading, isError } = useEmployee(id ? Number(id) : null)
  const empName = emp ? [emp.first_name, emp.last_name].filter(Boolean).join(' ') || 'Сотрудник' : 'Сотрудник'
  usePageTitle(empName)

  if (isLoading) return <LoadingSpinner />
  if (isError || !emp) return (
    <div style={{ padding: '40px 24px', color: 'var(--text-muted)', textAlign: 'center' }}>
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
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: 720 }}>
      {/* Back */}
      <button
        onClick={() => navigate(-1)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--text-muted)', fontSize: '13px',
          display: 'flex', alignItems: 'center', gap: '6px',
          fontFamily: 'var(--font-display)', alignSelf: 'flex-start',
          padding: 0,
        }}
      >
        ← Назад
      </button>

      {/* Header card */}
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '24px',
        display: 'flex',
        gap: '20px',
        alignItems: 'flex-start',
      }}>
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <div style={{
            width: 64, height: 64, borderRadius: '50%', background: gradient,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: '20px', fontWeight: 700,
            fontFamily: 'var(--font-display)',
            opacity: isBlocked ? 0.5 : 1,
          }}>
            {initials}
          </div>
          <div style={{
            position: 'absolute', bottom: 2, right: 2,
            width: 14, height: 14, borderRadius: '50%',
            background: isOnShift ? 'var(--emerald)' : '#5a6a7a',
            border: '2px solid var(--bg-card)',
          }} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 700,
            fontSize: '18px', color: 'var(--text-primary)', marginBottom: 4,
          }}>
            {name}
            {isBlocked && (
              <span style={{
                marginLeft: 10, fontSize: '11px', fontWeight: 600, padding: '2px 8px',
                borderRadius: 10, background: 'rgba(239,68,68,0.15)', color: 'var(--red)',
                verticalAlign: 'middle',
              }}>
                Заблокирован
              </span>
            )}
          </div>

          {emp.phone && (
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 12 }}>
              {emp.phone}
            </div>
          )}

          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: 12 }}>
            {emp.specialization.length > 0
              ? emp.specialization.map(spec => {
                  const label = SPEC_DISPLAY[spec] ?? spec
                  const color = SPEC_COLORS[label.replace(/^\S+\s/, '')] ?? 'var(--text-muted)'
                  return (
                    <span key={spec} style={{
                      fontSize: '11px', fontWeight: 600, padding: '3px 10px', borderRadius: 20,
                      background: `color-mix(in srgb, ${color} 13%, transparent)`, color,
                    }}>
                      {label}
                    </span>
                  )
                })
              : <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Нет специализации</span>
            }
          </div>

          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{
              fontSize: '11px', fontWeight: 600, padding: '3px 10px', borderRadius: 20,
              background: isVerified ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
              color: isVerified ? 'var(--emerald)' : 'var(--amber)',
            }}>
              {isVerified ? '✓ Верифицирован' : '⏳ На проверке'}
            </span>
            <span style={{
              fontSize: '11px', fontWeight: 600, padding: '3px 10px', borderRadius: 20,
              background: isOnShift ? 'rgba(16,185,129,0.1)' : 'rgba(90,106,122,0.1)',
              color: isOnShift ? 'var(--emerald)' : '#5a6a7a',
            }}>
              ● {isOnShift ? 'На смене' : 'Не на смене'}
            </span>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
        {[
          { label: 'Смен всего', value: emp.total_shifts },
          { label: 'Выполнено', value: emp.total_completed },
          { label: 'Рейтинг', value: emp.rating != null ? emp.rating.toFixed(1) : '—' },
        ].map(s => (
          <div key={s.label} style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: '16px 20px',
          }}>
            <div style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
              {s.value}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 4 }}>
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* Active shift */}
      {emp.active_shift && (
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: '20px',
        }}>
          <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 12 }}>
            Текущая смена
          </div>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>ID</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--text-primary)' }}>#{emp.active_shift.id}</div>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Тип</div>
              <div style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{emp.active_shift.shift_type ?? '—'}</div>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Заявок</div>
              <div style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                {emp.active_shift.current_request_count} / {emp.active_shift.max_requests}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Нагрузка</div>
              <div style={{ fontSize: '13px', color: emp.active_shift.load_percentage > 80 ? 'var(--red)' : 'var(--emerald)' }}>
                {emp.active_shift.load_percentage.toFixed(0)}%
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
