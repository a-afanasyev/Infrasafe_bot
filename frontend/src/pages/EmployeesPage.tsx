import { useEffect, useMemo, useState } from 'react'
import { useTopbar } from '../contexts/TopbarContext'
import {
  useEmployees,
  useApproveEmployee,
  useRejectEmployee,
  useBlockEmployee,
  useUnblockEmployee,
} from '../hooks/useEmployees'
import type { EmployeeBrief } from '../hooks/useEmployees'
import StaffCard from '../components/employees/StaffCard'
import PendingApprovalCard from '../components/employees/PendingApprovalCard'
import EmptyState from '../components/shared/EmptyState'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import AssignRequestModal from '../components/employees/AssignRequestModal'

const primaryBtnStyle: React.CSSProperties = {
  background: 'var(--accent)',
  border: 'none',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: '13px',
  color: '#fff',
  padding: '7px 14px',
  fontFamily: 'var(--font-display)',
  fontWeight: 600,
}

const secondaryBtnStyle: React.CSSProperties = {
  background: 'none',
  border: '1px solid var(--border)',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: '13px',
  color: 'var(--text-secondary)',
  padding: '7px 14px',
  fontFamily: 'var(--font-display)',
  fontWeight: 500,
}

function chipStyle(active: boolean): React.CSSProperties {
  return {
    background: active ? 'var(--accent)' : 'var(--bg-card)',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
    borderRadius: 20,
    cursor: 'pointer',
    fontSize: '12px',
    color: active ? '#fff' : 'var(--text-secondary)',
    padding: '5px 12px',
    fontFamily: 'var(--font-display)',
    fontWeight: active ? 600 : 400,
    transition: 'all 0.15s',
  }
}

export default function EmployeesPage() {
  const { setActions, clearActions } = useTopbar()
  const [roleFilter, setRoleFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [search, setSearch] = useState<string>('')

  const apiFilters: Record<string, string | boolean | undefined> = {
    ...(roleFilter !== 'all' ? { role: roleFilter } : {}),
    ...(statusFilter === 'on_shift' ? { has_active_shift: true } : {}),
    ...(statusFilter === 'verified' ? { verification_status: 'verified' } : {}),
  }

  const { data: employees = [], isLoading, isError } = useEmployees(apiFilters, search || undefined)

  const [assignTarget, setAssignTarget] = useState<EmployeeBrief | null>(null)

  const approveEmployee = useApproveEmployee()
  const rejectEmployee = useRejectEmployee()
  const blockEmployee = useBlockEmployee()
  const unblockEmployee = useUnblockEmployee()

  const total = employees.length
  const onShift = employees.filter(e => e.active_shift_id !== null).length
  const pending = employees.filter(
    e => e.verification_status !== 'verified' && e.verification_status !== 'rejected'
  ).length
  const verified = employees.filter(e => e.verification_status === 'verified').length

  const actionsNode = useMemo(() => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <input
        type="text"
        placeholder="Поиск сотрудника..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: '6px 12px',
          fontSize: '13px',
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-display)',
          outline: 'none',
          width: '200px',
        }}
      />
      <button style={secondaryBtnStyle}>Экспорт</button>
      <button style={primaryBtnStyle}>+ Добавить</button>
    </div>
  ), [search])

  useEffect(() => {
    setActions(actionsNode)
    return clearActions
  }, [setActions, clearActions, actionsNode])

  const STATS = [
    { label: 'Всего сотрудников', value: total, iconBg: 'var(--blue)', icon: '👥' },
    { label: 'На смене сейчас', value: onShift, iconBg: 'var(--emerald)', icon: '🟢' },
    { label: 'Ожидают одобрения', value: pending, iconBg: 'var(--amber)', icon: '⏳' },
    { label: 'Верифицированы', value: verified, iconBg: 'var(--violet)', icon: '✓' },
  ]

  const pendingEmployees = employees.filter(
    e => e.verification_status !== 'verified' && e.verification_status !== 'rejected'
  )

  if (isLoading) return <LoadingSpinner />

  if (isError) return (
    <div className="flex-1 flex items-center justify-center text-[var(--text-muted)]">
      Ошибка загрузки сотрудников
    </div>
  )

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Stats bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
        {STATS.map(card => (
          <div
            key={card.label}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: '16px',
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
            }}
          >
            <div style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              background: card.iconBg + '22',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '22px',
              flexShrink: 0,
            }}>
              {card.icon}
            </div>
            <div>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '22px',
                fontWeight: 600,
                color: 'var(--text-primary)',
              }}>
                {card.value}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
                {card.label}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Pending approvals */}
      {pendingEmployees.length > 0 && (
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: '20px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <span style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 600,
              fontSize: '14px',
              color: 'var(--text-primary)',
            }}>
              Ожидают одобрения
            </span>
            <span style={{
              background: 'rgba(245,158,11,0.2)',
              color: 'var(--amber)',
              borderRadius: 20,
              padding: '2px 8px',
              fontSize: '11px',
              fontWeight: 600,
            }}>
              {pendingEmployees.length}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {pendingEmployees.map(e => (
              <PendingApprovalCard
                key={e.id}
                employee={e}
                onApprove={(id) => approveEmployee.mutate(id)}
                onReject={(id) => rejectEmployee.mutate(id)}
                isPending={approveEmployee.isPending || rejectEmployee.isPending}
              />
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        {[
          { key: 'all', label: 'Все' },
          { key: 'executor', label: 'Исполнители' },
          { key: 'manager', label: 'Менеджеры' },
        ].map(f => (
          <button key={f.key} onClick={() => setRoleFilter(f.key)} style={chipStyle(roleFilter === f.key)}>
            {f.label}
          </button>
        ))}
        <div style={{ width: 1, height: 24, background: 'var(--border)', margin: '0 4px' }} />
        {[
          { key: 'all', label: 'Все статусы' },
          { key: 'on_shift', label: 'На смене' },
          { key: 'verified', label: 'Верифицированы' },
        ].map(f => (
          <button key={f.key} onClick={() => setStatusFilter(f.key)} style={chipStyle(statusFilter === f.key)}>
            {f.label}
          </button>
        ))}
      </div>

      {/* Staff grid */}
      {employees.length === 0 ? (
        <EmptyState icon="👥" title="Сотрудники не найдены" subtitle="Попробуйте другой фильтр" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
          {employees.map(emp => (
            <StaffCard
              key={emp.id}
              employee={emp}
              onAssign={(e) => setAssignTarget(e)}
              onBlock={(e) => {
                if (e.status === 'blocked') {
                  unblockEmployee.mutate(e.id)
                } else {
                  const empName = [e.first_name, e.last_name].filter(Boolean).join(' ') || `#${e.id}`
                  if (window.confirm(`Заблокировать сотрудника ${empName}?`)) {
                    blockEmployee.mutate(e.id)
                  }
                }
              }}
              isBlockPending={blockEmployee.isPending || unblockEmployee.isPending}
            />
          ))}
        </div>
      )}

      {assignTarget && (
        <AssignRequestModal
          employee={assignTarget}
          onClose={() => setAssignTarget(null)}
        />
      )}
    </div>
  )
}
